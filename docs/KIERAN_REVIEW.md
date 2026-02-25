# Kieran's Code Review: obs-summarizer

**Date:** 2026-02-25
**Scope:** llm.py, summarizer.py, pipeline.py (+ related modules)
**Python Target:** 3.9+ (configured for 3.11)
**Assessment:** Strong foundation with a few high-impact improvements needed.

---

## Executive Summary

This is well-structured, idiomatic Python code with good separation of concerns. However, there are **critical issues in error handling, type hints, and API design** that need attention before this is production-ready. The main problems:

1. **Generic exception handling** in `pipeline.py` masks real failures
2. **Missing type annotations** on several public APIs
3. **Swallowed exceptions** in cache/state modules (silent failures)
4. **Inconsistent error handling patterns** between Claude and local LLM clients
5. **Magic values** hardcoded in multiple places

**Verdict:** This code is **pragmatically acceptable for a v0.1**, but these issues should block v0.2 release to production.

---

## File-by-File Analysis

### 1. `/src/obs_summarizer/llm.py` — HIGH ISSUES

#### Issue 1.1: Missing return type annotation on factory function
**Severity:** HIGH | **Type:** Type Hints
**Location:** Line 18

The factory function `create_llm_client` returns a `Callable`, but doesn't specify what callable:

```python
def create_llm_client(config: Dict) -> Callable:
```

Should be:

```python
def create_llm_client(config: Dict) -> Callable[[str, str], LLMResponse]:
```

This is critical because callers need to know the signature. Currently `mypy` on strict mode will complain.

#### Issue 1.2: Overly broad type hints
**Severity:** MEDIUM | **Type:** Type Hints
**Location:** Lines 18, 37, 80, 108

Using bare `Dict` instead of `dict` violates modern Python 3.9+ style. Also:

```python
def create_llm_client(config: Dict) -> Callable:  # FAIL
```

Should be:

```python
def create_llm_client(config: dict) -> Callable[[str, str], LLMResponse]:  # PASS
```

This applies to all uses: `config: Dict` → `config: dict`.

#### Issue 1.3: Exception handling logic is duplicated and fragile
**Severity:** HIGH | **Type:** Error Handling / DRY
**Location:** Lines 49-76 (Claude) vs Lines 92-120 (Local)

Both `call_claude` and `call_local` have nearly identical retry logic, but:

1. **Different exception types** are caught (anthropic.* vs openai.*)
2. **Different conditions** trigger retry (status_code in [429, 500, 503] for local)
3. **Code is not DRY** — 60+ lines of duplicated retry loop

This violates DRY and makes maintenance brittle. Extract a retry abstraction:

```python
def _retry_with_exponential_backoff(
    fn: Callable[[], T],
    max_attempts: int = 3,
    base_delay: int = 2,
    is_retryable: Callable[[Exception], bool] = lambda e: True,
) -> T:
    """Retry a callable with exponential backoff."""
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            if attempt < max_attempts - 1 and is_retryable(e):
                wait_time = base_delay ** (attempt + 1)
                logger.warning(
                    f"Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                    f"Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
            else:
                raise
```

Then use it in both clients.

#### Issue 1.4: Lazy imports hide dependency issues
**Severity:** MEDIUM | **Type:** Design / Imports
**Location:** Lines 39, 82

```python
def _create_claude_client(config: Dict) -> Callable:
    """Create Claude API client with retry logic."""
    import anthropic  # Lazy import
```

Lazy imports are anti-patterns for required dependencies. These should be top-level imports. Lazy imports make it harder to catch missing dependencies at startup and hide the module's true dependencies. Only use lazy imports for optional/heavy dependencies.

Move to top:
```python
import anthropic
from openai import OpenAI
import openai  # For exception types
```

#### Issue 1.5: No validation of config dict keys
**Severity:** MEDIUM | **Type:** Defensive Programming
**Location:** Lines 37-86

`_create_claude_client` silently allows missing `api_key` (line 41):

```python
api_key = config.get("api_key")  # Returns None if missing
```

Then passes it to `Anthropic(api_key=api_key)`, which will silently fall back to env var. This is fragile because:

- Config validation should happen in one place (config.py)
- `api_key: None` is a confusing state

The config module already validates this (line 64-67 of config.py), so this is OK, but should be documented or asserted.

#### Issue 1.6: Max tokens hardcoded
**Severity:** LOW | **Type:** Magic Numbers
**Location:** Line 53

```python
response = client.messages.create(
    model=model,
    max_tokens=1024,  # Magic number
```

Should be in config or a constant:

```python
MAX_COMPLETION_TOKENS = 1024

response = client.messages.create(
    model=model,
    max_tokens=config.get("max_completion_tokens", MAX_COMPLETION_TOKENS),
```

#### Issue 1.7: Temperature not configurable for Claude
**Severity:** LOW | **Type:** API Design
**Location:** Lines 47-56

Claude client doesn't set temperature (uses API default), but local client sets `temperature=0.7` (line 100). This inconsistency can lead to different behavior. Both should be configurable via config or default to the same value.

---

### 2. `/src/obs_summarizer/summarizer.py` — MEDIUM ISSUES

#### Issue 2.1: JSON parsing error handling is verbose and creates garbage state
**Severity:** MEDIUM | **Type:** Error Handling
**Location:** Lines 76-96

The error handling is overly complex:

```python
try:
    summary = json.loads(response.content)
except json.JSONDecodeError:
    logger.warning(f"Failed to parse JSON for {title}. Retrying with stricter prompt.")
    strict_system = system + "\n\nIMPORTANT: Return ONLY valid JSON..."
    response = llm_call(strict_system, user)
    try:
        summary = json.loads(response.content)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON for {title}: {e}")
        summary = {  # Garbage fallback
            "summary": f"[Failed to summarize: {title}]",
            "bullets": [],
            ...
        }
```

Problems:

1. **Nested try/except** is hard to read
2. **Garbage state returned** — a failed summary looks identical to a real one
3. **No way for callers to detect failure** — the pipeline doesn't know this summary is fake
4. **Two LLM calls on retry** — expensive

Better approach:

```python
class SummarizationError(Exception):
    """Raised when a note cannot be summarized."""
    def __init__(self, title: str, reason: str):
        self.title = title
        self.reason = reason
        super().__init__(f"Failed to summarize '{title}': {reason}")

def summarize_note(...) -> dict[str, Any]:
    """..."""
    content = strip_frontmatter(content).strip()
    content = truncate_to_chars(content, max_chars)

    system = "You are a knowledge summarizer..."
    user = f"Title: {title}\n\nContent:\n{content}"

    response = llm_call(system, user)
    try:
        return json.loads(response.content)
    except json.JSONDecodeError as e:
        # Don't retry — the LLM is fundamentally broken for this input
        raise SummarizationError(title, f"Invalid JSON: {e}") from e
```

Then in `pipeline.py`, catch `SummarizationError` separately from generic exceptions.

#### Issue 2.2: `setdefault` is redundant after error handling
**Severity:** LOW | **Type:** Code Quality
**Location:** Lines 99-103

After the try/except, the code unconditionally sets defaults:

```python
summary.setdefault("summary", "")
summary.setdefault("bullets", [])
```

But the except block (lines 90-96) already creates all required fields. The setdefault calls are dead code if parsing succeeds, and redundant if it fails. Either:

1. Remove them (the except branch handles it), OR
2. Move into the except branch only

Choose option 1 (remove them).

#### Issue 2.3: `create_rollup` has no error handling
**Severity:** MEDIUM | **Type:** Error Handling
**Location:** Lines 108-144

If the LLM fails here, the exception propagates up with no context. Add a try/except:

```python
def create_rollup(llm_call: Callable, summaries: list[dict[str, Any]]) -> str:
    """Create a rollup digest from per-note summaries."""
    if not summaries:
        return "# Daily Digest\n\nNo notes to summarize today."

    # Format summaries...
    summaries_text = ""
    for i, summary in enumerate(summaries, 1):
        summaries_text += f"\n---\n**Article {i}**\n"
        summaries_text += f"- Summary: {summary.get('summary', '')}\n"
        # ...

    system = "You are a curator..."
    user = f"Please create a reading digest from these summaries:\n{summaries_text}"

    try:
        response = llm_call(system, user)
        return response.content
    except Exception as e:
        raise RollupError(f"Failed to create rollup digest: {e}") from e
```

#### Issue 2.4: Type hints use `List` and `Dict` instead of modern syntax
**Severity:** MEDIUM | **Type:** Type Hints
**Location:** Lines 5-6, throughout

```python
from typing import Any, Callable, Dict, List, Optional
```

Should use modern 3.9+ style:

```python
from typing import Any, Callable
```

And in signatures:

```python
def summarize_note(...) -> dict[str, Any]:  # Not Dict[str, Any]
def create_rollup(llm_call: Callable, summaries: list[dict[str, Any]]) -> str:
```

#### Issue 2.5: Missing type hints on callable parameter
**Severity:** HIGH | **Type:** Type Hints
**Location:** Lines 43-45, 108

```python
def summarize_note(
    llm_call: Callable, content: str, title: str, max_chars: int = 16000
) -> dict[str, Any]:
```

Should specify the callable's signature:

```python
def summarize_note(
    llm_call: Callable[[str, str], LLMResponse],
    content: str,
    title: str,
    max_chars: int = 16000,
) -> dict[str, Any]:
```

Same for `create_rollup`.

---

### 3. `/src/obs_summarizer/pipeline.py` — CRITICAL ISSUES

#### Issue 3.1: Overly broad exception handling masks real failures
**Severity:** CRITICAL | **Type:** Error Handling
**Location:** Lines 103-105

```python
except Exception as e:
    logger.warning(f"Failed to summarize {file_path.name}: {e}. Skipping.")
    continue
```

This swallows **all exceptions**, including:

- `KeyError` if summary dict is malformed
- `IOError` if the file disappears mid-processing
- `TypeError` if something is fundamentally wrong
- `OOM` errors (if applicable)

The pipeline reports `1` error as a "skip" and silently continues. If all files fail, you get an empty digest with exit code 0 (success). That's wrong.

**Fix:** Catch specific exceptions only:

```python
except (SummarizationError, json.JSONDecodeError) as e:
    logger.warning(f"Skipping {file_path.name}: {e}")
    continue
except FileNotFoundError as e:
    logger.error(f"File disappeared during processing: {file_path}: {e}")
    return 1
except Exception as e:
    logger.error(
        f"Unexpected error processing {file_path.name}: {e}",
        exc_info=True,
    )
    raise
```

#### Issue 3.2: Return codes are undocumented and asymmetric
**Severity:** MEDIUM | **Type:** API Design
**Location:** Lines 24-34

```python
Returns:
    Exit code (0 = success, 1 = error, 2 = no files found)
```

But the function also silently skips files (continues on exception, line 105). So:

- Exit 0 = "digest written successfully" (could be partial, could have cached items)
- Exit 2 = "no files found initially"
- Exit 1 = "no summaries generated OR pipeline exception"

This is confusing. Is exit 0 a success if we processed 1 of 100 files? Did we write an empty digest?

**Fix:** Add more granular return codes or state:

```python
@dataclass
class PipelineResult:
    exit_code: int
    files_found: int
    files_skipped: int
    files_summarized: int
    digest_path: Path | None

def run_pipeline(...) -> PipelineResult:
    ...
    return PipelineResult(
        exit_code=0,
        files_found=len(target_files),
        files_skipped=...,
        files_summarized=len(per_note_summaries),
        digest_path=digest_path,
    )
```

#### Issue 3.3: Type hints use old-style generic syntax
**Severity:** MEDIUM | **Type:** Type Hints
**Location:** Lines 7, throughout

```python
from typing import Callable, Dict, List, Optional
```

Should be:

```python
from typing import Callable
```

And use built-in generics:

```python
def run_pipeline(
    config: dict,
    since: str | None = None,
    dry_run: bool = False,
    no_cache: bool = False,
) -> int:
```

#### Issue 3.4: No type hints on `config` parameter
**Severity:** MEDIUM | **Type:** Type Hints
**Location:** Line 20

```python
def run_pipeline(
    config: Dict,  # Should specify what keys this needs
    ...
```

The `config` dict is polymorphic — different LLM backends need different keys. This should either:

1. Be a typed class (`@dataclass Config`), OR
2. Have detailed docstring specifying required/optional keys

Currently config.py handles validation, but `run_pipeline` should document what it expects.

#### Issue 3.5: File encoding errors silently skipped
**Severity:** MEDIUM | **Type:** Error Handling
**Location:** Line 88

```python
content = file_path.read_text(encoding="utf-8", errors="ignore")
```

Using `errors="ignore"` silently discards undecodable bytes. This can lead to:

- Lost content
- Corrupted summaries
- No indication to the user that something was dropped

Better:

```python
try:
    content = file_path.read_text(encoding="utf-8")
except UnicodeDecodeError as e:
    logger.warning(f"Skipping {file_path.name}: not valid UTF-8 ({e})")
    continue
```

#### Issue 3.6: Redundant cached item detection
**Severity:** LOW | **Type:** Code Quality
**Location:** Lines 128-129

```python
num_cached = len([s for s in per_note_summaries if "path" in s])
num_summarized = len(per_note_summaries) - num_cached
```

This logic checks if `"path"` key is in the summary to detect cached items. But **all** summaries have `"path"` added at line 94:

```python
summary["path"] = str(file_path)
```

So `num_cached` will always equal `num_summarized` (both at 0). This logic doesn't work.

The intent was probably to track which summaries came from cache vs. newly summarized. Store this explicitly:

```python
@dataclass
class ProcessedSummary:
    data: dict[str, Any]
    from_cache: bool

per_note_summaries: list[ProcessedSummary] = []
# ...
if not no_cache:
    cached = load_cache(cache_dir, cache_key)
    if cached:
        per_note_summaries.append(ProcessedSummary(data=cached, from_cache=True))
        continue

# ... summarize ...
per_note_summaries.append(ProcessedSummary(data=summary, from_cache=False))

# ... later ...
num_cached = len([s for s in per_note_summaries if s.from_cache])
num_summarized = len(per_note_summaries) - num_cached
```

---

### 4. `/src/obs_summarizer/cache.py` — MEDIUM ISSUES

#### Issue 4.1: Type hints use old-style imports
**Severity:** MEDIUM | **Type:** Type Hints
**Location:** Line 7

```python
from typing import Any, Dict, Optional
```

Should be:

```python
from typing import Any
```

And use built-ins:

```python
def load_cache(cache_dir: str, cache_key: str) -> dict[str, Any] | None:
def save_cache(cache_dir: str, cache_key: str, data: dict[str, Any]) -> None:
```

#### Issue 4.2: Silent failure in `load_cache`
**Severity:** HIGH | **Type:** Error Handling
**Location:** Lines 44-46

```python
except (json.JSONDecodeError, IOError) as e:
    logger.warning(f"Failed to load cache {cache_key}: {e}. Regenerating.")
    return None
```

Returning `None` on cache corruption is OK, but the log message "Regenerating" suggests the caller will retry. That's only true if the caller checks for `None` and re-summarizes. If the caller doesn't, you silently lose cached data.

This is acceptable, but the comment should clarify:

```python
except (json.JSONDecodeError, IOError) as e:
    logger.warning(f"Cache {cache_key} corrupted or unreadable ({e}). Will re-summarize.")
    return None
```

#### Issue 4.3: No validation of `cache_dir` parameter
**Severity:** LOW | **Type:** Defensive Programming
**Location:** Lines 26-46, 49-62

If `cache_dir` is empty string or None, behavior is undefined:

```python
def save_cache(cache_dir: str, cache_key: str, data: dict[str, Any]) -> None:
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)
```

If `cache_dir=""`, this creates `./` (the current directory). Add a guard:

```python
def save_cache(cache_dir: str, cache_key: str, data: dict[str, Any]) -> None:
    if not cache_dir:
        raise ValueError("cache_dir cannot be empty")
    cache_path = Path(cache_dir)
    ...
```

---

### 5. `/src/obs_summarizer/state.py` — MEDIUM ISSUES

#### Issue 5.1: Silent failure in `load_state`
**Severity:** MEDIUM | **Type:** Error Handling
**Location:** Lines 31-33

```python
except (json.JSONDecodeError, IOError) as e:
    logger.warning(f"Failed to load state from {state_path}: {e}. Treating as first run.")
    return {"last_run_iso": None}
```

Same as cache.py issue 4.2 — returning garbage state (`last_run_iso=None`) on file corruption. The pipeline will treat this as "first run" and process nothing. If state.json is corrupted, the user's checkpoint is lost.

Better: fail loudly and let the operator decide to manually fix or reset.

```python
except (json.JSONDecodeError, IOError) as e:
    logger.error(
        f"State file corrupted or unreadable: {state_path}\n"
        f"Error: {e}\n"
        f"Please manually repair or delete the file to reset.",
        exc_info=True,
    )
    raise StateError(f"Cannot load state from {state_path}") from e
```

#### Issue 5.2: Type hints use old-style
**Severity:** MEDIUM | **Type:** Type Hints
**Location:** Line 8

```python
from typing import Optional
```

Should be:

```python
# (no imports needed for basic types)
```

And in signatures:

```python
def load_state(state_path: str) -> dict:
def save_state(state: dict, state_path: str) -> None:
def get_since_datetime(
    config: dict,
    since_iso: str | None = None,
    state: dict | None = None,
) -> datetime:
```

#### Issue 5.3: Redundant Z-to-+00:00 conversion
**Severity:** LOW | **Type:** Code Quality
**Location:** Lines 79-97

The conversion appears in three places:

```python
since_iso = since_iso.replace("Z", "+00:00")
dt = datetime.fromisoformat(since_iso)
```

Extract a helper:

```python
def _parse_iso_datetime(iso_string: str) -> datetime:
    """Parse ISO 8601 string, handling Python 3.9 Z suffix compatibility."""
    iso_string = iso_string.replace("Z", "+00:00")
    dt = datetime.fromisoformat(iso_string)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
```

Then:

```python
if since_iso:
    return _parse_iso_datetime(since_iso)
if config.get("since_iso"):
    return _parse_iso_datetime(config["since_iso"])
if state and state.get("last_run_iso"):
    return datetime.fromisoformat(state["last_run_iso"].replace("Z", "+00:00"))
```

---

### 6. `/src/obs_summarizer/config.py` — GOOD (Minor Issues)

#### Issue 6.1: Type hints use old-style
**Severity:** LOW | **Type:** Type Hints
**Location:** Line 5

Use `dict` instead of `Dict`.

#### Issue 6.2: Return type should be more specific
**Severity:** LOW | **Type:** Type Hints
**Location:** Line 16

```python
def load_config(config_path: Optional[str] = None) -> dict:
```

Should be:

```python
def load_config(config_path: str | None = None) -> dict[str, Any]:
```

---

### 7. `/src/obs_summarizer/digest_writer.py` — GOOD (Minor Issues)

#### Issue 7.1: Type hints use old-style
**Severity:** LOW | **Type:** Type Hints
**Location:** Line 6

Use `list` and `dict` instead of `List` and `Dict`.

#### Issue 7.2: Magic indices and assumptions
**Severity:** LOW | **Type:** Code Quality
**Location:** Line 78

```python
theme = summary.get("tags", ["Uncategorized"])[0] or "Uncategorized"
```

Accessing `[0]` without checking length can raise `IndexError` if tags is an empty list. Better:

```python
themes = summary.get("tags", [])
theme = (themes[0] if themes else None) or "Uncategorized"
```

Or use a helper:

```python
def get_primary_theme(summary: dict[str, Any]) -> str:
    """Get the primary theme tag, or 'Uncategorized'."""
    themes = summary.get("tags", [])
    return (themes[0] if themes else None) or "Uncategorized"
```

---

### 8. `/src/obs_summarizer/scanner.py` — GOOD

No major issues. Minor notes:

- Type hints use old-style `List` and `Optional` (line 5)
- Consider adding a docstring to `list_markdown_files` about symlink handling

---

## Cross-Module Issues

### Issue X.1: Config validation is mixed across modules
**Severity:** MEDIUM | **Type:** Architecture / Responsibility

Config is loaded and validated in `config.py`, but `llm.py` and `pipeline.py` also assume certain keys exist (e.g., `config["llm_backend"]`, `config["vault_path"]`). If an unexpected config arrives, failures are scattered.

**Fix:** Define a `@dataclass Config` in config.py:

```python
@dataclass
class Config:
    """Validated application configuration."""
    vault_path: Path
    llm_backend: Literal["claude", "local"]
    cache_dir: Path
    state_path: Path
    include_folders: list[str]
    exclude_globs: list[str]
    digest_folder: str
    max_input_chars: int

    # Claude settings (optional)
    claude_model: str = "claude-sonnet-4-6"
    api_key: str | None = None

    # Local settings (optional)
    local_base_url: str | None = None
    local_model: str = "llama-3.2-3b-instruct"

    llm_timeout: int = 60

def load_config(config_path: str | None = None) -> Config:
    """Load and validate configuration."""
    # ... validation ...
    return Config(...)
```

Then all modules work with a typed object, not an untyped dict.

### Issue X.2: LLMResponse is minimal; no metadata
**Severity:** LOW | **Type:** API Design
**Location:** llm.py lines 11-15

```python
@dataclass
class LLMResponse:
    """Unified response from any LLM backend."""
    content: str
```

Could be richer:

```python
@dataclass
class LLMResponse:
    """Unified response from any LLM backend."""
    content: str
    model: str
    usage: dict[str, int] | None = None  # { "prompt_tokens": N, "completion_tokens": M }
```

Low priority, but useful for observability.

### Issue X.3: Logging is inconsistent
**Severity:** LOW | **Type:** Code Quality

Some modules use `logger.warning()`, others use `logger.error()`. Some include `exc_info=True`, others don't. Standardize:

- `logger.warning()` — recoverable issue, operation continues (cache miss, file skipped)
- `logger.error()` — non-recoverable, but not crashing (state corrupted, retries exhausted)
- `logger.error(..., exc_info=True)` — unexpected exception, include stack trace
- `logger.info()` — progress updates, success milestones

---

## Summary Table

| File | Issue | Severity | Type | Action |
|------|-------|----------|------|--------|
| llm.py | Missing return type on factory | HIGH | Type Hints | Specify `Callable[[str, str], LLMResponse]` |
| llm.py | Bare `Dict` instead of `dict` | MEDIUM | Type Hints | Use modern 3.9+ syntax |
| llm.py | Duplicate retry logic | HIGH | DRY / Error Handling | Extract `_retry_with_exponential_backoff` |
| llm.py | Lazy imports | MEDIUM | Imports | Move to top-level |
| llm.py | Max tokens hardcoded | LOW | Magic Numbers | Add to config |
| summarizer.py | Verbose nested JSON parsing error | MEDIUM | Error Handling | Use custom exception |
| summarizer.py | Garbage fallback state on failure | HIGH | Error Handling | Raise exception instead |
| summarizer.py | Missing type hints on Callable param | HIGH | Type Hints | Specify signature |
| summarizer.py | Old-style type imports | MEDIUM | Type Hints | Use modern syntax |
| pipeline.py | Overly broad exception handling | CRITICAL | Error Handling | Catch specific exceptions only |
| pipeline.py | Undocumented return codes | MEDIUM | API Design | Add dataclass or document better |
| pipeline.py | Redundant cached item detection | MEDIUM | Code Quality | Use explicit tracking |
| pipeline.py | Silent file encoding errors | MEDIUM | Error Handling | Catch and log UnicodeDecodeError |
| pipeline.py | Old-style type hints | MEDIUM | Type Hints | Use modern syntax |
| cache.py | Old-style type hints | MEDIUM | Type Hints | Use modern syntax |
| cache.py | No cache_dir validation | LOW | Defensive Programming | Add guard clause |
| state.py | Silent failure on corruption | MEDIUM | Error Handling | Fail loudly, let operator decide |
| state.py | Old-style type hints | MEDIUM | Type Hints | Use modern syntax |
| state.py | Redundant Z-to-+00:00 conversion | LOW | DRY | Extract helper function |
| config.py | Old-style type hints | LOW | Type Hints | Use modern syntax |
| digest_writer.py | Old-style type hints | LOW | Type Hints | Use modern syntax |
| digest_writer.py | Unsafe list indexing | LOW | Code Quality | Add bounds check |
| X.1 | Untyped config dict | MEDIUM | Architecture | Use `@dataclass Config` |

---

## Recommended Fixes (By Priority)

### Phase 1: CRITICAL (Blocks Production Release)

1. **llm.py** — Fix factory return type and duplicate retry logic
2. **pipeline.py** — Replace broad exception handling with specific catches
3. **summarizer.py** — Remove garbage fallback state; raise exception instead
4. **state.py** — Fail loudly on corruption, don't silently treat as first run
5. **pipeline.py** — Fix file encoding error handling

### Phase 2: HIGH (Before v1.0)

1. Add type hints to all Callable parameters
2. Replace all old-style type imports (`Dict`, `List`, `Optional`) with modern syntax
3. Extract retry logic abstraction
4. Create `@dataclass Config` to replace untyped dict
5. Add specific exception types (`SummarizationError`, `RollupError`, `StateError`)

### Phase 3: MEDIUM (Nice-to-Have)

1. Fix redundant cached item detection logic
2. Extract datetime parsing helper
3. Standardize logging levels
4. Add validation to `cache_dir` parameter
5. Improve `LLMResponse` with metadata

---

## Testing Notes

Current test coverage in `tests/` is good — test the fixes thoroughly:

- When `summarize_note` raises `SummarizationError`, does pipeline handle it correctly?
- Does broad exception catch in pipeline now only catch specific exceptions?
- Do old-type hints pass mypy on strict mode?
- Does the new retry abstraction handle all LLM backends correctly?

---

## Conclusion

This is **v0.1-quality code**: it works, it's reasonably clean, and it demonstrates good architecture. But it's not production-ready because:

1. Error handling is too broad and masks real failures
2. Type hints are incomplete and use old syntax
3. State management (cache, checkpoint) fails silently on corruption
4. Some logic is duplicated (retry) or broken (cached item detection)

**Recommended path forward:**

1. Address Phase 1 issues immediately (they're bugs, not style)
2. Before shipping to users, complete Phase 2 (stricter typing, better error handling)
3. Phase 3 can be deferred post-release if the team is under time pressure

**Kieran's verdict:** Ship v0.1 with Phase 1 fixes applied. Don't release v1.0 without Phase 2.
