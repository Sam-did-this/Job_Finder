from __future__ import annotations

import csv
import io
import json
from datetime import UTC, datetime

import pytest

from job_finder.history import History
from job_finder.models import Job, SourceResult
from job_finder.report import FORMATS, ReportContext, render
from job_finder.sources.feeds import parse_feed

NOW = datetime(2026, 11, 8, 12, 0, tzinfo=UTC)


def make_job(title="Python Dev", url="https://example.com/1", **kw) -> Job:
    return Job(title=title, url=url, source="test", company=kw.pop("company", "Acme"), **kw)


# --- history ---------------------------------------------------------------------------


def test_history_new_then_seen(tmp_path):
    hist = History(tmp_path / "h.db", legacy_json=None)
    jobs = [make_job()]
    hist.annotate(jobs)
    assert jobs[0].is_new
    hist.record(jobs)

    again = [make_job()]
    hist.annotate(again)
    assert not again[0].is_new


def test_history_recognises_cross_posts_by_company_and_title(tmp_path):
    hist = History(tmp_path / "h.db", legacy_json=None)
    hist.record([make_job(url="https://a/1")])
    repost = [make_job(url="https://b/2")]
    hist.annotate(repost)
    assert not repost[0].is_new


def test_mark_applied_by_short_id_and_status_survives_reseeing(tmp_path):
    hist = History(tmp_path / "h.db", legacy_json=None)
    job = make_job()
    hist.record([job])
    assert hist.set_status(job.id, "applied") == 1
    hist.record([job])  # seeing it again must not reset the status
    again = [make_job()]
    hist.annotate(again)
    assert again[0].status == "applied"
    assert hist.counts() == {"applied": 1}


def test_mark_unknown_id_and_bad_status(tmp_path):
    hist = History(tmp_path / "h.db", legacy_json=None)
    assert hist.set_status("deadbeef", "applied") == 0
    with pytest.raises(ValueError, match="status must be"):
        hist.set_status("x", "maybe")


def test_imports_v1_json_history_once(tmp_path):
    legacy = tmp_path / "job_finder_pro_history.json"
    legacy.write_text(json.dumps({"seen_links": ["https://old/1", "https://old/2"]}))
    hist = History(tmp_path / "h.db", legacy_json=legacy)
    old = [make_job(url="https://old/1")]
    hist.annotate(old)
    assert not old[0].is_new
    assert len(hist.recent()) == 2


def test_corrupt_legacy_file_is_ignored(tmp_path):
    legacy = tmp_path / "legacy.json"
    legacy.write_text("{not json")
    assert History(tmp_path / "h.db", legacy_json=legacy).recent() == []


# --- reports ---------------------------------------------------------------------------


def ctx(**kw) -> ReportContext:
    return ReportContext(
        generated_at=NOW,
        profile="python",
        results=[SourceResult("remotive", [make_job()]), SourceResult("reddit", error="HTTP 403")],
        total_matches=1,
        **kw,
    )


@pytest.mark.parametrize("fmt", FORMATS)
def test_every_format_renders_and_reports_failed_sources(fmt):
    out = render(fmt, [make_job()], ctx())
    assert "Python Dev" in out
    if fmt in ("text", "md", "html"):
        assert "HTTP 403" in out  # a failing source is visible, not silently "no jobs"


def test_json_is_valid_and_complete():
    data = json.loads(render("json", [make_job()], ctx()))
    assert data["jobs"][0]["title"] == "Python Dev"
    assert data["sources"][1] == {"name": "reddit", "count": 0, "error": "HTTP 403", "skipped": ""}


def test_html_escapes_untrusted_text_and_blocks_javascript_links():
    evil = make_job(title="<script>alert(1)</script>", url="javascript:alert(1)")
    page = render("html", [evil], ctx())
    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page
    assert 'href="javascript' not in page


def test_markdown_drops_unsafe_links():
    out = render("md", [make_job(url="javascript:alert(1)")], ctx())
    assert "javascript:" not in out


def test_csv_neutralises_formula_injection():
    job = make_job(title='=HYPERLINK("http://evil","click")', company="+cmd")
    rows = list(csv.reader(io.StringIO(render("csv", [job], ctx()))))
    header, row = rows
    assert row[header.index("title")].startswith("'=")
    assert row[header.index("company")].startswith("'+")


def test_text_report_ascii_badges_and_explain():
    job = make_job()
    job.is_new, job.score, job.reasons = True, 9, ["+4 python (title)"]
    out = render("text", [job], ctx(explain=True, emoji=False))
    assert "NEW" in out
    assert "TOP" in out
    assert "why: +4 python (title)" in out
    assert "🆕" not in out and "⭐" not in out


def test_empty_report_is_helpful():
    assert "No matching jobs" in render("text", [], ctx())


def test_feed_parser_handles_atom_and_rss():
    atom = parse_feed(
        '<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>T</title>'
        '<link href="https://x/1"/></entry></feed>'
    )
    assert atom == [
        {"title": "T", "title_all": ["T"], "link": "https://x/1", "link_all": ["https://x/1"]}
    ]
