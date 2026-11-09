"""Every source is tested against saved fixtures, never the live internet."""

from __future__ import annotations

import pytest
from defusedxml import DefusedXmlException

from job_finder.sources import REGISTRY, SourceSkipped
from job_finder.sources.feeds import parse_feed
from tests.conftest import FakeClient, fixture_text


def run(name, routes, cfg):
    return REGISTRY[name].fn(FakeClient(routes), cfg)


def test_registry_has_expected_sources():
    expected = {
        "remotive",
        "remoteok",
        "wwr",
        "python-org",
        "arbeitnow",
        "jobicy",
        "hn-hiring",
        "hn-freelance",
        "reddit",
        "adzuna",
        "craigslist",
        "demo",
    }
    assert expected <= set(REGISTRY)
    # Scraping and key-needing sources must never run by accident.
    assert not REGISTRY["craigslist"].default
    assert not REGISTRY["adzuna"].default
    assert not REGISTRY["demo"].default


def test_remotive(cfg):
    jobs = run("remotive", {"remotive.com": "remotive.json"}, cfg)
    assert [j.title for j in jobs] == ["Python Developer", "Office Manager"]
    first = jobs[0]
    assert first.company == "Acme"
    assert first.tags == ["python", "api"]
    assert first.salary == "$90k-$120k"  # extracted from the description
    assert first.posted_at.year == 2026
    assert "<p>" not in first.description


def test_remoteok_skips_legal_header_and_builds_salary(cfg):
    jobs = run("remoteok", {"remoteok.com": "remoteok.json"}, cfg)
    assert len(jobs) == 1
    assert jobs[0].title == "React Engineer"
    assert jobs[0].salary == "$90k-$130k"


def test_wwr_splits_company_and_title(cfg):
    jobs = run("wwr", {"weworkremotely.com": "wwr.rss"}, cfg)
    assert jobs[0].company == "Globex"
    assert jobs[0].title == "Junior Django Developer"
    assert jobs[0].tags == ["python", "django"]
    assert jobs[0].salary == "$60,000 to $80,000"
    assert jobs[1].company == ""


def test_python_org(cfg):
    jobs = run("python-org", {"python.org": "pythonjobs.rss.xml"}, cfg)
    assert jobs[0].title.startswith("Junior Python Developer")
    assert jobs[0].url.startswith("https://www.python.org/jobs/")


def test_arbeitnow_keeps_remote_only(cfg):
    jobs = run("arbeitnow", {"arbeitnow.com": "arbeitnow.json"}, cfg)
    assert [j.title for j in jobs] == ["Python Developer (m/w/d)"]
    assert jobs[0].posted_at is not None  # epoch seconds parsed


def test_jobicy(cfg):
    jobs = run("jobicy", {"jobicy.com": "jobicy.json"}, cfg)
    assert jobs[0].company == "Sample Co"
    assert jobs[0].location == "LATAM"
    assert jobs[0].salary == "$50k-$70k"
    assert jobs[0].posted_at is not None


def test_hn_hiring_only_top_level_comments(cfg):
    routes = {"search_by_date": "hn_story.json", "/search": "hn_comments.json"}
    jobs = run("hn-hiring", routes, cfg)
    assert len(jobs) == 1  # reply and deleted comment are ignored
    job = jobs[0]
    assert job.company == "Acme"
    assert job.title == "Acme | Remote | Python dev"
    assert job.url == "https://news.ycombinator.com/item?id=301"
    assert job.salary == "$100k-$140k"


def test_hn_freelance_without_matching_thread_returns_nothing(cfg):
    routes = {"search_by_date": "hn_story.json"}  # fixture has no freelancer thread
    assert run("hn-freelance", routes, cfg) == []


def test_reddit_forhire_keeps_only_hiring_posts(cfg):
    jobs = run("reddit", {"reddit.com": "reddit_forhire.atom.xml"}, cfg)
    assert len(jobs) == 1
    assert jobs[0].title.startswith("[HIRING]")
    assert jobs[0].kind == "freelance"
    assert jobs[0].salary == ""  # "$200" is a one-off budget, not a salary range


def test_craigslist_excludes_and_tags(cfg):
    jobs = run("craigslist", {"craigslist.org": "craigslist.html"}, cfg)
    titles = {j.title for j in jobs}
    assert "House cleaning helper - cash daily" in titles
    assert "Cashier wanted" not in titles  # 'cashier' is in the exclude list
    cleaner = next(j for j in jobs if j.title.startswith("House"))
    assert cleaner.tags == ["cash", "cleaning", "helper"]
    assert cleaner.location == "Astoria"
    assert cleaner.url.startswith("https://newyork.craigslist.org/")


def test_adzuna_skips_without_keys(cfg, monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    with pytest.raises(SourceSkipped):
        REGISTRY["adzuna"].fn(FakeClient({}), cfg)


def test_feed_parser_rejects_entity_expansion_bombs():
    with pytest.raises(DefusedXmlException):
        parse_feed(fixture_text("evil.xml"))
