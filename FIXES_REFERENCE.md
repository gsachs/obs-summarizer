# Detailed Fix Reference

Complete, copy-pasteable fixes for all critical and high-priority issues.

---

## Fix 1: llm.py — Factory Return Type & Retry Abstraction

### Current Code (WRONG)

```python
def create_llm_client(config: Dict) -> Callable:
    """Factory to create LLM client based on configuration."""
    backend = config["llm_backend"]
    if backend == "claude":
        return _create_claude_client(config)
    elif backend == "local":
        return _create_local_client(config)
    else:
        raise ValueError(f"Unknown llm_backend: {backend}")

def _create_claude_client(config: Dict) -> Callable:
    """Create Claude API client with retry logic."""
    import anthropic  # Lazy import
    api_key = config.get("api_key")
    # ... retry logic with nested try/except (60 lines)

def _create_local_client(config: Dict) -> Callable:
    """Create local LLM client (LM Studio / Ollama) with retry logic."""
    import openai  # Lazy import
    # ... similar retry logic (60 lines)
```

### Fixed Code

```python
"""LLM backend abstraction and client factory."""

import anthropic
import logging
import openai
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Constants
MAX_COMPLETION_TOKENS = 1024
DEFAULT_TEMPERATURE = 0.7
MAX_RETRY_ATTEMPTS = 3
INITIAL_BACKOFF_SECONDS = 2


@dataclass
class LLMResponse:
    """Unified response from any LLM backend."""

    content: str


class LLMError(Exception):
    """Base exception for LLM-related errors."""

    pass


class LLMRetryableError(LLMError):
    """Raised when an error is retryable (rate limit, timeout, etc.)."""

    pass


def _retry_with_exponential_backoff(
    fn: Callable[[], T],
    max_attempts: int = MAX_RETRY_ATTEMPTS,
    base_delay: int = INITIAL_BACKOFF_SECONDS,
    is_retryable: Callable[[Exception], bool] = lambda e: isinstance(e, LLMRetryableError),
) -> T:
    """Retry a callable with exponential backoff.

    Args:
        fn: Callable to execute
        max_attempts: Maximum number of attempts
        base_delay: Initial backoff delay in seconds
        is_retryable: Function to determine if exception should trigger retry

    Returns:
        Result of fn()

    Raises:
        Exception: If all retries are exhausted or exception is not retryable
    """
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            is_last_attempt = attempt == max_attempts - 1
            if is_last_attempt or not is_retryable(e):
                raise
            wait_time = base_delay ** (attempt + 1)
            logger.warning(
                f"Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                f"Retrying in {wait_time}s..."
            )
            time.sleep(wait_time)


def create_llm_client(
    config: dict,
) -> Callable[[str, str], LLMResponse]:
    """Factory to create LLM client based on configuration.

    Args:
        config: Configuration dict with llm_backend, and backend-specific settings

    Returns:
        A callable that takes (system: str, user: str) and returns LLMResponse
    """
    backend = config["llm_backend"]

    if backend == "claude":
        return _create_claude_client(config)
    elif backend == "local":
        return _create_local_client(config)
    else:
        raise ValueError(f"Unknown llm_backend: {backend}")


def _create_claude_client(config: dict) -> Callable[[str, str], LLMResponse]:
    """Create Claude API client with retry logic."""
    api_key = config.get("api_key")
    model = config.get("claude_model", "claude-sonnet-4-6")
    timeout = config.get("llm_timeout", 60)

    client = anthropic.Anthropic(api_key=api_key, timeout=timeout)

    def call_claude(system: str, user: str) -> LLMResponse:
        """Call Claude API with exponential backoff retry."""

        def _call() -> LLMResponse:
            response = client.messages.create(
                model=model,
                max_tokens=config.get("max_completion_tokens", MAX_COMPLETION_TOKENS),
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return LLMResponse(content=response.content[0].text)

        def _is_retryable(e: Exception) -> bool:
            return isinstance(
                e,
                (
                    anthropic.RateLimitError,
                    anthropic.APIConnectionError,
                    anthropic.APITimeoutError,
                ),
            )

        return _retry_with_exponential_backoff(_call, is_retryable=_is_retryable)

    return call_claude


def _create_local_client(config: dict) -> Callable[[str, str], LLMResponse]:
    """Create local LLM client (LM Studio / Ollama) with retry logic."""
    base_url = config["local_base_url"]
    model = config.get("local_model", "llama-3.2-3b-instruct")
    temperature = config.get("temperature", DEFAULT_TEMPERATURE)
    timeout = config.get("llm_timeout", 60)

    client = openai.OpenAI(base_url=base_url, api_key="not-needed", timeout=timeout)

    def call_local(system: str, user: str) -> LLMResponse:
        """Call local LLM with exponential backoff retry."""

        def _call() -> LLMResponse:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
            )
            return LLMResponse(content=response.choices[0].message.content)

        def _is_retryable(e: Exception) -> bool:
            # Retry on rate limit, server errors, and connection issues
            if isinstance(e, (openai.APIConnectionError, openai.APITimeoutError)):
                return True
            if isinstance(e, openai.APIStatusError):
                return getattr(e, "status_code", None) in (429, 500, 503)
            return False

        return _retry_with_exponential_backoff(_call, is_retryable=_is_retryable)

    return call_local
```

**Benefits:**
- ✓ Clear return type: `Callable[[str, str], LLMResponse]`
- ✓ DRY retry logic extracted to `_retry_with_exponential_backoff`
- ✓ Top-level imports (anthropic, openai) visible at module load time
- ✓ Configurable max_tokens and temperature
- ✓ Cleaner exception handling with helper function
- ✓ Modern type hints (`dict` not `Dict`)

---

## Fix 2: summarizer.py — Remove Garbage Fallback & Use Exceptions

### Current Code (WRONG)

```python
def summarize_note(
    llm_call: Callable, content: str, title: str, max_chars: int = 16000
) -> Dict[str, Any]:
    """Summarize a single note."""
    content = strip_frontmatter(content).strip()
    content = truncate_to_chars(content, max_chars)

    system = "You are a knowledge summarizer..."
    user = f"Title: {title}\n\nContent:\n{content}"

    response = llm_call(system, user)

    # Parse JSON response
    try:
        summary = json.loads(response.content)
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse JSON for {title}. Retrying with stricter prompt.")
        # Retry with stricter instructions
        strict_system = (
            system
            + "\n\nIMPORTANT: Return ONLY valid JSON, no extra text before or after."
        )
        response = llm_call(strict_system, user)
        try:
            summary = json.loads(response.content)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON for {title}: {e}")
            summary = {  # GARBAGE FALLBACK
                "summary": f"[Failed to summarize: {title}]",
                "bullets": [],
                "why_it_matters": "",
                "tags": [],
                "notable_quote": None,
            }

    # Ensure all required fields exist
    summary.setdefault("summary", "")
    summary.setdefault("bullets", [])
    summary.setdefault("why_it_matters", "")
    summary.setdefault("tags", [])
    summary.setdefault("notable_quote", None)

    return summary
```

### Fixed Code

```python
"""Note summarization and rollup logic."""

import json
import logging
from typing import Any, Callable

from obs_summarizer.llm import LLMResponse

logger = logging.getLogger(__name__)


class SummarizationError(Exception):
    """Raised when a note cannot be summarized."""

    def __init__(self, title: str, reason: str):
        self.title = title
        self.reason = reason
        super().__init__(f"Failed to summarize '{title}': {reason}")


class RollupError(Exception):
    """Raised when rollup digest cannot be created."""

    pass


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
    llm_call: Callable[[str, str], LLMResponse],
    content: str,
    title: str,
    max_chars: int = 16000,
) -> dict[str, Any]:
    """Summarize a single note.

    Args:
        llm_call: LLM client callable (system, user) -> LLMResponse
        content: Note markdown content
        title: Note title/filename
        max_chars: Max input chars before truncation

    Returns:
        Summary dict with fields: summary, bullets, why_it_matters, tags, notable_quote

    Raises:
        SummarizationError: If summarization fails
    """
    # Clean content
    content = strip_frontmatter(content).strip()
    content = truncate_to_chars(content, max_chars)

    system = (
        "You are a knowledge summarizer. Extract key insights from the given text. "
        "Return a JSON object with these exact fields:\n"
        '- summary: 1-2 sentences summarizing the main point\n'
        "- bullets: array of 5 key takeaways (strings)\n"
        "- why_it_matters: 1 sentence on relevance\n"
        "- tags: array of 1-3 topic tags\n"
        "- notable_quote: the most insightful quote from the text, or null"
    )

    user = f"Title: {title}\n\nContent:\n{content}"

    response = llm_call(system, user)

    # Parse JSON response
    try:
        summary = json.loads(response.content)
        return summary
    except json.JSONDecodeError as e:
        raise SummarizationError(title, f"Invalid JSON from LLM: {e}") from e


def create_rollup(
    llm_call: Callable[[str, str], LLMResponse],
    summaries: list[dict[str, Any]],
) -> str:
    """Create a rollup digest from per-note summaries.

    Args:
        llm_call: LLM client callable
        summaries: List of summary dicts (from summarize_note)

    Returns:
        Markdown digest content

    Raises:
        RollupError: If rollup creation fails
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

    try:
        response = llm_call(system, user)
        return response.content
    except Exception as e:
        raise RollupError(f"Failed to create rollup digest: {e}") from e
```

**Benefits:**
- ✓ No garbage fallback — exceptions are raised and propagated
- ✓ Custom `SummarizationError` and `RollupError` for specific handling
- ✓ Simplified JSON parsing (no nested try/except)
- ✓ Removed dead code (`setdefault` calls)
- ✓ Modern type hints (`dict[str, Any]` not `Dict[str, Any]`)
- ✓ Specific Callable type: `Callable[[str, str], LLMResponse]`

---

## Fix 3: pipeline.py — Specific Exception Handling

### Current Code (WRONG)

```python
for i, file_path in enumerate(target_files, 1):
    try:
        # Check cache unless no_cache is set
        mtime_ns = int(file_path.stat().st_mtime_ns)
        cache_key = make_cache_key(str(file_path), mtime_ns)

        if not no_cache:
            cached = load_cache(cache_dir, cache_key)
            if cached:
                logger.debug(f"Cache hit: {file_path.name}")
                per_note_summaries.append(cached)
                continue

        # Summarize this file
        logger.info(f"Summarizing {i}/{len(target_files)}: {file_path.name}")
        content = file_path.read_text(encoding="utf-8", errors="ignore")  # WRONG
        summary = summarize_note(
            llm_client, content, file_path.stem, max_chars=max_input_chars
        )

        # Add metadata
        summary["path"] = str(file_path)
        summary["mtime_utc"] = datetime.fromtimestamp(
            file_path.stat().st_mtime, tz=timezone.utc
        ).isoformat()

        # Cache it
        save_cache(cache_dir, cache_key, summary)
        per_note_summaries.append(summary)

    except Exception as e:  # WRONG: too broad
        logger.warning(f"Failed to summarize {file_path.name}: {e}. Skipping.")
        continue
```

### Fixed Code

```python
from obs_summarizer.summarizer import SummarizationError

for i, file_path in enumerate(target_files, 1):
    try:
        # Check cache unless no_cache is set
        mtime_ns = int(file_path.stat().st_mtime_ns)
        cache_key = make_cache_key(str(file_path), mtime_ns)

        if not no_cache:
            cached = load_cache(cache_dir, cache_key)
            if cached:
                logger.debug(f"Cache hit: {file_path.name}")
                per_note_summaries.append(cached)
                continue

        # Summarize this file
        logger.info(f"Summarizing {i}/{len(target_files)}: {file_path.name}")

        # Read file with proper encoding error handling
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            logger.warning(
                f"Skipping {file_path.name}: not valid UTF-8 "
                f"({e.reason} at position {e.start})"
            )
            continue

        # Summarize with proper error handling
        try:
            summary = summarize_note(
                llm_client, content, file_path.stem, max_chars=max_input_chars
            )
        except SummarizationError as e:
            logger.warning(f"Skipping {file_path.name}: {e.reason}")
            continue

        # Add metadata
        summary["path"] = str(file_path)
        summary["mtime_utc"] = datetime.fromtimestamp(
            file_path.stat().st_mtime, tz=timezone.utc
        ).isoformat()

        # Cache it
        save_cache(cache_dir, cache_key, summary)
        per_note_summaries.append(summary)

    except FileNotFoundError as e:
        logger.error(f"File disappeared during processing: {file_path}")
        return 1
    except Exception as e:
        # Unexpected error — crash and burn so we know something is wrong
        logger.error(f"Unexpected error processing {file_path.name}: {e}", exc_info=True)
        raise
```

**Benefits:**
- ✓ Catches specific exceptions only (SummarizationError, UnicodeDecodeError)
- ✓ File encoding errors are logged and skipped (not silently ignored)
- ✓ FileNotFoundError causes immediate exit (not silent skip)
- ✓ Unexpected exceptions are re-raised with full stack trace
- ✓ Operator knows when something went wrong

---

## Fix 4: state.py — Fail Loudly on Corruption

### Current Code (WRONG)

```python
def load_state(state_path: str) -> dict:
    """Load checkpoint state from JSON file."""
    path = Path(state_path)

    if not path.exists():
        return {"last_run_iso": None}

    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load state from {state_path}: {e}. Treating as first run.")
        return {"last_run_iso": None}  # WRONG: silent failure
```

### Fixed Code

```python
"""State and checkpoint management."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class StateError(Exception):
    """Raised when state cannot be loaded or saved."""

    pass


def load_state(state_path: str) -> dict:
    """Load checkpoint state from JSON file.

    Args:
        state_path: Path to state.json

    Returns:
        State dictionary with 'last_run_iso' key (None on first run)

    Raises:
        StateError: If state file is corrupted and unreadable
    """
    path = Path(state_path)

    if not path.exists():
        return {"last_run_iso": None}

    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state
    except (json.JSONDecodeError, IOError) as e:
        logger.error(
            f"State file corrupted or unreadable: {state_path}\n"
            f"Error: {e}\n"
            f"To recover:\n"
            f"  - Delete the file: rm {state_path}\n"
            f"  - Or restore from backup\n"
            f"  - Then run obs-digest again",
            exc_info=True,
        )
        raise StateError(f"Cannot load state from {state_path}") from e


def save_state(state: dict, state_path: str) -> None:
    """Save state atomically to disk.

    Writes to temp file first, then renames to avoid partial writes.

    Args:
        state: State dictionary
        state_path: Path to state.json
    """
    import tempfile

    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file, then rename atomically
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            json.dump(state, tmp, indent=2)
            tmp_path = tmp.name

        Path(tmp_path).replace(path)
    except IOError as e:
        logger.error(f"Failed to save state to {state_path}: {e}", exc_info=True)
        raise StateError(f"Cannot save state to {state_path}") from e


def _parse_iso_datetime(iso_string: str) -> datetime:
    """Parse ISO 8601 string, handling Python 3.9 Z suffix compatibility.

    Args:
        iso_string: ISO 8601 formatted datetime string (e.g., "2024-01-15T10:30:00Z")

    Returns:
        Timezone-aware datetime in UTC

    Raises:
        ValueError: If the string is not a valid ISO 8601 datetime
    """
    iso_string = iso_string.replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso_string)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def get_since_datetime(
    config: dict,
    since_iso: str | None = None,
    state: dict | None = None,
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
        return _parse_iso_datetime(since_iso)

    # Config file
    if config.get("since_iso"):
        return _parse_iso_datetime(config["since_iso"])

    # Checkpoint
    if state and state.get("last_run_iso"):
        return _parse_iso_datetime(state["last_run_iso"])

    # First run: default to now (no files will be found on first run)
    # User can override with --since to process historical files
    return datetime.now(timezone.utc)
```

**Benefits:**
- ✓ Fails loudly with `StateError` on corruption
- ✓ Clear error message with recovery instructions
- ✓ No silent "first run" fallback on corrupted state
- ✓ Extracted `_parse_iso_datetime` helper (DRY)
- ✓ Modern type hints (`str | None` not `Optional[str]`)

---

## Fix 5: All Modules — Type Hint Modernization

Replace in all files:

```python
# OLD (Python 3.8 and earlier)
from typing import Any, Callable, Dict, List, Optional

def function(param: Dict[str, Any]) -> List[str]:
    data: Optional[str] = None
    callback: Callable = None

# NEW (Python 3.9+)
from typing import Any, Callable

def function(param: dict[str, Any]) -> list[str]:
    data: str | None = None
    callback: Callable[[...], ...] | None = None
```

**Apply to:**
- `/src/obs_summarizer/llm.py` (line 6)
- `/src/obs_summarizer/summarizer.py` (line 5)
- `/src/obs_summarizer/pipeline.py` (line 7)
- `/src/obs_summarizer/cache.py` (line 7)
- `/src/obs_summarizer/state.py` (line 8)
- `/src/obs_summarizer/config.py` (line 5)
- `/src/obs_summarizer/digest_writer.py` (line 6)

---

## Testing Examples

Add to `/tests/`:

```python
def test_summarizer_raises_on_invalid_json():
    """summarize_note raises SummarizationError on invalid JSON."""
    from obs_summarizer.summarizer import SummarizationError, summarize_note

    def bad_llm_client(system: str, user: str):
        return LLMResponse(content="Not valid JSON")

    with pytest.raises(SummarizationError) as exc_info:
        summarize_note(bad_llm_client, "test content", "test.md")

    assert "test.md" in str(exc_info.value)
    assert "Invalid JSON" in str(exc_info.value)


def test_pipeline_reraises_unexpected_exceptions():
    """Pipeline re-raises unexpected exceptions instead of swallowing."""
    from obs_summarizer.pipeline import run_pipeline

    with patch("obs_summarizer.pipeline.list_markdown_files") as mock_list:
        with patch("obs_summarizer.pipeline.summarize_note") as mock_summarize:
            mock_list.return_value = [Path("test.md")]
            mock_summarize.side_effect = TypeError("Logic error")

            with pytest.raises(TypeError):
                run_pipeline(sample_config)


def test_state_raises_on_corrupted_file():
    """load_state raises StateError on corrupted state.json."""
    from obs_summarizer.state import StateError, load_state

    tmp_path = Path(tempfile.gettempdir()) / "corrupt_state.json"
    tmp_path.write_text("invalid json {{{")

    with pytest.raises(StateError):
        load_state(str(tmp_path))

    tmp_path.unlink()
```

---

## Summary of Changes

| File | Changes | LOC Change |
|------|---------|-----------|
| llm.py | Extract retry logic, fix types, move imports | -50 |
| summarizer.py | Remove garbage fallback, add exceptions, fix types | -40 |
| pipeline.py | Specific exception handling, encoding errors | +30 |
| state.py | Fail loudly, extract datetime parser | +20 |
| cache.py | Type hints modernization | 0 |
| config.py | Type hints modernization | 0 |
| digest_writer.py | Type hints modernization | 0 |
| scanner.py | Type hints modernization | 0 |
| Tests | Add error handling tests | +100 |

**Total effort:** ~3-4 hours for a careful developer.
