"""Tests for state module."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from obs_summarizer.state import get_since_datetime, load_state, save_state


def test_load_state_missing_file(tmp_state):
    """Missing state file returns default."""
    state = load_state(tmp_state)
    assert state == {"last_run_iso": None}


def test_load_state_valid(tmp_state, sample_state_dict):
    """Valid state loads correctly."""
    Path(tmp_state).write_text(json.dumps(sample_state_dict))
    state = load_state(tmp_state)
    assert state == sample_state_dict


def test_load_state_corrupt_json(tmp_state):
    """Corrupt JSON raises ValueError (cannot be silently recovered)."""
    Path(tmp_state).write_text("invalid json {")
    with pytest.raises(ValueError, match="corrupted"):
        load_state(tmp_state)


def test_save_state(tmp_state, sample_state_dict):
    """State saves correctly and atomically."""
    save_state(sample_state_dict, tmp_state)

    # Verify file exists and contains correct data
    assert Path(tmp_state).exists()
    loaded = json.loads(Path(tmp_state).read_text())
    assert loaded == sample_state_dict


def test_save_state_creates_directories(tmp_state):
    """Save state creates parent directories if needed."""
    nested_path = Path(tmp_state).parent / "nested" / "dirs" / "state.json"
    state = {"last_run_iso": "2026-02-25T12:00:00+00:00"}

    save_state(state, str(nested_path))

    assert nested_path.exists()
    assert json.loads(nested_path.read_text()) == state


def test_get_since_datetime_cli_override(sample_config, sample_state_dict):
    """CLI since_iso takes priority."""
    cli_time = "2026-02-20T10:00:00Z"
    result = get_since_datetime(sample_config, since_iso=cli_time, state=sample_state_dict)

    assert result == datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)


def test_get_since_datetime_config_file(sample_config, sample_state_dict):
    """Config file since_iso used if no CLI override."""
    sample_config["since_iso"] = "2026-02-21T10:00:00Z"
    result = get_since_datetime(sample_config, state=sample_state_dict)

    assert result == datetime(2026, 2, 21, 10, 0, 0, tzinfo=timezone.utc)


def test_get_since_datetime_checkpoint(sample_config, sample_state_dict):
    """Checkpoint used if no CLI or config override."""
    result = get_since_datetime(sample_config, state=sample_state_dict)

    assert result == datetime(2026, 2, 24, 12, 0, 0, tzinfo=timezone.utc)


def test_get_since_datetime_first_run(sample_config):
    """First run returns current time."""
    before = datetime.now(timezone.utc)
    result = get_since_datetime(sample_config, state={"last_run_iso": None})
    after = datetime.now(timezone.utc)

    assert before <= result <= after


def test_get_since_datetime_naive_iso_becomes_utc(sample_config):
    """ISO string without timezone becomes UTC."""
    result = get_since_datetime(sample_config, since_iso="2026-02-20T10:00:00")

    assert result == datetime(2026, 2, 20, 10, 0, 0, tzinfo=timezone.utc)
