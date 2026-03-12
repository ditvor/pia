"""Dataclass models for YouTrack data (Phase 1).

SQLAlchemy graph node/edge models are added in Phase 4.
All timestamps are Unix milliseconds as returned by the YouTrack REST API.
"""

from __future__ import annotations

import dataclasses
from typing import Optional


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class YTUser:
    """A YouTrack user (assignee, reporter, comment author, etc.)."""

    login: str
    full_name: str


# ---------------------------------------------------------------------------
# Issue sub-objects
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class YTComment:
    """A single comment on a YouTrack issue."""

    id: str
    text: str
    author: YTUser
    created: int  # Unix ms


@dataclasses.dataclass
class YTLinkedIssue:
    """A summary of an issue that appears inside a link relationship."""

    id_readable: str
    summary: str
    state: Optional[str]


@dataclasses.dataclass
class YTIssueLink:
    """A link relationship between the fetched issue and one or more issues."""

    direction: str        # "INWARD" | "OUTWARD" | "BOTH"
    link_type: str        # e.g. "Depend", "Duplicate", "Subtask"
    issues: list[YTLinkedIssue]


# ---------------------------------------------------------------------------
# Top-level issue
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class YTIssue:
    """A fully-fetched YouTrack issue with all Phase 1 fields populated."""

    id: str                          # Internal ID (e.g. "2-4521")
    id_readable: str                 # Human-readable ID (e.g. "PROJ-4521")
    summary: str
    description: Optional[str]
    project: str                     # Project short name (e.g. "PROJ")
    priority: Optional[str]          # e.g. "Critical", "Major"
    state: Optional[str]             # e.g. "Open", "In Progress", "Fixed"
    assignee: Optional[YTUser]
    reporter: Optional[YTUser]
    created: int                     # Unix ms
    updated: int                     # Unix ms
    resolved: Optional[int]          # Unix ms, or None if unresolved
    comments: list[YTComment]
    tags: list[str]
    links: list[YTIssueLink]


# ---------------------------------------------------------------------------
# Sprint
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class YTSprintIssue:
    """Lightweight issue summary as it appears inside a sprint."""

    id_readable: str
    summary: str
    state: Optional[str]
    estimation: Optional[int]        # Story points or hours, as configured


@dataclasses.dataclass
class YTSprint:
    """A YouTrack agile sprint with its issues."""

    id: str
    name: str
    issues: list[YTSprintIssue]


# ---------------------------------------------------------------------------
# Codebase scanner models
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class FileEntry:
    """Metadata for a single file discovered during a project scan."""

    path: str           # Relative to project root, using forward slashes
    size_bytes: int
    language: Optional[str]   # Inferred from extension; None if unknown


@dataclasses.dataclass
class ProjectTree:
    """Snapshot of a project's file tree produced by scan_project()."""

    root: str           # Absolute path to the project root
    files: list[FileEntry]


@dataclasses.dataclass
class CodeMatch:
    """A file that is likely relevant to a ticket, based on keyword matching."""

    filepath: str             # Relative path (same as FileEntry.path)
    match_score: int          # Number of distinct keywords that matched
    matched_keywords: list[str]
