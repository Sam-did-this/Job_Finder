"""Render results as text, Markdown, CSV, JSON or a self-contained HTML page."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from urllib.parse import urlparse

from job_finder.filters import TOP_MATCH_SCORE
from job_finder.models import Job, SourceResult
from job_finder.utils import age_label

FORMATS = ("text", "md", "csv", "json", "html")
EXTENSIONS = {".txt": "text", ".md": "md", ".csv": "csv", ".json": "json", ".html": "html"}


@dataclass
class ReportContext:
    generated_at: datetime
    profile: str
    terms: list[str] = field(default_factory=list)
    total_matches: int = 0
    results: list[SourceResult] = field(default_factory=list)
    explain: bool = False
    emoji: bool = True


def _badges(job: Job, emoji: bool) -> str:
    marks = []
    if job.is_new:
        marks.append("🆕" if emoji else "NEW")
    if job.score >= TOP_MATCH_SCORE:
        marks.append("⭐" if emoji else "TOP")
    if job.is_ai:
        marks.append("🤖" if emoji else "AI")
    if job.status == "applied":
        marks.append("✅" if emoji else "APPLIED")
    elif job.status == "saved":
        marks.append("🔖" if emoji else "SAVED")
    return " ".join(marks)


def _meta(job: Job) -> str:
    bits = [job.source, age_label(job.posted_at), job.location, job.salary]
    return " · ".join(b for b in bits if b)


def _safe_url(url: str) -> str:
    """Only http(s) URLs may become links (blocks javascript: and data: URLs from feeds)."""
    return url if urlparse(url).scheme in ("http", "https") else ""


def _status_lines(ctx: ReportContext) -> list[str]:
    lines = []
    for r in ctx.results:
        if r.ok:
            lines.append(f"{r.name}: {len(r.jobs)} fetched ({r.elapsed:.1f}s)")
        elif r.skipped:
            lines.append(f"{r.name}: skipped - {r.skipped}")
        else:
            lines.append(f"{r.name}: FAILED - {r.error}")
    return lines


def _summary(jobs: list[Job], ctx: ReportContext) -> str:
    new = sum(1 for j in jobs if j.is_new)
    top = sum(1 for j in jobs if j.score >= TOP_MATCH_SCORE)
    return (
        f"{ctx.total_matches} matched, showing {len(jobs)} | {new} new | {top} top matches"
        f" | profile: {ctx.profile}" + (f" | terms: {', '.join(ctx.terms)}" if ctx.terms else "")
    )


def render_text(jobs: list[Job], ctx: ReportContext) -> str:
    rule = "=" * 72
    out = [rule, f"JOB FINDER  {ctx.generated_at:%Y-%m-%d %H:%M}", _summary(jobs, ctx), rule]
    if not jobs:
        out.append("No matching jobs. Try broader terms, --since 14d, or another --profile.")
    for i, job in enumerate(jobs, 1):
        badges = _badges(job, ctx.emoji)
        head = f"{i:2d}. {job.title[:80]}" + (f"  {badges}" if badges else "")
        out.append("")
        out.append(head)
        company = f"{job.company} - " if job.company else ""
        out.append(f"    {company}{_meta(job)}  [score {job.score}]")
        out.append(f"    {job.url}")
        out.append(f"    id: {job.id}")
        if ctx.explain and job.reasons:
            out.append(f"    why: {', '.join(job.reasons)}")
    out.extend(["", rule, "Sources", *(f"  {line}" for line in _status_lines(ctx))])
    new = sum(1 for j in jobs if j.is_new)
    if new:
        out.append(f"\n{new} new since your last run. Track one with: job-finder mark <id> applied")
    return "\n".join(out) + "\n"


def render_markdown(jobs: list[Job], ctx: ReportContext) -> str:
    out = [
        f"# Job Finder report - {ctx.generated_at:%Y-%m-%d %H:%M}",
        "",
        f"_{_summary(jobs, ctx)}_",
        "",
    ]
    for i, job in enumerate(jobs, 1):
        badges = _badges(job, ctx.emoji)
        title = job.title.replace("[", "(").replace("]", ")")
        link = _safe_url(job.url)
        heading = f"[{title}]({link})" if link else title
        out.append(f"{i}. **{heading}** {badges}".rstrip())
        company = f"{job.company} - " if job.company else ""
        out.append(f"   - {company}{_meta(job)} (score {job.score}, id `{job.id}`)")
        if ctx.explain and job.reasons:
            out.append(f"   - why: {', '.join(job.reasons)}")
    out += ["", "## Sources", *(f"- {line}" for line in _status_lines(ctx)), ""]
    return "\n".join(out)


_FORMULA_CHARS = ("=", "+", "-", "@", "\t", "\r")


def _csv_safe(value: object) -> str:
    """Neutralise spreadsheet formula injection from untrusted text."""
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_CHARS) else text


def render_csv(jobs: list[Job], ctx: ReportContext) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "score",
            "new",
            "title",
            "company",
            "source",
            "kind",
            "location",
            "salary",
            "posted",
            "tags",
            "url",
        ]
    )
    for job in jobs:
        writer.writerow(
            [
                job.id,
                job.score,
                int(job.is_new),
                *map(
                    _csv_safe,
                    (
                        job.title,
                        job.company,
                        job.source,
                        job.kind,
                        job.location,
                        job.salary,
                        job.posted_at.date().isoformat() if job.posted_at else "",
                        ";".join(job.tags),
                        job.url,
                    ),
                ),
            ]
        )
    return buf.getvalue()


def render_json(jobs: list[Job], ctx: ReportContext) -> str:
    payload = {
        "generated_at": ctx.generated_at.isoformat(),
        "profile": ctx.profile,
        "terms": ctx.terms,
        "total_matches": ctx.total_matches,
        "sources": [
            {"name": r.name, "count": len(r.jobs), "error": r.error, "skipped": r.skipped}
            for r in ctx.results
        ],
        "jobs": [j.to_dict() for j in jobs],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Finder report</title>
<style>
:root{{--bg:#fff;--fg:#1b1f24;--muted:#5b6672;--card:#f5f7fa;--line:#dde2e8;--accent:#2457d6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#12151a;--fg:#e6e9ee;--muted:#9aa5b1;
--card:#1b2027;--line:#2b323b;--accent:#7aa2ff}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}}
main{{max-width:820px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:1.4rem;margin:0 0 4px}} .sub{{color:var(--muted);margin:0 0 20px}}
.job{{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:12px 14px;margin:10px 0}}
.job a.t{{color:var(--accent);font-weight:600;text-decoration:none}}
.job a.t:hover{{text-decoration:underline}}
.meta{{color:var(--muted);font-size:.9rem;margin-top:2px}}
.score{{float:right;font-variant-numeric:tabular-nums;color:var(--muted)}}
.badge{{display:inline-block;font-size:.72rem;border:1px solid var(--line);border-radius:99px;
padding:0 8px;margin-left:6px;color:var(--muted)}}
.why{{font-size:.8rem;color:var(--muted);margin-top:4px}}
h2{{font-size:1rem;margin-top:28px}} ul{{padding-left:20px;color:var(--muted)}}
</style></head><body><main>
<h1>Job Finder report</h1>
<p class="sub">{generated} · {summary}</p>
{cards}
<h2>Sources</h2><ul>{sources}</ul>
</main></body></html>
"""


def render_html(jobs: list[Job], ctx: ReportContext) -> str:
    cards = []
    for job in jobs:
        link = _safe_url(job.url)
        title = escape(job.title)
        head = (
            f'<a class="t" href="{escape(link)}" rel="noopener noreferrer">{title}</a>'
            if link
            else f'<span class="t">{title}</span>'
        )
        badges = "".join(
            f'<span class="badge">{escape(b)}</span>' for b in _badges(job, False).split()
        )
        company = f"{escape(job.company)} · " if job.company else ""
        why = (
            f'<div class="why">why: {escape(", ".join(job.reasons))}</div>'
            if ctx.explain and job.reasons
            else ""
        )
        cards.append(
            f'<div class="job"><span class="score">score {job.score}</span>{head}{badges}'
            f'<div class="meta">{company}{escape(_meta(job))}</div>{why}</div>'
        )
    if not cards:
        cards.append('<p class="sub">No matching jobs.</p>')
    return _HTML.format(
        generated=escape(f"{ctx.generated_at:%Y-%m-%d %H:%M}"),
        summary=escape(_summary(jobs, ctx)),
        cards="\n".join(cards),
        sources="".join(f"<li>{escape(line)}</li>" for line in _status_lines(ctx)),
    )


RENDERERS = {
    "text": render_text,
    "md": render_markdown,
    "csv": render_csv,
    "json": render_json,
    "html": render_html,
}


def render(fmt: str, jobs: list[Job], ctx: ReportContext) -> str:
    return RENDERERS[fmt](jobs, ctx)
