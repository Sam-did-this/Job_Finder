"""Configuration: built-in defaults, optionally overridden by a TOML file."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from platformdirs import user_config_path, user_data_path

APP = "job-finder"


def default_config_path() -> Path:
    return user_config_path(APP) / "config.toml"


def default_history_path() -> Path:
    return user_data_path(APP) / "history.sqlite3"


@dataclass
class Config:
    # general
    output_dir: Path = field(default_factory=lambda: Path.home() / "Documents")
    history_db: Path = field(default_factory=default_history_path)
    max_results: int = 50
    timeout: int = 15
    retries: int = 3
    delay: float = 1.0  # polite pause between requests inside one source
    workers: int = 6
    # search defaults
    profile: str = "dev"
    sources: list[str] | None = None  # None -> every source flagged default
    exclude: list[str] = field(default_factory=list)
    custom_profiles: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    # per-source options
    reddit_subreddits: list[str] = field(default_factory=lambda: ["forhire"])
    hn_pages: int = 2
    jobicy_tag: str = "python"
    adzuna_country: str = "us"
    adzuna_where: str = "New York"
    adzuna_what: str = "python developer"
    craigslist_city: str = "newyork"
    craigslist_subarea: str = "que"  # mnh, brx, brk, que, stn
    craigslist_categories: list[str] = field(default_factory=lambda: ["ggg", "lab", "dom", "trd"])
    craigslist_exclude: list[str] = field(
        default_factory=lambda: [
            "customer service",
            "call center",
            "retail",
            "cashier",
            "sales associate",
            "server",
            "bartender",
            "hostess",
            "receptionist",
            "front desk",
            "dental",
            "medical assistant",
            "rn",
            "registered nurse",
            "real estate",
            "insurance",
            "bank",
            "teller",
            "administrative",
            "assistant",
            "office",
        ]
    )
    craigslist_priority: list[str] = field(
        default_factory=lambda: [
            "cash",
            "daily pay",
            "same day",
            "under the table",
            "no experience",
            "helper",
            "clean",
            "cleaning",
            "move",
            "moving",
            "haul",
            "hauling",
            "labor",
            "construction",
            "warehouse",
            "painter",
            "painting",
            "handyman",
            "landscaping",
            "yard",
            "snow",
        ]
    )


def _path(value: str) -> Path:
    return Path(value).expanduser()


def load_config(path: Path | None = None) -> Config:
    """Load config from `path` (or the default location if it exists)."""
    cfg = Config()
    explicit = path is not None
    path = path or default_config_path()
    if not path.exists():
        if explicit:
            raise FileNotFoundError(f"config file not found: {path}")
        return cfg

    with path.open("rb") as fh:
        raw: dict[str, Any] = tomllib.load(fh)

    general = raw.get("general", {})
    if "output_dir" in general:
        cfg.output_dir = _path(general["output_dir"])
    if "history_db" in general:
        cfg.history_db = _path(general["history_db"])
    for key in ("max_results", "timeout", "retries", "workers"):
        if key in general:
            setattr(cfg, key, int(general[key]))
    if "delay" in general:
        cfg.delay = float(general["delay"])

    search = raw.get("search", {})
    cfg.profile = search.get("profile", cfg.profile)
    cfg.exclude = list(search.get("exclude", cfg.exclude))
    if "sources" in search:
        cfg.sources = list(search["sources"])

    cfg.custom_profiles = {
        name: {k: list(v) for k, v in body.items()}
        for name, body in raw.get("profiles", {}).items()
    }

    sources = raw.get("sources", {})
    cfg.reddit_subreddits = list(sources.get("reddit_subreddits", cfg.reddit_subreddits))
    cfg.hn_pages = int(sources.get("hn_pages", cfg.hn_pages))
    cfg.jobicy_tag = sources.get("jobicy_tag", cfg.jobicy_tag)
    cfg.adzuna_country = sources.get("adzuna_country", cfg.adzuna_country)
    cfg.adzuna_where = sources.get("adzuna_where", cfg.adzuna_where)
    cfg.adzuna_what = sources.get("adzuna_what", cfg.adzuna_what)
    cfg.craigslist_city = sources.get("craigslist_city", cfg.craigslist_city)
    cfg.craigslist_subarea = sources.get("craigslist_subarea", cfg.craigslist_subarea)
    cfg.craigslist_categories = list(
        sources.get("craigslist_categories", cfg.craigslist_categories)
    )
    cfg.craigslist_exclude = list(sources.get("craigslist_exclude", cfg.craigslist_exclude))
    cfg.craigslist_priority = list(sources.get("craigslist_priority", cfg.craigslist_priority))
    return cfg


EXAMPLE_CONFIG = """\
# job-finder configuration. Every key is optional; delete what you don't need.
# Location: run `job-finder init-config` to create this file in the right place.

[general]
output_dir = "~/Documents"      # where bare `-o name.md` files are saved
max_results = 50
timeout = 15                    # seconds per request
workers = 6                     # sources fetched in parallel

[search]
profile = "python"              # dev | python | security | ai | latam | gigs | your own below
exclude = ["unpaid", "commission only"]
# sources = ["remotive", "remoteok", "wwr", "hn-hiring", "hn-freelance"]

[sources]
reddit_subreddits = ["forhire", "PythonJobs"]
jobicy_tag = "python"
adzuna_where = "New York"       # needs ADZUNA_APP_ID and ADZUNA_APP_KEY env vars
craigslist_city = "newyork"     # craigslist is opt-in: --sources craigslist
craigslist_subarea = "que"      # mnh, brx, brk, que, stn

# Define your own profile. `include` = keywords you want, `boost` = nice-to-have,
# `penalize` = ranks lower, `exclude` = hide entirely.
[profiles.freelance-python]
include  = ["python", "django", "fastapi", "automation", "scraping", "scripting"]
boost    = ["freelance", "contract", "part-time", "junior", "entry level", "gig"]
penalize = ["senior", "staff", "principal", "10+ years"]
exclude  = ["unpaid"]
"""
