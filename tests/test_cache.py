"""Tests for cache module."""

import json
from pathlib import Path

import pytest

from obs_summarizer.cache import load_cache, make_cache_key, save_cache


def test_make_cache_key_consistent():
    """Cache key is deterministic."""
    key1 = make_cache_key("/vault/article.md", 12345)
    key2 = make_cache_key("/vault/article.md", 12345)
    assert key1 == key2


def test_make_cache_key_different_for_different_inputs():
    """Different inputs produce different keys."""
    key1 = make_cache_key("/vault/article1.md", 12345)
    key2 = make_cache_key("/vault/article2.md", 12345)
    key3 = make_cache_key("/vault/article1.md", 54321)

    assert key1 != key2
    assert key1 != key3
    assert key2 != key3


def test_save_cache_creates_directory(tmp_cache, sample_summary):
    """Save cache creates directory if needed."""
    key = make_cache_key("/vault/article.md", 12345)
    save_cache(tmp_cache, key, sample_summary)

    assert Path(tmp_cache).exists()
    assert (Path(tmp_cache) / f"{key}.json").exists()


def test_save_cache_stores_data(tmp_cache, sample_summary):
    """Save cache stores data correctly."""
    key = make_cache_key("/vault/article.md", 12345)
    save_cache(tmp_cache, key, sample_summary)

    # Read back and verify
    cache_file = Path(tmp_cache) / f"{key}.json"
    loaded = json.loads(cache_file.read_text())
    assert loaded == sample_summary


def test_load_cache_missing():
    """Load missing cache returns None."""
    result = load_cache("/nonexistent/cache", "nonexistent_key")
    assert result is None


def test_load_cache_valid(tmp_cache, sample_summary):
    """Load valid cache returns data."""
    key = make_cache_key("/vault/article.md", 12345)
    save_cache(tmp_cache, key, sample_summary)

    loaded = load_cache(tmp_cache, key)
    assert loaded == sample_summary


def test_load_cache_corrupt_json(tmp_cache):
    """Load corrupt cache returns None and logs warning."""
    key = make_cache_key("/vault/article.md", 12345)
    cache_file = Path(tmp_cache) / f"{key}.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("invalid json {")

    result = load_cache(tmp_cache, key)
    assert result is None


def test_cache_key_hex_format():
    """Cache key is hex digest."""
    key = make_cache_key("/vault/article.md", 12345)
    assert len(key) == 64  # SHA256 hex is 64 chars
    assert all(c in "0123456789abcdef" for c in key)
