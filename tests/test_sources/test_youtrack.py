"""Tests for the YouTrack REST API client."""

from __future__ import annotations

import json
import pathlib
from typing import Callable
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from pia.graph.models import YTIssue, YTSprint, YTUser
from pia.sources.youtrack import YouTrackClient, YouTrackError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURES_DIR = pathlib.Path(__file__).parent.parent / "fixtures" / "youtrack_responses"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _mock_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    """Return an AsyncClient that routes all requests through *handler*."""
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(base_url="https://test.youtrack.cloud", transport=transport)


def _json_response(data: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=data)


# ---------------------------------------------------------------------------
# get_issue — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_issue_returns_populated_dataclass():
    raw = _load_fixture("issue_sample.json")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/issues/PROJ-4521"
        assert "fields" in dict(request.url.params)
        return _json_response(raw)

    async with YouTrackClient("https://test.youtrack.cloud", "tok", _mock_client(handler)) as yt:
        issue = await yt.get_issue("PROJ-4521")

    assert isinstance(issue, YTIssue)
    assert issue.id_readable == "PROJ-4521"
    assert issue.summary == "Add CSV Export to Reports"
    assert issue.project == "PROJ"
    assert issue.priority == "Critical"
    assert issue.state == "Open"
    assert issue.resolved is None


@pytest.mark.asyncio
async def test_get_issue_parses_assignee_and_reporter():
    raw = _load_fixture("issue_sample.json")

    async with YouTrackClient("...", "tok", _mock_client(lambda _: _json_response(raw))) as yt:
        issue = await yt.get_issue("PROJ-4521")

    assert issue.assignee == YTUser(login="john.doe", full_name="John Doe")
    assert issue.reporter == YTUser(login="sarah.pm", full_name="Sarah PM")


@pytest.mark.asyncio
async def test_get_issue_parses_comments():
    raw = _load_fixture("issue_sample.json")

    async with YouTrackClient("...", "tok", _mock_client(lambda _: _json_response(raw))) as yt:
        issue = await yt.get_issue("PROJ-4521")

    assert len(issue.comments) == 3
    first = issue.comments[0]
    assert first.id == "comment-1"
    assert "Acme Corp" in first.text
    assert first.author.login == "sarah.pm"
    assert first.created == 1700000000000


@pytest.mark.asyncio
async def test_get_issue_parses_tags():
    raw = _load_fixture("issue_sample.json")

    async with YouTrackClient("...", "tok", _mock_client(lambda _: _json_response(raw))) as yt:
        issue = await yt.get_issue("PROJ-4521")

    assert set(issue.tags) == {"enterprise", "export", "sprint-14"}


@pytest.mark.asyncio
async def test_get_issue_parses_links():
    raw = _load_fixture("issue_sample.json")

    async with YouTrackClient("...", "tok", _mock_client(lambda _: _json_response(raw))) as yt:
        issue = await yt.get_issue("PROJ-4521")

    assert len(issue.links) == 2

    depend_link = next(lnk for lnk in issue.links if lnk.link_type == "Depend")
    assert depend_link.direction == "INWARD"
    assert len(depend_link.issues) == 1
    assert depend_link.issues[0].id_readable == "PROJ-4400"
    assert depend_link.issues[0].state == "Fixed"

    relate_link = next(lnk for lnk in issue.links if lnk.link_type == "Relate")
    relate_ids = [i.id_readable for i in relate_link.issues]
    assert "HD-892" in relate_ids
    assert "PROJ-4389" in relate_ids


# ---------------------------------------------------------------------------
# get_issue — optional / null fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_issue_handles_null_optional_fields():
    """An issue with no assignee, no description, no tags, no comments, no links."""
    minimal = {
        "id": "2-1",
        "idReadable": "PROJ-1",
        "summary": "Minimal issue",
        "description": None,
        "project": {"shortName": "PROJ"},
        "priority": None,
        "state": None,
        "assignee": None,
        "reporter": None,
        "created": 1700000000000,
        "updated": 1700000000000,
        "resolved": None,
        "comments": [],
        "tags": [],
        "links": [],
    }

    async with YouTrackClient("...", "tok", _mock_client(lambda _: _json_response(minimal))) as yt:
        issue = await yt.get_issue("PROJ-1")

    assert issue.assignee is None
    assert issue.reporter is None
    assert issue.description is None
    assert issue.priority is None
    assert issue.state is None
    assert issue.comments == []
    assert issue.tags == []
    assert issue.links == []


@pytest.mark.asyncio
async def test_get_issue_handles_missing_keys_gracefully():
    """YouTrack sometimes omits keys entirely instead of returning null."""
    sparse = {
        "id": "2-2",
        "idReadable": "PROJ-2",
        "summary": "Sparse issue",
        "created": 1700000000000,
        "updated": 1700000000000,
    }

    async with YouTrackClient("...", "tok", _mock_client(lambda _: _json_response(sparse))) as yt:
        issue = await yt.get_issue("PROJ-2")

    assert issue.description is None
    assert issue.assignee is None
    assert issue.comments == []
    assert issue.tags == []
    assert issue.links == []


# ---------------------------------------------------------------------------
# get_issue — error handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_issue_raises_on_401():
    handler = lambda _: httpx.Response(401, text="Unauthorized")

    async with YouTrackClient("...", "bad-token", _mock_client(handler)) as yt:
        with pytest.raises(YouTrackError) as exc_info:
            await yt.get_issue("PROJ-1")

    assert exc_info.value.status_code == 401
    assert "authentication" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_get_issue_raises_on_404():
    handler = lambda _: httpx.Response(404, text="Not Found")

    async with YouTrackClient("...", "tok", _mock_client(handler)) as yt:
        with pytest.raises(YouTrackError) as exc_info:
            await yt.get_issue("PROJ-9999")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_issue_raises_on_500():
    handler = lambda _: httpx.Response(500, text="Internal Server Error")

    async with YouTrackClient("...", "tok", _mock_client(handler)) as yt:
        with pytest.raises(YouTrackError) as exc_info:
            await yt.get_issue("PROJ-1")

    assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_get_issue_raises_on_network_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    async with YouTrackClient("...", "tok", _mock_client(handler)) as yt:
        with pytest.raises(YouTrackError) as exc_info:
            await yt.get_issue("PROJ-1")

    assert exc_info.value.status_code is None
    assert "Network error" in str(exc_info.value)


# ---------------------------------------------------------------------------
# search_issues
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_issues_returns_list():
    results = [
        {
            "id": "2-4521",
            "idReadable": "PROJ-4521",
            "summary": "Add CSV Export to Reports",
            "state": {"name": "Open"},
            "priority": {"name": "Critical"},
            "assignee": {"login": "john.doe", "fullName": "John Doe"},
            "created": 1700000000000,
            "updated": 1700518400000,
        },
        {
            "id": "2-4522",
            "idReadable": "PROJ-4522",
            "summary": "Fix login redirect loop",
            "state": {"name": "In Progress"},
            "priority": {"name": "Major"},
            "assignee": None,
            "created": 1700100000000,
            "updated": 1700400000000,
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/issues"
        assert request.url.params["query"] == "project: PROJ state: Open"
        return _json_response(results)

    async with YouTrackClient("...", "tok", _mock_client(handler)) as yt:
        issues = await yt.search_issues("project: PROJ state: Open")

    assert len(issues) == 2
    assert issues[0].id_readable == "PROJ-4521"
    assert issues[0].priority == "Critical"
    assert issues[1].assignee is None


@pytest.mark.asyncio
async def test_search_issues_returns_empty_list():
    async with YouTrackClient("...", "tok", _mock_client(lambda _: _json_response([]))) as yt:
        issues = await yt.search_issues("project: PROJ state: Open")

    assert issues == []


@pytest.mark.asyncio
async def test_search_issues_propagates_error():
    async with YouTrackClient("...", "tok", _mock_client(lambda _: httpx.Response(401))) as yt:
        with pytest.raises(YouTrackError):
            await yt.search_issues("project: PROJ")


# ---------------------------------------------------------------------------
# get_sprint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sprint_returns_populated_dataclass():
    sprint_data = {
        "id": "sprint-14",
        "name": "Sprint 14",
        "issues": [
            {
                "id": "2-4521",
                "idReadable": "PROJ-4521",
                "summary": "Add CSV Export to Reports",
                "state": {"name": "Open"},
                "estimation": {"value": 5},
            },
            {
                "id": "2-4522",
                "idReadable": "PROJ-4522",
                "summary": "Fix login redirect loop",
                "state": {"name": "In Progress"},
                "estimation": None,
            },
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/agiles/board-1/sprints/sprint-14"
        return _json_response(sprint_data)

    async with YouTrackClient("...", "tok", _mock_client(handler)) as yt:
        sprint = await yt.get_sprint("board-1", "sprint-14")

    assert isinstance(sprint, YTSprint)
    assert sprint.id == "sprint-14"
    assert sprint.name == "Sprint 14"
    assert len(sprint.issues) == 2

    first = sprint.issues[0]
    assert first.id_readable == "PROJ-4521"
    assert first.state == "Open"
    assert first.estimation == 5

    second = sprint.issues[1]
    assert second.estimation is None


@pytest.mark.asyncio
async def test_get_sprint_handles_empty_issues():
    sprint_data = {"id": "sprint-15", "name": "Sprint 15", "issues": []}

    async with YouTrackClient("...", "tok", _mock_client(lambda _: _json_response(sprint_data))) as yt:
        sprint = await yt.get_sprint("board-1", "sprint-15")

    assert sprint.issues == []


@pytest.mark.asyncio
async def test_get_sprint_raises_on_404():
    async with YouTrackClient("...", "tok", _mock_client(lambda _: httpx.Response(404))) as yt:
        with pytest.raises(YouTrackError) as exc_info:
            await yt.get_sprint("board-1", "nonexistent")

    assert exc_info.value.status_code == 404
