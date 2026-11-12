"""Separate truth data from the extraction code; report local measurements."""
import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv

from app.config import Settings
from app.extraction import estimate_cost, extract
from app.ocr import read_pages
from app.validation import normalize, validate_fields

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["mock", "openai"], default="mock")
    parser.add_argument("--output", default="evaluation_results/latest.json")
    args = parser.parse_args()
    load_dotenv()
    # Explicit --mode wins over the .env setting.
    settings = Settings(extraction_mode=args.mode)
    cases = json.loads((ROOT / "samples/golden.json").read_text())
    results = []
    for case in cases:
        start = time.perf_counter()
        pages = read_pages((ROOT / "samples" / case["file"]).read_bytes(), settings)
        document, usage = extract(pages, settings)
        fields, warnings = validate_fields(document, pages)
        comparison = {name: ((field.value is None and case["expected"][name] is None)
                            or (field.value is not None and case["expected"][name] is not None
                                and normalize(field.value) == normalize(case["expected"][name])))
                      for name, field in fields.items()}
        status = "needs_review" if warnings else "validated"
        results.append({"file": case["file"], "field_matches": comparison,
                        "status_match": status == case["expected_status"],
                        "latency_ms": round((time.perf_counter() - start) * 1000, 2),
                        "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                        "estimated_cost_usd": estimate_cost(usage, settings)})
    matched = sum(sum(row["field_matches"].values()) for row in results)
    total = sum(len(row["field_matches"]) for row in results)
    report = {"mode": args.mode, "model": settings.openai_model if args.mode == "openai" else None,
              "dataset": "six fictional labeled-document fixtures; not a production benchmark",
              "field_accuracy": matched / total, "matched_fields": matched, "total_fields": total,
              "status_accuracy": sum(row["status_match"] for row in results) / len(results), "cases": results}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "cases"}, indent=2))
    if matched != total or not all(row["status_match"] for row in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

