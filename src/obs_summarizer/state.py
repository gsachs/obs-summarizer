"""State and checkpoint management."""

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def load_state(state_path: str) -> dict:
    """Load checkpoint state from JSON file.

    Args:
        state_path: Path to state.json

    Returns:
        State dictionary with 'last_run_iso' key (may be None on first run)
    """
    path = Path(state_path)

    if not path.exists():
        return {"last_run_iso": None}

    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load state from {state_path}: {e}. Treating as first run.")
        return {"last_run_iso": None}


def save_state(state: dict, state_path: str) -> None:
    """Save state atomically to disk.

    Writes to temp file first, then renames to avoid partial writes.

    Args:
        state: State dictionary
        state_path: Path to state.json
    """
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file, then rename atomically
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as tmp:
        json.dump(state, tmp, indent=2)
        tmp_path = tmp.name

    Path(tmp_path).replace(path)


def get_since_datetime(
    config: dict, since_iso: Optional[str] = None, state: Optional[dict] = None
) -> datetime:
    """Determine the 'since' datetime for file filtering.

    Priority:
    1. since_iso argument (CLI override)
    2. config['since_iso'] (config file)
    3. state['last_run_iso'] (checkpoint)
    4. 24 hours ago (first run default)

    Args:
        config: Configuration dictionary
        since_iso: Optional ISO format string from CLI
        state: Optional state dictionary

    Returns:
        UTC datetime for filtering
    """
    # CLI override
    if since_iso:
        # Convert Z suffix to +00:00 for Python 3.9 compatibility
        since_iso = since_iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(since_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    # Config file
    if config.get("since_iso"):
        config_iso = config["since_iso"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(config_iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    # Checkpoint
    if state and state.get("last_run_iso"):
        checkpoint_iso = state["last_run_iso"].replace("Z", "+00:00")
        return datetime.fromisoformat(checkpoint_iso)

    # First run: default to now (no files will be found on first run)
    # User can override with --since to process historical files
    return datetime.now(timezone.utc)
