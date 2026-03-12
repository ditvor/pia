"""Context assembly — serialises domain objects into filled prompt strings.

The ContextAssembler is the bridge between raw data (YTIssue, CodeMatch)
and the LLM. It is responsible for:

  1. Converting typed dataclasses to JSON-serialisable dicts.
  2. Enforcing a per-section character budget so the assembled prompt
     stays inside the configured token limit (using ~4 chars/token as
     the approximation).
  3. Filling prompt templates with the assembled sections.

No LLM calls happen here. The assembler is fully synchronous and testable
without any external dependencies.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import logging
from typing import Any

from pia.graph.models import CodeMatch, YTIssue
from pia.llm.prompts import TICKET_ENRICHMENT_PROMPT

logger = logging.getLogger(__name__)

# Rough approximation used throughout: 1 token ≈ 4 characters.
_CHARS_PER_TOKEN: int = 4

# Minimum description length retained even under tight budgets.
_MIN_DESCRIPTION_CHARS: int = 200


def _ms_to_date(ts_ms: int | None) -> str | None:
    """Convert a Unix-millisecond timestamp to an ISO 8601 date string."""
    if ts_ms is None:
        return None
    return datetime.datetime.utcfromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d")


def _truncate(text: str, limit: int, marker: str = "… [truncated]") -> str:
    """Truncate *text* to *limit* characters, appending *marker* if cut."""
    if len(text) <= limit:
        return text
    return text[: limit - len(marker)] + marker


# ---------------------------------------------------------------------------
# Public dataclass returned by the assembler (useful for tests / logging)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class AssembledContext:
    """Result of a ContextAssembler.assemble_*() call."""

    prompt: str

    # Character counts of each section (for diagnostics / logging).
    ticket_chars: int
    linked_chars: int
    code_chars: int

    # True if any section was shortened to fit the budget.
    was_truncated: bool


# ---------------------------------------------------------------------------
# ContextAssembler
# ---------------------------------------------------------------------------


class ContextAssembler:
    """Builds filled LLM prompt strings from typed domain objects.

    Args:
        max_tokens: Target token ceiling for the assembled context sections.
            The prompt template itself is not counted against this budget
            because its size is fixed and small relative to the data.
    """

    def __init__(self, max_tokens: int = 6000) -> None:
        self.max_tokens = max_tokens
        # Fractional token budget per section (must sum to ≤ 1.0).
        self.budget: dict[str, float] = {
            "ticket": 0.40,
            "linked": 0.20,
            "code": 0.30,
        }

    def _char_budget(self, section: str) -> int:
        """Return the character allowance for a named section."""
        return int(self.max_tokens * self.budget[section] * _CHARS_PER_TOKEN)

    # ------------------------------------------------------------------
    # Section serialisers
    # ------------------------------------------------------------------

    def _issue_to_dict(self, issue: YTIssue, char_budget: int) -> tuple[dict[str, Any], bool]:
        """Serialise a YTIssue to a JSON-ready dict within *char_budget*.

        Returns:
            (dict, was_truncated)
        """
        was_truncated = False

        description = issue.description or ""
        # Reserve roughly one-third of the budget for the description.
        desc_budget = max(_MIN_DESCRIPTION_CHARS, char_budget // 3)
        if len(description) > desc_budget:
            description = _truncate(description, desc_budget)
            was_truncated = True

        # Remaining budget split across comments.
        comment_budget_total = char_budget - len(description) - 500  # 500 for other fields
        comment_budget_each = max(
            300, comment_budget_total // max(len(issue.comments), 1)
        )

        comments: list[dict[str, Any]] = []
        accumulated = 0
        for c in issue.comments:
            text = c.text
            if len(text) > comment_budget_each:
                text = _truncate(text, comment_budget_each)
                was_truncated = True
            entry: dict[str, Any] = {
                "author": c.author.full_name or c.author.login,
                "date": _ms_to_date(c.created),
                "text": text,
            }
            entry_len = len(json.dumps(entry))
            if comment_budget_total > 0 and accumulated + entry_len > comment_budget_total:
                was_truncated = True
                break
            comments.append(entry)
            accumulated += entry_len

        d: dict[str, Any] = {
            "id": issue.id_readable,
            "summary": issue.summary,
            "description": description if description else None,
            "project": issue.project,
            "state": issue.state,
            "priority": issue.priority,
            "assignee": (
                f"{issue.assignee.full_name} ({issue.assignee.login})"
                if issue.assignee else None
            ),
            "reporter": (
                f"{issue.reporter.full_name} ({issue.reporter.login})"
                if issue.reporter else None
            ),
            "created": _ms_to_date(issue.created),
            "updated": _ms_to_date(issue.updated),
            "resolved": _ms_to_date(issue.resolved),
            "tags": issue.tags,
            "comments": comments,
        }
        return d, was_truncated

    def _linked_to_list(
        self, issue: YTIssue, char_budget: int
    ) -> tuple[list[dict[str, Any]], bool]:
        """Flatten all link relationships into a list of linked-issue dicts.

        Returns:
            (list, was_truncated)
        """
        was_truncated = False
        items: list[dict[str, Any]] = []
        accumulated = 0

        for link in issue.links:
            for linked in link.issues:
                entry: dict[str, Any] = {
                    "id": linked.id_readable,
                    "summary": linked.summary,
                    "state": linked.state,
                    "relationship": f"{link.link_type} ({link.direction})",
                }
                entry_len = len(json.dumps(entry))
                if accumulated + entry_len > char_budget:
                    was_truncated = True
                    break
                items.append(entry)
                accumulated += entry_len

        return items, was_truncated

    def _format_code_areas(
        self, matches: list[CodeMatch], char_budget: int
    ) -> tuple[str, bool]:
        """Format code matches as a human-readable bullet list.

        Returns:
            (text, was_truncated)
        """
        if not matches:
            return "_No relevant files identified in the local project tree._", False

        was_truncated = False
        lines: list[str] = []
        accumulated = 0

        for match in matches:
            keywords = ", ".join(match.matched_keywords)
            line = f"- `{match.filepath}`  [matched: {keywords}]"
            if accumulated + len(line) + 1 > char_budget:
                was_truncated = True
                break
            lines.append(line)
            accumulated += len(line) + 1  # +1 for newline

        return "\n".join(lines), was_truncated

    # ------------------------------------------------------------------
    # Public assembly methods
    # ------------------------------------------------------------------

    def assemble_ticket_enrichment(
        self,
        issue: YTIssue,
        code_matches: list[CodeMatch],
    ) -> AssembledContext:
        """Build a filled TICKET_ENRICHMENT_PROMPT for *issue*.

        Args:
            issue: Fully-fetched YouTrack issue.
            code_matches: Ranked code matches from the codebase scanner.

        Returns:
            An ``AssembledContext`` whose ``.prompt`` is ready to send to
            the LLM.
        """
        issue_dict, t_trunc = self._issue_to_dict(issue, self._char_budget("ticket"))
        linked_list, l_trunc = self._linked_to_list(issue, self._char_budget("linked"))
        code_text, c_trunc = self._format_code_areas(
            code_matches, self._char_budget("code")
        )

        ticket_json = json.dumps(issue_dict, indent=2, ensure_ascii=False)
        linked_json = json.dumps(linked_list, indent=2, ensure_ascii=False)

        prompt = TICKET_ENRICHMENT_PROMPT.format(
            ticket_json=ticket_json,
            linked_issues_json=linked_json,
            code_areas=code_text,
        )

        was_truncated = t_trunc or l_trunc or c_trunc
        if was_truncated:
            logger.debug(
                "Context for %s was truncated (ticket=%s linked=%s code=%s)",
                issue.id_readable,
                t_trunc,
                l_trunc,
                c_trunc,
            )

        return AssembledContext(
            prompt=prompt,
            ticket_chars=len(ticket_json),
            linked_chars=len(linked_json),
            code_chars=len(code_text),
            was_truncated=was_truncated,
        )
