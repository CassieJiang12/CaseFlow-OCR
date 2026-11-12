from typing import Literal

from pydantic import BaseModel, ConfigDict


class EvidenceField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str | None
    page: int | None
    quote: str | None


class ExtractedDocument(BaseModel):
    """Explicit keys make the JSON schema stable for API consumers."""

    model_config = ConfigDict(extra="forbid")
    case_number: EvidenceField
    court_name: EvidenceField
    plaintiff: EvidenceField
    defendant: EvidenceField
    document_title: EvidenceField
    filing_date: EvidenceField


FIELD_NAMES = tuple(ExtractedDocument.model_fields)
LABELS = {
    "case_number": ("Case Number", "Case No"),
    "court_name": ("Court Name", "Court"),
    "plaintiff": ("Plaintiff",),
    "defendant": ("Defendant",),
    "document_title": ("Document Title", "Document"),
    "filing_date": ("Filing Date",),
}


class OCRPage(BaseModel):
    number: int
    text: str


class CheckedField(BaseModel):
    value: str | None
    page: int | None
    quote: str | None
    verified: bool
    issue: str | None


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    # Failed provider calls may have unknown billable usage.
    complete: bool = True


class ExtractionResult(BaseModel):
    id: str
    created_at: str
    status: Literal["validated", "needs_review"]
    provider: Literal["mock", "openai"]
    model: str | None
    fields: dict[str, CheckedField]
    pages: list[OCRPage]
    warnings: list[str]
    usage: Usage
    estimated_cost_usd: float | None
    latency_ms: float


class PipelineError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.status_code = status_code

