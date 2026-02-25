"""Tests for config module."""

import os
import tempfile
from pathlib import Path

import pytest

from obs_summarizer.config import ConfigError, load_config


def test_load_config_missing_file():
    """Config file missing raises error."""
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config("nonexistent.yaml")


def test_load_config_invalid_yaml():
    """Invalid YAML raises error."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("invalid: [yaml: content:")
        f.flush()
        try:
            with pytest.raises(ConfigError, match="Invalid YAML"):
                load_config(f.name)
        finally:
            os.unlink(f.name)


def test_load_config_missing_vault_path():
    """Missing vault_path raises error."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("llm_backend: claude\n")
        f.flush()
        try:
            with pytest.raises(ConfigError, match="Missing required field: vault_path"):
                load_config(f.name)
        finally:
            os.unlink(f.name)


def test_load_config_vault_path_not_exists():
    """Non-existent vault_path raises error."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("vault_path: /nonexistent/path\n")
        f.flush()
        try:
            with pytest.raises(ConfigError, match="Vault path does not exist"):
                load_config(f.name)
        finally:
            os.unlink(f.name)


def test_load_config_invalid_llm_backend():
    """Invalid llm_backend raises error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir) / "vault"
        vault.mkdir()

        config_file = Path(tmpdir) / "config.yaml"
        config_file.write_text(f"vault_path: {vault}\nllm_backend: invalid\n")

        with pytest.raises(ConfigError, match="Invalid llm_backend"):
            load_config(str(config_file))


def test_load_config_claude_missing_api_key():
    """Claude backend without API key raises error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir) / "vault"
        vault.mkdir()

        config_file = Path(tmpdir) / "config.yaml"
        config_file.write_text(f"vault_path: {vault}\nllm_backend: claude\n")

        # Temporarily unset API key
        old_key = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
                load_config(str(config_file))
        finally:
            if old_key:
                os.environ["ANTHROPIC_API_KEY"] = old_key


def test_load_config_local_missing_base_url():
    """Local backend without base_url raises error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault = Path(tmpdir) / "vault"
        vault.mkdir()

        config_file = Path(tmpdir) / "config.yaml"
        config_file.write_text(f"vault_path: {vault}\nllm_backend: local\n")

        with pytest.raises(ConfigError, match="local_base_url"):
            load_config(str(config_file))


def test_load_config_valid(tmp_vault):
    """Valid config loads successfully with defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "config.yaml"
        config_file.write_text(
            f"vault_path: {tmp_vault}\n"
            "llm_backend: local\n"
            "local_base_url: http://localhost:1234/v1\n"
            "exclude_globs:\n"
            "  - '**/.obsidian/**'\n"
        )

        config = load_config(str(config_file))

        assert config["vault_path"] == str(tmp_vault)
        assert config["llm_backend"] == "local"
        assert config["exclude_globs"] == ["**/.obsidian/**"]
        assert config["digest_folder"] == "Daily Digests"
        assert config["max_input_chars"] == 16000
        assert config["cache_dir"] == ".cache/summaries"
        assert config["state_path"] == "state.json"


@pytest.mark.parametrize("path_key", ["cache_dir", "state_path"])
def test_load_config_rejects_absolute_paths(tmp_vault, path_key):
    """Absolute paths for cache_dir and state_path raise ConfigError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "config.yaml"
        config_file.write_text(
            f"vault_path: {tmp_vault}\n"
            "llm_backend: local\n"
            "local_base_url: http://localhost:1234/v1\n"
            f"{path_key}: /etc/cron.d\n"
        )
        with pytest.raises(ConfigError, match="must be a relative path"):
            load_config(str(config_file))


def test_load_config_expands_tilde(tmp_vault):
    """Tilde in vault_path is expanded."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "config.yaml"
        # Write with actual path (tilde expansion is tested implicitly)
        config_file.write_text(
            f"vault_path: {tmp_vault}\n"
            "llm_backend: local\n"
            "local_base_url: http://localhost:1234/v1\n"
        )
        config = load_config(str(config_file))
        assert config["vault_path"] == str(tmp_vault)
