"""Core data types."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass
class Job:
    """One job listing, normalised across every source."""

    title: str
    url: str
    source: str
    company: str = ""
    kind: str = "remote"  # remote | local | freelance
    location: str = ""
    tags: list[str] = field(default_factory=list)
    description: str = ""
    posted_at: datetime | None = None
    salary: str = ""
    # Filled in by the pipeline, not by sources:
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    is_new: bool = False
    is_ai: bool = False
    status: str = ""  # "", seen, saved, applied, ignored

    @property
    def id(self) -> str:
        """Short stable id used by `job-finder mark`."""
        return hashlib.sha1(self.url.encode("utf-8")).hexdigest()[:8]  # noqa: S324 - not security

    @property
    def dedupe_key(self) -> str:
        """Company+title with punctuation/case removed, to catch cross-posted listings."""
        return _NON_ALNUM.sub("", f"{self.company}{self.title}".lower())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "url": self.url,
            "source": self.source,
            "kind": self.kind,
            "location": self.location,
            "tags": self.tags,
            "salary": self.salary,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "score": self.score,
            "reasons": self.reasons,
            "is_new": self.is_new,
            "is_ai": self.is_ai,
            "status": self.status,
        }


@dataclass
class SourceResult:
    """Outcome of fetching one source: jobs, or the reason there are none."""

    name: str
    jobs: list[Job] = field(default_factory=list)
    error: str = ""
    skipped: str = ""
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.error and not self.skipped
