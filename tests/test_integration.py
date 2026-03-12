"""End-to-end integration test for the message-routing pipeline.

Scope
-----
This test exercises the full Phase 1 pipeline with real implementations for
every component *except* the two network boundaries:

  Real                              Mocked
  ─────────────────────────────     ─────────────────────────────────────
  YouTrackClient._parse_issue()     YouTrack HTTP  (httpx.MockTransport)
  _extract_keywords()               LLM completion (CapturingLLM stub)
  scan_project() / find_relevant_files()
  ContextAssembler.assemble_ticket_enrichment()
  MessageRouter.route()

The fixture codebase at tests/fixtures/sample_codebase/ mirrors a real
project; the fixture ticket PROJ-4521 is about "CSV Export to Reports".
Together they let us assert that the right code files surface in the prompt
sent to the LLM.
"""

from __future__ import annotations

import json
import pathlib
from typing import ClassVar
from unittest.mock import MagicMock

import httpx
import pytest

from pia.agent.router import MessageRouter
from pia.llm.context import ContextAssembler
from pia.sources.youtrack import YouTrackClient

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FIXTURES = pathlib.Path(__file__).parent / "fixtures"
_ISSUE_FIXTURE = _FIXTURES / "youtrack_responses" / "issue_sample.json"
_SAMPLE_CODEBASE = _FIXTURES / "sample_codebase"

# Deterministic LLM response — returned verbatim by the stub.
_LLM_RESPONSE = """\
## PROJ-4521 — Add CSV Export to Reports

**Business context**
Enterprise customers (Acme Corp and others) have requested CSV export from
the reporting module. Acme's renewal is in six weeks, making this time-sensitive.

**Technical context**
The API refactor (PROJ-4400) is merged, which unblocks this work.
The PDF export path (PROJ-4389) is already in production and can serve as a
reference implementation.

**Relevant code areas**
See `src/services/export/csv_export.py` for the starting point.

**Suggested next steps**
1. Spike the CSV serialisation layer in `csv_export.py`.
2. Wire the new endpoint in `src/api/routes/reports.py`.
3. Add tests in `tests/test_export.py`.
"""


# ---------------------------------------------------------------------------
# LLM stub — captures the prompt, returns a deterministic response
# ---------------------------------------------------------------------------


class _CapturingLLM:
    """Drop-in replacement for LLMClient that records every prompt it receives."""

    call_count: int
    captured_prompts: list[str]
    _RESPONSE: ClassVar[str] = _LLM_RESPONSE

    def __init__(self) -> None:
        self.call_count = 0
        self.captured_prompts = []

    async def complete(self, prompt: str) -> str:
        self.call_count += 1
        self.captured_prompts.append(prompt)
        return self._RESPONSE

    @property
    def last_prompt(self) -> str:
        return self.captured_prompts[-1]


# ---------------------------------------------------------------------------
# HTTP mock helpers
# ---------------------------------------------------------------------------


def _load_issue_fixture() -> dict:
    return json.loads(_ISSUE_FIXTURE.read_text(encoding="utf-8"))


def _make_yt_client(issue_data: dict) -> YouTrackClient:
    """Build a YouTrackClient backed by an httpx.MockTransport.

    Serves *issue_data* for any GET /api/issues/<id> request.
    Returns 404 for all other paths.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/issues/PROJ-4521"):
            return httpx.Response(200, json=issue_data)
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(
        base_url="https://test.youtrack.cloud",
        transport=transport,
    )
    return YouTrackClient(
        base_url="https://test.youtrack.cloud",
        token="test-token",
        http_client=http_client,
    )


# ---------------------------------------------------------------------------
# Settings stub — only codebase fields matter (clients are injected)
# ---------------------------------------------------------------------------


def _make_settings(codebase_root: str) -> MagicMock:
    settings = MagicMock()
    settings.codebase.root = codebase_root
    settings.codebase.exclude_patterns = ["__pycache__/", "*.pyc", "*.min.js"]
    return settings


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_route_proj_4521_end_to_end():
    """Full pipeline: mock YouTrack → real parser → real scanner → real
    assembler → LLM stub → markdown response."""

    issue_data = _load_issue_fixture()
    yt_client = _make_yt_client(issue_data)
    llm = _CapturingLLM()
    assembler = ContextAssembler()
    settings = _make_settings(str(_SAMPLE_CODEBASE))

    router = MessageRouter(
        settings,
        yt_client=yt_client,
        llm_client=llm,
        assembler=assembler,
    )

    response = await router.route("Tell me about PROJ-4521")

    # ------------------------------------------------------------------ #
    # 1. The router returns exactly what the LLM produced.
    # ------------------------------------------------------------------ #
    assert response == _LLM_RESPONSE

    # ------------------------------------------------------------------ #
    # 2. The LLM was called exactly once.
    # ------------------------------------------------------------------ #
    assert llm.call_count == 1

    # ------------------------------------------------------------------ #
    # 3. The prompt contains the ticket fields parsed from the fixture.
    # ------------------------------------------------------------------ #
    prompt = llm.last_prompt
    assert "PROJ-4521" in prompt
    assert "Add CSV Export to Reports" in prompt
    assert "Critical" in prompt          # priority
    assert "Open" in prompt              # state
    assert "John Doe" in prompt          # assignee
    assert "Sarah PM" in prompt          # reporter / comment author

    # ------------------------------------------------------------------ #
    # 4. The prompt includes the ticket description and comments.
    # ------------------------------------------------------------------ #
    assert "Enterprise customers" in prompt          # description text
    assert "Acme Corp" in prompt                     # comment text
    assert "API refactor" in prompt                  # comment text

    # ------------------------------------------------------------------ #
    # 5. The prompt includes all four linked issues.
    # ------------------------------------------------------------------ #
    assert "PROJ-4400" in prompt   # Depend INWARD  — API refactor
    assert "PROJ-4389" in prompt   # Relate OUTWARD — PDF Export
    assert "HD-892" in prompt      # Relate OUTWARD — helpdesk
    assert "HD-901" in prompt      # Relate OUTWARD — helpdesk

    # ------------------------------------------------------------------ #
    # 6. The codebase scanner found export-related files.
    #    "csv" and "export" are high-signal keywords from the ticket text;
    #    both appear as substrings in the fixture codebase paths.
    # ------------------------------------------------------------------ #
    assert "csv_export" in prompt, (
        "Expected csv_export.py to appear in code-areas section of prompt"
    )
    assert "services/export" in prompt, (
        "Expected export service directory to appear in code-areas section"
    )

    # ------------------------------------------------------------------ #
    # 7. Excluded artefacts do not appear in the code-areas section.
    #    The fixture codebase contains __pycache__/ and .pyc files;
    #    they must be filtered out before keyword matching.
    # ------------------------------------------------------------------ #
    assert "__pycache__" not in prompt
    assert ".pyc" not in prompt
    assert ".min.js" not in prompt


@pytest.mark.asyncio
async def test_route_proj_4521_reports_route_in_prompt():
    """The reports API route file surfaces because 'report' is a keyword."""
    issue_data = _load_issue_fixture()
    yt_client = _make_yt_client(issue_data)
    llm = _CapturingLLM()
    settings = _make_settings(str(_SAMPLE_CODEBASE))

    router = MessageRouter(
        settings,
        yt_client=yt_client,
        llm_client=llm,
        assembler=ContextAssembler(),
    )

    await router.route("Tell me about PROJ-4521")

    # "report" is a substring of both the ticket text and the file path
    # src/api/routes/reports.py — it must appear in the code-areas section.
    assert "reports" in llm.last_prompt


@pytest.mark.asyncio
async def test_route_proj_4521_linked_relationship_labels_in_prompt():
    """Link direction and type labels are serialised into the prompt."""
    issue_data = _load_issue_fixture()
    yt_client = _make_yt_client(issue_data)
    llm = _CapturingLLM()
    settings = _make_settings(str(_SAMPLE_CODEBASE))

    router = MessageRouter(
        settings,
        yt_client=yt_client,
        llm_client=llm,
        assembler=ContextAssembler(),
    )

    await router.route("Tell me about PROJ-4521")

    prompt = llm.last_prompt
    # Relationship labels produced by ContextAssembler._linked_to_list()
    assert "Depend" in prompt
    assert "INWARD" in prompt
    assert "Relate" in prompt
    assert "OUTWARD" in prompt


@pytest.mark.asyncio
async def test_route_ignores_unknown_message_without_hitting_youtrack():
    """Non-ticket messages must return the fallback without any HTTP call."""
    call_log: list[httpx.Request] = []

    def spy_handler(request: httpx.Request) -> httpx.Response:
        call_log.append(request)
        return httpx.Response(500)  # should never be reached

    transport = httpx.MockTransport(spy_handler)
    http_client = httpx.AsyncClient(
        base_url="https://test.youtrack.cloud",
        transport=transport,
    )
    yt_client = YouTrackClient(
        base_url="https://test.youtrack.cloud",
        token="tok",
        http_client=http_client,
    )

    llm = _CapturingLLM()
    settings = _make_settings(str(_SAMPLE_CODEBASE))

    router = MessageRouter(
        settings,
        yt_client=yt_client,
        llm_client=llm,
        assembler=ContextAssembler(),
    )

    response = await router.route("What can you do?")

    assert "PIA" in response              # fallback message
    assert llm.call_count == 0           # LLM never touched
    assert len(call_log) == 0            # YouTrack never touched


@pytest.mark.asyncio
async def test_route_youtrack_404_returns_friendly_message():
    """A 404 from YouTrack produces a human-readable error, not an exception."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "Not Found"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(
        base_url="https://test.youtrack.cloud",
        transport=transport,
    )
    yt_client = YouTrackClient(
        base_url="https://test.youtrack.cloud",
        token="tok",
        http_client=http_client,
    )

    llm = _CapturingLLM()
    settings = _make_settings(str(_SAMPLE_CODEBASE))

    router = MessageRouter(
        settings,
        yt_client=yt_client,
        llm_client=llm,
        assembler=ContextAssembler(),
    )

    response = await router.route("Tell me about PROJ-9999")

    assert "PROJ-9999" in response
    assert "not found" in response.lower()
    assert llm.call_count == 0
