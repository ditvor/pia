"""Tests for the LLM layer: ContextAssembler and LLMClient."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from pia.graph.models import (
    CodeMatch,
    YTComment,
    YTIssue,
    YTIssueLink,
    YTLinkedIssue,
    YTUser,
)
from pia.llm.client import LLMClient, LLMError
from pia.llm.context import AssembledContext, ContextAssembler
from pia.llm.prompts import TICKET_ENRICHMENT_PROMPT

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_issue(
    *,
    description: str | None = "Enterprise customers want CSV export.",
    comments: list[YTComment] | None = None,
    links: list[YTIssueLink] | None = None,
    tags: list[str] | None = None,
) -> YTIssue:
    """Build a minimal but realistic YTIssue for testing."""
    if comments is None:
        comments = [
            YTComment(
                id="c1",
                text="Acme Corp asked for this in their last call.",
                author=YTUser(login="sarah.pm", full_name="Sarah PM"),
                created=1700000000000,
            ),
            YTComment(
                id="c2",
                text="Should be straightforward now that PROJ-4400 is merged.",
                author=YTUser(login="john.doe", full_name="John Doe"),
                created=1700259200000,
            ),
        ]
    if links is None:
        links = [
            YTIssueLink(
                direction="INWARD",
                link_type="Depend",
                issues=[
                    YTLinkedIssue(
                        id_readable="PROJ-4400",
                        summary="API refactor — consolidate report endpoints",
                        state="Fixed",
                    )
                ],
            ),
            YTIssueLink(
                direction="OUTWARD",
                link_type="Relate",
                issues=[
                    YTLinkedIssue(
                        id_readable="HD-892",
                        summary="Customer request: CSV download from reports",
                        state="Open",
                    ),
                ],
            ),
        ]
    return YTIssue(
        id="2-4521",
        id_readable="PROJ-4521",
        summary="Add CSV Export to Reports",
        description=description,
        project="PROJ",
        priority="Critical",
        state="Open",
        assignee=YTUser(login="john.doe", full_name="John Doe"),
        reporter=YTUser(login="sarah.pm", full_name="Sarah PM"),
        created=1700000000000,
        updated=1700518400000,
        resolved=None,
        comments=comments,
        tags=tags or ["enterprise", "export"],
        links=links,
    )


def _make_matches() -> list[CodeMatch]:
    return [
        CodeMatch(
            filepath="src/services/export/csv_export.py",
            match_score=2,
            matched_keywords=["csv", "export"],
        ),
        CodeMatch(
            filepath="src/services/export/controller.py",
            match_score=1,
            matched_keywords=["export"],
        ),
        CodeMatch(
            filepath="src/api/routes/reports.py",
            match_score=1,
            matched_keywords=["report"],
        ),
    ]


# ---------------------------------------------------------------------------
# ContextAssembler — prompt content
# ---------------------------------------------------------------------------


def test_assembled_prompt_contains_ticket_id():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert "PROJ-4521" in ctx.prompt


def test_assembled_prompt_contains_summary():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert "Add CSV Export to Reports" in ctx.prompt


def test_assembled_prompt_contains_state_and_priority():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert "Open" in ctx.prompt
    assert "Critical" in ctx.prompt


def test_assembled_prompt_contains_assignee():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert "John Doe" in ctx.prompt


def test_assembled_prompt_contains_description():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert "Enterprise customers want CSV export" in ctx.prompt


def test_assembled_prompt_contains_comment_text():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert "Acme Corp" in ctx.prompt


def test_assembled_prompt_contains_linked_issue_ids():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert "PROJ-4400" in ctx.prompt
    assert "HD-892" in ctx.prompt


def test_assembled_prompt_contains_linked_issue_state():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert "Fixed" in ctx.prompt


def test_assembled_prompt_contains_code_file_paths():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert "src/services/export/csv_export.py" in ctx.prompt
    assert "src/api/routes/reports.py" in ctx.prompt


def test_assembled_prompt_contains_matched_keywords():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert "csv" in ctx.prompt
    assert "export" in ctx.prompt


def test_assembled_prompt_contains_relationship_type():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert "Depend" in ctx.prompt
    assert "Relate" in ctx.prompt


# ---------------------------------------------------------------------------
# ContextAssembler — edge cases
# ---------------------------------------------------------------------------


def test_assembled_context_is_dataclass():
    result = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert isinstance(result, AssembledContext)
    assert isinstance(result.prompt, str)
    assert len(result.prompt) > 100


def test_assembled_prompt_contains_template_structure():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    # The filled template must not still contain raw format placeholders.
    assert "{ticket_json}" not in ctx.prompt
    assert "{linked_issues_json}" not in ctx.prompt
    assert "{code_areas}" not in ctx.prompt


def test_assemble_no_code_matches_renders_placeholder():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), code_matches=[])
    assert "No relevant files" in ctx.prompt


def test_assemble_no_links_renders_empty_array():
    issue = _make_issue(links=[])
    ctx = ContextAssembler().assemble_ticket_enrichment(issue, _make_matches())
    assert "[]" in ctx.prompt


def test_assemble_no_description_does_not_crash():
    issue = _make_issue(description=None)
    ctx = ContextAssembler().assemble_ticket_enrichment(issue, _make_matches())
    assert "PROJ-4521" in ctx.prompt


def test_assemble_no_comments_does_not_crash():
    issue = _make_issue(comments=[])
    ctx = ContextAssembler().assemble_ticket_enrichment(issue, _make_matches())
    assert "Add CSV Export to Reports" in ctx.prompt


def test_assemble_char_counts_are_positive():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), _make_matches())
    assert ctx.ticket_chars > 0
    assert ctx.linked_chars > 0
    assert ctx.code_chars > 0


def test_assemble_was_truncated_false_for_small_issue():
    ctx = ContextAssembler(max_tokens=6000).assemble_ticket_enrichment(
        _make_issue(), _make_matches()
    )
    assert ctx.was_truncated is False


def test_assemble_truncates_very_long_description():
    long_desc = "x" * 20_000
    issue = _make_issue(description=long_desc)
    ctx = ContextAssembler(max_tokens=6000).assemble_ticket_enrichment(issue, [])
    assert ctx.was_truncated is True
    assert "truncated" in ctx.prompt.lower()


def test_assemble_truncates_many_comments():
    many_comments = [
        YTComment(
            id=f"c{i}",
            text="a" * 1000,
            author=YTUser(login="user", full_name="User"),
            created=1700000000000 + i,
        )
        for i in range(50)
    ]
    issue = _make_issue(comments=many_comments)
    ctx = ContextAssembler(max_tokens=2000).assemble_ticket_enrichment(issue, [])
    assert ctx.was_truncated is True


def test_assemble_budget_sections_sum_to_expected():
    assembler = ContextAssembler(max_tokens=6000)
    assert sum(assembler.budget.values()) <= 1.0


# ---------------------------------------------------------------------------
# ContextAssembler — serialisation details
# ---------------------------------------------------------------------------


def test_ticket_json_is_valid_json():
    """The ticket section must be valid JSON that can be reparsed."""
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), [])
    # Extract the JSON block between the first ```json / ``` markers.
    prompt = ctx.prompt
    start = prompt.index("```json\n") + len("```json\n")
    end = prompt.index("\n```", start)
    ticket_json_str = prompt[start:end]
    parsed = json.loads(ticket_json_str)
    assert parsed["id"] == "PROJ-4521"
    assert parsed["summary"] == "Add CSV Export to Reports"


def test_timestamps_are_converted_to_dates():
    ctx = ContextAssembler().assemble_ticket_enrichment(_make_issue(), [])
    # 1700000000000 ms → 2023-11-14
    assert "2023-11-14" in ctx.prompt


# ---------------------------------------------------------------------------
# LLMClient — provider validation
# ---------------------------------------------------------------------------


def test_llm_client_raises_on_unsupported_provider():
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        LLMClient(provider="cohere", model="x", api_key="k")


# ---------------------------------------------------------------------------
# LLMClient — Anthropic (mocked SDK client)
# ---------------------------------------------------------------------------


def _make_anthropic_mock(response_text: str) -> MagicMock:
    """Build a mock that looks like anthropic.AsyncAnthropic."""
    content_block = MagicMock()
    content_block.text = response_text

    message = MagicMock()
    message.content = [content_block]

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=message)
    mock_client.close = AsyncMock()
    return mock_client


@pytest.mark.asyncio
async def test_llm_client_returns_anthropic_response_text():
    mock = _make_anthropic_mock("Here is your ticket summary.")
    async with LLMClient(
        provider="anthropic", model="claude-sonnet-4-6", api_key="k", _client=mock
    ) as client:
        result = await client.complete("Tell me about PROJ-4521")
    assert result == "Here is your ticket summary."


@pytest.mark.asyncio
async def test_llm_client_passes_prompt_to_anthropic():
    mock = _make_anthropic_mock("ok")
    async with LLMClient(
        provider="anthropic", model="claude-sonnet-4-6", api_key="k", _client=mock
    ) as client:
        await client.complete("my prompt text")

    call_kwargs = mock.messages.create.call_args.kwargs
    assert call_kwargs["messages"][0]["content"] == "my prompt text"
    assert call_kwargs["messages"][0]["role"] == "user"


@pytest.mark.asyncio
async def test_llm_client_passes_model_to_anthropic():
    mock = _make_anthropic_mock("ok")
    async with LLMClient(
        provider="anthropic", model="claude-opus-4-6", api_key="k", _client=mock
    ) as client:
        await client.complete("prompt")

    assert mock.messages.create.call_args.kwargs["model"] == "claude-opus-4-6"


@pytest.mark.asyncio
async def test_llm_client_passes_temperature_to_anthropic():
    mock = _make_anthropic_mock("ok")
    async with LLMClient(
        provider="anthropic",
        model="claude-sonnet-4-6",
        api_key="k",
        temperature=0.1,
        _client=mock,
    ) as client:
        await client.complete("prompt")

    assert mock.messages.create.call_args.kwargs["temperature"] == 0.1


@pytest.mark.asyncio
async def test_llm_client_passes_max_tokens_to_anthropic():
    mock = _make_anthropic_mock("ok")
    async with LLMClient(
        provider="anthropic",
        model="claude-sonnet-4-6",
        api_key="k",
        max_tokens=2048,
        _client=mock,
    ) as client:
        await client.complete("prompt")

    assert mock.messages.create.call_args.kwargs["max_tokens"] == 2048


@pytest.mark.asyncio
async def test_llm_client_wraps_sdk_exception_as_llm_error():
    mock = MagicMock()
    mock.messages = MagicMock()
    mock.messages.create = AsyncMock(side_effect=RuntimeError("connection refused"))
    mock.close = AsyncMock()

    async with LLMClient(
        provider="anthropic", model="claude-sonnet-4-6", api_key="k", _client=mock
    ) as client:
        with pytest.raises(LLMError, match="LLM call failed"):
            await client.complete("prompt")


@pytest.mark.asyncio
async def test_llm_client_raises_on_empty_content_list():
    message = MagicMock()
    message.content = []  # empty — no blocks

    mock = MagicMock()
    mock.messages = MagicMock()
    mock.messages.create = AsyncMock(return_value=message)
    mock.close = AsyncMock()

    async with LLMClient(
        provider="anthropic", model="claude-sonnet-4-6", api_key="k", _client=mock
    ) as client:
        with pytest.raises(LLMError):
            await client.complete("prompt")


# ---------------------------------------------------------------------------
# End-to-end: assembler → client (both mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assembler_output_feeds_into_client():
    """Verify the full pipeline: assemble context → send to mocked LLM."""
    expected_reply = "## PROJ-4521: Add CSV Export to Reports\n\nStatus: Open..."

    mock = _make_anthropic_mock(expected_reply)
    client = LLMClient(
        provider="anthropic", model="claude-sonnet-4-6", api_key="k", _client=mock
    )

    assembler = ContextAssembler()
    ctx = assembler.assemble_ticket_enrichment(_make_issue(), _make_matches())

    result = await client.complete(ctx.prompt)

    assert result == expected_reply
    # Verify the prompt that was sent contains the ticket ID.
    sent_prompt = mock.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "PROJ-4521" in sent_prompt
    assert "csv_export.py" in sent_prompt
