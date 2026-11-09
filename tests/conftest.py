from __future__ import annotations

import json
from pathlib import Path

import pytest
import requests

from job_finder.config import Config

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeResponse:
    def __init__(self, text: str, status: int = 200) -> None:
        self.text = text
        self.status_code = status

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)


class FakeClient:
    """Stands in for job_finder.http.Client. `routes` maps a URL substring to a fixture file."""

    def __init__(self, routes: dict[str, str]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def _text(self, url: str) -> str:
        self.calls.append(url)
        for needle, name in self.routes.items():
            if needle in url:
                return fixture_text(name)
        raise AssertionError(f"unexpected URL in test: {url}")

    def get_text(self, url: str, **kwargs) -> str:
        return self._text(url)

    def get_json(self, url: str, **kwargs):
        return json.loads(self._text(url))

    def get(self, url: str, **kwargs):
        return FakeResponse(self._text(url))


@pytest.fixture
def cfg(tmp_path) -> Config:
    return Config(
        output_dir=tmp_path / "out",
        history_db=tmp_path / "history.sqlite3",
        delay=0,
        workers=2,
    )
