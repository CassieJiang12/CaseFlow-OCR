from app.extraction import mock_extract
from app.models import EvidenceField, OCRPage
from app.validation import validate_fields


def document():
    pages = [OCRPage(number=1, text="Case Number: DEMO-42\nCourt Name: Training Court\nPlaintiff: Avery Stone\nDefendant: Cedar Labs\nDocument Title: Complaint\nFiling Date: 2026-10-22")]
    parsed, _ = mock_extract(pages)
    return parsed, pages


def test_rejects_hallucinated_value_even_with_real_quote():
    parsed, pages = document()
    parsed.plaintiff = EvidenceField(value="Invented Person", page=1, quote="Plaintiff: Avery Stone")
    fields, warnings = validate_fields(parsed, pages)
    assert fields["plaintiff"].value is None
    assert fields["plaintiff"].issue == "value_not_in_quote"


def test_rejects_fabricated_quote():
    parsed, pages = document()
    parsed.plaintiff = EvidenceField(value="Invented Person", page=1, quote="Plaintiff: Invented Person")
    fields, _ = validate_fields(parsed, pages)
    assert fields["plaintiff"].issue == "quote_not_in_source"


def test_rejects_swapped_parties_even_when_name_appears_in_source():
    parsed, pages = document()
    parsed.plaintiff = parsed.defendant
    fields, _ = validate_fields(parsed, pages)
    assert fields["plaintiff"].issue == "label_value_mismatch"


def test_rejects_wrong_page():
    parsed, pages = document()
    parsed.plaintiff.page = 7
    fields, _ = validate_fields(parsed, pages)
    assert not fields["plaintiff"].verified


def test_conflict_is_rejected_even_if_model_chooses_one_value():
    parsed, pages = document()
    pages.append(OCRPage(number=2, text="Case Number: OTHER-55"))
    fields, _ = validate_fields(parsed, pages)
    assert fields["case_number"].issue == "conflicting_source_values"

