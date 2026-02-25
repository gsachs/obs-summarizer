# Critical Issues — Must Fix Before Shipping

## Overview

Three CRITICAL issues that break production readiness. All others can be deferred.

---

## 1. Pipeline Exception Handling is a Silent Failure Bomb

**File:** `/src/obs_summarizer/pipeline.py`
**Lines:** 103-105
**Severity:** CRITICAL

### The Problem

```python
except Exception as e:
    logger.warning(f"Failed to summarize {file_path.name}: {e}. Skipping.")
    continue
```

This catches **every exception** including:
- KeyError (malformed state)
- TypeError (logic bugs)
- IOError (file disappears)
- MemoryError (out of memory)

If all 100 files fail to summarize, the pipeline **returns exit code 0** (success) and writes an empty digest. The operator thinks everything worked.

### The Fix

```python
except (SummarizationError, json.JSONDecodeError) as e:
    # Expected failures — skip this file
    logger.warning(f"Skipping {file_path.name}: {e}")
    continue
except FileNotFoundError:
    # File disappeared mid-processing — abort
    logger.error(f"File disappeared: {file_path}")
    return 1
except Exception as e:
    # Unexpected failure — crash and burn
    logger.error(f"Unexpected error: {e}", exc_info=True)
    raise
```

Also fix line 88 (silent encoding errors):

```python
# BEFORE (wrong):
content = file_path.read_text(encoding="utf-8", errors="ignore")

# AFTER (correct):
try:
    content = file_path.read_text(encoding="utf-8")
except UnicodeDecodeError as e:
    logger.warning(f"Skipping {file_path.name}: not valid UTF-8")
    continue
```

---

## 2. Summarizer Returns Garbage on LLM Failure

**File:** `/src/obs_summarizer/summarizer.py`
**Lines:** 76-96
**Severity:** CRITICAL

### The Problem

When JSON parsing fails, the code returns a fake summary:

```python
except json.JSONDecodeError as e:
    logger.error(f"Failed to parse JSON for {title}: {e}")
    summary = {
        "summary": f"[Failed to summarize: {title}]",
        "bullets": [],
        "why_it_matters": "",
        "tags": [],
        "notable_quote": None,
    }
```

This looks identical to a real summary. The pipeline can't tell the difference and includes it in the digest. The user gets a fake summary labeled "[Failed to summarize: ...]" in their digest.

### The Fix

Define a custom exception and fail loudly:

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
        raise SummarizationError(title, f"Invalid JSON from LLM: {e}") from e
```

Remove the nested try/except and garbage fallback entirely. Let the exception propagate to pipeline.py, where it's caught and handled (issue #1).

---

## 3. State Corruption is Silent

**File:** `/src/obs_summarizer/state.py`
**Lines:** 31-33
**Severity:** CRITICAL

### The Problem

If `state.json` is corrupted, the code silently returns `{"last_run_iso": None}`:

```python
except (json.JSONDecodeError, IOError) as e:
    logger.warning(f"Failed to load state from {state_path}: {e}. Treating as first run.")
    return {"last_run_iso": None}
```

This treats the corrupted state as "first run" and processes nothing. The user's checkpoint is lost silently.

If this happens repeatedly (state keeps getting corrupted), the user has no way to know and can't recover except by manually deleting the file.

### The Fix

Fail loudly and let the operator decide what to do:

```python
class StateError(Exception):
    """Raised when state cannot be loaded."""
    pass

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
        logger.error(
            f"State file corrupted: {state_path}\n"
            f"Error: {e}\n"
            f"Manual fix: delete the file to reset to first-run mode, "
            f"or restore from backup.",
            exc_info=True,
        )
        raise StateError(f"Cannot load state from {state_path}") from e
```

Then in `pipeline.py`, let this exception bubble up (don't catch it). The pipeline will fail with a clear error message.

---

## Type Hints (Secondary)

These are blocking mypy in strict mode:

**File:** `/src/obs_summarizer/llm.py` (line 18)

```python
# BEFORE (wrong):
def create_llm_client(config: Dict) -> Callable:

# AFTER (correct):
def create_llm_client(config: dict) -> Callable[[str, str], LLMResponse]:
```

**File:** `/src/obs_summarizer/summarizer.py` (lines 43, 108)

```python
# BEFORE (wrong):
def summarize_note(llm_call: Callable, ...) -> Dict[str, Any]:
def create_rollup(llm_call: Callable, ...) -> str:

# AFTER (correct):
def summarize_note(
    llm_call: Callable[[str, str], LLMResponse],
    ...
) -> dict[str, Any]:
def create_rollup(
    llm_call: Callable[[str, str], LLMResponse],
    ...
) -> str:
```

Replace all `Dict` with `dict`, `List` with `list`, `Optional[X]` with `X | None`, and import from `typing` only when necessary (Callable, Any).

---

## Testing Strategy

After fixes, add tests for:

1. **pipeline.py**: Verify specific exceptions are caught and others are re-raised
2. **summarizer.py**: Verify `SummarizationError` is raised on bad JSON
3. **state.py**: Verify `StateError` is raised on corrupted state.json

Example:

```python
def test_pipeline_reraises_unexpected_exception():
    """Pipeline re-raises unexpected exceptions instead of swallowing."""
    with patch("obs_summarizer.pipeline.list_markdown_files") as mock_list:
        with patch("obs_summarizer.pipeline.summarize_note") as mock_summarize:
            mock_list.return_value = [Path("test.md")]
            mock_summarize.side_effect = TypeError("Something went wrong")

            result = run_pipeline(sample_config)

            # Should fail, not silently continue
            assert result == 1  # Error exit code
```

---

## Summary

| Issue | File | Fix | Effort |
|-------|------|-----|--------|
| Broad exception handling masks failures | pipeline.py | Catch specific exceptions only | 1 hour |
| Garbage summary state on LLM failure | summarizer.py | Raise custom exception | 30 min |
| Silent state corruption | state.py | Fail loudly with StateError | 30 min |
| Missing type hints on Callable | llm.py, summarizer.py | Specify `Callable[[str, str], LLMResponse]` | 15 min |
| Old-style type imports | All modules | Use modern 3.9+ syntax | 30 min |

**Total effort:** ~3 hours to address all CRITICAL issues.

**Recommendation:** Fix these before any release to production.
