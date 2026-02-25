"""Tests for digest_writer module."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from obs_summarizer.digest_writer import format_digest_markdown, write_digest_note


def test_format_digest_markdown_empty():
    """Format digest with no summaries."""
    result = format_digest_markdown([])
    assert "---\ntype: digest\n" in result
    assert "Daily Digest" in result


def test_format_digest_markdown_with_summaries(sample_summary):
    """Format digest with article summaries."""
    summaries = [sample_summary]
    result = format_digest_markdown(summaries)

    assert "---\ntype: digest\n" in result
    assert "type: digest" in result
    assert "articles_count: 1" in result
    assert sample_summary["summary"] in result
    assert sample_summary["why_it_matters"] in result


def test_format_digest_markdown_groups_by_tags(sample_summary):
    """Summaries are grouped by tag/theme."""
    summary1 = {
        **sample_summary,
        "tags": ["ai"],
        "summary": "AI article",
    }
    summary2 = {
        **sample_summary,
        "tags": ["ml"],
        "summary": "ML article",
    }

    result = format_digest_markdown([summary1, summary2])

    assert "## Ai\n" in result
    assert "## Ml\n" in result


def test_format_digest_markdown_includes_frontmatter():
    """Frontmatter has correct date and counts."""
    date = datetime(2026, 2, 25, tzinfo=timezone.utc)
    summaries = [{
        "summary": "Test",
        "bullets": [],
        "why_it_matters": "Test",
        "tags": ["test"],
        "notable_quote": None,
    }]

    result = format_digest_markdown(summaries, date=date)

    assert "---\n" in result
    assert "type: digest\n" in result
    assert "date: 2026-02-25\n" in result
    assert "articles_count: 1\n" in result


def test_write_digest_note_creates_file():
    """Write digest note creates file in vault."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)
        digest_folder = "Daily Digests"
        content = "# Test Digest\n\nContent here"

        result = write_digest_note(str(vault), digest_folder, content)

        assert result.exists()
        assert result.parent.name == "Daily Digests"
        assert result.name.endswith("-digest.md")
        assert result.read_text() == content


def test_write_digest_note_overwrites_existing():
    """Writing digest overwrites existing digest for same date."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)
        digest_folder = "Daily Digests"
        date = datetime(2026, 2, 25, tzinfo=timezone.utc)

        # Write first digest
        write_digest_note(str(vault), digest_folder, "First content", date=date)

        # Write second digest for same date
        result = write_digest_note(
            str(vault), digest_folder, "Second content", date=date
        )

        # Should have overwritten
        assert result.read_text() == "Second content"


def test_write_digest_note_creates_directories():
    """Parent directories are created if needed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)
        digest_folder = "deep/nested/Daily Digests"

        result = write_digest_note(str(vault), digest_folder, "Content")

        assert result.parent.exists()
        assert result.exists()


def test_format_digest_markdown_includes_quotes():
    """Notable quotes are included in output."""
    summary = {
        "summary": "Test",
        "bullets": [],
        "why_it_matters": "Test",
        "tags": ["test"],
        "notable_quote": "This is a quote",
    }

    result = format_digest_markdown([summary])

    assert "> This is a quote" in result


def test_format_digest_markdown_handles_missing_fields():
    """Missing fields are handled gracefully."""
    summary = {
        "summary": "Test",
        # missing bullets, why_it_matters, tags, quote
    }

    result = format_digest_markdown([summary])

    assert "Test" in result
    assert result  # Just ensure it generates something


def test_write_digest_note_rejects_path_traversal():
    """Path traversal attempts are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)

        # Attempt 1: Directory traversal with ..
        with pytest.raises(ValueError, match="must be relative path within vault"):
            write_digest_note(str(vault), "../../etc", "Content")

        # Attempt 2: Absolute path
        with pytest.raises(ValueError, match="must be relative path within vault"):
            write_digest_note(str(vault), "/etc/cron.d", "Content")

        # Attempt 3: Mixed traversal
        with pytest.raises(ValueError, match="must be relative path within vault"):
            write_digest_note(str(vault), "Drafts/../../../tmp", "Content")


def test_write_digest_note_allows_nested_relative_paths():
    """Valid nested relative paths are allowed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir)

        # Valid: nested relative path
        result = write_digest_note(str(vault), "Archive/2026/February", "Content")

        assert result.exists()
        assert "Archive/2026/February" in str(result)
        assert result.read_text() == "Content"
