import json

import httpx
import pytest
from openai import OpenAI

from app.config import Settings
from app.extraction import OpenAIExtractor, estimate_cost, mock_extract
from app.models import OCRPage, PipelineError, Usage


def live_settings():
    return Settings(_env_file=None, extraction_mode="openai", openai_api_key="test-key-not-real")


def test_sdk_serializes_schema_and_parses_response_without_network():
    pages = [OCRPage(number=1, text="Case Number: DEMO-42")]
    parsed, _ = mock_extract(pages)
    def handler(request):
        body = json.loads(request.content)
        assert body["text"]["format"]["type"] == "json_schema"
        assert body["text"]["format"]["strict"] is True
        assert body["store"] is False
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 1, "status": "completed",
            "model": "gpt-4o-mini", "output": [{"id": "msg_test", "type": "message",
            "role": "assistant", "status": "completed", "content": [{"type": "output_text",
            "text": parsed.model_dump_json(), "annotations": []}]}],
            "usage": {"input_tokens": 120, "output_tokens": 40, "total_tokens": 160,
                      "input_tokens_details": {"cached_tokens": 0},
                      "output_tokens_details": {"reasoning_tokens": 0}},
        })
    client = OpenAI(api_key="test-key-not-real", http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result, usage = OpenAIExtractor(live_settings(), client).extract(pages)
    assert result.case_number.value == "DEMO-42"
    assert usage.input_tokens == 120
    assert usage.output_tokens == 40


def test_provider_rate_limit_is_visible_instead_of_silent_mock_fallback():
    def handler(request):
        return httpx.Response(429, json={"error": {"message": "rate limited", "type": "rate_limit_error", "code": "rate_limit"}})
    client = OpenAI(api_key="test-key-not-real", max_retries=0,
                    http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(PipelineError) as exc:
        OpenAIExtractor(live_settings(), client).extract([OCRPage(number=1, text="Case Number: A")])
    assert exc.value.code == "llm_rate_limit"


def test_unknown_rates_do_not_report_zero_cost():
    assert estimate_cost(Usage(input_tokens=1000, output_tokens=100), live_settings()) is None


def test_cost_formula_with_explicit_example_rates():
    settings = live_settings().model_copy(update={"input_usd_per_million": 1.0, "output_usd_per_million": 4.0})
    assert estimate_cost(Usage(input_tokens=1000, output_tokens=100), settings) == 0.0014


def test_live_mode_requires_key():
    with pytest.raises(ValueError):
        Settings(_env_file=None, extraction_mode="openai", openai_api_key="")

