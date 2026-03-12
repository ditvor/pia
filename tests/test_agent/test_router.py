"""Tests for the message router."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pia.agent.router import (
    MessageRouter,
    _extract_keywords,
    _extract_ticket_id,
    _FALLBACK_MESSAGE,
)
from pia.graph.models import CodeMatch, YTIssue
from pia.llm.client import LLMError
from pia.sources.youtrack import YouTrackError


# ---------------------------------------------------------------------------
# _extract_ticket_id
# ---------------------------------------------------------------------------


def test_extract_ticket_id_simple():
    assert _extract_ticket_id("Look at PROJ-1234 please") == "PROJ-1234"


def test_extract_ticket_id_at_start():
    assert _extract_ticket_id("PROJ-4521 is broken") == "PROJ-4521"


def test_extract_ticket_id_standalone():
    assert _extract_ticket_id("PROJ-1") == "PROJ-1"


def test_extract_ticket_id_multi_letter_prefix():
    assert _extract_ticket_id("HD-892") == "HD-892"


def test_extract_ticket_id_alphanumeric_prefix():
    assert _extract_ticket_id("AB2-100") == "AB2-100"


def test_extract_ticket_id_returns_first_when_multiple():
    result = _extract_ticket_id("PROJ-1 and HD-2")
    assert result == "PROJ-1"


def test_extract_ticket_id_none_when_no_match():
    assert _extract_ticket_id("no ticket here") is None


def test_extract_ticket_id_no_lowercase_match():
    # Lowercase IDs must not match.
    assert _extract_ticket_id("proj-1234") is None


def test_extract_ticket_id_no_partial_word_match():
    # Embedded in a longer token — word boundary should prevent match.
    assert _extract_ticket_id("XPROJ-1234Y") is None


def test_extract_ticket_id_ignores_pure_digits():
    assert _extract_ticket_id("123-456") is None


# ---------------------------------------------------------------------------
# _extract_keywords
# ---------------------------------------------------------------------------


def test_extract_keywords_basic():
    kws = _extract_keywords("Export button broken")
    assert "export" in kws
    assert "button" in kws
    assert "broken" in kws


def test_extract_keywords_stop_words_filtered():
    kws = _extract_keywords("the button is broken")
    assert "the" not in kws
    assert "is" not in kws
    assert "button" in kws


def test_extract_keywords_short_tokens_filtered():
    kws = _extract_keywords("OK go do it")
    # "OK" → 2 chars, filtered; "go" → 2 chars, filtered
    assert "ok" not in kws
    assert "go" not in kws


def test_extract_keywords_includes_description():
    kws = _extract_keywords("Export", "CSV download fails")
    assert "export" in kws
    assert "download" in kws
    assert "fails" in kws


def test_extract_keywords_deduplicates():
    kws = _extract_keywords("login login login")
    assert kws.count("login") == 1


def test_extract_keywords_empty_inputs():
    assert _extract_keywords("") == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue(**kwargs) -> YTIssue:
    defaults = dict(
        id="2-1",
        id_readable="PROJ-1",
        summary="Fix export button",
        description="The CSV export fails",
        project="PROJ",
        state="Open",
        priority="Normal",
        assignee=None,
        reporter=None,
        created=0,
        updated=0,
        resolved=None,
        comments=[],
        tags=[],
        links=[],
    )
    defaults.update(kwargs)
    return YTIssue(**defaults)


def _make_settings():
    settings = MagicMock()
    settings.youtrack.url = "https://yt.example.com"
    settings.youtrack.token = "tok"
    settings.llm.provider = "anthropic"
    settings.llm.model = "claude-sonnet-4-6"
    settings.llm.api_key = "key"
    settings.llm.max_tokens = 4096
    settings.llm.temperature = 0.1
    settings.codebase.root = None
    settings.codebase.exclude_patterns = []
    return settings


# ---------------------------------------------------------------------------
# MessageRouter.route — no ticket ID
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_no_ticket_returns_fallback():
    router = MessageRouter(
        _make_settings(),
        yt_client=MagicMock(),
        llm_client=MagicMock(),
        assembler=MagicMock(),
    )
    result = await router.route("Hello, what can you do?")
    assert result == _FALLBACK_MESSAGE


# ---------------------------------------------------------------------------
# MessageRouter.route — ticket found, LLM succeeds
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_ticket_found_returns_llm_response():
    issue = _make_issue()
    yt = MagicMock()
    yt.get_issue = AsyncMock(return_value=issue)

    llm = MagicMock()
    llm.complete = AsyncMock(return_value="**Summary for PROJ-1**\n\nAll good.")

    assembler = MagicMock()
    ctx = MagicMock()
    ctx.prompt = "assembled prompt"
    assembler.assemble_ticket_enrichment.return_value = ctx

    router = MessageRouter(_make_settings(), yt_client=yt, llm_client=llm, assembler=assembler)

    with patch("pia.agent.router.scan_project", return_value=MagicMock()), \
         patch("pia.agent.router.find_relevant_files", return_value=[]):
        result = await router.route("Tell me about PROJ-1")

    assert result == "**Summary for PROJ-1**\n\nAll good."
    yt.get_issue.assert_awaited_once_with("PROJ-1")
    llm.complete.assert_awaited_once_with("assembled prompt")


# ---------------------------------------------------------------------------
# MessageRouter.route — YouTrack 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_ticket_not_found_404():
    yt = MagicMock()
    yt.get_issue = AsyncMock(side_effect=YouTrackError("not found", status_code=404))

    router = MessageRouter(
        _make_settings(),
        yt_client=yt,
        llm_client=MagicMock(),
        assembler=MagicMock(),
    )
    result = await router.route("PROJ-999")
    assert "PROJ-999" in result
    assert "not found" in result.lower()


# ---------------------------------------------------------------------------
# MessageRouter.route — YouTrack 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_ticket_auth_error_401():
    yt = MagicMock()
    yt.get_issue = AsyncMock(side_effect=YouTrackError("unauthorized", status_code=401))

    router = MessageRouter(
        _make_settings(),
        yt_client=yt,
        llm_client=MagicMock(),
        assembler=MagicMock(),
    )
    result = await router.route("PROJ-1")
    assert "authentication" in result.lower()


# ---------------------------------------------------------------------------
# MessageRouter.route — unexpected YouTrack error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_ticket_unexpected_error():
    yt = MagicMock()
    yt.get_issue = AsyncMock(side_effect=RuntimeError("connection reset"))

    router = MessageRouter(
        _make_settings(),
        yt_client=yt,
        llm_client=MagicMock(),
        assembler=MagicMock(),
    )
    result = await router.route("PROJ-1")
    assert "unexpected error" in result.lower()
    assert "PROJ-1" in result


# ---------------------------------------------------------------------------
# MessageRouter.route — LLM error falls back to raw ticket info
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_llm_error_returns_raw_ticket_info():
    issue = _make_issue(id_readable="PROJ-1", summary="Fix export", state="Open", priority="High")
    yt = MagicMock()
    yt.get_issue = AsyncMock(return_value=issue)

    llm = MagicMock()
    llm.complete = AsyncMock(side_effect=LLMError("rate limit"))

    assembler = MagicMock()
    ctx = MagicMock()
    ctx.prompt = "prompt"
    assembler.assemble_ticket_enrichment.return_value = ctx

    router = MessageRouter(_make_settings(), yt_client=yt, llm_client=llm, assembler=assembler)

    with patch("pia.agent.router.scan_project", return_value=MagicMock()), \
         patch("pia.agent.router.find_relevant_files", return_value=[]):
        result = await router.route("PROJ-1")

    assert "PROJ-1" in result
    assert "Fix export" in result
    assert "Open" in result
    assert "High" in result


# ---------------------------------------------------------------------------
# MessageRouter.route — codebase scan failure is non-fatal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_codebase_scan_failure_is_non_fatal():
    issue = _make_issue()
    yt = MagicMock()
    yt.get_issue = AsyncMock(return_value=issue)

    llm = MagicMock()
    llm.complete = AsyncMock(return_value="LLM says OK")

    assembler = MagicMock()
    ctx = MagicMock()
    ctx.prompt = "prompt"
    assembler.assemble_ticket_enrichment.return_value = ctx

    router = MessageRouter(_make_settings(), yt_client=yt, llm_client=llm, assembler=assembler)

    # _find_code blows up → should still get LLM response
    with patch.object(router, "_find_code", side_effect=OSError("disk error")):
        result = await router.route("PROJ-1")

    assert result == "LLM says OK"


# ---------------------------------------------------------------------------
# MessageRouter.route — code matches are passed to assembler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_code_matches_passed_to_assembler():
    issue = _make_issue()
    yt = MagicMock()
    yt.get_issue = AsyncMock(return_value=issue)

    llm = MagicMock()
    llm.complete = AsyncMock(return_value="ok")

    assembler = MagicMock()
    ctx = MagicMock()
    ctx.prompt = "prompt"
    assembler.assemble_ticket_enrichment.return_value = ctx

    match = CodeMatch(filepath="src/export.py", match_score=2, matched_keywords=["export"])
    router = MessageRouter(_make_settings(), yt_client=yt, llm_client=llm, assembler=assembler)

    with patch.object(router, "_find_code", return_value=[match]):
        await router.route("PROJ-1")

    assembler.assemble_ticket_enrichment.assert_called_once_with(issue, [match])
