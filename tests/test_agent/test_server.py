"""Tests for the ACP server factory."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from pia.agent.server import PIAInput, PIAOutput, create_pia_server


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_settings(agent_name: str = "pia") -> MagicMock:
    settings = MagicMock()
    settings.agent.name = agent_name
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
# Server creation
# ---------------------------------------------------------------------------


def test_create_pia_server_returns_server():
    from acp.server.highlevel import Server

    server = create_pia_server(_make_settings())
    assert isinstance(server, Server)


def test_server_name_matches_settings():
    server = create_pia_server(_make_settings(agent_name="my-pia"))
    assert server.name == "my-pia"


def test_server_has_one_agent_registered():
    server = create_pia_server(_make_settings())
    agents = server._agent_manager.list_agents()
    assert len(agents) == 1


def test_server_agent_name_matches_settings():
    server = create_pia_server(_make_settings(agent_name="pia"))
    agents = server._agent_manager.list_agents()
    assert agents[0].name == "pia"


def test_server_agent_input_model():
    server = create_pia_server(_make_settings())
    agents = server._agent_manager.list_agents()
    assert agents[0].input is PIAInput


def test_server_agent_output_model():
    server = create_pia_server(_make_settings())
    agents = server._agent_manager.list_agents()
    assert agents[0].output is PIAOutput


# ---------------------------------------------------------------------------
# Input / Output model shapes
# ---------------------------------------------------------------------------


def test_pia_input_has_message_field():
    inp = PIAInput(message="hello")
    assert inp.message == "hello"


def test_pia_output_has_response_field():
    out = PIAOutput(response="hello back")
    assert out.response == "hello back"


def test_pia_input_message_required():
    with pytest.raises(Exception):
        PIAInput()  # type: ignore[call-arg]


def test_pia_output_response_required():
    with pytest.raises(Exception):
        PIAOutput()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Agent run_fn wires through to router
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_run_fn_calls_router():
    from unittest.mock import AsyncMock, patch

    settings = _make_settings()
    server = create_pia_server(settings)
    agents = server._agent_manager.list_agents()
    run_fn = agents[0].run_fn

    ctx = MagicMock()
    inp = PIAInput(message="PROJ-1")

    with patch("pia.agent.server.MessageRouter.route", new=AsyncMock(return_value="mocked")) as mock_route:
        result = await run_fn(inp, ctx)

    assert isinstance(result, PIAOutput)
    assert result.response == "mocked"
    mock_route.assert_awaited_once_with("PROJ-1")
