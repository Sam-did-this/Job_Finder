"""Orchestration: run sources in parallel and isolate their failures."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from xml.etree.ElementTree import ParseError  # noqa: S405 - only the exception type

import requests
from defusedxml import DefusedXmlException

from job_finder.config import Config
from job_finder.http import Client, make_client
from job_finder.models import SourceResult
from job_finder.sources import REGISTRY, SourceSkipped

log = logging.getLogger(__name__)


def resolve_sources(requested: list[str] | None, cfg: Config) -> list[str]:
    """Turn --sources / config into a validated list of registered source names."""
    if requested == ["all"]:
        return list(REGISTRY)
    names = requested or cfg.sources or [n for n, s in REGISTRY.items() if s.default]
    unknown = [n for n in names if n not in REGISTRY]
    if unknown:
        raise ValueError(
            f"unknown source(s): {', '.join(unknown)} (available: {', '.join(REGISTRY)})"
        )
    return names


def describe_error(exc: Exception) -> str:
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, requests.Timeout):
        return "timed out"
    if isinstance(exc, requests.ConnectionError):
        return "connection failed"
    if isinstance(exc, ParseError | DefusedXmlException):
        return "unreadable feed (site layout may have changed)"
    if isinstance(exc, ValueError | KeyError | TypeError | AttributeError):
        return f"unexpected response format ({type(exc).__name__}: {exc})"
    return f"{type(exc).__name__}: {exc}"


def collect(
    names: list[str],
    cfg: Config,
    client_factory: Callable[[Config], Client] = make_client,
) -> list[SourceResult]:
    """Fetch every named source concurrently. One failing source never stops the rest."""

    def work(name: str) -> SourceResult:
        started = time.monotonic()
        try:
            jobs = REGISTRY[name].fn(client_factory(cfg), cfg)
            return SourceResult(name, jobs, elapsed=time.monotonic() - started)
        except SourceSkipped as exc:
            return SourceResult(name, skipped=str(exc))
        except Exception as exc:  # noqa: BLE001 - boundary: report, don't crash the run
            log.debug("source %s failed", name, exc_info=True)
            return SourceResult(name, error=describe_error(exc), elapsed=time.monotonic() - started)

    with ThreadPoolExecutor(max_workers=max(1, min(cfg.workers, len(names) or 1))) as pool:
        return list(pool.map(work, names))
