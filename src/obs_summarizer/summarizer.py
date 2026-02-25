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
        "You are a knowledge summarizer. Your task is to extract key insights from the given text and return ONLY a JSON object.\n\n"
        "CRITICAL RULES:\n"
        "1. Return ONLY valid JSON - no markdown, no explanation, no preamble\n"
        "2. The response must start with { and end with }\n"
        "3. All strings must be properly escaped\n"
        "4. Arrays must be valid JSON arrays\n\n"
        "Required fields in the JSON object:\n"
        '- "summary": string (1-2 sentences summarizing the main point)\n'
        '- "bullets": array of 5 strings (key takeaways)\n'
        '- "why_it_matters": string (1 sentence on relevance)\n'
        '- "tags": array of 1-3 strings (topic tags)\n'
        '- "notable_quote": string or null (the most insightful quote from the text)\n\n'
        "COMPLETE EXAMPLE:\n"
        "{\n"
        '  "summary": "This article discusses privacy in the digital age and advocates for journaling.",\n'
        '  "bullets": ["Social media inverted privacy norms", "Constant sharing is now the default", "Privacy requires active effort", "Journaling offers a private alternative", "Personal reflection is valuable"],\n'
        '  "why_it_matters": "Understanding privacy tradeoffs helps readers make informed choices.",\n'
        '  "tags": ["privacy", "technology", "reflection"],\n'
        '  "notable_quote": "Sharing has become the default; not sharing is the exception."\n'
        "}\n\n"
        "Return ONLY the JSON object, starting with { and ending with }. No other text."
    )

    user = f"Title: {title}\n\nContent:\n{content}"

    response = llm_call(system, user)

    # Parse JSON response with robust extraction
    def extract_json(content: str) -> dict:
        """Extract JSON from response, handling markdown code blocks or extra text."""
        original_content = content
        content = content.strip()

        # Method 1: Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Method 2: Try extracting from markdown code block (```json ... ```)
        if "```json" in content:
            # Find opening fence
            start_idx = content.find("```json")
            if start_idx >= 0:
                # Start after the opening fence and any newline
                start = start_idx + 7  # len("```json")
                if start < len(content) and content[start] == "\n":
                    start += 1

                # Find closing fence
                end_idx = content.find("```", start)
                if end_idx > start:
                    json_str = content[start:end_idx].strip()
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        pass

        # Method 3: Try extracting first {...} JSON object
        # Find the first { and last } and try to parse that
        brace_start = content.find("{")
        if brace_start >= 0:
            # Find the LAST closing brace to capture the entire object
            brace_end = content.rfind("}")
            if brace_end > brace_start:
                json_str = content[brace_start:brace_end+1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    # Try to find a valid JSON endpoint by looking for closing patterns
                    # In case there are multiple closing braces
                    for i in range(brace_end, brace_start, -1):
                        if content[i] == "}":
                            try:
                                candidate = content[brace_start:i+1]
                                return json.loads(candidate)
                            except json.JSONDecodeError:
                                pass

        # If all extraction methods fail, provide detailed error
        raise json.JSONDecodeError(
            f"Could not extract valid JSON from response",
            original_content[:500], 0
        )

    try:
        summary = extract_json(response.content)
    except json.JSONDecodeError as first_error:
        logger.debug(f"First JSON parse failed for {title}. Response length: {len(response.content)}")
        logger.debug(f"First 500 chars: {response.content[:500]}")
        logger.warning(f"Failed to parse JSON for {title}. Retrying with stricter prompt.")
        # Retry with stricter instructions
        strict_system = (
            "STRICT JSON OUTPUT ONLY.\n\n"
            "Return a valid JSON object with these exact fields:\n"
            '- "summary": 1-2 sentences\n'
            '- "bullets": array of 5 strings\n'
            '- "why_it_matters": 1 sentence\n'
            '- "tags": array of 1-3 strings\n'
            '- "notable_quote": string or null\n\n'
            "DO NOT include markdown code blocks (no ```).\n"
            "DO NOT include any text before or after the JSON object.\n"
            "Response must start with { and end with }.\n\n"
            "Example:\n"
            '{"summary":"...", "bullets":["..."], "why_it_matters":"...", "tags":["..."], "notable_quote":null}'
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
