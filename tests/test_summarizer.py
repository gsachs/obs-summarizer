"""Tests for summarizer module."""

import json
from unittest.mock import MagicMock

import pytest

from obs_summarizer.llm import LLMResponse
from obs_summarizer.summarizer import (
    create_rollup,
    strip_frontmatter,
    summarize_note,
    truncate_to_chars,
)


def test_strip_frontmatter_with_yaml():
    """Strip YAML frontmatter from markdown."""
    content = "---\ntitle: Test\n---\n\n# Heading\n\nBody"
    result = strip_frontmatter(content)
    assert result == "# Heading\n\nBody"


def test_strip_frontmatter_without_yaml():
    """Content without frontmatter returned as-is."""
    content = "# Heading\n\nBody"
    result = strip_frontmatter(content)
    assert result == "# Heading\n\nBody"


def test_truncate_to_chars_under_limit():
    """Text under limit returned unchanged."""
    text = "This is short text"
    result = truncate_to_chars(text, 100)
    assert result == text


def test_truncate_to_chars_over_limit():
    """Text over limit is truncated with marker."""
    text = "This is a very long text that exceeds the limit"
    result = truncate_to_chars(text, 20)
    assert len(result) <= 20 + len("\n[... truncated]")
    assert "[... truncated]" in result


def test_summarize_note_valid_json():
    """Summarize note parses valid JSON response."""
    mock_llm = MagicMock()
    summary_json = {
        "summary": "Test summary",
        "bullets": ["Point 1", "Point 2"],
        "why_it_matters": "It matters",
        "tags": ["test"],
        "notable_quote": "Quote",
    }
    mock_llm.return_value = LLMResponse(content=json.dumps(summary_json))

    result = summarize_note(mock_llm, "Test content", "test.md")

    assert result["summary"] == "Test summary"
    assert result["bullets"] == ["Point 1", "Point 2"]
    assert result["why_it_matters"] == "It matters"
    assert result["tags"] == ["test"]
    assert result["notable_quote"] == "Quote"


def test_summarize_note_strips_frontmatter():
    """Frontmatter is stripped before sending to LLM."""
    mock_llm = MagicMock()
    mock_llm.return_value = LLMResponse(
        content=json.dumps(
            {
                "summary": "Test",
                "bullets": [],
                "why_it_matters": "Test",
                "tags": [],
                "notable_quote": None,
            }
        )
    )

    content = "---\ntitle: Test\n---\n\n# Content"
    summarize_note(mock_llm, content, "test.md")

    # Verify the LLM was called with stripped content
    call_args = mock_llm.call_args
    assert "---" not in call_args[0][1]
    assert "# Content" in call_args[0][1]


def test_summarize_note_truncates_long_content():
    """Long content is truncated."""
    mock_llm = MagicMock()
    mock_llm.return_value = LLMResponse(
        content=json.dumps(
            {
                "summary": "Test",
                "bullets": [],
                "why_it_matters": "Test",
                "tags": [],
                "notable_quote": None,
            }
        )
    )

    long_content = "A" * 20000
    summarize_note(mock_llm, long_content, "test.md", max_chars=10000)

    # Verify the LLM was called with truncated content
    call_args = mock_llm.call_args
    user_message = call_args[0][1]
    assert len(user_message) < 15000


def test_summarize_note_invalid_json_retries():
    """Invalid JSON triggers retry with stricter prompt."""
    mock_llm = MagicMock()
    # First call returns invalid JSON, second returns valid
    mock_llm.side_effect = [
        LLMResponse(content="Not valid JSON"),
        LLMResponse(
            content=json.dumps(
                {
                    "summary": "Test",
                    "bullets": [],
                    "why_it_matters": "Test",
                    "tags": [],
                    "notable_quote": None,
                }
            )
        ),
    ]

    result = summarize_note(mock_llm, "Test content", "test.md")

    # Verify retry happened
    assert mock_llm.call_count == 2
    assert result["summary"] == "Test"


def test_summarize_note_sets_defaults():
    """Missing fields are set to defaults."""
    mock_llm = MagicMock()
    mock_llm.return_value = LLMResponse(content=json.dumps({"summary": "Test"}))

    result = summarize_note(mock_llm, "Test", "test.md")

    assert result["summary"] == "Test"
    assert result["bullets"] == []
    assert result["why_it_matters"] == ""
    assert result["tags"] == []
    assert result["notable_quote"] is None


def test_create_rollup_empty():
    """Empty summaries list returns placeholder."""
    mock_llm = MagicMock()
    result = create_rollup(mock_llm, [])
    assert "No notes" in result


def test_create_rollup_formats_summaries():
    """Rollup formats summaries into digest."""
    mock_llm = MagicMock()
    mock_llm.return_value = LLMResponse(content="# Digest\n\nFormatted content")

    summaries = [
        {
            "summary": "Article 1 summary",
            "bullets": ["Point 1", "Point 2"],
            "why_it_matters": "Important",
            "tags": ["ai"],
            "notable_quote": "Quote 1",
        },
        {
            "summary": "Article 2 summary",
            "bullets": ["Point 3", "Point 4"],
            "why_it_matters": "Also important",
            "tags": ["ml"],
            "notable_quote": "Quote 2",
        },
    ]

    result = create_rollup(mock_llm, summaries)

    # Verify the LLM was called with formatted summaries
    call_args = mock_llm.call_args
    user_message = call_args[0][1]
    assert "Article 1 summary" in user_message
    assert "Article 2 summary" in user_message
    assert "Point 1" in user_message
    assert result == "# Digest\n\nFormatted content"
