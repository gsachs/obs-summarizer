"""Write digest notes to Obsidian vault."""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def write_digest_note(
    vault_path: str,
    digest_folder: str,
    digest_content: str,
    date: Optional[datetime] = None,
) -> Path:
    """Write digest as a new Obsidian note.

    Args:
        vault_path: Path to Obsidian vault
        digest_folder: Folder name for digests (relative to vault)
        digest_content: Markdown content of digest
        date: Date for digest filename (defaults to today UTC)

    Returns:
        Path to written digest file

    Raises:
        ValueError: If digest_folder tries to escape vault boundary
    """
    if date is None:
        date = datetime.now(timezone.utc)

    vault = Path(vault_path).resolve()

    # SECURITY: Validate digest_folder is relative and stays within vault
    if digest_folder.startswith("/") or ".." in digest_folder:
        raise ValueError(
            f"digest_folder must be relative path within vault: {digest_folder}"
        )

    digest_dir = vault / digest_folder
    digest_dir = digest_dir.resolve()

    # Verify it's still within vault after resolving symlinks
    try:
        digest_dir.relative_to(vault)
    except ValueError:
        raise ValueError(
            f"digest_folder would escape vault boundary: {digest_folder}\n"
            f"Vault: {vault}\n"
            f"Resolved path: {digest_dir}"
        )

    digest_dir.mkdir(parents=True, exist_ok=True)

    # Filename: YYYY-MM-DD-digest.md
    filename = f"{date.strftime('%Y-%m-%d')}-digest.md"
    digest_path = digest_dir / filename

    # Write file (overwrites if exists - idempotent)
    digest_path.write_text(digest_content, encoding="utf-8")
    logger.info(f"Wrote digest to {digest_path}")

    return digest_path


def format_digest_markdown(
    summaries: List[Dict],
    date: Optional[datetime] = None,
) -> str:
    """Format summaries into digest markdown.

    Args:
        summaries: List of summary dicts (from summarizer)
        date: Date for digest header (defaults to today UTC)

    Returns:
        Formatted markdown string
    """
    if date is None:
        date = datetime.now(timezone.utc)

    # YAML frontmatter
    frontmatter = (
        f"---\n"
        f"type: digest\n"
        f"date: {date.strftime('%Y-%m-%d')}\n"
        f"articles_count: {len(summaries)}\n"
        f"generated_by: obs-digest\n"
        f"---\n"
    )

    # Header
    header = f"\n# Daily Digest — {date.strftime('%B %d, %Y')}\n"

    # Group by theme (inferred from tags)
    articles_by_theme = {}
    for i, summary in enumerate(summaries):
        theme = summary.get("tags", ["Uncategorized"])[0] or "Uncategorized"
        if theme not in articles_by_theme:
            articles_by_theme[theme] = []
        articles_by_theme[theme].append((i + 1, summary))

    # Format articles grouped by theme
    body = ""
    for theme, articles in sorted(articles_by_theme.items()):
        body += f"\n## {theme.title()}\n"
        for article_num, summary in articles:
            body += f"\n### Article {article_num}\n"

            # Quote if available
            quote = summary.get("notable_quote")
            if quote:
                body += f"\n> {quote}\n"

            # Summary
            body += f"\n**Summary:** {summary.get('summary', '')}\n"

            # Bullets
            bullets = summary.get("bullets", [])
            if bullets:
                body += "\n**Key takeaways:**\n"
                for bullet in bullets:
                    body += f"- {bullet}\n"

            # Why it matters
            why = summary.get("why_it_matters")
            if why:
                body += f"\n**Why it matters:** {why}\n"

            # Tags
            tags = summary.get("tags", [])
            if tags:
                tag_str = " ".join(f"#{tag}" for tag in tags)
                body += f"\n**Tags:** {tag_str}\n"

    # Top insights summary (if generated)
    if len(summaries) > 1:
        body += "\n---\n\n## Top Insights\n\n_Cross-cutting themes across saved articles_\n"

    return frontmatter + header + body
