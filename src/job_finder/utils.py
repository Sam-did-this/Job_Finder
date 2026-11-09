"""Small helpers: HTML stripping, dates, salary extraction."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

MAX_DESCRIPTION = 3000

_AMOUNT = r"\d{2,3}(?:,\d{3}|(?:\.\d)?k)\b"
_SALARY = re.compile(
    rf"(?:US)?\$\s?{_AMOUNT}(?:\s*(?:-|–|—|to)\s*(?:US)?\$?\s?{_AMOUNT})?",
    re.I,
)
_SINCE = re.compile(r"^(\d+)\s*([hdw])$", re.I)


def strip_html(raw: str | None, limit: int = MAX_DESCRIPTION) -> str:
    """Convert an HTML fragment to plain text (newlines kept between blocks)."""
    if not raw:
        return ""
    text = BeautifulSoup(raw, "html.parser").get_text("\n")
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:limit]


def parse_date(value: object) -> datetime | None:
    """Parse ISO-8601, RFC-2822 or epoch seconds into an aware UTC datetime."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, int | float) or str(value).strip().isdigit():
            return datetime.fromtimestamp(float(value), tz=UTC)  # type: ignore[arg-type]
        text = str(value).strip()
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            dt = parsedate_to_datetime(text)
    except (ValueError, TypeError, OverflowError, OSError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def extract_salary(text: str) -> str:
    """Return the first '$80k-$120k' / '$90,000' style figure in text, or ''."""
    match = _SALARY.search(text or "")
    return match.group(0).strip() if match else ""


def parse_since(value: str) -> timedelta:
    """'12h' / '3d' / '2w' -> timedelta. Raises ValueError on bad input."""
    match = _SINCE.match(value.strip())
    if not match:
        raise ValueError(f"invalid --since value {value!r}; use e.g. 12h, 3d or 2w")
    amount, unit = int(match.group(1)), match.group(2).lower()
    return timedelta(**{{"h": "hours", "d": "days", "w": "weeks"}[unit]: amount})


def age_label(posted: datetime | None, now: datetime | None = None) -> str:
    """'3h ago', '2d ago', or '' when unknown."""
    if posted is None:
        return ""
    delta = (now or datetime.now(UTC)) - posted
    hours = int(delta.total_seconds() // 3600)
    if hours < 1:
        return "just now"
    if hours < 48:
        return f"{hours}h ago"
    return f"{delta.days}d ago"
