from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from job_finder.filters import (
    PROFILES,
    Profile,
    compile_terms,
    dedupe,
    hits,
    parse_terms,
    resolve_profile,
    score_job,
    select,
)
from job_finder.models import Job
from job_finder.utils import age_label, extract_salary, parse_date, parse_since, strip_html

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def job(title="Python Developer", **kw) -> Job:
    kw.setdefault("url", f"https://example.com/{title.replace(' ', '-')}")
    kw.setdefault("source", "test")
    return Job(title=title, **kw)


# --- the v1 false-positive bugs -------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "Please email us",
        "We maintain things",
        "paid vacation",
        "Learn on the job",
        "western region",
    ],
)
def test_short_keywords_do_not_match_inside_words(text):
    assert not hits(compile_terms(["ai", "rn", "ml", "api", "node"]), text)


def test_whole_word_matches_still_work():
    pattern = compile_terms(["ai", "c++", "node.js"])
    assert hits(pattern, "AI engineer") == {"ai"}
    assert hits(pattern, "We use C++ and Node.js daily") == {"c++", "node.js"}


def test_parse_terms():
    assert parse_terms(" python, cash ,, ai ") == ["python", "cash", "ai"]
    assert parse_terms("") == []
    assert parse_terms(None) == []


# --- scoring ---------------------------------------------------------------------------


def test_junior_python_outranks_senior_python():
    profile = PROFILES["python"]
    junior = score_job(job("Junior Python Developer"), profile, now=NOW)
    senior = score_job(job("Senior Python Developer"), profile, now=NOW)
    assert junior.score > senior.score
    assert any("senior" in r for r in senior.reasons)


def test_remote_in_description_no_longer_counts_as_a_dev_match():
    profile = PROFILES["python"]
    ranked = select(
        [job("Warehouse Associate", description="remote friendly")], profile=profile, now=NOW
    )
    assert ranked == []  # v1 let anything through because "remote" was a dev keyword


def test_recency_and_salary_bonuses():
    fresh = score_job(
        job(posted_at=NOW - timedelta(hours=3), salary="$90k"), PROFILES["python"], now=NOW
    )
    stale = score_job(job(posted_at=NOW - timedelta(days=60)), PROFILES["python"], now=NOW)
    assert fresh.score - stale.score == (2 + 1) - (-2)


def test_ai_flag_uses_word_boundaries():
    assert score_job(job("AI Engineer"), PROFILES["dev"], now=NOW).is_ai
    assert not score_job(job("Email Marketing Python Dev"), PROFILES["dev"], now=NOW).is_ai


def test_custom_profile_from_config():
    profile = resolve_profile("mine", {"mine": {"include": ["rust"], "exclude": ["unpaid"]}})
    assert isinstance(profile, Profile)
    assert (
        select(
            [job("Rust Dev"), job("Rust Dev unpaid", url="https://x/2")], profile=profile, now=NOW
        )[0].title
        == "Rust Dev"
    )
    with pytest.raises(ValueError, match="unknown profile"):
        resolve_profile("nope")


# --- select / dedupe -------------------------------------------------------------------


def test_search_terms_are_required_and_search_description_and_tags():
    profile = PROFILES["dev"]
    jobs = [
        job("Backend Engineer", description="We use Rust", url="https://x/1"),
        job("Backend Engineer II", tags=["rust"], url="https://x/2"),
        job("Backend Engineer III", description="We use Go", url="https://x/3"),
    ]
    found = select(jobs, profile=profile, terms=["rust"], now=NOW)
    assert {j.url for j in found} == {"https://x/1", "https://x/2"}


def test_exclude_since_and_min_score():
    profile = PROFILES["python"]
    jobs = [
        job("Python Dev (unpaid)", url="https://x/1"),
        job("Python Dev", url="https://x/2", posted_at=NOW - timedelta(days=10)),
        job("Python Dev Fresh", url="https://x/3", posted_at=NOW - timedelta(hours=2)),
    ]
    kept = select(jobs, profile=profile, exclude=["unpaid"], since=timedelta(days=3), now=NOW)
    assert [j.url for j in kept] == ["https://x/3"]
    assert select(jobs, profile=profile, min_score=999, now=NOW) == []


def test_dedupe_by_url_and_by_company_title():
    a = job("Python Dev", company="Acme", url="https://a/1", source="remotive")
    b = job("python dev!", company="ACME", url="https://b/2", source="wwr")  # cross-posted
    c = job("Python Dev", company="Acme", url="https://a/1")  # same url
    d = job("Go Dev", company="Acme", url="https://a/3")
    assert [j.url for j in dedupe([a, b, c, d])] == ["https://a/1", "https://a/3"]


def test_results_sorted_best_first():
    jobs = [
        job("Senior Python Dev", url="https://x/1"),
        job("Junior Python Dev", url="https://x/2"),
    ]
    assert select(jobs, profile=PROFILES["python"], now=NOW)[0].title == "Junior Python Dev"


# --- utils -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Pay is $90k-$120k plus bonus", "$90k-$120k"),
        ("$120,000 to $150,000 / year", "$120,000 to $150,000"),
        ("budget $200", ""),
        ("no money here", ""),
    ],
)
def test_extract_salary(text, expected):
    assert extract_salary(text) == expected


def test_parse_date_variants():
    assert parse_date("2026-11-07T10:00:00Z").tzinfo is not None
    assert parse_date("Fri, 06 Nov 2026 12:00:00 +0000").day == 6
    assert parse_date(1794000000).year == 2026
    assert parse_date("2026-11-05 10:00:00").hour == 10
    assert parse_date("garbage") is None
    assert parse_date(None) is None


def test_parse_since_and_age_label():
    assert parse_since("3d") == timedelta(days=3)
    assert parse_since("12H") == timedelta(hours=12)
    with pytest.raises(ValueError, match="invalid --since"):
        parse_since("soon")
    assert age_label(NOW - timedelta(hours=5), NOW) == "5h ago"
    assert age_label(NOW - timedelta(days=4), NOW) == "4d ago"
    assert age_label(None) == ""


def test_strip_html():
    assert strip_html("<p>Hello <b>world</b></p><p>Next</p>") == "Hello \nworld\nNext"
    assert strip_html(None) == ""
