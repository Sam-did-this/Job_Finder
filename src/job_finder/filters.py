"""Keyword matching, scoring profiles, de-duplication and sorting.

All keyword matching uses whole-word boundaries so "ai" no longer matches "email"
and "rn" no longer matches "learn".
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from job_finder.models import Job

AI_KEYWORDS = (
    "ai",
    "machine learning",
    "ml",
    "llm",
    "llms",
    "gpt",
    "copilot",
    "chatgpt",
    "prompt engineer",
    "generative ai",
    "openai",
    "anthropic",
    "claude",
    "gemini",
    "nlp",
)

TOP_MATCH_SCORE = 8


@dataclass(frozen=True)
class Profile:
    """A bundle of keywords describing what you're looking for."""

    name: str
    include: tuple[str, ...] = ()
    boost: tuple[str, ...] = ()
    penalize: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    description: str = ""


_SENIORITY = (
    "senior",
    "sr",
    "staff",
    "principal",
    "lead",
    "director",
    "head of",
    "manager",
    "10+ years",
    "8+ years",
    "7+ years",
    "security clearance",
    "clearance required",
)
_JUNIOR = ("junior", "jr", "entry level", "entry-level", "associate", "intern", "internship")
_FREELANCE = ("freelance", "contract", "contractor", "part-time", "part time", "gig", "one-off")

PROFILES: dict[str, Profile] = {
    "dev": Profile(
        "dev",
        include=(
            "python",
            "javascript",
            "typescript",
            "react",
            "node",
            "full stack",
            "fullstack",
            "backend",
            "frontend",
            "software engineer",
            "web developer",
            "api",
            "cloud",
            "devops",
            *AI_KEYWORDS,
        ),
        boost=_JUNIOR + _FREELANCE,
        penalize=_SENIORITY,
        description="Broad software roles (the original script's behaviour).",
    ),
    "python": Profile(
        "python",
        include=(
            "python",
            "django",
            "flask",
            "fastapi",
            "pandas",
            "automation",
            "scripting",
            "web scraping",
            "scraper",
            "selenium",
            "pytest",
        ),
        boost=_JUNIOR + _FREELANCE,
        penalize=_SENIORITY,
        description="Python work, tilted towards junior/freelance.",
    ),
    "security": Profile(
        "security",
        include=(
            "security",
            "cybersecurity",
            "infosec",
            "appsec",
            "soc analyst",
            "pentest",
            "penetration",
            "osint",
            "incident response",
            "grc",
            "iam",
            "identity",
            "threat",
            "vulnerability",
            "blue team",
            "red team",
        ),
        boost=_JUNIOR + ("analyst", "tier 1", "tier 2") + _FREELANCE,
        penalize=_SENIORITY,
        description="Cybersecurity / identity roles, entry-level friendly.",
    ),
    "ai": Profile(
        "ai",
        include=AI_KEYWORDS + ("data scientist", "mlops", "rag", "embeddings"),
        boost=_JUNIOR + _FREELANCE,
        penalize=_SENIORITY,
        description="AI / ML / LLM roles.",
    ),
    "latam": Profile(
        "latam",
        include=(
            "latam",
            "latin america",
            "south america",
            "americas",
            "peru",
            "lima",
            "spanish",
            "bilingual",
            "gmt-5",
            "est timezone",
            "utc-5",
        ),
        boost=_JUNIOR + _FREELANCE,
        penalize=_SENIORITY + ("us only", "us citizens only", "must reside in the us"),
        description="Roles open to people working from Latin America (e.g. Lima).",
    ),
    "gigs": Profile(
        "gigs",
        include=(
            "cash",
            "daily pay",
            "same day",
            "helper",
            "clean",
            "cleaning",
            "moving",
            "hauling",
            "labor",
            "handyman",
            "painting",
            "landscaping",
            "snow",
        ),
        boost=("cash", "same day", "daily pay"),
        description="Local odd jobs and cash work (pairs with the craigslist source).",
    ),
}


def parse_terms(raw: str | Iterable[str] | None) -> list[str]:
    """'python, cash ,ai' -> ['python', 'cash', 'ai']."""
    if not raw:
        return []
    parts = raw.split(",") if isinstance(raw, str) else list(raw)
    return [p.strip() for p in parts if p and p.strip()]


def compile_terms(terms: Iterable[str]) -> re.Pattern[str] | None:
    """Whole-word, case-insensitive matcher for any of `terms` (None when empty)."""
    cleaned = sorted({t.strip() for t in terms if t and t.strip()}, key=len, reverse=True)
    if not cleaned:
        return None
    alternation = "|".join(re.escape(t) for t in cleaned)
    # (?<!\w)/(?!\w) instead of \b so terms like "c++" or "node.js" still work.
    return re.compile(rf"(?<!\w)(?:{alternation})(?!\w)", re.I)


def hits(pattern: re.Pattern[str] | None, text: str) -> set[str]:
    return {m.group(0).lower() for m in pattern.finditer(text)} if pattern and text else set()


_AI_RE = compile_terms(AI_KEYWORDS)


def resolve_profile(name: str, custom: dict[str, dict[str, list[str]]] | None = None) -> Profile:
    custom = custom or {}
    if name in custom:
        body = custom[name]
        return Profile(
            name,
            include=tuple(body.get("include", ())),
            boost=tuple(body.get("boost", ())),
            penalize=tuple(body.get("penalize", ())),
            exclude=tuple(body.get("exclude", ())),
            description="Custom profile from config.",
        )
    if name in PROFILES:
        return PROFILES[name]
    known = ", ".join(sorted({*PROFILES, *custom}))
    raise ValueError(f"unknown profile {name!r} (available: {known})")


def score_job(
    job: Job,
    profile: Profile,
    terms: Iterable[str] = (),
    now: datetime | None = None,
) -> Job:
    """Fill job.score / job.reasons / job.is_ai in place and return the job."""
    now = now or datetime.now(UTC)
    tags_text = " ".join(job.tags)
    body = f"{job.company} {tags_text} {job.description}"

    include = compile_terms([*terms, *profile.include])
    boost = compile_terms(profile.boost)
    penalize = compile_terms(profile.penalize)

    score = 0
    reasons: list[str] = []

    title_hits = hits(include, job.title)
    tag_hits = hits(include, tags_text) - title_hits
    desc_hits = hits(include, job.description) - title_hits - tag_hits
    for words, points, where in (
        (title_hits, 4, "title"),
        (tag_hits, 2, "tags"),
        (desc_hits, 1, "text"),
    ):
        for word in sorted(words):
            score += points
            reasons.append(f"+{points} {word} ({where})")

    boost_title = hits(boost, job.title)
    for word in sorted(boost_title):
        score += 3
        reasons.append(f"+3 {word} (title)")
    for word in sorted(hits(boost, body) - boost_title):
        score += 1
        reasons.append(f"+1 {word}")

    pen_title = hits(penalize, job.title)
    for word in sorted(pen_title):
        score -= 5
        reasons.append(f"-5 {word} (title)")
    for word in sorted(hits(penalize, body) - pen_title):
        score -= 1
        reasons.append(f"-1 {word}")

    if job.posted_at:
        age = now - job.posted_at
        if age <= timedelta(days=1):
            score += 2
            reasons.append("+2 posted <24h")
        elif age <= timedelta(days=3):
            score += 1
            reasons.append("+1 posted <3d")
        elif age > timedelta(days=30):
            score -= 2
            reasons.append("-2 older than 30d")
    if job.salary:
        score += 1
        reasons.append("+1 salary listed")

    job.score = score
    job.reasons = reasons
    job.is_ai = bool(_AI_RE and _AI_RE.search(f"{job.title} {body}"))
    return job


def dedupe(jobs: Iterable[Job]) -> list[Job]:
    """Drop repeats by URL, then by normalised company+title. Keeps the first seen."""
    seen_urls: set[str] = set()
    seen_keys: set[str] = set()
    unique: list[Job] = []
    for job in jobs:
        if not job.url or job.url in seen_urls:
            continue
        seen_urls.add(job.url)
        key = job.dedupe_key
        if key and key in seen_keys:
            continue
        seen_keys.add(key)
        unique.append(job)
    return unique


def select(
    jobs: Iterable[Job],
    *,
    profile: Profile,
    terms: list[str] | None = None,
    exclude: list[str] | None = None,
    since: timedelta | None = None,
    min_score: int | None = None,
    now: datetime | None = None,
) -> list[Job]:
    """Filter, score, de-duplicate and rank jobs (best first).

    `terms` (from -s) are required: a job must mention at least one. With no terms,
    the profile's `include` list is the requirement, so the default run isn't a firehose.
    """
    now = now or datetime.now(UTC)
    terms = terms or []
    required = compile_terms(terms or profile.include)
    excluded = compile_terms([*(exclude or []), *profile.exclude])

    chosen: list[Job] = []
    for job in dedupe(jobs):
        head = f"{job.title} {job.company} {' '.join(job.tags)}"
        if excluded and excluded.search(head):
            continue
        if since and job.posted_at and now - job.posted_at > since:
            continue
        searchable = f"{head} {job.description}"
        if required and not required.search(searchable):
            continue
        score_job(job, profile, terms, now)
        if min_score is not None and job.score < min_score:
            continue
        chosen.append(job)

    epoch = datetime.min.replace(tzinfo=UTC)
    chosen.sort(key=lambda j: (j.score, j.posted_at or epoch), reverse=True)
    return chosen
