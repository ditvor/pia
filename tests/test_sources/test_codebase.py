"""Tests for the codebase scanner."""

from __future__ import annotations

import pathlib
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from pia.graph.models import CodeMatch, FileEntry, ProjectTree
from pia.sources.codebase import (
    _detect_language,
    _should_exclude_dir,
    _should_exclude_file,
    find_relevant_files,
    get_recent_changes,
    scan_project,
)

SAMPLE_CODEBASE = pathlib.Path(__file__).parent.parent / "fixtures" / "sample_codebase"

# ---------------------------------------------------------------------------
# _detect_language
# ---------------------------------------------------------------------------


def test_detect_language_python():
    assert _detect_language("foo.py") == "Python"


def test_detect_language_typescript():
    assert _detect_language("component.tsx") == "TypeScript"


def test_detect_language_unknown():
    assert _detect_language("Makefile") is None


def test_detect_language_case_insensitive_extension():
    # Extension lookup is normalised to lowercase, so .PY → Python.
    assert _detect_language("script.PY") == "Python"


# ---------------------------------------------------------------------------
# _should_exclude_dir / _should_exclude_file
# ---------------------------------------------------------------------------


def test_exclude_dir_matches_pattern():
    assert _should_exclude_dir("node_modules", ["node_modules/"])
    assert _should_exclude_dir("__pycache__", ["__pycache__/"])
    assert _should_exclude_dir(".git", [".git/"])


def test_exclude_dir_does_not_match_non_dir_pattern():
    assert not _should_exclude_dir("src", ["*.min.js"])
    assert not _should_exclude_dir("dist", ["dist"])  # no trailing slash → not a dir pattern


def test_exclude_dir_no_false_positives():
    assert not _should_exclude_dir("src", ["node_modules/", ".git/"])
    assert not _should_exclude_dir("build_tools", ["build/"])  # partial name must not match


def test_exclude_file_matches_glob():
    assert _should_exclude_file("app.min.js", ["*.min.js"])
    assert _should_exclude_file("vendor.min.js", ["*.min.js"])


def test_exclude_file_does_not_match_dir_pattern():
    assert not _should_exclude_file("node_modules", ["node_modules/"])


def test_exclude_file_no_false_positives():
    assert not _should_exclude_file("app.js", ["*.min.js"])


# ---------------------------------------------------------------------------
# scan_project — basic behaviour
# ---------------------------------------------------------------------------


def test_scan_project_returns_project_tree():
    tree = scan_project(SAMPLE_CODEBASE)
    assert isinstance(tree, ProjectTree)
    assert tree.root == str(SAMPLE_CODEBASE.resolve())


def test_scan_project_finds_python_files():
    tree = scan_project(SAMPLE_CODEBASE)
    paths = [f.path for f in tree.files]
    assert any("csv_export.py" in p for p in paths)
    assert any("reports.py" in p for p in paths)
    assert any("controller.py" in p for p in paths)


def test_scan_project_excludes_pycache():
    tree = scan_project(SAMPLE_CODEBASE)
    paths = [f.path for f in tree.files]
    assert not any("__pycache__" in p for p in paths)


def test_scan_project_excludes_min_js():
    tree = scan_project(SAMPLE_CODEBASE)
    paths = [f.path for f in tree.files]
    assert not any(p.endswith(".min.js") for p in paths)


def test_scan_project_paths_are_relative_with_forward_slashes():
    tree = scan_project(SAMPLE_CODEBASE)
    for entry in tree.files:
        assert not pathlib.Path(entry.path).is_absolute()
        assert "\\" not in entry.path  # always forward slashes


def test_scan_project_detects_python_language():
    tree = scan_project(SAMPLE_CODEBASE)
    py_files = [f for f in tree.files if f.path.endswith(".py")]
    assert py_files, "expected at least one .py file"
    assert all(f.language == "Python" for f in py_files)


def test_scan_project_records_positive_sizes():
    tree = scan_project(SAMPLE_CODEBASE)
    # Files with content should have positive size; empty files are 0 — both are valid.
    assert all(f.size_bytes >= 0 for f in tree.files)
    # At least some files should have non-zero size (our fixtures have content).
    assert any(f.size_bytes > 0 for f in tree.files)


def test_scan_project_respects_custom_exclude():
    # Exclude the entire 'tests' directory by passing a custom pattern.
    tree = scan_project(SAMPLE_CODEBASE, exclude_patterns=["tests/"])
    paths = [f.path for f in tree.files]
    assert not any(p.startswith("tests/") for p in paths)


def test_scan_project_default_excludes_do_not_hide_src():
    tree = scan_project(SAMPLE_CODEBASE)
    paths = [f.path for f in tree.files]
    assert any(p.startswith("src/") for p in paths)


def test_scan_project_empty_excludes_includes_pycache():
    # With no exclude patterns, __pycache__ should appear.
    tree = scan_project(SAMPLE_CODEBASE, exclude_patterns=[])
    paths = [f.path for f in tree.files]
    assert any("__pycache__" in p for p in paths)


# ---------------------------------------------------------------------------
# find_relevant_files
# ---------------------------------------------------------------------------


def _make_tree(*paths: str) -> ProjectTree:
    """Build a minimal ProjectTree from a list of relative paths."""
    files = [FileEntry(path=p, size_bytes=10, language="Python") for p in paths]
    return ProjectTree(root="/project", files=files)


def test_find_relevant_files_matches_keyword_in_directory():
    tree = _make_tree(
        "src/services/export/controller.py",
        "src/api/routes/reports.py",
        "src/models/user.py",
    )
    matches = find_relevant_files(tree, ["export"])
    paths = [m.filepath for m in matches]
    assert "src/services/export/controller.py" in paths
    assert "src/models/user.py" not in paths


def test_find_relevant_files_matches_keyword_in_filename():
    tree = _make_tree(
        "src/services/export/csv_export.py",
        "src/services/export/pdf_export.py",
        "src/api/routes/auth.py",
    )
    matches = find_relevant_files(tree, ["csv"])
    paths = [m.filepath for m in matches]
    assert "src/services/export/csv_export.py" in paths
    assert "src/api/routes/auth.py" not in paths


def test_find_relevant_files_case_insensitive():
    tree = _make_tree("src/services/Export/Controller.py")
    matches = find_relevant_files(tree, ["export", "CONTROLLER"])
    assert len(matches) == 1
    assert matches[0].match_score == 2


def test_find_relevant_files_score_reflects_keyword_count():
    tree = _make_tree(
        "src/services/export/csv_export.py",   # matches "export" AND "csv"
        "src/services/export/pdf_export.py",   # matches "export" only
        "src/models/report.py",                # matches neither
    )
    matches = find_relevant_files(tree, ["export", "csv"])
    assert matches[0].filepath == "src/services/export/csv_export.py"
    assert matches[0].match_score == 2
    assert matches[1].filepath == "src/services/export/pdf_export.py"
    assert matches[1].match_score == 1


def test_find_relevant_files_returns_matched_keywords():
    tree = _make_tree("src/services/export/csv_export.py")
    matches = find_relevant_files(tree, ["export", "csv", "unrelated"])
    assert set(matches[0].matched_keywords) == {"export", "csv"}


def test_find_relevant_files_no_match_returns_empty():
    tree = _make_tree("src/models/user.py", "src/api/routes/auth.py")
    matches = find_relevant_files(tree, ["billing", "invoice"])
    assert matches == []


def test_find_relevant_files_empty_keywords_returns_empty():
    tree = _make_tree("src/models/user.py")
    assert find_relevant_files(tree, []) == []


def test_find_relevant_files_short_keywords_ignored():
    # Single-character keywords should not produce matches (too noisy).
    tree = _make_tree("src/a/b.py")
    assert find_relevant_files(tree, ["a"]) == []


def test_find_relevant_files_respects_max_results():
    paths = [f"src/services/export/handler_{i}.py" for i in range(20)]
    tree = _make_tree(*paths)
    matches = find_relevant_files(tree, ["export"], max_results=5)
    assert len(matches) == 5


def test_find_relevant_files_deduplicates_keywords():
    tree = _make_tree("src/services/export/controller.py")
    # Passing the same keyword multiple times should count as one match.
    matches = find_relevant_files(tree, ["export", "Export", "EXPORT"])
    assert matches[0].match_score == 1


def test_find_relevant_files_against_real_fixture():
    """Integration: scan the real fixture codebase and check keyword matches."""
    tree = scan_project(SAMPLE_CODEBASE)
    matches = find_relevant_files(tree, ["export", "csv"])

    paths = [m.filepath for m in matches]
    # csv_export.py matches both keywords → highest score
    assert matches[0].match_score == 2
    assert any("csv_export" in p for p in paths)
    # reports.py has no keyword match
    assert not any("reports" in p and "export" not in p for p in [matches[0].filepath])


# ---------------------------------------------------------------------------
# get_recent_changes
# ---------------------------------------------------------------------------


def test_get_recent_changes_no_git_dir(tmp_path):
    result = get_recent_changes(tmp_path)
    assert result == {}


def test_get_recent_changes_parses_git_output(tmp_path):
    (tmp_path / ".git").mkdir()

    git_output = (
        "\n"  # blank line before first commit's files
        "src/services/export/csv_export.py\n"
        "src/api/routes/reports.py\n"
        "\n"
        "src/services/export/csv_export.py\n"  # touched again in second commit
        "\n"
    )

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = git_output

    with patch("pia.sources.codebase.subprocess.run", return_value=mock_result):
        counts = get_recent_changes(tmp_path)

    assert counts["src/services/export/csv_export.py"] == 2
    assert counts["src/api/routes/reports.py"] == 1


def test_get_recent_changes_git_not_installed(tmp_path):
    (tmp_path / ".git").mkdir()

    with patch(
        "pia.sources.codebase.subprocess.run",
        side_effect=FileNotFoundError("git not found"),
    ):
        result = get_recent_changes(tmp_path)

    assert result == {}


def test_get_recent_changes_git_timeout(tmp_path):
    (tmp_path / ".git").mkdir()

    with patch(
        "pia.sources.codebase.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="git", timeout=30),
    ):
        result = get_recent_changes(tmp_path)

    assert result == {}


def test_get_recent_changes_nonzero_exit(tmp_path):
    (tmp_path / ".git").mkdir()

    mock_result = MagicMock()
    mock_result.returncode = 128
    mock_result.stderr = "fatal: not a git repository"
    mock_result.stdout = ""

    with patch("pia.sources.codebase.subprocess.run", return_value=mock_result):
        result = get_recent_changes(tmp_path)

    assert result == {}


def test_get_recent_changes_respects_days_parameter(tmp_path):
    (tmp_path / ".git").mkdir()

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = ""

    with patch("pia.sources.codebase.subprocess.run", return_value=mock_result) as mock_run:
        get_recent_changes(tmp_path, days=30)

    call_args = mock_run.call_args
    cmd = call_args[0][0]
    assert "--since=30 days ago" in cmd
