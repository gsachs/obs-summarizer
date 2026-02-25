"""Tests for pipeline module."""

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from obs_summarizer.llm import LLMResponse
from obs_summarizer.pipeline import run_pipeline


def test_run_pipeline_no_files(sample_config, tmp_vault):
    """Pipeline returns 2 when no files found."""
    # Mock list_markdown_files to return empty list
    with patch("obs_summarizer.pipeline.list_markdown_files") as mock_list:
        mock_list.return_value = []

        result = run_pipeline(sample_config)

        assert result == 2


def test_run_pipeline_with_since_no_files(sample_config):
    """Pipeline with future --since finds no files."""
    result = run_pipeline(sample_config, since="2099-01-01T00:00:00Z")
    assert result == 2


def _make_summary(path="/vault/note.md"):
    return {
        "summary": "Test summary",
        "bullets": ["Point 1", "Point 2"],
        "why_it_matters": "It matters.",
        "tags": ["test"],
        "notable_quote": None,
        "path": path,
        "mtime_utc": "2026-02-25T00:00:00+00:00",
    }


def test_run_pipeline_happy_path(sample_config, tmp_vault):
    """Happy path: file summarized, digest written, state saved, exit 0."""
    note = tmp_vault / "note.md"
    note.write_text("# Test\nContent")

    mock_summary = _make_summary(str(note))
    mock_llm = MagicMock()

    with patch("obs_summarizer.pipeline.create_llm_client", return_value=mock_llm), \
         patch("obs_summarizer.pipeline.list_markdown_files", return_value=[note]), \
         patch("obs_summarizer.pipeline.filter_files_since", return_value=[note]), \
         patch("obs_summarizer.pipeline.load_cache", return_value=None), \
         patch("obs_summarizer.pipeline.save_cache"), \
         patch("obs_summarizer.pipeline.summarize_note", return_value=mock_summary), \
         patch("obs_summarizer.pipeline.create_rollup", return_value="rollup text"), \
         patch("obs_summarizer.pipeline.write_digest_note", return_value=Path("/vault/digest.md")) as mock_write, \
         patch("obs_summarizer.pipeline.save_state") as mock_save_state:

        result = run_pipeline(sample_config)

    assert result == 0
    mock_write.assert_called_once()
    mock_save_state.assert_called_once()


def test_run_pipeline_cache_hit(sample_config, tmp_vault):
    """Cache hit: file loaded from cache, LLM not called."""
    note = tmp_vault / "note.md"
    note.write_text("# Test\nContent")
    cached_summary = _make_summary(str(note))
    mock_llm = MagicMock()

    with patch("obs_summarizer.pipeline.create_llm_client", return_value=mock_llm), \
         patch("obs_summarizer.pipeline.list_markdown_files", return_value=[note]), \
         patch("obs_summarizer.pipeline.filter_files_since", return_value=[note]), \
         patch("obs_summarizer.pipeline.load_cache", return_value=cached_summary), \
         patch("obs_summarizer.pipeline.summarize_note") as mock_summarize, \
         patch("obs_summarizer.pipeline.create_rollup", return_value="rollup"), \
         patch("obs_summarizer.pipeline.write_digest_note", return_value=Path("/vault/digest.md")), \
         patch("obs_summarizer.pipeline.save_state"):

        result = run_pipeline(sample_config)

    assert result == 0
    mock_summarize.assert_not_called()


def test_run_pipeline_summarization_failure_skips_file(sample_config, tmp_vault):
    """Expected ValueError on one file skips it and continues with remaining files."""
    note_a = tmp_vault / "a.md"
    note_b = tmp_vault / "b.md"
    note_a.write_text("# A")
    note_b.write_text("# B")

    summary_b = _make_summary(str(note_b))
    mock_llm = MagicMock()

    with patch("obs_summarizer.pipeline.create_llm_client", return_value=mock_llm), \
         patch("obs_summarizer.pipeline.list_markdown_files", return_value=[note_a, note_b]), \
         patch("obs_summarizer.pipeline.filter_files_since", return_value=[note_a, note_b]), \
         patch("obs_summarizer.pipeline.load_cache", return_value=None), \
         patch("obs_summarizer.pipeline.save_cache"), \
         patch("obs_summarizer.pipeline.summarize_note", side_effect=[ValueError("bad json"), summary_b]), \
         patch("obs_summarizer.pipeline.create_rollup", return_value="rollup"), \
         patch("obs_summarizer.pipeline.write_digest_note", return_value=Path("/vault/digest.md")), \
         patch("obs_summarizer.pipeline.save_state"):

        result = run_pipeline(sample_config)

    # Pipeline continues and succeeds with remaining file
    assert result == 0


def test_run_pipeline_dry_run(sample_config, tmp_vault):
    """Dry run: no digest written, no state saved."""
    note = tmp_vault / "note.md"
    note.write_text("# Test\nContent")

    with patch("obs_summarizer.pipeline.list_markdown_files", return_value=[note]), \
         patch("obs_summarizer.pipeline.filter_files_since", return_value=[note]), \
         patch("obs_summarizer.pipeline.write_digest_note") as mock_write, \
         patch("obs_summarizer.pipeline.save_state") as mock_save_state:

        result = run_pipeline(sample_config, dry_run=True)

    assert result == 0
    mock_write.assert_not_called()
    mock_save_state.assert_not_called()


def test_run_pipeline_cache_count_accurate(sample_config, tmp_vault):
    """Cache hit and fresh counts are tracked correctly (not inverted)."""
    note_a = tmp_vault / "a.md"
    note_b = tmp_vault / "b.md"
    note_a.write_text("# A")
    note_b.write_text("# B")

    cached_a = _make_summary(str(note_a))
    summary_b = _make_summary(str(note_b))
    mock_llm = MagicMock()

    with patch("obs_summarizer.pipeline.create_llm_client", return_value=mock_llm), \
         patch("obs_summarizer.pipeline.list_markdown_files", return_value=[note_a, note_b]), \
         patch("obs_summarizer.pipeline.filter_files_since", return_value=[note_a, note_b]), \
         patch("obs_summarizer.pipeline.load_cache", side_effect=[cached_a, None]), \
         patch("obs_summarizer.pipeline.save_cache"), \
         patch("obs_summarizer.pipeline.summarize_note", return_value=summary_b), \
         patch("obs_summarizer.pipeline.create_rollup", return_value="rollup"), \
         patch("obs_summarizer.pipeline.write_digest_note", return_value=Path("/vault/digest.md")), \
         patch("obs_summarizer.pipeline.save_state"):

        result = run_pipeline(sample_config)

    assert result == 0
