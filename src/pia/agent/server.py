"""ACP server — handles protocol handshake and message routing."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from acp.server.highlevel import Server

from pia.agent.router import MessageRouter
from pia.config.settings import Settings

logger = logging.getLogger(__name__)

_AGENT_DESCRIPTION = (
    "PIA — Product Intelligence Agent. "
    "Send a YouTrack ticket ID (e.g. PROJ-4521) to get a rich summary: "
    "business context, related code areas, linked issues, and comment highlights."
)


class PIAInput(BaseModel):
    """Input model for the PIA agent."""

    message: str


class PIAOutput(BaseModel):
    """Output model for the PIA agent."""

    response: str


def create_pia_server(settings: Settings) -> Server:
    """Create and configure the ACP server for PIA.

    Args:
        settings: Loaded PIA settings.

    Returns:
        A configured :class:`Server` instance ready to run.
    """
    server = Server(
        name=settings.agent.name,
        instructions=_AGENT_DESCRIPTION,
    )
    router = MessageRouter(settings)

    @server.agent(
        name=settings.agent.name,
        description=_AGENT_DESCRIPTION,
        input=PIAInput,
        output=PIAOutput,
    )
    async def run_pia(inp: PIAInput, ctx) -> PIAOutput:  # noqa: ANN001
        logger.debug("ACP agent received message: %.80s…", inp.message)
        response = await router.route(inp.message)
        return PIAOutput(response=response)

    return server
