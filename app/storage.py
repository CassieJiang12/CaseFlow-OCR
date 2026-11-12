import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.models import ExtractionResult


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, status TEXT NOT NULL,
                provider TEXT NOT NULL, model TEXT, latency_ms REAL NOT NULL,
                input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL,
                usage_complete INTEGER NOT NULL, estimated_cost_usd REAL,
                result_json TEXT, error_code TEXT)""")

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def save(self, result: ExtractionResult):
        self._insert((result.id, result.created_at, result.status, result.provider,
                      result.model, result.latency_ms, result.usage.input_tokens,
                      result.usage.output_tokens, int(result.usage.complete),
                      result.estimated_cost_usd, result.model_dump_json(), None))

    def save_failure(self, run_id, created_at, provider, model, latency_ms, code):
        self._insert((run_id, created_at, "failed", provider, model, latency_ms,
                      0, 0, 0, None, None, code))

    def _insert(self, values):
        with self.connect() as db:
            db.execute("INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", values)

    def get(self, run_id: str) -> ExtractionResult | None:
        with self.connect() as db:
            row = db.execute("SELECT result_json FROM runs WHERE id=?", (run_id,)).fetchone()
        return ExtractionResult.model_validate_json(row[0]) if row and row[0] else None

    def delete(self, run_id: str) -> bool:
        with self.connect() as db:
            return db.execute("DELETE FROM runs WHERE id=?", (run_id,)).rowcount > 0

    def metrics(self):
        with self.connect() as db:
            db.row_factory = sqlite3.Row
            row = db.execute("""SELECT COUNT(*) AS runs,
                COALESCE(SUM(status='failed'),0) AS failures,
                COALESCE(SUM(status='needs_review'),0) AS needs_review,
                COALESCE(SUM(input_tokens),0) AS input_tokens,
                COALESCE(SUM(output_tokens),0) AS output_tokens,
                AVG(latency_ms) AS mean_latency_ms,
                SUM(estimated_cost_usd) AS known_estimated_cost_usd,
                COALESCE(SUM(estimated_cost_usd IS NULL),0) AS runs_with_unknown_cost,
                COALESCE(SUM(usage_complete=0),0) AS runs_with_incomplete_usage
                FROM runs""").fetchone()
        return dict(row)

