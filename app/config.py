from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    extraction_mode: Literal["mock", "openai"] = "mock"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    input_usd_per_million: float | None = Field(default=None, ge=0)
    output_usd_per_million: float | None = Field(default=None, ge=0)
    database_path: Path = Path("data/caseflow.sqlite3")
    max_upload_mb: int = Field(default=10, ge=1, le=50)
    max_pages: int = Field(default=5, ge=1, le=20)
    max_ocr_chars: int = Field(default=40000, ge=100, le=100000)
    ocr_timeout_seconds: int = Field(default=20, ge=1, le=120)
    llm_timeout_seconds: int = Field(default=30, ge=1, le=120)
    tesseract_cmd: str = ""

    @field_validator("input_usd_per_million", "output_usd_per_million", mode="before")
    @classmethod
    def blank_price_means_unknown(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def require_key_for_live_mode(self):
        if self.extraction_mode == "openai" and not self.openai_api_key.strip():
            raise ValueError("Set OPENAI_API_KEY before selecting openai mode.")
        return self

