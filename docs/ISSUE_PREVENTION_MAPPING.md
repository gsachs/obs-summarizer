# Issue Prevention Mapping

**Maps the 5 critical issues to fixed code and prevention mechanisms**

---

## Quick Reference: Which Issues Were Fixed Where?

| Issue | Problem | Fixed In | Prevention Test | CLAUDE.md Section |
|-------|---------|----------|-----------------|-------------------|
| **#1: API Key Exposure** | Keys logged in error messages | `llm.py`, `config.py` | `test_no_api_keys_in_logs()` | Security, Comments |
| **#2: Path Traversal** | User input allows `../` escape | `scanner.py`, `pipeline.py` | `test_path_traversal_blocked()` | Security, Boundaries |
| **#3: Broad Exception Handling** | `except Exception` masks bugs | `pipeline.py` | `test_pipeline_reraises_unexpected_exception()` | Error Handling, Functions |
| **#4: Silent State Corruption** | Corrupted state treated as first-run | `state.py` | `test_state_corruption_raises_exception()` | Error Handling, Don't Return Null |
| **#5: Fake Summary Objects** | Garbage state returned on failure | `summarizer.py`, `pipeline.py` | `test_summarize_raises_on_json_failure()` | Error Handling, Type Safety |

---

## Issue #1: API Key Exposure

### Before (WRONG)

```python
# llm.py — Lazy import with possible logging
def _create_claude_client(config: Dict) -> Callable:
    import anthropic  # Lazy import
    api_key = config.get("api_key")
    # ... retry logic with try/except that could log api_key

    logger.info(f"Connecting with key: {api_key}")  # EXPOSED
```

### After (CORRECT)

```python
# llm.py — Top-level imports, no secret logging
import anthropic

def _create_claude_client(config: dict) -> Callable[[str, str], LLMResponse]:
    api_key = config.get("api_key")
    client = anthropic.Anthropic(api_key=api_key, timeout=timeout)

    def call_claude(system: str, user: str) -> LLMResponse:
        def _call() -> LLMResponse:
            response = client.messages.create(...)
            return LLMResponse(content=response.content[0].text)

        def _is_retryable(e: Exception) -> bool:
            # Only log exception type, not entire exception
            return isinstance(e, (anthropic.RateLimitError, ...))

        return _retry_with_exponential_backoff(_call, is_retryable=_is_retryable)

    return call_claude
```

### Prevention

**Code Review Checklist Item:**
- [ ] API keys loaded from environment only
- [ ] No `logger.info(f"key={api_key}")`
- [ ] Exception messages stripped of credentials
- [ ] Lazy imports only for optional dependencies

**Test Case:**
```python
def test_no_api_keys_in_logs():
    """Verify sensitive credentials never leak into logs."""
    # See PREVENTION_STRATEGIES.md
```

**CLAUDE.md Principles:**
1. **Security** — "Never hardcode secrets... use environment variables"
2. **Comments** — "Don't log credentials, ever"
3. **Boundaries** — "Wrap third-party APIs to strip credentials before logging"

---

## Issue #2: Path Traversal Vulnerability

### Before (WRONG)

```python
# scanner.py — No validation of user input paths
def list_markdown_files(vault_path: str, include_folders: list[str]) -> list[Path]:
    vault = Path(vault_path)

    # User-supplied folder could escape vault
    for folder in include_folders:  # What if folder = "../../../etc"?
        for md_file in (vault / folder).rglob("*.md"):
            yield md_file  # Could be /etc/passwd
```

### After (CORRECT)

```python
# scanner.py — Validate paths stay within vault
def list_markdown_files(vault_path: str, include_folders: list[str]) -> list[Path]:
    vault = Path(vault_path).resolve()

    for folder in include_folders:
        # Reject parent references
        folder_parts = Path(folder).parts
        if ".." in folder_parts or folder.startswith("/"):
            logger.warning(f"Rejecting unsafe folder: {folder}")
            continue

        target = (vault / folder).resolve()

        # Verify resolved path is within vault
        if not target.is_relative_to(vault):
            logger.error(f"Path escape attempt: {folder}")
            raise SecurityError(f"Folder outside vault: {folder}")

        # Now safe to traverse
        for md_file in target.rglob("*.md"):
            # Verify each file is also within vault
            if md_file.resolve().is_relative_to(vault):
                yield md_file
```

### Prevention

**Code Review Checklist Item:**
- [ ] All file paths use `pathlib.Path`, not string concatenation
- [ ] `.resolve()` called to get canonical path
- [ ] `.is_relative_to(root)` verifies path stays in bounds
- [ ] `..` and `/` rejected from user input
- [ ] Symlinks verified to be within bounds

**Test Case:**
```python
def test_path_traversal_blocked():
    """Verify path traversal attempts are rejected."""
    # See PREVENTION_STRATEGIES.md
```

**CLAUDE.md Principles:**
1. **Security** — "Validate all input... use allow-lists, not deny-lists"
2. **Defensive Programming** — "Validate inputs and preconditions at the top"
3. **Boundaries** — "Use interfaces at boundaries"

---

## Issue #3: Broad Exception Handling (Swallowing Exceptions)

### Before (WRONG)

```python
# pipeline.py — Catches every exception
for i, file_path in enumerate(target_files, 1):
    try:
        # Read file with silent UTF-8 errors
        content = file_path.read_text(encoding="utf-8", errors="ignore")

        # Summarize
        summary = summarize_note(llm_client, content, file_path.stem)

        # Cache
        save_cache(cache_dir, cache_key, summary)
        per_note_summaries.append(summary)

    except Exception as e:  # CATCHES EVERYTHING
        logger.warning(f"Failed to summarize {file_path.name}: {e}. Skipping.")
        continue
```

**Problem:** If all 100 files fail, returns exit code 0 (success) with empty digest.

### After (CORRECT)

```python
# pipeline.py — Specific exception handling
from obs_summarizer.summarizer import SummarizationError

for i, file_path in enumerate(target_files, 1):
    try:
        # Read file with proper encoding error handling
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            logger.warning(f"Skipping {file_path.name}: invalid UTF-8")
            continue

        # Summarize with specific error handling
        try:
            summary = summarize_note(llm_client, content, file_path.stem)
        except SummarizationError as e:
            logger.warning(f"Skipping {file_path.name}: {e.reason}")
            continue

        # Cache it
        save_cache(cache_dir, cache_key, summary)
        per_note_summaries.append(summary)

    except FileNotFoundError as e:
        # File disappeared — stop immediately
        logger.error(f"File disappeared: {file_path}")
        return 1
    except Exception as e:
        # Unexpected error — crash and burn
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise
```

**Benefit:** Distinguishes expected failures (skip file) from unexpected (crash).

### Prevention

**Code Review Checklist Item:**
- [ ] Never bare `except Exception`
- [ ] Each try block has <5 statements (one failure scenario)
- [ ] Unexpected exceptions re-raised with `raise`
- [ ] Expected exceptions logged at WARNING level
- [ ] Unexpected exceptions logged at ERROR level with `exc_info=True`
- [ ] No empty except blocks

**Test Case:**
```python
def test_pipeline_reraises_unexpected_exceptions():
    """Pipeline re-raises unexpected exceptions instead of swallowing."""
    # See PREVENTION_STRATEGIES.md
```

**CLAUDE.md Principles:**
1. **Error Handling** — "Extract try/catch into own functions. Error handling is one thing"
2. **Functions** — "Do one thing... if you can extract with a distinct name, it's doing more"
3. **Comments** — "Explain WHY error is swallowed (expected) vs re-raised (unexpected)"

---

## Issue #4: Silent State Corruption

### Before (WRONG)

```python
# state.py — Corruption treated as first-run
def load_state(state_path: str) -> dict:
    path = Path(state_path)

    if not path.exists():
        return {"last_run_iso": None}

    try:
        with open(path, "r") as f:
            state = json.load(f)
        return state
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load state: {e}. Treating as first run.")
        return {"last_run_iso": None}  # USER LOSES CHECKPOINT
```

**Problem:** If state.json corrupts, pipeline skips all files (treats as first run).

### After (CORRECT)

```python
# state.py — Corruption raises exception
class StateError(Exception):
    """Raised when state cannot be loaded or saved."""
    pass

def load_state(state_path: str) -> dict:
    path = Path(state_path)

    # File doesn't exist — first run is OK
    if not path.exists():
        return {"last_run_iso": None}

    # File exists — must be valid JSON
    try:
        with open(path, "r", encoding="utf-8") as f:
            state = json.load(f)
        return state
    except (json.JSONDecodeError, IOError) as e:
        logger.error(
            f"State file corrupted: {state_path}\n"
            f"Error: {e}\n"
            f"To recover:\n"
            f"  - Delete: rm {state_path}\n"
            f"  - Or restore from backup",
            exc_info=True,
        )
        raise StateError(f"Cannot load state from {state_path}") from e
```

**Benefit:** Operator knows state is corrupted and what to do about it.

### Prevention

**Code Review Checklist Item:**
- [ ] Distinguish "doesn't exist" from "corrupted"
- [ ] Corruption raises exception (not returns default)
- [ ] Exception message includes recovery instructions
- [ ] Different exception types for different failures (StateError, ConfigError, etc.)
- [ ] State operations logged at INFO level
- [ ] State writes are atomic (temp file → rename)

**Test Case:**
```python
def test_state_corruption_raises_exception():
    """Loading corrupted state.json raises StateError, not returns default."""
    # See PREVENTION_STRATEGIES.md
```

**CLAUDE.md Principles:**
1. **Error Handling** — "Provide context with exceptions... include recovery instructions"
2. **Don't Return Null** — "Returning null creates work for callers"
3. **Fail Fast** — "Crash loudly in development"

---

## Issue #5: Fake Summary Objects (Garbage State)

### Before (WRONG)

```python
# summarizer.py — Returns fake summary on failure
def summarize_note(llm_call: Callable, content: str, title: str) -> Dict[str, Any]:
    response = llm_call(system, user)

    try:
        summary = json.loads(response.content)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON for {title}: {e}")
        summary = {  # LOOKS LIKE REAL DATA
            "summary": f"[Failed to summarize: {title}]",
            "bullets": [],
            "why_it_matters": "",
            "tags": [],
            "notable_quote": None,
        }

    return summary  # CALLER CAN'T TELL IF REAL OR FAKE
```

**Problem:** Pipeline includes fake summaries in digest (looks like real data).

### After (CORRECT)

```python
# summarizer.py — Raises exception on failure
class SummarizationError(Exception):
    """Raised when a note cannot be summarized."""
    def __init__(self, title: str, reason: str):
        self.title = title
        self.reason = reason
        super().__init__(f"Failed to summarize '{title}': {reason}")

def summarize_note(
    llm_call: Callable[[str, str], LLMResponse],
    content: str,
    title: str,
    max_chars: int = 16000,
) -> dict[str, Any]:
    """Summarize a note.

    Raises:
        SummarizationError: If LLM returns invalid JSON
    """
    response = llm_call(system, user)

    try:
        return json.loads(response.content)
    except json.JSONDecodeError as e:
        raise SummarizationError(title, f"Invalid JSON: {e}") from e
```

Then in pipeline:

```python
# pipeline.py — Handles exception, doesn't include fake summary
try:
    summary = summarize_note(llm_client, content, file_path.stem)
except SummarizationError as e:
    logger.warning(f"Skipping {file_path.name}: {e.reason}")
    continue  # File is not included in digest
```

**Benefit:** Fake summaries can never reach the digest.

### Prevention

**Code Review Checklist Item:**
- [ ] Functions that can fail raise exception, not return fake object
- [ ] No object with "error" or "success" field for caller to check
- [ ] Return type is fully valid on success (no None for required fields)
- [ ] Failure distinguished from success at type level (exception vs return)
- [ ] Docstring documents which exceptions are raised

**Test Case:**
```python
def test_summarize_raises_on_json_failure():
    """summarize_note raises SummarizationError on invalid JSON."""
    # See PREVENTION_STRATEGIES.md
```

**CLAUDE.md Principles:**
1. **Error Handling** — "Use exceptions, not return codes"
2. **Type Safety** — "Make illegal states unrepresentable"
3. **Don't Return Null** — "Return exception instead"

---

## How These Issues Interconnect

```
Issue #5 (Fake Summaries)
    ↓ prevented by Issue #3 (Specific Exceptions)
    ↓ which requires Issue #3 (Catch SummarizationError specifically)

Issue #4 (Silent State Corruption)
    ↓ prevented by raising StateError
    ↓ which pipeline must NOT swallow (Issue #3)

Issue #2 (Path Traversal)
    ↓ prevented by validating paths at start (Issue #3: fail fast)
    ↓ which raises SecurityError
    ↓ which pipeline must NOT swallow

Issue #1 (API Key Exposure)
    ↓ prevented by wrapping exceptions (Issue #3: wrap third-party)
    ↓ and using environment variables
```

**The interconnection:** Issue #3 (Broad Exception Handling) is the *foundation*. Once you fix this, the other issues become detectable because exceptions propagate properly.

---

## Code Review Priority Order

When reviewing code, check issues in this order:

### Phase 1: Critical (Security & Correctness)

1. **Issue #2: Path Traversal**
   - Check: Are file paths validated? `.resolve().is_relative_to(root)`?
   - Ask: Could user input escape the intended directory?

2. **Issue #1: API Key Exposure**
   - Check: Is anything secret logged or in exception messages?
   - Ask: Does config load from environment only?

3. **Issue #3: Broad Exception Handling**
   - Check: Any bare `except Exception`?
   - Ask: Would unexpected errors be visible to the operator?

### Phase 2: Reliability (State Management)

4. **Issue #4: Silent State Corruption**
   - Check: Do corruption scenarios raise exceptions?
   - Ask: If a file is corrupted, does the operator know?

5. **Issue #5: Fake Summary Objects**
   - Check: Are exceptions raised instead of garbage objects returned?
   - Ask: Could a failed operation produce fake data that looks valid?

---

## Checklist for Code Review

Copy this into your PR review template:

```markdown
## Security & Error Handling

- [ ] No broad `except Exception` catches
- [ ] Specific exceptions raised for expected failures
- [ ] Unexpected exceptions re-raised with context
- [ ] No secrets in logs or exception messages
- [ ] File paths validated with `.resolve().is_relative_to()`
- [ ] No fake/garbage objects returned on failure
- [ ] State corruption raises exception, not returns default
- [ ] All modified functions have docstrings with "Raises:" section

## Type Safety

- [ ] Modern type hints used (`dict`, `str | None`, not `Dict`, `Optional`)
- [ ] Callable parameters specify signature: `Callable[[str, str], LLMResponse]`
- [ ] No bare `Callable` without parameter/return types
- [ ] Functions document exceptions in "Raises:" section

## Testing

- [ ] Tests verify exceptions are raised, not swallowed
- [ ] Corruption/encoding error cases are tested
- [ ] Path traversal attempts are blocked (if file I/O)
- [ ] Secrets never appear in logs (grep logs for patterns)
```

---

## Related Standards

See also:
- `PREVENTION_STRATEGIES.md` — Detailed prevention strategies for each issue
- `CRITICAL_ISSUES.md` — Original issue descriptions
- `FIXES_REFERENCE.md` — Complete fixed code (copy-pasteable)
- `CLAUDE.md` — Coding standards this project follows
