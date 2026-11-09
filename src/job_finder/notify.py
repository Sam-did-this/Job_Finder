"""Optional push notifications through ntfy.sh."""

from __future__ import annotations

import re
from collections.abc import Sequence

import requests

from job_finder.http import USER_AGENT
from job_finder.models import Job

_TOPIC_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def send_ntfy(topic: str, jobs: Sequence[Job], *, timeout: int = 10) -> None:
    """Send the best new matches to an ntfy topic. Raises ValueError for a bad topic name."""
    if not _TOPIC_RE.match(topic):
        raise ValueError("ntfy topic may only contain letters, digits, '-' and '_' (max 64)")
    if not jobs:
        return
    top = sorted(jobs, key=lambda j: j.score, reverse=True)[:8]
    lines = [f"{j.title}" + (f" - {j.company}" if j.company else "") for j in top]
    body = "\n".join(lines)
    if len(jobs) > len(top):
        body += f"\n(+{len(jobs) - len(top)} more)"
    response = requests.post(
        f"https://ntfy.sh/{topic}",
        data=body.encode("utf-8"),
        headers={
            "Title": f"{len(jobs)} new job matches",
            "Tags": "briefcase",
            "Click": top[0].url,
            "User-Agent": USER_AGENT,
        },
        timeout=timeout,
    )
    response.raise_for_status()
