#!/usr/bin/env python3
"""Shared infrastructure for the Jira/GitHub collectors.

This module isolates the impure edges of the plugin — environment/auth, HTTP
transport with pagination and retry, and date/quarter parsing — so the domain
modules (workstream_map, load_context, metrics, render) stay pure and trivially
testable. The HTTP transport is injected, which keeps unit tests hermetic: no
live network, no third-party mocking library.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Callable, Dict, List, Optional

_DEFAULT_BASE_URL = "https://redhat.atlassian.net"
_SEARCH_PATH = "/rest/api/3/search/jql"
_DEFAULT_PAGE_SIZE = 100
_DEFAULT_MAX_RETRIES = 2
_QUARTER_PATTERN = re.compile(r"^(?P<year>\d{4})Q(?P<quarter>[1-4])$")
_QUARTER_MONTHS = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}
_LAST_DAY_OF_MONTH = {1: 31, 3: 31, 6: 30, 9: 30, 10: 31, 12: 31}


class CollectorError(Exception):
    """A collector could not complete because of an external failure."""


class JiraAuthError(CollectorError):
    """Jira credentials are missing or were rejected."""


@dataclass(frozen=True)
class JiraConfig:
    """Everything needed to talk to a Jira instance."""

    base_url: str
    username: str
    api_token: str


@dataclass(frozen=True)
class HttpResponse:
    """A minimal HTTP response the transport layer returns.

    Kept deliberately tiny so tests can construct one without ``requests``.
    """

    status_code: int
    body: str

    def json(self) -> dict:
        """Parse the body as JSON, raising ``ValueError`` on malformed input."""
        return json.loads(self.body)


# A transport takes (method, path, json_body) and returns an HttpResponse.
Transport = Callable[[str, str, Optional[dict]], HttpResponse]


def jira_config_from_env(env: Dict[str, str]) -> JiraConfig:
    """Build a ``JiraConfig`` from environment variables.

    Raises ``JiraAuthError`` (before any network call) when the required
    credentials are absent.
    """
    username = env.get("JIRA_USERNAME")
    api_token = env.get("JIRA_API_TOKEN")
    if not username or not api_token:
        raise JiraAuthError(
            "JIRA_USERNAME and JIRA_API_TOKEN must be set to reach Jira REST"
        )
    base_url = env.get("JIRA_BASE_URL", _DEFAULT_BASE_URL).rstrip("/")
    return JiraConfig(base_url=base_url, username=username, api_token=api_token)


class JiraClient:
    """Talks to Jira Cloud REST v3 over an injected transport.

    Pagination uses ``nextPageToken`` (this instance does not use ``startAt``).
    Transient 5xx responses are retried; auth failures raise immediately.
    """

    def __init__(
        self,
        config: JiraConfig,
        transport: Transport,
        max_retries: int = _DEFAULT_MAX_RETRIES,
    ) -> None:
        self._config = config
        self._transport = transport
        self._max_retries = max_retries

    @property
    def base_url(self) -> str:
        return self._config.base_url

    def search(
        self, jql: str, fields: List[str], page_size: int = _DEFAULT_PAGE_SIZE
    ) -> List[dict]:
        """Return every issue matching ``jql``, following pagination to the end."""
        issues: List[dict] = []
        next_page_token: Optional[str] = None
        while True:
            payload = {"jql": jql, "fields": fields, "maxResults": page_size}
            if next_page_token:
                payload["nextPageToken"] = next_page_token
            page = self._request_json("POST", _SEARCH_PATH, payload)
            issues.extend(page.get("issues", []))
            next_page_token = page.get("nextPageToken")
            if page.get("isLast", not next_page_token) or not next_page_token:
                return issues

    def get_issue(self, issue_key: str, fields: List[str]) -> dict:
        """Fetch a single issue's requested fields."""
        path = f"/rest/api/3/issue/{issue_key}?fields={','.join(fields)}"
        return self._request_json("GET", path, None)

    def _request_json(self, method: str, path: str, body: Optional[dict]) -> dict:
        response = self._request_with_retry(method, path, body)
        try:
            return response.json()
        except ValueError as error:
            raise CollectorError(f"malformed JSON from Jira {path}: {error}") from error

    def _request_with_retry(
        self, method: str, path: str, body: Optional[dict]
    ) -> HttpResponse:
        attempts = 0
        while True:
            response = self._transport(method, path, body)
            if response.status_code in (401, 403):
                raise JiraAuthError(f"Jira rejected credentials ({response.status_code})")
            if response.status_code >= 500:
                attempts += 1
                if attempts > self._max_retries:
                    raise CollectorError(
                        f"Jira server error {response.status_code} after "
                        f"{self._max_retries} retries"
                    )
                continue
            if response.status_code != 200:
                raise CollectorError(
                    f"Jira request to {path} failed with {response.status_code}"
                )
            return response


@dataclass(frozen=True)
class Window:
    """An inclusive date range for a reporting period."""

    start: date
    end: date

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def contains_timestamp(self, timestamp: str) -> bool:
        """Return whether a Jira ISO timestamp falls within the window."""
        return self.contains(_date_from_timestamp(timestamp))


def parse_date(text: str) -> date:
    """Parse an ISO ``YYYY-MM-DD`` date string."""
    return date.fromisoformat(text)


def _date_from_timestamp(timestamp: str) -> date:
    """Parse the date portion of a Jira timestamp (``2026-05-01T12:00:...``)."""
    return date.fromisoformat(timestamp[:10])


def quarter_to_window(quarter: str) -> Window:
    """Convert a ``YYYYQn`` label into its inclusive calendar-quarter window.

    Raises ``ValueError`` for anything that is not a well-formed quarter.
    """
    match = _QUARTER_PATTERN.match(quarter)
    if not match:
        raise ValueError(f"not a valid quarter label: {quarter!r} (expected e.g. 2026Q2)")
    year = int(match.group("year"))
    first_month, last_month = _QUARTER_MONTHS[int(match.group("quarter"))]
    return Window(
        start=date(year, first_month, 1),
        end=date(year, last_month, _LAST_DAY_OF_MONTH[last_month]),
    )


def resolve_window(
    quarter: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Window:
    """Resolve a reporting window from a quarter label or an explicit date pair.

    Raises ``ValueError`` when neither a quarter nor a complete date range is
    supplied.
    """
    if quarter:
        return quarter_to_window(quarter)
    if from_date and to_date:
        return Window(parse_date(from_date), parse_date(to_date))
    raise ValueError("provide a quarter, or both a start and end date")


def build_default_transport(config: JiraConfig) -> Transport:
    """Build the production HTTP transport backed by ``requests``.

    ``requests`` is imported lazily so unit tests, which inject a transport,
    never require it.
    """
    import requests
    from requests.auth import HTTPBasicAuth

    auth = HTTPBasicAuth(config.username, config.api_token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    def transport(method: str, path: str, body: Optional[dict]) -> HttpResponse:
        response = requests.request(
            method,
            f"{config.base_url}{path}",
            json=body,
            auth=auth,
            headers=headers,
            timeout=60,
        )
        return HttpResponse(response.status_code, response.text)

    return transport
