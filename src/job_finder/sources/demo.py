"""Offline demo data so anyone can try the tool (and see the report) without network access.

Every company here is fictional.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from job_finder.config import Config
from job_finder.http import Client
from job_finder.models import Job
from job_finder.sources.base import register

_ROWS = [
    (
        "Junior Python Automation Developer",
        "Northwind Labs",
        "Remotive",
        5,
        ["python", "automation"],
        "Contract role. Build scraping and reporting scripts with Python and pandas. $45-$60/hr.",
    ),
    (
        "Senior Backend Engineer (Python/Go)",
        "Globex Systems",
        "RemoteOK",
        20,
        ["python", "backend"],
        "8+ years required. Lead a team of five. $180k-$220k.",
    ),
    (
        "SOC Analyst I (Remote, LATAM friendly)",
        "Initech Security",
        "WeWorkRemotely",
        30,
        ["security", "soc"],
        "Entry level analyst. Spanish a plus. Work from anywhere in the Americas.",
    ),
    (
        "Freelance: Python script to clean CSV exports",
        "r/forhire post",
        "r/forhire",
        3,
        ["python", "freelance"],
        "Small one-off gig, budget $150. Need it this week.",
    ),
    (
        "LLM Prompt Engineer",
        "Hooli AI",
        "Jobicy",
        60,
        ["ai", "llm"],
        "Design prompts and evals for a customer-support assistant. Python preferred.",
    ),
    (
        "Acme Corp | Remote | Django developer",
        "Acme Corp",
        "HN Who's Hiring",
        12,
        ["django"],
        "Django + Postgres, small team, remote-first. Junior welcome.",
    ),
    (
        "Office Assistant (cash weekly)",
        "Local business",
        "Craigslist",
        2,
        ["cash"],
        "Filing and phones.",
    ),
]


@register("demo", default=False, description="Offline sample data (try the tool without network)")
def fetch_demo(client: Client, cfg: Config) -> list[Job]:
    now = datetime.now(UTC)
    return [
        Job(
            title=title,
            url=f"https://example.com/demo/{i}",
            company=company,
            source=source,
            tags=tags,
            description=desc,
            posted_at=now - timedelta(days=days),
            salary="",
        )
        for i, (title, company, source, days, tags, desc) in enumerate(_ROWS, 1)
    ]
