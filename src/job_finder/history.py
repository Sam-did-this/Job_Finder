"""SQLite-backed history: what you've seen, saved, applied to or ignored."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from job_finder.models import Job

STATUSES = ("seen", "saved", "applied", "ignored")
LEGACY_JSON = Path.home() / "job_finder_pro_history.json"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    url        TEXT PRIMARY KEY,
    id         TEXT NOT NULL,
    key        TEXT NOT NULL DEFAULT '',
    title      TEXT NOT NULL DEFAULT '',
    company    TEXT NOT NULL DEFAULT '',
    source     TEXT NOT NULL DEFAULT '',
    status     TEXT NOT NULL DEFAULT 'seen',
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_id  ON jobs(id);
CREATE INDEX IF NOT EXISTS idx_jobs_key ON jobs(key);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class History:
    def __init__(self, path: Path, legacy_json: Path | None = LEGACY_JSON) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        fresh = not path.exists()
        with closing(self._connect()) as db, db:
            db.executescript(_SCHEMA)
        if fresh and legacy_json:
            self._import_legacy(legacy_json)

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def _import_legacy(self, legacy: Path) -> int:
        """One-time import of the v1 job_finder_pro_history.json 'seen_links' list."""
        try:
            links = json.loads(legacy.read_text(encoding="utf-8")).get("seen_links", [])
        except (OSError, ValueError, AttributeError):
            return 0
        stamp = _now()
        rows = [
            (url, Job(title="", url=url, source="").id, stamp, stamp)
            for url in links
            if isinstance(url, str) and url
        ]
        with closing(self._connect()) as db, db:
            db.executemany(
                "INSERT OR IGNORE INTO jobs (url, id, first_seen, last_seen) VALUES (?, ?, ?, ?)",
                rows,
            )
        return len(rows)

    def annotate(self, jobs: Iterable[Job]) -> None:
        """Set job.is_new and job.status from stored history."""
        with closing(self._connect()) as db:
            for job in jobs:
                row = db.execute("SELECT status FROM jobs WHERE url = ?", (job.url,)).fetchone()
                if row is None and job.dedupe_key:
                    row = db.execute(
                        "SELECT status FROM jobs WHERE key = ? LIMIT 1", (job.dedupe_key,)
                    ).fetchone()
                job.is_new = row is None
                job.status = row["status"] if row else ""

    def record(self, jobs: Iterable[Job]) -> None:
        """Remember these jobs as seen (existing rows keep their status)."""
        stamp = _now()
        with closing(self._connect()) as db, db:
            for job in jobs:
                db.execute(
                    "INSERT INTO jobs "
                    "(url, id, key, title, company, source, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(url) DO UPDATE SET last_seen = excluded.last_seen, "
                    "key = excluded.key, title = excluded.title, company = excluded.company",
                    (
                        job.url,
                        job.id,
                        job.dedupe_key,
                        job.title,
                        job.company,
                        job.source,
                        stamp,
                        stamp,
                    ),
                )

    def set_status(self, job_id: str, status: str) -> int:
        """Mark a job (by short id or full URL). Returns how many rows changed."""
        if status not in STATUSES:
            raise ValueError(f"status must be one of: {', '.join(STATUSES)}")
        with closing(self._connect()) as db, db:
            cur = db.execute(
                "UPDATE jobs SET status = ? WHERE id = ? OR url = ?", (status, job_id, job_id)
            )
            return cur.rowcount

    def recent(self, limit: int = 20, status: str | None = None) -> list[sqlite3.Row]:
        query = "SELECT * FROM jobs"
        params: list[object] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY last_seen DESC, first_seen DESC LIMIT ?"
        params.append(limit)
        with closing(self._connect()) as db:
            return db.execute(query, params).fetchall()

    def counts(self) -> dict[str, int]:
        with closing(self._connect()) as db:
            rows = db.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}
