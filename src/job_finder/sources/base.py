"""Source registry. A source is a function (client, cfg) -> list[Job]."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from job_finder.config import Config
from job_finder.http import Client
from job_finder.models import Job

FetchFn = Callable[[Client, Config], list[Job]]


class SourceSkipped(Exception):  # noqa: N818 - control flow signal, not an error
    """Raised by a source that can't run (e.g. missing API key). Shown as 'skipped'."""


@dataclass(frozen=True)
class SourceSpec:
    name: str
    fn: FetchFn
    kind: str
    description: str
    default: bool


REGISTRY: dict[str, SourceSpec] = {}


def register(name: str, *, kind: str = "remote", description: str = "", default: bool = True):
    """Decorator: add a fetch function to the registry under `name`."""

    def wrap(fn: FetchFn) -> FetchFn:
        REGISTRY[name] = SourceSpec(name, fn, kind, description, default)
        return fn

    return wrap
