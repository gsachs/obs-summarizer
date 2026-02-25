"""Tests for scanner module."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from obs_summarizer.scanner import filter_files_since, list_markdown_files


def test_list_markdown_files_basic(tmp_vault):
    """Find all markdown files in vault."""
    files = list_markdown_files(str(tmp_vault))

    file_names = {f.name for f in files}
    assert "article1.md" in file_names
    assert "article2.md" in file_names
    assert "template.md" in file_names
    assert "empty.md" not in file_names  # Empty files are filtered


def test_list_markdown_files_exclude_globs(tmp_vault):
    """Exclude globs filter out files."""
    files = list_markdown_files(
        str(tmp_vault),
        exclude_globs=["**/.obsidian", "templates"],
    )

    file_names = {f.name for f in files}
    assert "article1.md" in file_names
    assert "article2.md" in file_names
    assert "template.md" not in file_names  # Excluded by globs


def test_list_markdown_files_include_folders(tmp_vault):
    """Include specific folders only."""
    files = list_markdown_files(
        str(tmp_vault),
        include_folders=["Clippings"],
    )

    file_names = {f.name for f in files}
    assert "article1.md" in file_names
    assert "article2.md" in file_names
    assert "template.md" not in file_names  # Not in Clippings


def test_list_markdown_files_skip_symlinks(tmp_vault):
    """Symlinks are skipped."""
    if not hasattr(Path, "symlink_to"):
        pytest.skip("Symlinks not supported on this platform")

    # Create a symlink
    symlink = tmp_vault / "link.md"
    symlink.symlink_to(tmp_vault / "Clippings" / "article1.md")

    files = list_markdown_files(str(tmp_vault), exclude_globs=["**/.obsidian/**", "**/templates/**"])
    file_names = {f.name for f in files}
    assert "link.md" not in file_names


def test_list_markdown_files_sorted_by_mtime(tmp_vault):
    """Files are sorted by mtime (oldest first)."""
    files = list_markdown_files(
        str(tmp_vault),
        exclude_globs=["**/.obsidian/**", "**/templates/**"],
    )

    # Verify sorted by mtime
    mtimes = [f.stat().st_mtime for f in files]
    assert mtimes == sorted(mtimes)


def test_filter_files_since_basic(tmp_vault):
    """Filter files by modification time."""
    all_files = list_markdown_files(
        str(tmp_vault),
        exclude_globs=["**/.obsidian/**", "**/templates/**"],
    )

    # Filter for files modified in the future (should be none)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    filtered = filter_files_since(all_files, future)

    assert len(filtered) == 0


def test_filter_files_since_past(tmp_vault):
    """Filter files modified since a past time."""
    all_files = list_markdown_files(
        str(tmp_vault),
        exclude_globs=["**/.obsidian/**", "**/templates/**"],
    )

    # Filter for files modified since 1 hour ago
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    filtered = filter_files_since(all_files, past)

    # All files were just created, so they should match
    assert len(filtered) > 0


def test_list_markdown_files_include_folders_traversal(tmp_vault, tmp_path):
    """include_folders entries that escape the vault raise ValueError."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("secret")

    with pytest.raises(ValueError, match="outside vault boundary"):
        list_markdown_files(
            str(tmp_vault),
            include_folders=["../outside"],
        )


def test_filter_files_since_sorted(tmp_vault):
    """Filtered files are sorted by mtime."""
    all_files = list_markdown_files(
        str(tmp_vault),
        exclude_globs=["**/.obsidian/**", "**/templates/**"],
    )

    past = datetime.now(timezone.utc) - timedelta(hours=1)
    filtered = filter_files_since(all_files, past)

    mtimes = [f.stat().st_mtime for f in filtered]
    assert mtimes == sorted(mtimes)
