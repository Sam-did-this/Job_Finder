"""Local-work sources. Both are opt-in (not in the default source list)."""

from __future__ import annotations

import os
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from job_finder.config import Config
from job_finder.filters import compile_terms, hits
from job_finder.http import Client
from job_finder.models import Job
from job_finder.sources.base import SourceSkipped, register
from job_finder.utils import extract_salary, parse_date, strip_html


@register(
    "adzuna",
    kind="local",
    default=False,
    description="Adzuna job-search API for local jobs (needs free ADZUNA_APP_ID/KEY)",
)
def fetch_adzuna(client: Client, cfg: Config) -> list[Job]:
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise SourceSkipped("set ADZUNA_APP_ID and ADZUNA_APP_KEY (free at developer.adzuna.com)")
    data = client.get_json(
        f"https://api.adzuna.com/v1/api/jobs/{cfg.adzuna_country}/search/1",
        params={
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": 50,
            "what": cfg.adzuna_what,
            "where": cfg.adzuna_where,
            "sort_by": "date",
        },
    )
    jobs = []
    for item in data.get("results", []):
        salary = ""
        if item.get("salary_min"):
            salary = f"${int(item['salary_min']) // 1000}k"
            if item.get("salary_max"):
                salary += f"-${int(item['salary_max']) // 1000}k"
        description = strip_html(item.get("description"))
        jobs.append(
            Job(
                title=item.get("title", ""),
                url=item.get("redirect_url", ""),
                company=(item.get("company") or {}).get("display_name", ""),
                source="Adzuna",
                kind="local",
                location=(item.get("location") or {}).get("display_name", ""),
                description=description,
                posted_at=parse_date(item.get("created")),
                salary=salary or extract_salary(description),
            )
        )
    return jobs


@register(
    "craigslist",
    kind="local",
    default=False,
    description="Craigslist gigs (best-effort HTML scrape; check their terms before use)",
)
def fetch_craigslist(client: Client, cfg: Config) -> list[Job]:
    base = f"https://{cfg.craigslist_city}.craigslist.org"
    excluded = compile_terms(cfg.craigslist_exclude)
    priority = compile_terms(cfg.craigslist_priority)
    jobs: list[Job] = []
    for i, category in enumerate(cfg.craigslist_categories):
        if i:
            time.sleep(cfg.delay)
        html = client.get_text(f"{base}/search/{cfg.craigslist_subarea}/{category}")
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("li.cl-static-search-result, li.cl-search-result, li.result-row")
        for row in rows:
            link = row.find("a", href=True)
            if link is None:
                continue
            title_tag = row.select_one(".title, .titlestring, .result-title") or link
            title = title_tag.get_text(strip=True)
            if not title or hits(excluded, title):
                continue
            tags = sorted(hits(priority, title))
            location_tag = row.select_one(".location")
            jobs.append(
                Job(
                    title=title,
                    url=urljoin(base, link["href"]),
                    source="Craigslist",
                    kind="local",
                    tags=tags,
                    location=location_tag.get_text(strip=True) if location_tag else "",
                )
            )
    return jobs
