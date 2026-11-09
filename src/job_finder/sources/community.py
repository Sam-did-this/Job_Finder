"""Community sources: Hacker News monthly threads and Reddit hiring posts.

These are where real freelance gigs and small teams show up.
"""

from __future__ import annotations

import time

from job_finder.config import Config
from job_finder.http import Client
from job_finder.models import Job
from job_finder.sources.base import register
from job_finder.sources.feeds import parse_feed
from job_finder.utils import extract_salary, parse_date, strip_html

ALGOLIA = "https://hn.algolia.com/api/v1"


def _latest_thread(client: Client, title_prefix: str) -> dict | None:
    """Newest monthly thread posted by the 'whoishiring' bot whose title starts with prefix."""
    data = client.get_json(
        f"{ALGOLIA}/search_by_date",
        params={"tags": "story,author_whoishiring", "hitsPerPage": 12},
    )
    for hit in data.get("hits", []):
        if (hit.get("title") or "").lower().startswith(title_prefix.lower()):
            return hit
    return None


def _thread_jobs(client: Client, cfg: Config, prefix: str, source: str, kind: str) -> list[Job]:
    story = _latest_thread(client, prefix)
    if not story:
        return []
    story_id = str(story["objectID"])
    jobs: list[Job] = []
    for page in range(cfg.hn_pages):
        data = client.get_json(
            f"{ALGOLIA}/search",
            params={"tags": f"comment,story_{story_id}", "hitsPerPage": 500, "page": page},
        )
        for hit in data.get("hits", []):
            if str(hit.get("parent_id")) != story_id or not hit.get("comment_text"):
                continue  # replies and deleted comments
            text = strip_html(hit["comment_text"])
            first_line = text.split("\n", 1)[0]
            title = first_line if len(first_line) <= 140 else first_line[:137] + "..."
            company = first_line.split("|", 1)[0].strip()[:60]
            jobs.append(
                Job(
                    title=title,
                    url=f"https://news.ycombinator.com/item?id={hit['objectID']}",
                    company=company,
                    source=source,
                    kind=kind,
                    description=text,
                    posted_at=parse_date(hit.get("created_at")),
                    salary=extract_salary(text),
                )
            )
        if page + 1 >= data.get("nbPages", 1):
            break
        time.sleep(cfg.delay)
    return jobs


@register("hn-hiring", description="Hacker News 'Ask HN: Who is hiring?' (latest month)")
def fetch_hn_hiring(client: Client, cfg: Config) -> list[Job]:
    return _thread_jobs(client, cfg, "ask hn: who is hiring", "HN Who's Hiring", "remote")


@register(
    "hn-freelance",
    description="Hacker News 'Freelancer? Seeking freelancer?' thread",
    kind="freelance",
)
def fetch_hn_freelance(client: Client, cfg: Config) -> list[Job]:
    return _thread_jobs(
        client, cfg, "ask hn: freelancer? seeking freelancer", "HN Freelance", "freelance"
    )


@register("reddit", kind="freelance", description="Reddit hiring posts (subreddits set in config)")
def fetch_reddit(client: Client, cfg: Config) -> list[Job]:
    jobs: list[Job] = []
    for i, sub in enumerate(cfg.reddit_subreddits):
        if i:
            time.sleep(cfg.delay)
        xml = client.get_text(f"https://www.reddit.com/r/{sub}/new/.rss")
        for item in parse_feed(xml):
            title = item.get("title", "")
            lowered = title.lower()
            if sub.lower() == "forhire" and "[hiring]" not in lowered:
                continue  # r/forhire mixes people offering services with people hiring
            description = strip_html(item.get("content") or item.get("description"))
            jobs.append(
                Job(
                    title=title,
                    url=item.get("link", ""),
                    source=f"r/{sub}",
                    kind="freelance",
                    description=description,
                    posted_at=parse_date(item.get("updated") or item.get("pubDate")),
                    salary=extract_salary(f"{title} {description}"),
                )
            )
    return jobs
