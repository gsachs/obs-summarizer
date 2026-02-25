---
title: "Path Traversal, Config Injection, Dead Return, and Extract JSON Refactor"
date: 2026-02-25
problem_type:
  - security-issues
  - runtime-errors
  - code-quality
component:
  - scanner.py
  - config.py
  - summarizer.py
  - llm.py
symptoms:
  - "include_folders accepted paths outside the vault root, enabling path traversal via .. segments"
  - "cache_dir and state_path accepted absolute paths such as /etc/cron.d without validation"
  - "extract_json was a nested 55-line function inside summarize_note, untestable in isolation and shadowing the outer content parameter"
  - "extract_json raised json.JSONDecodeError instead of the semantically correct ValueError"
  - "call_claude and call_local retry loops returned None implicitly when retries exhausted, causing AttributeError at the call site"
tags:
  - python
  - security
  - path-traversal
  - config-validation
  - refactoring
  - error-handling
  - retry-logic
  - pytest
  - pathlib
  - obsidian
related_files:
  - src/obs_summarizer/scanner.py
  - src/obs_summarizer/config.py
  - src/obs_summarizer/summarizer.py
  - src/obs_summarizer/llm.py
  - tests/test_scanner.py
  - tests/test_config.py
  - tests/test_summarizer.py
---

# Path Traversal, Config Injection, Dead Return, and Extract JSON Refactor

## Problem

Four bugs were identified and fixed in the `obs-summarizer` Python CLI tool across two security vulnerabilities, one code quality issue, and one reliability gap.

**Security: `include_folders` path traversal (`scanner.py`)**
The `include_folders` configuration option accepted arbitrary relative path strings and constructed `Path` objects by joining them directly to the vault root. Because `pathlib` resolves `..` segments silently, a config entry like `../../etc` resolved to a directory outside the vault boundary without any error.

**Security: `cache_dir` / `state_path` accept absolute paths (`config.py`)**
`cache_dir` and `state_path` config values were accepted without validation. Setting them to absolute paths like `/etc/cron.d` caused the application to write JSON files to arbitrary locations. The fix for `digest_folder` (SEC-HIGH-001) used a three-layer validation approach but these two paths were never validated, creating an inconsistent security model.

**Code quality: Nested `extract_json` untestable and wrong exception type (`summarizer.py`)**
`extract_json` was a 55-line function defined inside `summarize_note`, closing over nothing from the outer scope. It shadowed the outer `content` parameter, could not be tested in isolation, and raised `json.JSONDecodeError` where `ValueError` was the semantically correct exception — causing the outer retry handler to catch an artificially-raised error as if it were a real parse failure.

**Reliability: Implicit `None` return after LLM retry loops (`llm.py`)**
`call_claude` and `call_local` had no explicit `raise` after their retry loops. If the loop exhausted all attempts without hitting an explicit `return` or `raise`, Python returned `None` implicitly. The caller (`summarizer.py`) then accessed `.content` on `None`, producing `AttributeError: 'NoneType' object has no attribute 'content'` far from the actual failure site.

## Solution

### Fix 1: Path Traversal in `include_folders` (`scanner.py`)

**Root cause:** Direct `vault / folder` path construction with no boundary check.

Before:
```python
if include_folders:
    roots = [vault / folder for folder in include_folders]
```

After:
```python
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
```

`Path.resolve()` expands all symlinks and `..` segments to produce an absolute canonical path. `Path.relative_to()` raises `ValueError` if the resolved candidate is not within the resolved vault root — making the boundary check immune to traversal tricks. The error message includes both the vault and resolved paths for immediate diagnosis.

---

### Fix 2: Absolute Path Rejection for `cache_dir` / `state_path` (`config.py`)

**Root cause:** No validation after the `setdefault` calls that establish these config keys.

Added immediately after the `setdefault` block:
```python
# SECURITY: Reject absolute paths for write destinations
# Prevents writing cache/state files to arbitrary system locations
for path_key in ("cache_dir", "state_path"):
    path_val = config[path_key]
    if Path(path_val).is_absolute():
        raise ConfigError(
            f"'{path_key}' must be a relative path, got: {path_val}\n"
            f"Relative paths are resolved from the working directory."
        )
```

`Path(path_val).is_absolute()` returns `True` for any path starting with a filesystem root. Raising `ConfigError` at config load time — before any file I/O — follows fail-fast: the error surfaces with a clear message at the earliest possible moment, and no partial state is written.

---

### Fix 3: `extract_json` → Module-Level `_parse_json` (`summarizer.py`)

**Root cause:** 55-line nested function entangling JSON parsing with the summarization workflow; wrong exception type leaked implementation details.

Removed the nested function entirely. Added module-level:
```python
def _parse_json(text: str) -> dict:
    """Extract JSON object from LLM response text.

    Handles:
    - Clean JSON responses (direct parse)
    - JSON embedded in prose or after preamble text (brace extraction)

    Raises:
        ValueError: If no valid JSON object can be extracted
    """
    text = text.strip()

    # Method 1: Direct parse (ideal case)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Method 2: Brace extraction (handles preamble text or trailing text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Cannot parse JSON from LLM response: {text[:200]!r}")
```

Both call sites in `summarize_note` now catch `ValueError`. The leading underscore signals private module scope without exposing it as part of the public API. The 200-char truncation in the error avoids flooding logs while remaining actionable.

---

### Fix 4: Explicit Raise After LLM Retry Loops (`llm.py`)

**Root cause:** `for` loop exits normally when it exhausts its range; Python returns `None` from a function with no `return` statement.

Added after each retry loop body:
```python
raise RuntimeError("call_claude: exhausted 3 attempts without returning or raising")
```

Also tightened `Callable` type annotations to make the return contract explicit:
```python
def create_llm_client(config: Dict) -> Callable[[str, str], LLMResponse]:
def _create_claude_client(config: Dict) -> Callable[[str, str], LLMResponse]:
def _create_local_client(config: Dict) -> Callable[[str, str], LLMResponse]:
```

`mypy`/`pyright` can now catch mismatches between factory return type and call sites at analysis time rather than runtime.

## Tests Added

**scanner.py** — `tests/test_scanner.py`:
```python
def test_list_markdown_files_include_folders_traversal(tmp_vault, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.md").write_text("secret")

    with pytest.raises(ValueError, match="outside vault boundary"):
        list_markdown_files(str(tmp_vault), include_folders=["../outside"])
```

**config.py** — `tests/test_config.py`:
```python
@pytest.mark.parametrize("path_key", ["cache_dir", "state_path"])
def test_load_config_rejects_absolute_paths(tmp_vault, path_key):
    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "config.yaml"
        config_file.write_text(
            f"vault_path: {tmp_vault}\n"
            "llm_backend: local\n"
            "local_base_url: http://localhost:1234/v1\n"
            f"{path_key}: /etc/cron.d\n"
        )
        with pytest.raises(ConfigError, match="must be a relative path"):
            load_config(str(config_file))
```

**summarizer.py** — `tests/test_summarizer.py`:
```python
def test_parse_json_direct():
    assert _parse_json('{"key": "value"}') == {"key": "value"}

def test_parse_json_with_preamble():
    assert _parse_json('Here is the JSON: {"key": "value"} done.') == {"key": "value"}

def test_parse_json_invalid():
    with pytest.raises(ValueError):
        _parse_json("not json at all")
```

Final test count: **78 passed** (up from 72 before this session).

## Prevention

### Path Handling in Python CLI Tools

**Always resolve before comparing.** Call `Path.resolve()` on both the untrusted input and the intended root before any comparison. Unresolved paths allow `..` sequences and symlinks to escape the intended directory.

```python
# Correct pattern
resolved = Path(user_input).resolve()
resolved.relative_to(vault_root.resolve())  # raises ValueError if outside

# Wrong — string prefix checks are trivially bypassed
user_input.startswith(str(vault_root))
```

**Reject absolute paths at the configuration boundary.** Any path a user configures for cache, state, or output should be relative to a well-defined project root. Validate this at config load time, not at use time, so the error surfaces immediately with a clear message rather than at the moment of a write deep in the call stack.

**Validate at the boundary, use freely inside.** Once a path has been validated and resolved, pass the resolved `Path` object through the rest of the call stack. Do not re-validate the same path repeatedly, and do not pass raw strings that must be re-resolved later.

---

### LLM API Retry and Error-Handling Patterns

**Make the exhausted-retry case explicit and loud.** After every retry loop, the code must either return a valid result or raise. There is no third option.

```python
# Correct
for attempt in range(max_retries):
    try:
        return call_llm(prompt)
    except TransientError:
        continue
raise RuntimeError(f"LLM call failed after {max_retries} attempts")

# Wrong — falls off the end, returns None implicitly
for attempt in range(max_retries):
    try:
        return call_llm(prompt)
    except TransientError:
        continue
```

**Distinguish retriable from fatal errors.** Only catch exceptions that indicate a transient condition (rate limits, timeouts, network errors). Let authentication errors, malformed-request errors, and other permanent failures propagate immediately.

**Raise the right exception type at the right level of abstraction.** `RuntimeError("LLM call failed after 3 attempts")` is meaningful to the pipeline. `anthropic.APIStatusError` is not.

**Extract JSON parsing to a dedicated, testable function.** Nesting parsing logic inside a retry loop entangles concerns, prevents direct testing, and makes the retry logic harder to read. A module-level `_parse_json` raises `ValueError` on malformed input — easy to assert in tests and easy to compose.

---

### Code Review Checklist

When reviewing path-handling code:

- [ ] Every user-supplied path is resolved with `Path.resolve()` before any comparison or use
- [ ] Paths that must remain within a root directory are checked with `.relative_to()`, not string prefix matching
- [ ] Configuration values for cache, state, or output directories are validated as relative paths at load time, not at use time
- [ ] No `Path` construction or `open()` call receives an unvalidated string from config or user input

When reviewing LLM retry loops:

- [ ] Every retry loop ends with an explicit `raise` — never an implicit `return None`
- [ ] The exception caught in the retry condition is the narrowest possible type (transient errors only)
- [ ] JSON parsing from LLM responses is extracted into a standalone function, not inlined in the retry body
- [ ] The extracted parsing function raises `ValueError` (not `json.JSONDecodeError` or a catch-all) on malformed input
- [ ] All exception messages include enough context to diagnose the failure without a debugger

When reviewing any function extracted from a larger block:

- [ ] No parameter shadowing — extracted function's parameter names don't shadow outer scope names
- [ ] The function raises the semantically correct exception type for its level of abstraction
- [ ] The function is directly reachable from tests without invoking its former host function

---

### Test Patterns That Catch These Issues Early

**Test boundary enforcement directly, not through a happy path.** For path traversal, construct an explicit traversal payload (`../../../etc/passwd`) and assert `ValueError` is raised with a message identifying the violation.

**Parametrize security-boundary tests across all relevant config keys.** The parametrized `test_load_config_rejects_absolute_paths` pattern ensures that adding a new path-type config field requires adding a new parameter, making omission visible at test-authoring time.

**Test extracted functions in isolation before testing them through callers.** `test_parse_json_direct`, `test_parse_json_with_preamble`, and `test_parse_json_invalid` give `_parse_json` a complete behavioral specification. If the parsing logic regresses, these tests fail immediately and point to the exact function.

**Test the exhausted-retry case explicitly.** Mock the LLM client to raise a transient error on every call, then assert that the pipeline raises `RuntimeError` rather than returning `None` or silently producing empty output.

**Always use `match=` in `pytest.raises`.** A bare `pytest.raises(ValueError)` passes if *any* `ValueError` is raised anywhere — including from unrelated code. Asserting on the message text (`match="outside vault boundary"`) ties the test to the specific invariant being enforced.

## Related

- [`docs/solutions/security-issues/critical-security-and-python-error-handling.md`](critical-security-and-python-error-handling.md) — Phase 1 fixes: API key exposure, `digest_folder` path traversal, overly broad exception handling, fake summary objects, silent state corruption
- [`docs/plans/2026-02-25-feat-obsidian-digest-agent-plan.md`](../../plans/2026-02-25-feat-obsidian-digest-agent-plan.md) — Original implementation plan; Phase 2a specifies retry backoff strategy, Phase 3b specifies partial failure tolerance
- Todos resolved: 009 (scanner traversal), 010 (extract_json refactor), 011 (implicit None LLM), 012 (cache_dir/state_path)
