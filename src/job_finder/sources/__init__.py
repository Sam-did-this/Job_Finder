"""Importing this package registers every built-in source."""

from job_finder.sources import boards, community, demo, local  # noqa: F401
from job_finder.sources.base import REGISTRY, SourceSkipped, SourceSpec, register

__all__ = ["REGISTRY", "SourceSkipped", "SourceSpec", "register"]
