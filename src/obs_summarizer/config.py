"""Configuration loading and validation."""

import os
from pathlib import Path
from typing import Any, Optional

import yaml


class ConfigError(Exception):
    """Raised when configuration is invalid."""

    pass


def load_config(config_path: Optional[str] = None) -> dict:
    """Load and validate configuration from YAML file.

    Args:
        config_path: Path to config file. Defaults to 'config.yaml' in current directory.

    Returns:
        Validated configuration dictionary.

    Raises:
        ConfigError: If config file is missing, invalid, or validation fails.
    """
    if config_path is None:
        config_path = "config.yaml"

    config_file = Path(config_path)
    if not config_file.exists():
        raise ConfigError(f"Config file not found: {config_path}")

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {config_path}: {e}") from e

    if config is None:
        config = {}

    # Validate required fields
    if "vault_path" not in config:
        raise ConfigError("Missing required field: vault_path")

    vault_path = Path(config["vault_path"]).expanduser()
    if not vault_path.exists():
        raise ConfigError(f"Vault path does not exist: {vault_path}")
    if not vault_path.is_dir():
        raise ConfigError(f"Vault path is not a directory: {vault_path}")

    config["vault_path"] = str(vault_path)

    # Validate llm_backend
    llm_backend = config.get("llm_backend", "claude")
    if llm_backend not in ("claude", "local"):
        raise ConfigError(f"Invalid llm_backend: {llm_backend}. Must be 'claude' or 'local'.")
    config["llm_backend"] = llm_backend

    # Validate Claude settings
    if llm_backend == "claude":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise ConfigError(
                "llm_backend is 'claude' but ANTHROPIC_API_KEY environment variable is not set"
            )
        config.setdefault("claude_model", "claude-sonnet-4-6")

    # Validate local settings
    if llm_backend == "local":
        if "local_base_url" not in config:
            raise ConfigError("llm_backend is 'local' but local_base_url is not configured")
        config.setdefault("local_model", "llama-3.2-3b-instruct")

    # Set defaults
    config.setdefault("include_folders", [])
    config.setdefault("exclude_globs", [])
    config.setdefault("digest_folder", "Daily Digests")
    config.setdefault("max_input_chars", 16000)
    config.setdefault("cache_dir", ".cache/summaries")
    config.setdefault("state_path", "state.json")

    return config
