import re
from datetime import date

from app.models import CheckedField, ExtractedDocument, FIELD_NAMES, LABELS, OCRPage


def normalize(text: str) -> str:
    return " ".join(text.split()).casefold()


def validate_fields(document: ExtractedDocument, pages: list[OCRPage]):
    sources = {page.number: page.text for page in pages}
    checked = {}
    warnings = []
    for name in FIELD_NAMES:
        field = getattr(document, name)
        issue = None
        if not field.value or not field.value.strip():
            issue = "missing_or_ambiguous"
        elif field.page not in sources or not field.quote or not field.quote.strip():
            issue = "missing_evidence"
        elif normalize(field.quote) not in normalize(sources[field.page]):
            issue = "quote_not_in_source"
        elif normalize(field.value) not in normalize(field.quote):
            issue = "value_not_in_quote"
        else:
            # Tie evidence to the requested label, not just any matching text.
            label_pattern = r"(?:^|\n)\s*(?:" + "|".join(map(re.escape, LABELS[name])) + r")\s*:\s*([^\n]+)"
            values = re.findall(label_pattern, sources[field.page], flags=re.I)
            if normalize(field.value) not in {normalize(value) for value in values}:
                issue = "label_value_mismatch"
            # Catch conflicting labeled values across pages, not just the chosen page.
            all_values = {normalize(value) for page in pages
                          for value in re.findall(label_pattern, page.text, flags=re.I)}
            if len(all_values) > 1:
                issue = "conflicting_source_values"
            if name == "filing_date":
                try:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", field.value):
                        raise ValueError()
                    date.fromisoformat(field.value)
                except ValueError:
                    issue = "invalid_date"
        verified = issue is None
        # Reject unsupported candidates rather than returning them as trusted data.
        checked[name] = CheckedField(
            value=field.value if verified else None,
            page=field.page if verified else None,
            quote=field.quote if verified else None,
            verified=verified,
            issue=issue,
        )
        if issue:
            warnings.append(f"{name}: {issue}")
    return checked, warnings

