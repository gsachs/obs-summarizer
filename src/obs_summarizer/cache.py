"""Summary caching system."""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def make_cache_key(file_path: str, mtime_ns: int) -> str:
    """Generate cache key from file path and nanosecond mtime.

    Args:
        file_path: Full path to markdown file
        mtime_ns: File modification time in nanoseconds

    Returns:
        SHA256 hex digest
    """
    key_input = f"{file_path}:{mtime_ns}"
    return hashlib.sha256(key_input.encode()).hexdigest()


def load_cache(cache_dir: str, cache_key: str) -> Optional[Dict[str, Any]]:
    """Load cached summary from disk.

    Args:
        cache_dir: Cache directory path
        cache_key: Cache key (from make_cache_key)

    Returns:
        Cached summary dict, or None if missing/corrupt
    """
    cache_path = Path(cache_dir) / f"{cache_key}.json"

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load cache {cache_key}: {e}. Regenerating.")
        return None


def save_cache(cache_dir: str, cache_key: str, data: Dict[str, Any]) -> None:
    """Save summary to cache.

    Args:
        cache_dir: Cache directory path
        cache_key: Cache key (from make_cache_key)
        data: Summary data to cache
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    cache_file = cache_path / f"{cache_key}.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
