import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.config import Settings
from app.extraction import estimate_cost, extract
from app.models import ExtractionResult, PipelineError
from app.ocr import read_pages
from app.storage import Store
from app.validation import validate_fields

logger = logging.getLogger("caseflow")
logging.basicConfig(level=logging.INFO, format="%(message)s")


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()
    store = Store(config.database_path)
    capacity = BoundedSemaphore(2)
    app = FastAPI(title="CaseFlow OCR", version="0.1.0")
    app.state.settings = config
    app.state.store = store

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(Path(__file__).parent / "static" / "index.html")

    @app.get("/health")
    def health():
        return {"status": "ok", "extraction_mode": config.extraction_mode,
                "model": config.openai_model if config.extraction_mode == "openai" else None}

    @app.post("/api/extractions", response_model=ExtractionResult, status_code=201)
    def upload(file: UploadFile):
        if not capacity.acquire(blocking=False):
            file.file.close()
            raise HTTPException(503, detail={"code": "busy", "message": "Two jobs are already running."})
        start = time.perf_counter()
        run_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        model = config.openai_model if config.extraction_mode == "openai" else None
        try:
            data = file.file.read(config.max_upload_mb * 1024 * 1024 + 1)
            if not data:
                raise PipelineError("empty_file", "Upload a document.", 400)
            if len(data) > config.max_upload_mb * 1024 * 1024:
                raise PipelineError("file_too_large", "Upload exceeds the configured size limit.", 413)
            pages = read_pages(data, config)
            document, usage = extract(pages, config)
            fields, warnings = validate_fields(document, pages)
            result = ExtractionResult(
                id=run_id, created_at=created_at,
                status="needs_review" if warnings else "validated",
                provider=config.extraction_mode, model=model, fields=fields,
                pages=pages, warnings=warnings, usage=usage,
                estimated_cost_usd=estimate_cost(usage, config),
                latency_ms=round((time.perf_counter() - start) * 1000, 2),
            )
            store.save(result)
            logger.info(json.dumps({"event": "extraction_completed", "id": run_id,
                                    "provider": result.provider, "model": model,
                                    "status": result.status, "pages": len(pages),
                                    "latency_ms": result.latency_ms,
                                    "input_tokens": usage.input_tokens,
                                    "output_tokens": usage.output_tokens,
                                    "estimated_cost_usd": result.estimated_cost_usd}))
            return result
        except PipelineError as exc:
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            store.save_failure(run_id, created_at, config.extraction_mode, model, elapsed, exc.code)
            logger.warning(json.dumps({"event": "extraction_failed", "id": run_id,
                                       "code": exc.code, "latency_ms": elapsed}))
            raise HTTPException(exc.status_code, detail={"code": exc.code, "message": exc.public_message}) from exc
        finally:
            file.file.close()
            capacity.release()

    @app.get("/api/extractions/{run_id}", response_model=ExtractionResult)
    def get_result(run_id: str):
        result = store.get(run_id)
        if result is None:
            raise HTTPException(404, "Extraction not found.")
        return result

    @app.delete("/api/extractions/{run_id}", status_code=204)
    def delete_result(run_id: str):
        if not store.delete(run_id):
            raise HTTPException(404, "Extraction not found.")

    @app.get("/api/metrics")
    def metrics():
        return store.metrics()

    return app


# Factory startup avoids database creation during imports: uvicorn app.main:create_app --factory

