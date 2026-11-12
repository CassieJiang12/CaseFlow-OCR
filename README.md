# CaseFlow OCR

Document-processing API that turns scanned court documents into six metadata fields, links each accepted value to OCR evidence, and flags uncertain results for review.

**Stack:** Python 3.11+, FastAPI, Tesseract, pypdfium2, OpenAI API, Pydantic, SQLite, pytest, Docker.

## What it does

1. Accepts PDF, PNG, and JPEG uploads.
2. Rasterizes PDF pages (including image-only PDFs) and runs Tesseract OCR.
3. Extracts case number, court name, plaintiff, defendant, document title, and filing date.
4. Checks quoted evidence, page references, field labels, conflicting values, and date validity.
5. Returns `null` for unsupported values and sets `needs_review` when a check fails.
6. Stores results in SQLite and exposes deletion, run metrics, token usage, and optional cost estimates.
7. Includes a small browser UI for upload, OCR inspection, and JSON export.

## Extraction modes

| Mode | OCR | Extraction | API key |
| --- | --- | --- | --- |
| `mock` (default) | Real Tesseract | Deterministic labeled-line parser | No |
| `openai` | Real Tesseract | OpenAI Responses API with a Pydantic schema | Yes |

Mock mode is not an LLM. Live-mode failures never silently fall back to mock results.

## Quick start (macOS)

Install Python 3.11+ and Tesseract, then from this directory:

```bash
brew install python tesseract
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
python -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1
```

Open <http://127.0.0.1:8000> and upload `samples/01_clean_scan.pdf`.

On Ubuntu/Debian: `sudo apt-get install tesseract-ocr tesseract-ocr-eng`. On Windows, use Docker below, or install Tesseract and set `TESSERACT_CMD` in `.env` to the executable path.

## Quick start (Docker)

```bash
cp .env.example .env
docker compose up --build
```

Open <http://127.0.0.1:8000>. A named volume persists SQLite results across restarts.

## OpenAI extraction

Edit `.env` and restart:

```dotenv
EXTRACTION_MODE=openai
OPENAI_API_KEY=your-own-key
OPENAI_MODEL=gpt-4o-mini
```

Optional `INPUT_USD_PER_MILLION` and `OUTPUT_USD_PER_MILLION` are list-price rates you configure. If either is blank, live cost is `null` (unknown).

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Health and configured extraction mode |
| POST | `/api/extractions` | Multipart upload under form field `file` |
| GET | `/api/extractions/{id}` | Retrieve a saved extraction |
| DELETE | `/api/extractions/{id}` | Delete a saved record |
| GET | `/api/metrics` | Aggregate latency, usage, and cost estimates |

```bash
curl -F 'file=@samples/01_clean_scan.pdf' http://127.0.0.1:8000/api/extractions
```

OpenAPI schemas are at `/docs`. Example field payload:

```json
{
  "value": "DEMO-2026-0042",
  "page": 1,
  "quote": "Case Number: DEMO-2026-0042",
  "verified": true,
  "issue": null
}
```

`validated` means programmed source and format checks passed. It does not mean human approval or legal validity.

## Tests and evaluation

```bash
python -m pytest -q
python -m scripts.evaluate --mode mock --output evaluation_results/mock.json
python -m scripts.evaluate --mode openai --output evaluation_results/openai.json
```

The evaluator scores six labeled PDF fixtures against `samples/golden.json`. Answer keys are used only by evaluation, never by extraction. Regenerate fixtures with `python -m scripts.make_samples`.

## Project layout

| Path | Responsibility |
| --- | --- |
| `app/main.py` | HTTP endpoints and orchestration |
| `app/ocr.py` | PDF rasterization and OCR |
| `app/extraction.py` | Prompt, mock/live providers, cost formula |
| `app/models.py` | Pydantic contracts |
| `app/validation.py` | Grounding and business checks |
| `app/storage.py` | SQLite persistence and metrics |
| `app/static/index.html` | Upload and evidence UI |
| `tests/` | OCR, grounding, provider, and API tests |
| `scripts/evaluate.py` | Golden-fixture evaluation |
| `examples/dotnet-client/` | Optional C# HTTP client |

## Design notes

This is a single modular service with a synchronous request path and a two-job per-process limit. PDFium rendering is serialized. OCR and LLM calls have timeouts. The default bind is local, with no authentication or tenant isolation. Upload bytes are not retained; OCR text and extracted fields remain in SQLite until deleted.
