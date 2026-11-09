"""Command-line interface."""

from __future__ import annotations

import argparse
import contextlib
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

from job_finder import __version__
from job_finder.config import EXAMPLE_CONFIG, Config, default_config_path, load_config
from job_finder.core import collect, resolve_sources
from job_finder.filters import PROFILES, parse_terms, resolve_profile, select
from job_finder.history import STATUSES, History
from job_finder.notify import send_ntfy
from job_finder.report import EXTENSIONS, FORMATS, ReportContext, render
from job_finder.sources import REGISTRY
from job_finder.utils import parse_since

COMMANDS = {"search", "sources", "mark", "history", "init-config"}


def _common() -> argparse.ArgumentParser:
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--config", type=Path, help="path to a config.toml")
    parent.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    return parent


def build_parser() -> argparse.ArgumentParser:
    common = _common()
    parser = argparse.ArgumentParser(
        prog="job-finder",
        description="Search remote tech jobs, freelance gigs and local work from one CLI.",
        epilog="Run with no command to search. Example: job-finder -s python --since 3d",
    )
    parser.add_argument("--version", action="version", version=f"job-finder {__version__}")
    sub = parser.add_subparsers(dest="command")

    s = sub.add_parser("search", parents=[common], help="search all sources (default command)")
    s.add_argument(
        "-s", "--search", default="", help='required keywords, comma separated: "python, ai"'
    )
    s.add_argument(
        "-x", "--exclude", default="", help="hide jobs mentioning these (title/company/tags)"
    )
    s.add_argument("-p", "--profile", help=f"scoring profile: {', '.join(PROFILES)} or your own")
    s.add_argument("--sources", help="comma list of sources, or 'all' (see `job-finder sources`)")
    s.add_argument("--since", help="only jobs posted within e.g. 12h, 3d, 2w")
    s.add_argument("--min-score", type=int, help="hide jobs scoring below this")
    s.add_argument("-n", "--limit", type=int, help="max jobs to show (default from config)")
    s.add_argument("--new-only", action="store_true", help="only jobs not seen in earlier runs")
    s.add_argument("--show-ignored", action="store_true", help="include jobs you marked ignored")
    s.add_argument("--explain", action="store_true", help="show why each job got its score")
    s.add_argument(
        "-f", "--format", choices=FORMATS, help="output format (default: from -o extension)"
    )
    s.add_argument("-o", "--output", help="save to file; bare names go to the configured folder")
    s.add_argument("--no-history", action="store_true", help="don't read or update history")
    s.add_argument("--no-emoji", action="store_true", help="plain-ASCII badges")
    s.add_argument("--ntfy", metavar="TOPIC", help="push new matches to an ntfy.sh topic")
    s.add_argument("--demo", action="store_true", help="use offline sample data (no network)")

    sub.add_parser("sources", parents=[common], help="list available sources")

    m = sub.add_parser("mark", parents=[common], help="mark a job as applied / saved / ignored")
    m.add_argument("job_id", help="the id shown under each job (or its full URL)")
    m.add_argument("status", choices=STATUSES)

    h = sub.add_parser("history", parents=[common], help="show recently seen jobs")
    h.add_argument("--status", choices=STATUSES)
    h.add_argument("-n", "--limit", type=int, default=20)

    i = sub.add_parser("init-config", parents=[common], help="write an example config file")
    i.add_argument("--force", action="store_true", help="overwrite an existing config")
    return parser


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def _output_path(raw: str, cfg: Config) -> Path:
    path = Path(raw).expanduser()
    # A bare filename keeps the v1 behaviour: save into the configured folder.
    return path if path.parent != Path(".") or raw.startswith(".") else cfg.output_dir / path


def cmd_search(args: argparse.Namespace, cfg: Config) -> int:
    profile = resolve_profile(args.profile or cfg.profile, cfg.custom_profiles)
    since = parse_since(args.since) if args.since else None
    terms = parse_terms(args.search)
    if args.demo:
        names, args.no_history = ["demo"], True
    else:
        names = resolve_sources(parse_terms(args.sources) or None, cfg)

    _err(f"Searching {len(names)} source(s): {', '.join(names)}")
    results = collect(names, cfg)
    for r in results:
        if r.error:
            _err(f"  ! {r.name} failed: {r.error}")
        elif r.skipped:
            _err(f"  - {r.name} skipped: {r.skipped}")
    if not any(r.ok for r in results):
        _err("No source returned data. Check your connection, or try --demo to see sample output.")
        return 1

    jobs = select(
        [job for r in results for job in r.jobs],
        profile=profile,
        terms=terms,
        exclude=[*cfg.exclude, *parse_terms(args.exclude)],
        since=since,
        min_score=args.min_score,
    )

    history = None if args.no_history else History(cfg.history_db)
    if history:
        history.annotate(jobs)
        if not args.show_ignored:
            jobs = [j for j in jobs if j.status != "ignored"]
        if args.new_only:
            jobs = [j for j in jobs if j.is_new]

    shown = jobs[: args.limit or cfg.max_results]
    fmt = args.format or EXTENSIONS.get(Path(args.output or "").suffix.lower(), "text")
    ctx = ReportContext(
        generated_at=datetime.now(UTC).astimezone(),
        profile=profile.name,
        terms=terms,
        total_matches=len(jobs),
        results=results,
        explain=args.explain,
        emoji=not args.no_emoji,
    )
    output = render(fmt, shown, ctx)

    if args.output:
        path = _output_path(args.output, cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as fh:
            fh.write(output)
        print(f"Saved {len(shown)} jobs to {path}")
    else:
        sys.stdout.write(output)

    if args.ntfy:
        fresh = [j for j in shown if j.is_new]
        try:
            send_ntfy(args.ntfy, fresh)
        except (ValueError, requests.RequestException) as exc:
            _err(f"  ! ntfy notification failed: {exc}")
    if history:
        history.record(shown)
    return 0


def cmd_sources(args: argparse.Namespace, cfg: Config) -> int:
    for name, spec in REGISTRY.items():
        flag = "default" if spec.default else "opt-in "
        print(f"{name:14} {flag}  {spec.kind:9} {spec.description}")
    return 0


def cmd_mark(args: argparse.Namespace, cfg: Config) -> int:
    changed = History(cfg.history_db).set_status(args.job_id, args.status)
    if not changed:
        _err(f"No job with id/url {args.job_id!r} in history. Ids appear under each result.")
        return 1
    print(f"Marked {args.job_id} as {args.status}.")
    return 0


def cmd_history(args: argparse.Namespace, cfg: Config) -> int:
    history = History(cfg.history_db)
    counts = history.counts()
    print("History: " + (", ".join(f"{n} {s}" for s, n in sorted(counts.items())) or "empty"))
    for row in history.recent(args.limit, args.status):
        title = row["title"] or row["url"]
        print(f"  {row['id']}  {row['status']:8} {row['last_seen'][:10]}  {title[:70]}")
    return 0


def cmd_init_config(args: argparse.Namespace, cfg: Config) -> int:
    path = args.config or default_config_path()
    if path.exists() and not args.force:
        _err(f"{path} already exists (use --force to overwrite).")
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    print(f"Wrote {path}")
    return 0


HANDLERS = {
    "search": cmd_search,
    "sources": cmd_sources,
    "mark": cmd_mark,
    "history": cmd_history,
    "init-config": cmd_init_config,
}


def normalize_argv(argv: list[str]) -> list[str]:
    """Make `job-finder -s python` mean `search -s python`, and accept --config / -v anywhere.

    Global flags are moved to just after the command so every subparser sees them.
    """
    rest: list[str] = []
    shared: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--config" and i + 1 < len(argv):
            shared += [tok, argv[i + 1]]
            i += 2
        elif tok.startswith("--config=") or tok in ("-v", "--verbose"):
            shared.append(tok)
            i += 1
        else:
            rest.append(tok)
            i += 1
    if not rest or (rest[0] not in COMMANDS and rest[0] not in ("-h", "--help", "--version")):
        rest.insert(0, "search")
    return rest[:1] + shared + rest[1:]


def main(argv: list[str] | None = None) -> int:
    argv = normalize_argv(list(sys.argv[1:] if argv is None else argv))
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    # urllib3 logs every retry at WARNING; only show that noise with -v.
    logging.getLogger("urllib3").setLevel(logging.DEBUG if args.verbose else logging.ERROR)
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    try:
        # init-config creates the file, so it must not require it to exist yet.
        cfg = Config() if args.command == "init-config" else load_config(args.config)
        return HANDLERS[args.command](args, cfg)
    except KeyboardInterrupt:
        _err("\nCancelled.")
        return 130
    except (ValueError, FileNotFoundError, OSError) as exc:
        _err(f"error: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
