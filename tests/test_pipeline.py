"""Tests for pipeline module."""

from unittest.mock import MagicMock, patch

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
