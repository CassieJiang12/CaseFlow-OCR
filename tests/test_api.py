import pytest


@pytest.mark.ocr
@pytest.mark.parametrize("filename,status", [
    ("01_clean_scan.pdf", "validated"),
    ("01_clean_scan.png", "validated"),
    ("02_missing_filing_date.pdf", "needs_review"),
    ("03_invalid_date.pdf", "needs_review"),
    ("04_conflicting_case_numbers.pdf", "needs_review"),
    ("05_instruction_in_document.pdf", "validated"),
    ("06_two_page_scan.pdf", "validated"),
])
def test_real_scan_to_api_result(client, samples, filename, status):
    response = client.post("/api/extractions", files={"file": (filename, (samples / filename).read_bytes())})
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["status"] == status
    assert result["provider"] == "mock"
    assert result["usage"]["input_tokens"] == 0
    assert result["estimated_cost_usd"] == 0
    assert result["fields"]["plaintiff"]["value"] == "Avery Stone"
    if filename.startswith("05"):
        assert result["fields"]["case_number"]["value"] == "DEMO-2026-0042"
    assert client.get("/api/extractions/" + result["id"]).json() == result
    assert client.get("/api/metrics").json()["runs"] == 1
    assert client.delete("/api/extractions/" + result["id"]).status_code == 204
    assert client.get("/api/extractions/" + result["id"]).status_code == 404


@pytest.mark.ocr
def test_blank_scan_does_not_reach_extractor(client, samples):
    response = client.post("/api/extractions", files={"file": ("blank.pdf", (samples / "07_blank_scan.pdf").read_bytes())})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "no_readable_text"
    assert client.get("/api/metrics").json()["failures"] == 1


@pytest.mark.parametrize("payload,code", [(b"", 400), (b"hello, not a PDF", 415), (b"%PDF-broken", 422)])
def test_rejects_bad_uploads_even_when_named_pdf(client, payload, code):
    response = client.post("/api/extractions", files={"file": ("fake.pdf", payload)})
    assert response.status_code == code


def test_size_limit(client):
    response = client.post("/api/extractions", files={"file": ("big.pdf", b"x" * (10 * 1024 * 1024 + 1))})
    assert response.status_code == 413


def test_home_and_health(client):
    assert "CaseFlow OCR" in client.get("/").text
    assert client.get("/health").json()["extraction_mode"] == "mock"
    assert client.get("/api/extractions/does-not-exist").status_code == 404

