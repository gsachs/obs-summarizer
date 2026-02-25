"""Shared test fixtures."""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture
def tmp_vault():
    """Create a temporary vault directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir) / "vault"
        vault.mkdir()

        # Create test structure
        (vault / "Clippings").mkdir()
        (vault / "templates").mkdir()
        (vault / ".obsidian").mkdir()

        # Create test markdown files
        note1 = vault / "Clippings" / "article1.md"
        note1.write_text("---\ntitle: Article 1\n---\n\n# Article 1\n\nContent here.")

        note2 = vault / "Clippings" / "article2.md"
        note2.write_text("# Article 2\n\nMore content.")

        template = vault / "templates" / "template.md"
        template.write_text("# Template\n\n{{variable}}")

        # Create empty file to test filtering
        empty = vault / "empty.md"
        empty.write_text("")

        yield vault


@pytest.fixture
def tmp_cache():
    """Create temporary cache directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_dir = Path(tmpdir) / "cache"
        cache_dir.mkdir()
        yield str(cache_dir)


@pytest.fixture
def tmp_state():
    """Create temporary state file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_file = Path(tmpdir) / "state.json"
        yield str(state_file)


@pytest.fixture
def sample_config(tmp_vault):
    """Create a sample config dictionary."""
    return {
        "vault_path": str(tmp_vault),
        "llm_backend": "claude",
        "claude_model": "claude-sonnet-4-6",
        "include_folders": [],
        "exclude_globs": ["**/.obsidian/**", "**/templates/**"],
        "digest_folder": "Daily Digests",
        "max_input_chars": 16000,
        "cache_dir": ".cache/summaries",
        "state_path": "state.json",
    }


@pytest.fixture
def sample_state_dict():
    """Create a sample state dictionary."""
    return {
        "last_run_iso": datetime(2026, 2, 24, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    }


@pytest.fixture
def sample_summary():
    """Create a sample summary dict."""
    return {
        "summary": "This is a test summary.",
        "bullets": ["Point 1", "Point 2", "Point 3"],
        "why_it_matters": "Because it's important.",
        "tags": ["test", "example"],
        "notable_quote": "A notable quote.",
        "path": "/vault/article.md",
        "mtime_utc": datetime.now(timezone.utc).isoformat(),
    }
