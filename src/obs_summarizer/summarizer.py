"""Note summarization and rollup logic."""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from obs_summarizer.llm import LLMResponse

logger = logging.getLogger(__name__)


def strip_frontmatter(text: str) -> str:
    """Remove YAML frontmatter from markdown.

    Args:
        text: Markdown content

    Returns:
        Content without frontmatter
    """
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].lstrip()
    return text


def truncate_to_chars(text: str, max_chars: int) -> str:
    """Truncate text to max_chars with marker.

    Args:
        text: Content to truncate
        max_chars: Maximum characters

    Returns:
        Truncated content (or original if under limit)
    """
    if len(text) > max_chars:
        return text[:max_chars] + "\n[... truncated]"
    return text


def summarize_note(
    llm_call: Callable, content: str, title: str, max_chars: int = 16000
) -> Dict[str, Any]:
    """Summarize a single note.

    Args:
        llm_call: LLM client callable (system, user) -> LLMResponse
        content: Note markdown content
        title: Note title/filename
        max_chars: Max input chars before truncation

    Returns:
        Summary dict with fields: summary, bullets, why_it_matters, tags, notable_quote
    """
    # Clean content
    content = strip_frontmatter(content).strip()
    content = truncate_to_chars(content, max_chars)

    system = (
        "You are a knowledge summarizer. Extract key insights from the given text.\n\n"
        "Return ONLY a valid JSON object (nothing before or after) with these exact fields:\n"
        "- summary: 1-2 sentences summarizing the main point\n"
        "- bullets: array of 5 key takeaways (strings)\n"
        "- why_it_matters: 1 sentence on relevance\n"
        "- tags: array of 1-3 topic tags (strings)\n"
        "- notable_quote: the most insightful quote from the text, or null\n\n"
        "Example response format (valid JSON only):\n"
        '{"summary": "...", "bullets": [...], "why_it_matters": "...", "tags": [...], "notable_quote": "..."}'
    )

    user = f"Title: {title}\n\nContent:\n{content}"

    response = llm_call(system, user)

    # Parse JSON response with robust extraction
    def extract_json(content: str) -> dict:
        """Extract JSON from response, handling markdown code blocks or extra text."""
        content = content.strip()

        # Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Try extracting from markdown code block
        if "```json" in content:
            start = content.find("```json") + 7
            end = content.find("```", start)
            if end > start:
                try:
                    return json.loads(content[start:end].strip())
                except json.JSONDecodeError:
                    pass

        # Try extracting first {...} object
        start = content.find("{")
        if start >= 0:
            end = content.rfind("}")
            if end > start:
                try:
                    return json.loads(content[start:end+1])
                except json.JSONDecodeError:
                    pass

        # If all extraction methods fail
        raise json.JSONDecodeError(
            f"Could not extract valid JSON from response: {content[:200]}...",
            content, 0
        )

    try:
        summary = extract_json(response.content)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse JSON for {title}. Retrying with stricter prompt.")
        # Retry with stricter instructions
        strict_system = (
            system
            + "\n\nIMPORTANT: Return ONLY the JSON object, nothing else. No markdown, no explanation."
        )
        response = llm_call(strict_system, user)
        try:
            summary = extract_json(response.content)
        except json.JSONDecodeError as e:
            # JSON parsing failed even after retry - this is a critical error
            # Raise instead of returning fake data that would silently corrupt the digest
            raise ValueError(
                f"Failed to parse JSON response for {title} after retry.\n"
                f"LLM response: {response.content[:200]}...\n"
                f"Error: {e}"
            ) from e

    # Fill in defaults for missing fields (but only if JSON was successfully parsed)
    summary.setdefault("summary", "")
    summary.setdefault("bullets", [])
    summary.setdefault("why_it_matters", "")
    summary.setdefault("tags", [])
    summary.setdefault("notable_quote", None)

    return summary


def create_rollup(llm_call: Callable, summaries: List[Dict[str, Any]]) -> str:
    """Create a rollup digest from per-note summaries.

    Args:
        llm_call: LLM client callable
        summaries: List of summary dicts (from summarize_note)

    Returns:
        Markdown digest content
    """
    if not summaries:
        return "# Daily Digest\n\nNo notes to summarize today."

    # Format summaries for the rollup prompt
    summaries_text = ""
    for i, summary in enumerate(summaries, 1):
        summaries_text += f"\n---\n**Article {i}**\n"
        summaries_text += f"- Summary: {summary.get('summary', '')}\n"
        summaries_text += (
            f"- Key points: {', '.join(summary.get('bullets', [])[:3])}\n"
        )
        summaries_text += f"- Why it matters: {summary.get('why_it_matters', '')}\n"
        summaries_text += f"- Tags: {', '.join(summary.get('tags', []))}\n"

    system = (
        "You are a curator creating a daily reading digest. "
        "Your job is to:\n"
        "1. Group the article summaries by theme or topic\n"
        "2. For each group, write a brief 1-2 sentence overview\n"
        "3. At the end, list 3-5 cross-cutting insights that span multiple articles\n\n"
        "Return markdown formatted output with clear headings and organization."
    )

    user = f"Please create a reading digest from these summaries:\n{summaries_text}"

    response = llm_call(system, user)
    return response.content
