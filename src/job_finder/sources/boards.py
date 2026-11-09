"""Public remote-job APIs and RSS feeds (no scraping, no API keys)."""

from __future__ import annotations

import re

from job_finder.config import Config
from job_finder.http import Client
from job_finder.models import Job
from job_finder.sources.base import register
from job_finder.sources.feeds import parse_feed
from job_finder.utils import extract_salary, parse_date, strip_html


def _split_tags(value: str) -> list[str]:
    return [t.strip() for t in re.split(r"[,/]", value) if t.strip()]


@register("remotive", description="Remotive public API (software-dev category)")
def fetch_remotive(client: Client, cfg: Config) -> list[Job]:
    data = client.get_json(
        "https://remotive.com/api/remote-jobs",
        params={"category": "software-dev", "limit": 100},
    )
    jobs = []
    for item in data.get("jobs", []):
        description = strip_html(item.get("description"))
        salary = item.get("salary") or extract_salary(description)
        jobs.append(
            Job(
                title=item.get("title", ""),
                url=item.get("url", ""),
                company=item.get("company_name", ""),
                source="Remotive",
                location=item.get("candidate_required_location", ""),
                tags=list(item.get("tags") or []),
                description=description,
                posted_at=parse_date(item.get("publication_date")),
                salary=salary,
            )
        )
    return jobs


@register("remoteok", description="RemoteOK public API (link back to RemoteOK required by ToS)")
def fetch_remoteok(client: Client, cfg: Config) -> list[Job]:
    data = client.get_json("https://remoteok.com/api")
    jobs = []
    for item in data:
        if not isinstance(item, dict) or "position" not in item:  # first element is a legal note
            continue
        salary = ""
        if item.get("salary_min") and item.get("salary_max"):
            salary = f"${item['salary_min'] // 1000}k-${item['salary_max'] // 1000}k"
        description = strip_html(item.get("description"))
        jobs.append(
            Job(
                title=item.get("position", ""),
                url=item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('slug', '')}",
                company=item.get("company", ""),
                source="RemoteOK",
                location=item.get("location", ""),
                tags=list(item.get("tags") or []),
                description=description,
                posted_at=parse_date(item.get("date") or item.get("epoch")),
                salary=salary or extract_salary(description),
            )
        )
    return jobs


@register("wwr", description="We Work Remotely programming RSS feed")
def fetch_wwr(client: Client, cfg: Config) -> list[Job]:
    xml = client.get_text("https://weworkremotely.com/categories/remote-programming-jobs.rss")
    jobs = []
    for item in parse_feed(xml):
        raw_title = item.get("title", "")
        company, _, title = raw_title.partition(": ")  # feed format: "Company: Job title"
        if not title:
            company, title = "", raw_title
        description = strip_html(item.get("description"))
        jobs.append(
            Job(
                title=title,
                url=item.get("link", ""),
                company=company,
                source="WeWorkRemotely",
                location=item.get("region", ""),
                tags=_split_tags(item.get("skills", "")),
                description=description,
                posted_at=parse_date(item.get("pubDate")),
                salary=extract_salary(description),
            )
        )
    return jobs


@register("python-org", description="python.org/jobs RSS feed")
def fetch_python_org(client: Client, cfg: Config) -> list[Job]:
    xml = client.get_text("https://www.python.org/jobs/feed/rss/")
    jobs = []
    for item in parse_feed(xml):
        description = strip_html(item.get("description"))
        jobs.append(
            Job(
                title=item.get("title", ""),
                url=item.get("link", ""),
                source="python.org",
                tags=["python"],
                description=description,
                posted_at=parse_date(item.get("pubDate")),
                salary=extract_salary(description),
            )
        )
    return jobs


@register("arbeitnow", description="Arbeitnow job-board API (remote listings only)")
def fetch_arbeitnow(client: Client, cfg: Config) -> list[Job]:
    data = client.get_json("https://www.arbeitnow.com/api/job-board-api")
    jobs = []
    for item in data.get("data", []):
        if not item.get("remote"):
            continue
        description = strip_html(item.get("description"))
        jobs.append(
            Job(
                title=item.get("title", ""),
                url=item.get("url", ""),
                company=item.get("company_name", ""),
                source="Arbeitnow",
                location=item.get("location", ""),
                tags=list(item.get("tags") or []) + list(item.get("job_types") or []),
                description=description,
                posted_at=parse_date(item.get("created_at")),
                salary=extract_salary(description),
            )
        )
    return jobs


@register("jobicy", description="Jobicy remote-jobs API (tag set by jobicy_tag in config)")
def fetch_jobicy(client: Client, cfg: Config) -> list[Job]:
    data = client.get_json(
        "https://jobicy.com/api/v2/remote-jobs", params={"count": 50, "tag": cfg.jobicy_tag}
    )
    jobs = []
    for item in data.get("jobs", []):
        description = strip_html(item.get("jobDescription") or item.get("jobExcerpt"))
        industry = item.get("jobIndustry") or []
        salary = ""
        if item.get("salaryMin"):
            salary = f"${int(item['salaryMin']) // 1000}k"
            if item.get("salaryMax"):
                salary += f"-${int(item['salaryMax']) // 1000}k"
        jobs.append(
            Job(
                title=item.get("jobTitle", ""),
                url=item.get("url", ""),
                company=item.get("companyName", ""),
                source="Jobicy",
                location=item.get("jobGeo", ""),
                tags=[industry] if isinstance(industry, str) else list(industry),
                description=description,
                posted_at=parse_date(item.get("pubDate")),
                salary=salary or extract_salary(description),
            )
        )
    return jobs
