"""Routes user messages to the appropriate handler.

Phase 1 supports two intents:
  - ticket_detail  — message contains a YouTrack ticket ID (e.g. PROJ-4521)
  - general        — everything else; returns a helpful capability listing

The public entry point is ``MessageRouter.route(message)``.
"""

from __future__ import annotations

import logging
import pathlib
import re
from typing import Optional

from pia.config.settings import Settings
from pia.graph.models import CodeMatch, YTIssue
from pia.llm.client import LLMClient, LLMError
from pia.llm.context import ContextAssembler
from pia.sources.codebase import find_relevant_files, scan_project
from pia.sources.youtrack import YouTrackClient, YouTrackError

logger = logging.getLogger(__name__)

# Matches YouTrack-style readable ticket IDs: one or more uppercase letters,
# a hyphen, and one or more digits.  Word boundaries prevent matching inside
# longer tokens.
_TICKET_ID_RE = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")

# English stop words and domain-specific noise words excluded from keyword
# extraction to avoid low-signal matches.
_STOP_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "can", "this", "that", "these", "those",
    "it", "its", "we", "they", "you", "he", "she", "i", "me", "my",
    "our", "your", "his", "her", "their", "from", "into", "by", "as",
    "not", "no", "add", "new", "get", "set", "use", "via", "about",
    "after", "also", "all", "some", "when", "what", "which", "who",
    "how", "now", "just", "been", "more", "than", "then", "there",
})

_FALLBACK_MESSAGE = """\
I'm **PIA** — your Product Intelligence Agent.

I can help you with:

- **Ticket context** — type a YouTrack ticket ID (e.g. `PROJ-4521`) and I'll give you \
a rich summary: business context, related code areas, linked issues, and comment highlights.

More capabilities are coming in future phases (sprint overviews, customer demand analysis, \
impact tracking).

Try: *"Tell me about PROJ-1234"* or just paste a ticket ID.\
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_ticket_id(message: str) -> Optional[str]:
    """Return the first YouTrack ticket ID found in *message*, or ``None``."""
    match = _TICKET_ID_RE.search(message)
    return match.group(1) if match else None


def _extract_keywords(summary: str, description: Optional[str] = None) -> list[str]:
    """Tokenise ticket text into a list of meaningful lowercase keywords.

    Filters out stop words and tokens shorter than three characters.
    """
    text = summary + " " + (description or "")
    tokens = re.findall(r"\b[a-zA-Z][a-zA-Z0-9_]*\b", text)
    return list({
        t.lower() for t in tokens
        if len(t) >= 3 and t.lower() not in _STOP_WORDS
    })


# ---------------------------------------------------------------------------
# MessageRouter
# ---------------------------------------------------------------------------


class MessageRouter:
    """Routes a user message to the appropriate handler and returns a response.

    Args:
        settings: Loaded PIA settings.
        yt_client: Optional pre-built YouTrack client (used in tests).
        llm_client: Optional pre-built LLM client (used in tests).
        assembler: Optional pre-built context assembler (used in tests).
    """

    def __init__(
        self,
        settings: Settings,
        *,
        yt_client: Optional[YouTrackClient] = None,
        llm_client: Optional[LLMClient] = None,
        assembler: Optional[ContextAssembler] = None,
    ) -> None:
        self._settings = settings
        self._yt = yt_client or YouTrackClient(
            base_url=settings.youtrack.url,
            token=settings.youtrack.token,
        )
        self._llm = llm_client or LLMClient(
            provider=settings.llm.provider,
            model=settings.llm.model,
            api_key=settings.llm.api_key,
            max_tokens=settings.llm.max_tokens,
            temperature=settings.llm.temperature,
        )
        self._assembler = assembler or ContextAssembler()

    async def route(self, message: str) -> str:
        """Dispatch *message* to the correct handler and return the response.

        Args:
            message: Raw text sent by the user in the IDE chat.

        Returns:
            Markdown-formatted response string.
        """
        ticket_id = _extract_ticket_id(message)
        if ticket_id:
            logger.info("Routing to ticket handler for %s", ticket_id)
            return await self._handle_ticket(ticket_id)

        logger.debug("No ticket ID detected; returning fallback message")
        return _FALLBACK_MESSAGE

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _handle_ticket(self, ticket_id: str) -> str:
        """Fetch, enrich, and summarise a single YouTrack ticket."""
        # 1. Fetch the issue from YouTrack.
        try:
            issue = await self._yt.get_issue(ticket_id)
        except YouTrackError as exc:
            return self._youtrack_error_message(ticket_id, exc)
        except Exception as exc:
            logger.exception("Unexpected error fetching %s", ticket_id)
            return (
                f"An unexpected error occurred while fetching **{ticket_id}**: {exc}"
            )

        # 2. Find relevant code areas (best-effort; never blocks the response).
        code_matches: list[CodeMatch] = []
        try:
            code_matches = self._find_code(issue)
        except Exception as exc:
            logger.warning("Codebase scan failed (non-fatal): %s", exc)

        # 3. Assemble context and call the LLM.
        ctx = self._assembler.assemble_ticket_enrichment(issue, code_matches)
        try:
            return await self._llm.complete(ctx.prompt)
        except LLMError as exc:
            logger.error("LLM call failed for %s: %s", ticket_id, exc)
            return (
                f"I fetched **{ticket_id}** but encountered an error generating "
                f"the summary: {exc}\n\n"
                f"**{issue.id_readable}: {issue.summary}**\n"
                f"State: {issue.state} | Priority: {issue.priority}"
            )

    def _find_code(self, issue: YTIssue) -> list[CodeMatch]:
        """Scan the local codebase for files relevant to *issue*."""
        root = self._settings.codebase.root or str(pathlib.Path.cwd())
        keywords = _extract_keywords(issue.summary, issue.description)
        if not keywords:
            return []
        tree = scan_project(root, self._settings.codebase.exclude_patterns)
        return find_relevant_files(tree, keywords)

    # ------------------------------------------------------------------
    # Error message helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _youtrack_error_message(ticket_id: str, exc: YouTrackError) -> str:
        if exc.status_code == 404:
            return (
                f"Ticket **{ticket_id}** was not found in YouTrack. "
                "Check that the ID is correct and that the project is accessible."
            )
        if exc.status_code == 401:
            return (
                "YouTrack authentication failed. "
                "Check that `YOUTRACK_TOKEN` is set correctly and has not expired."
            )
        return (
            f"YouTrack returned an error while fetching **{ticket_id}** "
            f"(HTTP {exc.status_code}): {exc}"
        )
