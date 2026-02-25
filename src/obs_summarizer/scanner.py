"""Vault file scanning and filtering."""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional


def list_markdown_files(
    vault_path: str,
    include_folders: Optional[List[str]] = None,
    exclude_globs: Optional[List[str]] = None,
) -> List[Path]:
    """Discover markdown files in vault.

    Args:
        vault_path: Path to Obsidian vault
        include_folders: If provided, restrict search to these folders (relative to vault)
        exclude_globs: Glob patterns to exclude

    Returns:
        Sorted list of Path objects (oldest mtime first)
    """
    vault = Path(vault_path)

    # Determine search roots
    if include_folders:
        roots = []
        for folder in include_folders:
            resolved = (vault / folder).resolve()
            try:
                resolved.relative_to(vault.resolve())
            except ValueError:
                raise ValueError(
                    f"include_folders entry '{folder}' resolves outside vault boundary.\n"
                    f"Vault: {vault}\nResolved: {resolved}"
                )
            roots.append(resolved)
    else:
        roots = [vault]

    # Collect markdown files
    files = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(root.glob("**/*.md"))

    # Build exclusion set - expand globs to actual files
    excluded_paths = set()
    if exclude_globs:
        for pattern in exclude_globs:
            matches = list(vault.glob(pattern))
            for match in matches:
                if match.is_file():
                    excluded_paths.add(match)
                elif match.is_dir():
                    # Also exclude all files within this directory
                    excluded_paths.update(match.glob("**/*.md"))

    # Filter: exclude, skip symlinks, skip empty files
    filtered = [
        f
        for f in files
        if f not in excluded_paths and not f.is_symlink() and f.stat().st_size > 0
    ]

    # Sort by mtime (oldest first)
    return sorted(filtered, key=lambda p: p.stat().st_mtime)


def filter_files_since(files: List[Path], since_dt: datetime) -> List[Path]:
    """Filter files by modification time.

    Args:
        files: List of file paths
        since_dt: Minimum modification time (UTC)

    Returns:
        Files modified after since_dt, sorted by mtime (oldest first)
    """
    result = []
    for f in files:
        mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        if mtime > since_dt:
            result.append(f)
    return sorted(result, key=lambda p: p.stat().st_mtime)
