"""One shared HTTP policy: retries with backoff, timeouts, an honest User-Agent."""

from __future__ import annotations

from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from job_finder import __version__
from job_finder.config import Config

USER_AGENT = f"job-finder/{__version__} (+https://github.com/Sam-did-this/Job_Finder)"


class Client:
    """Thin wrapper around requests.Session that always applies the timeout."""

    def __init__(self, timeout: int = 15, retries: int = 3) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        retry = Retry(
            total=retries,
            backoff_factor=1.0,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        response = self.session.get(url, **kwargs)
        response.raise_for_status()
        return response

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self.get(url, **kwargs).json()

    def get_text(self, url: str, **kwargs: Any) -> str:
        return self.get(url, **kwargs).text


def make_client(cfg: Config) -> Client:
    return Client(timeout=cfg.timeout, retries=cfg.retries)
