"""Local codebase scanner — file tree walking, keyword matching, git log."""

from __future__ import annotations

import fnmatch
import logging
import os
import pathlib
import subprocess
from typing import Optional

from pia.graph.models import CodeMatch, FileEntry, ProjectTree

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

_LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".cs": "C#",
    ".cpp": "C++",
    ".c": "C",
    ".h": "C/C++",
    ".swift": "Swift",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".md": "Markdown",
    ".sql": "SQL",
    ".sh": "Shell",
    ".toml": "TOML",
    ".xml": "XML",
}


def _detect_language(filename: str) -> Optional[str]:
    """Return the language name for a filename based on its extension."""
    suffix = pathlib.Path(filename).suffix.lower()
    return _LANGUAGE_MAP.get(suffix)


# ---------------------------------------------------------------------------
# Exclude pattern helpers
# ---------------------------------------------------------------------------

def _should_exclude_dir(dir_name: str, exclude_patterns: list[str]) -> bool:
    """Return True if a directory name matches any exclusion pattern.

    Directory patterns end with ``/`` (e.g. ``node_modules/``).
    """
    for pattern in exclude_patterns:
        if pattern.endswith("/"):
            if dir_name == pattern.rstrip("/"):
                return True
    return False


def _should_exclude_file(filename: str, exclude_patterns: list[str]) -> bool:
    """Return True if a filename matches any non-directory exclusion pattern.

    Supports glob wildcards (e.g. ``*.min.js``).
    """
    for pattern in exclude_patterns:
        if not pattern.endswith("/"):
            if fnmatch.fnmatch(filename, pattern):
                return True
    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_project(
    root_path: str | pathlib.Path,
    exclude_patterns: Optional[list[str]] = None,
) -> ProjectTree:
    """Walk a project directory and return metadata for every included file.

    Directories whose names match a pattern ending in ``/`` are pruned
    entirely (skipped along with all descendants). Files whose names match
    a glob pattern (e.g. ``*.min.js``) are skipped individually.

    Args:
        root_path: Absolute or relative path to the project root.
        exclude_patterns: Patterns to exclude.  Directory patterns end with
            ``/`` (e.g. ``".git/"``); file patterns may include globs
            (e.g. ``"*.min.js"``).  Defaults to a sensible set.

    Returns:
        A ``ProjectTree`` with one ``FileEntry`` per discovered file.
    """
    if exclude_patterns is None:
        exclude_patterns = [
            "node_modules/",
            ".git/",
            "dist/",
            "build/",
            "__pycache__/",
            ".venv/",
            "*.min.js",
        ]

    root = pathlib.Path(root_path).resolve()
    files: list[FileEntry] = []

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        # Prune excluded directories in-place so os.walk skips their subtrees.
        dirnames[:] = [
            d for d in dirnames
            if not _should_exclude_dir(d, exclude_patterns)
        ]

        for filename in filenames:
            if _should_exclude_file(filename, exclude_patterns):
                continue

            abs_path = pathlib.Path(dirpath) / filename
            try:
                size = abs_path.stat().st_size
            except OSError:
                size = 0

            # Store paths with forward slashes regardless of OS.
            rel = abs_path.relative_to(root).as_posix()

            files.append(FileEntry(
                path=rel,
                size_bytes=size,
                language=_detect_language(filename),
            ))

    logger.debug("Scanned %s: %d files found", root, len(files))
    return ProjectTree(root=str(root), files=files)


def find_relevant_files(
    project_tree: ProjectTree,
    keywords: list[str],
    max_results: int = 10,
) -> list[CodeMatch]:
    """Score each file in *project_tree* by how many *keywords* it matches.

    Matching is case-insensitive substring search against the full relative
    file path (which covers directory names, the file name, and the stem).
    A keyword must be at least two characters long to avoid noise.

    Args:
        project_tree: Output of ``scan_project()``.
        keywords: Terms extracted from a ticket's summary and description.
        max_results: Maximum number of results to return.

    Returns:
        List of ``CodeMatch`` objects sorted by ``match_score`` descending,
        capped at ``max_results``.  Files with a score of zero are excluded.
    """
    # Normalise and de-duplicate; drop very short tokens.
    clean_keywords = list({kw.lower() for kw in keywords if len(kw) >= 2})

    if not clean_keywords:
        return []

    matches: list[CodeMatch] = []

    for entry in project_tree.files:
        path_lower = entry.path.lower()
        matched = [kw for kw in clean_keywords if kw in path_lower]
        if matched:
            matches.append(CodeMatch(
                filepath=entry.path,
                match_score=len(matched),
                matched_keywords=sorted(matched),
            ))

    matches.sort(key=lambda m: m.match_score, reverse=True)
    return matches[:max_results]


def get_recent_changes(
    root: str | pathlib.Path,
    days: int = 90,
) -> dict[str, int]:
    """Count how many times each file was touched in the recent git history.

    Runs ``git log`` in *root* and counts filename occurrences in the output.
    Returns an empty dict if the directory has no ``.git`` folder or if the
    git command fails.

    Args:
        root: Project root (must contain a ``.git`` directory).
        days: How many days of history to include.

    Returns:
        Mapping of relative file path → number of commits that touched it.
    """
    root = pathlib.Path(root).resolve()

    if not (root / ".git").is_dir():
        logger.debug("No .git found at %s; skipping git log", root)
        return {}

    try:
        result = subprocess.run(
            [
                "git", "log",
                f"--since={days} days ago",
                "--name-only",
                "--pretty=format:",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.warning("git log failed: %s", exc)
        return {}

    if result.returncode != 0:
        logger.warning("git log exited %d: %s", result.returncode, result.stderr.strip())
        return {}

    counts: dict[str, int] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            counts[line] = counts.get(line, 0) + 1

    return counts
