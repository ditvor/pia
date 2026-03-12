"""YouTrack REST API client."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from pia.graph.models import (
    YTComment,
    YTIssue,
    YTIssueLink,
    YTLinkedIssue,
    YTSprint,
    YTSprintIssue,
    YTUser,
)

logger = logging.getLogger(__name__)

# Fields requested for a full issue fetch (get_issue).
_ISSUE_FIELDS = (
    "id,idReadable,summary,description,project(shortName),"
    "priority(name),state(name),"
    "assignee(login,fullName),reporter(login,fullName),"
    "created,updated,resolved,"
    "comments(id,text,author(login,fullName),created),"
    "tags(name),"
    "links(direction,linkType(name),issues(idReadable,summary,state(name)))"
)

# Lighter field set returned by search_issues (no comments, no links).
_SEARCH_FIELDS = (
    "id,idReadable,summary,state(name),priority(name),"
    "assignee(login,fullName),created,updated"
)

# Fields for a sprint fetch.
_SPRINT_FIELDS = "id,name,issues(id,idReadable,summary,state(name),estimation(value))"


# ---------------------------------------------------------------------------
# Error type
# ---------------------------------------------------------------------------


class YouTrackError(Exception):
    """Raised when the YouTrack API returns an unexpected response.

    Attributes:
        status_code: HTTP status code, or None for network-level failures.
    """

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_user(data: dict[str, Any] | None) -> YTUser | None:
    """Parse a YouTrack user object, returning None if absent."""
    if not data:
        return None
    return YTUser(login=data["login"], full_name=data.get("fullName", ""))


def _parse_issue(data: dict[str, Any]) -> YTIssue:
    """Parse a YouTrack issue response dict into a YTIssue dataclass."""
    comments = [
        YTComment(
            id=c["id"],
            text=c.get("text", ""),
            author=_parse_user(c.get("author")) or YTUser(login="unknown", full_name=""),
            created=c["created"],
        )
        for c in (data.get("comments") or [])
    ]

    tags = [t["name"] for t in (data.get("tags") or [])]

    links = [
        YTIssueLink(
            direction=lnk["direction"],
            link_type=lnk["linkType"]["name"],
            issues=[
                YTLinkedIssue(
                    id_readable=i["idReadable"],
                    summary=i["summary"],
                    state=(i.get("state") or {}).get("name"),
                )
                for i in (lnk.get("issues") or [])
            ],
        )
        for lnk in (data.get("links") or [])
    ]

    return YTIssue(
        id=data["id"],
        id_readable=data["idReadable"],
        summary=data["summary"],
        description=data.get("description"),
        project=(data.get("project") or {}).get("shortName", ""),
        priority=(data.get("priority") or {}).get("name"),
        state=(data.get("state") or {}).get("name"),
        assignee=_parse_user(data.get("assignee")),
        reporter=_parse_user(data.get("reporter")),
        created=data["created"],
        updated=data["updated"],
        resolved=data.get("resolved"),
        comments=comments,
        tags=tags,
        links=links,
    )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class YouTrackClient:
    """Async client for the YouTrack REST API.

    Args:
        base_url: Base URL of the YouTrack instance
            (e.g. ``https://example.youtrack.cloud``).
        token: Permanent token for Bearer authentication.
        http_client: Optional pre-built ``httpx.AsyncClient``.
            When provided the caller is responsible for its lifecycle.
            When omitted the client is created (and closed) internally.
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """Issue a GET request and return parsed JSON.

        Args:
            path: URL path relative to the base URL.
            params: Optional query parameters.

        Raises:
            YouTrackError: On non-2xx responses or network failures.
        """
        try:
            response = await self._client.get(path, params=params)
        except httpx.RequestError as exc:
            raise YouTrackError(f"Network error contacting YouTrack: {exc}") from exc

        if response.status_code == 401:
            raise YouTrackError(
                "YouTrack authentication failed — check your token.",
                status_code=401,
            )
        if response.status_code == 404:
            raise YouTrackError(
                f"YouTrack resource not found: {path}",
                status_code=404,
            )
        if not response.is_success:
            raise YouTrackError(
                f"YouTrack returned HTTP {response.status_code}: {response.text[:200]}",
                status_code=response.status_code,
            )

        return response.json()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_issue(self, issue_id: str) -> YTIssue:
        """Fetch a single issue by its readable ID.

        Args:
            issue_id: The issue's readable ID (e.g. ``PROJ-4521``).

        Returns:
            A fully-populated ``YTIssue``.

        Raises:
            YouTrackError: If the issue cannot be retrieved.
        """
        logger.debug("Fetching issue %s", issue_id)
        data = await self._get(
            f"/api/issues/{issue_id}",
            params={"fields": _ISSUE_FIELDS},
        )
        return _parse_issue(data)

    async def search_issues(self, query: str, max_results: int = 20) -> list[YTIssue]:
        """Search issues using YouTrack query syntax.

        Args:
            query: YouTrack query string
                (e.g. ``"project: PROJ state: Open priority: Critical"``).
            max_results: Maximum number of results to return.

        Returns:
            List of matching ``YTIssue`` objects.
            Note: only the fields in ``_SEARCH_FIELDS`` are populated;
            ``comments``, ``links``, ``tags``, and ``description`` will be empty.

        Raises:
            YouTrackError: If the search request fails.
        """
        logger.debug("Searching issues: %s", query)
        data = await self._get(
            "/api/issues",
            params={"query": query, "fields": _SEARCH_FIELDS, "$top": max_results},
        )
        return [_parse_issue(item) for item in data]

    async def get_sprint(self, agile_id: str, sprint_id: str) -> YTSprint:
        """Fetch a sprint and its issues.

        Args:
            agile_id: The agile board ID.
            sprint_id: The sprint ID.

        Returns:
            A ``YTSprint`` dataclass with issues populated.

        Raises:
            YouTrackError: If the sprint cannot be retrieved.
        """
        logger.debug("Fetching sprint %s/%s", agile_id, sprint_id)
        data = await self._get(
            f"/api/agiles/{agile_id}/sprints/{sprint_id}",
            params={"fields": _SPRINT_FIELDS},
        )
        issues = [
            YTSprintIssue(
                id_readable=i["idReadable"],
                summary=i["summary"],
                state=(i.get("state") or {}).get("name"),
                estimation=(i.get("estimation") or {}).get("value"),
            )
            for i in (data.get("issues") or [])
        ]
        return YTSprint(id=data["id"], name=data["name"], issues=issues)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """Close the underlying HTTP client if it was created internally."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> YouTrackClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
