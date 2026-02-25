"""Tests for CLI module."""

from unittest.mock import patch

import pytest

from obs_summarizer.cli import main


def test_cli_help(capsys):
    """CLI help works."""
    with patch("sys.argv", ["obs-digest", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0


def test_cli_missing_config():
    """Missing config file returns error."""
    with patch("sys.argv", ["obs-digest", "--config", "/nonexistent/config.yaml"]):
        result = main()
        assert result == 1


def test_cli_config_arg_parsing(tmp_path):
    """CLI accepts config argument."""
    from obs_summarizer.config import ConfigError

    bad_config = str(tmp_path / "config.yaml")
    # File doesn't exist, so it should fail at config load
    with patch("sys.argv", ["obs-digest", "--config", bad_config]):
        result = main()
        assert result == 1  # Config load fails
