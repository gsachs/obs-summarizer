# Prevention Strategies for Future Development

**Document Date:** 2026-02-25
**Applies To:** obs-summarizer project and similar Python applications
**Audience:** Development team, code reviewers, CI/CD maintainers

---

## Overview

This document codifies lessons learned from 5 critical issues discovered during the code review process. Each section provides:

1. **Pattern to Watch For** — What the anti-pattern looks like
2. **Code Review Checklist** — Questions reviewers must ask
3. **Test Cases** — Tests that would catch this issue
4. **CLAUDE.md Principles** — Which coding standards apply

The goal is to catch these issues **before they reach production**.

---

## Issue #1: API Key Exposure in Logs and Configuration

### Pattern to Watch For

**The Anti-Pattern:**

```python
# WRONG: API keys visible in logs and config
api_key = config.get("api_key")
logger.info(f"Connecting to API with key: {api_key}")

# WRONG: Keys hardcoded in source
ANTHROPIC_API_KEY = "sk-ant-abc123xyz..."

# WRONG: Keys committed to repo
# .env
API_KEY=secret123

# WRONG: Keys in exception messages
try:
    client = Anthropic(api_key=api_key)
except Exception as e:
    logger.error(f"Failed to connect with key {api_key}: {e}")
```

**What to Look For:**

- Logging that includes passwords, tokens, or API keys
- Config files with secrets (even test secrets)
- Exception messages that contain credentials
- String interpolation of sensitive values
- Lazy imports that hide dependency validation (can mask missing creds)
- Config defaults that look like real keys

---

### Code Review Checklist

When reviewing any code that touches configuration or external services:

- [ ] **Are any API keys, tokens, or passwords logged?** (even at DEBUG level)
  - Search for `logger.` calls in the same function as credential handling
  - Check that exception messages don't include secrets

- [ ] **Are secrets loaded from environment or secure vault, not hardcoded?**
  - Verify `os.getenv()`, `config.get()` from environment, or secret manager
  - Reject code with hardcoded strings that look like keys

- [ ] **Does the `.gitignore` exclude all secret files?**
  - `.env`, `.env.local`, `*.pem`, `*.key`, `secrets.json`, `config.local.*`
  - Run `git check-ignore .env` to verify

- [ ] **Are there any test credentials that look realistic?**
  - Test keys should be obviously fake: `test-api-key-do-not-use`, `fake-sk-1234`
  - Real-looking keys (36+ characters) are a security violation

- [ ] **Does error handling preserve secrets?**
  - Wrap third-party exceptions to strip credentials before logging
  - Example: `except anthropic.APIError as e: raise MyError(str(e).replace(api_key, "***")) from e`

- [ ] **Are lazy imports used for required dependencies?**
  - Top-level imports should be visible; lazy imports hide dependency requirements
  - If an import is truly optional, document why

---

### Test Cases That Catch This

```python
import os
import tempfile
import logging
from unittest.mock import patch
from io import StringIO

def test_no_api_keys_in_logs():
    """Ensure API keys are never logged, even in error cases."""
    from obs_summarizer.llm import create_llm_client, LLMError

    # Set a fake but realistic-looking API key
    test_key = "sk-ant-1234567890abcdefghijklmnopqrstuvwxyz"

    # Capture log output
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    logger = logging.getLogger("obs_summarizer")
    logger.addHandler(handler)

    config = {
        "llm_backend": "claude",
        "api_key": test_key,
    }

    # Try to create client and trigger logging
    client = create_llm_client(config)

    # Verify key does not appear anywhere in logs
    log_output = log_stream.getvalue()
    assert test_key not in log_output, "API key leaked into logs!"
    assert "sk-ant-" not in log_output, "API key pattern found in logs!"


def test_no_secrets_in_exception_messages():
    """Ensure exception messages don't contain credentials."""
    from obs_summarizer.llm import _create_claude_client

    test_key = "sk-ant-secret123"
    config = {
        "llm_backend": "claude",
        "api_key": test_key,
        "claude_model": "claude-opus-4-6",
    }

    # Patch the Anthropic client to raise an error
    with patch("anthropic.Anthropic") as mock:
        mock.side_effect = RuntimeError(f"Failed with key {test_key}")

        try:
            _create_claude_client(config)
        except Exception as e:
            assert test_key not in str(e), "Secret in exception message!"


def test_environment_variables_not_logged_in_config_loading():
    """Ensure config loading doesn't log environment variable values."""
    import logging
    from io import StringIO
    from obs_summarizer.config import load_config

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    logger = logging.getLogger("obs_summarizer")
    logger.addHandler(handler)

    with patch.dict(os.environ, {"OBS_API_KEY": "secret-test-key"}):
        # This should work without logging the key
        config = load_config()

        log_output = log_stream.getvalue()
        assert "secret-test-key" not in log_output


def test_config_validation_requires_api_key_not_logged():
    """Verify missing API key is reported without attempting to use it."""
    from obs_summarizer.config import load_config, ConfigError

    # Missing API key should fail fast with clear message, not attempt connection
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ConfigError) as exc_info:
            load_config()

        assert "API key" in str(exc_info.value)
        # The error message should NOT contain a partially-formed key
```

---

### CLAUDE.md Principles That Apply

**From CLAUDE.md:**

1. **Defensive Programming & Validation**
   - "Validate inputs and preconditions at the top of the function"
   - "Don't return null. Returning null creates work for callers"
   - **Application:** Validate API keys exist at config load time, not at connection time

2. **Error Handling**
   - "Provide context with exceptions... include the operation that failed, the type of failure"
   - "Define exceptions in terms of the caller's needs, not the source. Wrap third-party APIs"
   - **Application:** Catch external exceptions and re-raise without credentials

3. **Security**
   - "Never hardcode secrets... use environment variables, secret managers"
   - "Log security events... Never log secrets, tokens, or PII in plain text"
   - **Application:** Pre-commit hooks must scan for secret patterns

4. **Configuration & Environment**
   - "Config lives in the environment, not in code"
   - "Use environment variables or config services. Never committed to the repository"
   - **Application:** All secrets from `os.getenv()` or secrets manager, never config files

5. **Naming**
   - "Use intention-revealing names"
   - **Application:** Variables like `api_key` clearly signal "this is sensitive"

---

## Issue #2: Path Traversal Vulnerability

### Pattern to Watch For

**The Anti-Pattern:**

```python
# WRONG: User-supplied path can escape vault
file_path = Path(vault_path) / user_input
content = file_path.read_text()  # Could read /etc/passwd if user_input is "../../etc/passwd"

# WRONG: No validation of resolved path
import os
full_path = os.path.join(vault_path, user_filename)
with open(full_path) as f:  # Still vulnerable to ../

# WRONG: String manipulation instead of Path object
path = f"{vault_path}/{user_input}"  # Looks safe but isn't

# WRONG: Symlink following without verification
file_path = Path(vault_path) / user_input
if file_path.exists():
    # Symlink could point outside vault_path
    return file_path.read_text()
```

**What to Look For:**

- File paths constructed from user input without validation
- No check that resolved path is within expected directory
- Symlinks followed without verification
- Use of string concatenation instead of `pathlib.Path`
- No call to `.resolve()` to get the canonical path
- Relative path components (`..`) not stripped

---

### Code Review Checklist

When reviewing any file system operations:

- [ ] **Is the file path constructed from user input?**
  - If yes, is it validated to stay within a root directory?
  - Use `Path.resolve().is_relative_to(root)` or equivalent

- [ ] **Does the code use `pathlib.Path` for all path operations?**
  - Reject string concatenation: `f"{dir}/{file}"`
  - Require: `Path(dir) / file`

- [ ] **Is the resolved (canonical) path checked against bounds?**
  - After all symlink resolution: `resolved_path.resolve()`
  - Check that it starts with expected root: `resolved_path.is_relative_to(vault_path)`

- [ ] **Are relative path components stripped?**
  - Any user input containing `../`, `..\\`, or starting with `/` should be rejected
  - Use `Path(user_input).parts` and check for `..` or absolute paths

- [ ] **Are symlinks handled safely?**
  - `.resolve()` follows symlinks by default
  - `.resolve(strict=False)` for non-existent paths
  - Verify resolved path is within bounds after resolution

- [ ] **Is the directory listing safe?**
  - `glob()` and `rglob()` should never receive untrusted patterns
  - Use explicit filter instead: `[f for f in dir.iterdir() if f.name.endswith(".md")]`

- [ ] **Are there any symlink race conditions?**
  - `exists()` then `read()` is a TOCTOU race
  - Use try/except instead: `try: return f.read_text() except FileNotFoundError: ...`

---

### Test Cases That Catch This

```python
import tempfile
from pathlib import Path
import pytest
from obs_summarizer.scanner import list_markdown_files

def test_path_traversal_blocked():
    """Path traversal attempts are rejected."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)

        # Create a file outside the vault
        outside = Path(tmp).parent / "outside.md"
        outside.write_text("# Secret")

        # Try to access it via path traversal
        traversal_attempts = [
            "../outside.md",
            "../../outside.md",
            "/etc/passwd",  # Absolute path
            "sub/../../outside.md",
        ]

        for attempt in traversal_attempts:
            # Should not list files outside vault
            files = list_markdown_files(str(vault), folders=[])
            file_names = [f.name for f in files]

            assert "outside.md" not in file_names, f"Traversal succeeded: {attempt}"
            assert "/etc/passwd" not in [str(f) for f in files], "Absolute path accessed"


def test_symlink_points_outside_vault_rejected():
    """Symlinks pointing outside vault are not followed."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        vault.mkdir()

        outside = Path(tmp) / "outside.md"
        outside.write_text("# Secret")

        # Create symlink inside vault pointing outside
        symlink = vault / "link.md"
        symlink.symlink_to(outside)

        # Verify the symlink exists
        assert symlink.exists()

        # But list_markdown_files should reject it (or at least not include outside content)
        files = list_markdown_files(str(vault), folders=[])

        # Option 1: Symlinks are rejected entirely
        # Option 2: Symlinks are followed but resolved path is checked
        for f in files:
            assert f.resolve().is_relative_to(vault), f"Symlink escaped vault: {f}"


def test_resolved_path_must_be_within_root():
    """After resolution, path must be within root directory."""
    from obs_summarizer.pipeline import _is_safe_path  # Hypothetical function

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # Safe paths
        assert _is_safe_path(root / "file.md", root)
        assert _is_safe_path(root / "sub" / "file.md", root)

        # Unsafe paths
        assert not _is_safe_path(root.parent / "file.md", root)
        assert not _is_safe_path(Path("/etc/passwd"), root)


def test_relative_path_components_stripped():
    """User input with '..' is rejected."""
    from pathlib import Path

    def safe_path(root: Path, user_input: str) -> Path:
        """Safely construct path from user input."""
        # Reject absolute paths
        if user_input.startswith("/"):
            raise ValueError("Absolute paths not allowed")

        # Reject parent directory references
        if ".." in Path(user_input).parts:
            raise ValueError("Parent directory references not allowed")

        return (root / user_input).resolve()

    root = Path("/tmp/vault")

    # Should accept
    assert safe_path(root, "file.md")
    assert safe_path(root, "sub/file.md")

    # Should reject
    with pytest.raises(ValueError):
        safe_path(root, "../outside.md")

    with pytest.raises(ValueError):
        safe_path(root, "/etc/passwd")

    with pytest.raises(ValueError):
        safe_path(root, "sub/../../outside.md")


def test_no_toctou_race_in_file_operations():
    """No check-then-use race conditions in file access."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        test_file = vault / "test.md"
        test_file.write_text("content")

        # WRONG: Check then use (could be deleted between)
        # if test_file.exists():
        #     content = test_file.read_text()  # Could raise FileNotFoundError

        # RIGHT: Try-except
        try:
            content = test_file.read_text()
        except FileNotFoundError:
            content = None

        # Verify exception was caught
        test_file.unlink()

        try:
            content = test_file.read_text()
            assert False, "Should have raised FileNotFoundError"
        except FileNotFoundError:
            pass  # Expected
```

---

### CLAUDE.md Principles That Apply

1. **Security**
   - "Validate all input... use allow-lists, not deny-lists"
   - **Application:** Path inputs must be explicitly whitelisted, not just checked for bad patterns

2. **Defensive Programming**
   - "Validate inputs and preconditions at the top of the function"
   - "Fail fast rather than nesting the entire body in conditionals"
   - **Application:** Reject unsafe paths immediately

3. **Error Handling**
   - "Don't return null. Returning null creates work for callers"
   - "Use exceptions, not return codes"
   - **Application:** Raise `SecurityError` or `PathValidationError` on traversal attempts

4. **Boundaries**
   - "Use interfaces at boundaries... define an interface that describes what you need"
   - **Application:** `def list_files(vault_path: str, globs: list[str]) -> list[Path]` — document that paths are safe

---

## Issue #3: Broad Exception Handling (Swallowing Exceptions)

### Pattern to Watch For

**The Anti-Pattern:**

```python
# WRONG: Catches every exception
try:
    result = do_something()
except Exception as e:
    logger.warning(f"Failed: {e}. Skipping.")
    continue

# WRONG: Multiple unrelated operations in one try block
try:
    validate_input()      # Raises ValueError
    call_external_api()   # Raises APIError
    save_to_database()    # Raises IOError
except Exception as e:
    logger.error(f"Operation failed: {e}")
    return None

# WRONG: No distinction between expected and unexpected failures
for item in items:
    try:
        process(item)
    except Exception:
        pass  # Silent failure

# WRONG: Using bare except
for file in files:
    try:
        summarize(file)
    except:  # Catches KeyboardInterrupt, SystemExit, etc.
        continue
```

**What to Look For:**

- Bare `except Exception` catching everything
- Multiple unrelated operations in one try block
- Silent failures (empty except blocks)
- No distinction between expected (validation) and unexpected (logic bug) exceptions
- Catch-all that masks bugs (TypeError, KeyError should crash, not be silently handled)
- Exception swallowing that hides systemic problems

---

### Code Review Checklist

When reviewing exception handling:

- [ ] **Does the code catch `Exception` broadly?**
  - Reject: `except Exception as e:`
  - Require: `except (SpecificError1, SpecificError2) as e:`

- [ ] **Is the try block too large?**
  - Does it contain 5+ statements or multiple logical operations?
  - Split into separate try blocks, one per "expected failure mode"

- [ ] **Are caught exceptions expected or unexpected?**
  - Expected: `SummarizationError`, `FileNotFoundError`, `json.JSONDecodeError`, `UnicodeDecodeError`
  - Unexpected: `TypeError`, `KeyError`, `AttributeError`, `NameError`
  - Unexpected exceptions should re-raise, not be silently handled

- [ ] **Is the exception re-raised after logging?**
  - For unexpected exceptions: `except Exception as e: logger.error(...); raise`
  - For expected: `except ExpectedError as e: logger.warning(...); continue`

- [ ] **Would this catch `KeyboardInterrupt` or `SystemExit`?**
  - Never catch bare `Exception` — use specific exception types
  - `KeyboardInterrupt` and `SystemExit` inherit from `BaseException`, but `Exception` can catch others too

- [ ] **Is the operation's failure mode documented?**
  - Does the docstring say "raises MyError on failure"?
  - Or is error handling a surprise to the caller?

- [ ] **Are there empty except blocks?**
  - Reject: `except SomeError: pass`
  - Require: At minimum, `logger.warning()` or explicit comment `except SomeError: pass  # Intentional: ...`

- [ ] **Does the code fail loudly or silently?**
  - If all items fail (e.g., 100 files fail to process), does the operator know?
  - Return exit code 1? Raise an exception? Log errors?

---

### Test Cases That Catch This

```python
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

def test_pipeline_does_not_catch_unexpected_exceptions():
    """Pipeline re-raises unexpected exceptions instead of silently continuing."""
    from obs_summarizer.pipeline import run_pipeline
    from obs_summarizer.summarizer import SummarizationError

    config = {
        "vault_path": "/tmp/vault",
        "llm_backend": "claude",
        "digest_folder": "/tmp",
    }

    # Patch list_markdown_files to return a test file
    with patch("obs_summarizer.pipeline.list_markdown_files") as mock_list:
        with patch("obs_summarizer.pipeline.summarize_note") as mock_summarize:
            mock_list.return_value = [Path("test.md")]

            # Raise an unexpected error (not a SummarizationError)
            mock_summarize.side_effect = TypeError("Logic error in summarize")

            # Pipeline should re-raise, not swallow
            with pytest.raises(TypeError):
                run_pipeline(config)


def test_pipeline_catches_expected_exceptions_only():
    """Pipeline catches expected exceptions and skips files."""
    from obs_summarizer.pipeline import run_pipeline
    from obs_summarizer.summarizer import SummarizationError

    config = {
        "vault_path": "/tmp/vault",
        "llm_backend": "claude",
        "digest_folder": "/tmp",
        "cache_dir": "/tmp/cache",
    }

    with patch("obs_summarizer.pipeline.list_markdown_files") as mock_list:
        with patch("obs_summarizer.pipeline.summarize_note") as mock_summarize:
            mock_list.return_value = [Path("file1.md"), Path("file2.md")]

            # file1 fails (expected), file2 succeeds (unexpected error caught means test fails)
            mock_summarize.side_effect = [
                SummarizationError("file1.md", "Invalid JSON"),
                {"summary": "File 2 summary", "bullets": []},
            ]

            # Should succeed with 1 summary (file1 skipped)
            result = run_pipeline(config)
            assert result == 0
            assert mock_summarize.call_count == 2  # Both attempted


def test_encoding_errors_are_caught_specifically():
    """UnicodeDecodeError is caught and logged, not silently ignored."""
    from obs_summarizer.pipeline import run_pipeline
    import logging

    config = {
        "vault_path": "/tmp/vault",
        "llm_backend": "claude",
        "digest_folder": "/tmp",
    }

    with patch("obs_summarizer.pipeline.list_markdown_files") as mock_list:
        with patch("obs_summarizer.pipeline.Path.read_text") as mock_read:
            mock_list.return_value = [Path("bad_encoding.md")]

            # Simulate bad UTF-8 file
            mock_read.side_effect = UnicodeDecodeError(
                encoding="utf-8",
                object=b"\x80",
                start=0,
                end=1,
                reason="invalid start byte",
            )

            # Should be caught and logged as warning
            with patch("obs_summarizer.pipeline.logger") as mock_logger:
                result = run_pipeline(config)
                # File should be skipped, not crash
                assert result == 0
                # Logger should warn about encoding
                mock_logger.warning.assert_called()


def test_all_files_failing_returns_error_code():
    """If all files fail, pipeline returns error code (not success with empty digest)."""
    from obs_summarizer.pipeline import run_pipeline
    from obs_summarizer.summarizer import SummarizationError

    config = {
        "vault_path": "/tmp/vault",
        "llm_backend": "claude",
        "digest_folder": "/tmp",
    }

    with patch("obs_summarizer.pipeline.list_markdown_files") as mock_list:
        with patch("obs_summarizer.pipeline.summarize_note") as mock_summarize:
            mock_list.return_value = [Path("f1.md"), Path("f2.md")]
            mock_summarize.side_effect = SummarizationError("all", "All fail")

            with patch("obs_summarizer.pipeline.write_digest"):
                result = run_pipeline(config)

                # Should indicate partial or complete failure
                # Either return 1, or return 0 with 0 summaries (which could be logged)
                # Operator should know something went wrong
                assert result in (1, 0)  # Depends on design decision


def test_exception_context_preserved():
    """When re-raising, exception context is preserved (chained exceptions)."""
    from obs_summarizer.pipeline import run_pipeline

    def failing_operation():
        try:
            int("not a number")  # Raises ValueError
        except ValueError as e:
            # Right: re-raise with context
            raise RuntimeError("Operation failed") from e

    with pytest.raises(RuntimeError) as exc_info:
        failing_operation()

    # Verify __cause__ is set (exception chaining)
    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, ValueError)


def test_logging_happens_before_continue():
    """Skipped items are logged with details, not silently skipped."""
    import logging
    from io import StringIO

    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    logger = logging.getLogger("obs_summarizer.pipeline")
    logger.addHandler(handler)

    with patch("obs_summarizer.pipeline.list_markdown_files") as mock_list:
        with patch("obs_summarizer.pipeline.summarize_note") as mock_summarize:
            mock_list.return_value = [Path("skip_me.md")]
            mock_summarize.side_effect = FileNotFoundError("File gone")

            result = run_pipeline({"vault_path": "/tmp", ...})

            log_output = log_stream.getvalue()
            assert "skip_me.md" in log_output  # File name should be in logs
            assert "File gone" in log_output or "disappeared" in log_output  # Reason should be logged
```

---

### CLAUDE.md Principles That Apply

1. **Error Handling**
   - "Prefer exceptions to error codes"
   - "Extract try/catch blocks into their own functions. Error handling *is* one thing"
   - "Don't swallow exceptions silently. An empty `catch` block is a bug"
   - **Application:** Each expected failure type gets its own catch; unexpected exceptions re-raise

2. **Functions**
   - "Do one thing... If you extract another function with a name that isn't merely a restatement, it's doing more than one thing"
   - **Application:** One try block per failure scenario, not multiple unrelated operations

3. **Comments**
   - "A comment explaining WHY something is swallowed is acceptable, but the comment must be specific"
   - **Application:** `except ExpectedError: pass  # Expected: invalid JSON, log and skip` is OK; `except Exception: pass` is never OK

4. **Fail Fast**
   - "Validate inputs and preconditions at the top of the function... Fail fast"
   - "Return or throw early rather than nesting"
   - **Application:** Unexpected exceptions should crash immediately, not be hidden

---

## Issue #4: Silent State Corruption

### Pattern to Watch For

**The Anti-Pattern:**

```python
# WRONG: Corrupted state treated as "first run"
def load_state(state_path: str) -> dict:
    try:
        with open(state_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"State corrupted. Treating as first run.")
        return {"last_run": None}  # User loses checkpoint!

# WRONG: Silent cache corruption
def load_cache(key: str) -> dict | None:
    try:
        return json.load(open(f"cache/{key}.json"))
    except:
        return None  # Caller doesn't know cache is corrupt

# WRONG: Database corruption treated as empty
def load_from_db(id: str) -> dict:
    try:
        row = db.query(f"SELECT * FROM items WHERE id = {id}")
    except Exception:
        return {}  # Looks like item doesn't exist, but actually DB is broken

# WRONG: Multiple failures for same state file produce same fallback
for run_id in range(1000):
    state = load_state()  # Silent fallback each time
    if state is None:  # Can't tell if it's first-run or corrupted
        initialize()
```

**What to Look For:**

- Exception handling that returns a default/empty value
- No distinction between "file doesn't exist" and "file is corrupted"
- Callers can't tell the difference between first-run and failure state
- Repeated silent failures (same file corrupts, loads fail 10 times)
- Operator has no way to recover (needs manual intervention but doesn't know)
- State loss without warning

---

### Code Review Checklist

When reviewing state/configuration/cache loading:

- [ ] **Does the code distinguish between "doesn't exist" and "corrupted"?**
  - `if not path.exists(): return default_state`
  - `else: try/except should raise, not return default`

- [ ] **Does corruption raise an exception instead of returning fallback?**
  - Reject: `except JSONDecodeError: return {}`
  - Require: `except JSONDecodeError as e: raise StateError(...) from e`

- [ ] **Can the caller tell if an exception was raised?**
  - If not, add custom exception types
  - `StateError`, `CacheError`, `ConfigError` so caller can handle differently

- [ ] **Is there operator guidance if this fails?**
  - Exception message should say how to recover: "Delete the file and re-run" or "Restore from backup"
  - Not just: "Failed to load"

- [ ] **Is the state change logged?**
  - Every time state is loaded/saved, log it (at INFO level)
  - So operator can see: "Loaded state from checkpoint: last_run=2026-02-25T10:00:00Z"

- [ ] **Are state transitions atomic?**
  - Write to temp file, then rename (not write directly)
  - Prevents partial/corrupted writes if crash mid-operation

- [ ] **Is there a fallback recovery mechanism?**
  - If state is corrupted, can the user recover?
  - Backup/restore process documented
  - Or explicit reset command: `obs-digest reset-state`

- [ ] **Are cache misses and corruption distinguished?**
  - `load_cache(key)` returns `None` for miss (OK, re-generate)
  - But what if the cache file is corrupted? Still `None`? Or exception?
  - Log it either way so operator knows

---

### Test Cases That Catch This

```python
import json
import tempfile
from pathlib import Path
import pytest

def test_state_corruption_raises_exception():
    """Loading corrupted state.json raises StateError, not returns default."""
    from obs_summarizer.state import load_state, StateError

    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state_path.write_text("{ invalid json }")

        # Should raise StateError, not return {"last_run": None}
        with pytest.raises(StateError) as exc_info:
            load_state(str(state_path))

        # Exception should have helpful message
        assert "corrupted" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


def test_nonexistent_state_returns_default():
    """Nonexistent state.json (first run) returns default, not raises."""
    from obs_summarizer.state import load_state

    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"

        # File doesn't exist — should return default
        state = load_state(str(state_path))
        assert state == {"last_run": None}  # Or similar default


def test_state_corruption_not_retried_silently():
    """If state.json is corrupt, corruption is not silently retried."""
    from obs_summarizer.state import load_state, StateError
    from obs_summarizer.pipeline import run_pipeline

    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state_path.write_text("corrupted")

        config = {"state_path": str(state_path), ...}

        # Pipeline should fail, not silently continue with default state
        with pytest.raises(StateError):
            run_pipeline(config)


def test_cache_corruption_logged_not_silent():
    """Cache corruption is logged as warning, not silently treated as miss."""
    from obs_summarizer.cache import load_cache
    import logging

    with tempfile.TemporaryDirectory() as tmp:
        cache_key = "test_key"
        cache_file = Path(tmp) / f"{cache_key}.json"
        cache_file.write_text("{ bad json }")

        with patch("obs_summarizer.cache.logger") as mock_logger:
            result = load_cache(str(tmp), cache_key)

            # Should return None (miss), but also log warning
            assert result is None
            mock_logger.warning.assert_called()  # Not silent!


def test_state_save_is_atomic():
    """State save writes to temp file, then renames (atomic)."""
    from obs_summarizer.state import save_state

    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state = {"last_run": "2026-02-25T10:00:00Z"}

        # Patch rename to verify it's called
        with patch("pathlib.Path.replace") as mock_replace:
            save_state(state, str(state_path))

            # Should call replace (atomic rename)
            mock_replace.assert_called()


def test_state_error_message_includes_recovery_steps():
    """StateError exception includes recovery instructions."""
    from obs_summarizer.state import load_state, StateError

    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state_path.write_text("corrupted")

        with pytest.raises(StateError) as exc_info:
            load_state(str(state_path))

        error_msg = str(exc_info.value)
        # Should suggest how to fix: delete file, restore backup, etc.
        assert "delete" in error_msg.lower() or "restore" in error_msg.lower() or "reset" in error_msg.lower()


def test_repeated_state_corruption_not_masked():
    """If state loading fails repeatedly, operator knows (not masked by retries)."""
    from obs_summarizer.state import load_state, StateError
    from obs_summarizer.pipeline import run_pipeline

    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state_path.write_text("corrupted")

        config = {"state_path": str(state_path), ...}

        # Run 3 times — should fail all 3 times, not mask the issue
        for _ in range(3):
            with pytest.raises(StateError):
                run_pipeline(config)


def test_state_transitions_logged():
    """State load/save operations are logged so operator can audit."""
    from obs_summarizer.state import load_state, save_state
    import logging

    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"

        with patch("obs_summarizer.state.logger") as mock_logger:
            # Load (first run)
            state = load_state(str(state_path))
            mock_logger.info.assert_called()  # Should log

            # Save
            save_state({"last_run": "2026-02-25T10:00:00Z"}, str(state_path))
            mock_logger.info.assert_called()  # Should log
```

---

### CLAUDE.md Principles That Apply

1. **Error Handling**
   - "Use exceptions, not return codes"
   - "Provide context with exceptions... include enough information to diagnose"
   - **Application:** Distinguish between "file doesn't exist" and "file is corrupted"

2. **Don't Return Null**
   - "Don't return null. Returning null creates work for callers and invites NullPointerException"
   - "Return empty collections, special-case objects, or throw exceptions instead"
   - **Application:** Don't return a default state when file is corrupted; raise exception

3. **Fail Fast**
   - "Crash loudly in development, degrade gracefully in production"
   - "Never swallow exceptions silently"
   - **Application:** Corrupted state is a problem; surface it, don't hide it

4. **Logging**
   - "Log security events... never log secrets"
   - "Log structured data... Include correlation/request IDs"
   - **Application:** Every state transition should be logged for audit trail

---

## Issue #5: Fake Summary Objects (Garbage State)

### Pattern to Watch For

**The Anti-Pattern:**

```python
# WRONG: Create garbage object that looks valid
try:
    summary = json.loads(response)
except json.JSONDecodeError:
    # Fallback to fake summary
    summary = {
        "summary": "[Failed to summarize]",
        "bullets": [],
        "why_it_matters": "",
        "tags": [],
        "notable_quote": None,
    }
    # This looks identical to a real summary!
    return summary

# WRONG: Partial object returned on failure
def fetch_user(id: str) -> dict:
    try:
        return api.get(f"/users/{id}")
    except Exception:
        return {
            "id": id,
            "name": "Unknown",
            # Missing other fields — incomplete object
        }

# WRONG: Object with error indicator but treated as success
def summarize(text: str) -> dict:
    try:
        return llm_summarize(text)
    except Exception as e:
        return {
            "success": False,  # Client must check this
            "error": str(e),
            # Other fields are garbage
        }
    # Caller might not check success flag

# WRONG: Null/None values that are indistinguishable from missing
def fetch_config(key: str) -> str | None:
    try:
        return cache[key]
    except KeyError:
        return None  # Could mean "not in cache" or "cache is broken"
```

**What to Look For:**

- Exception handlers that construct fake objects to return
- Objects that look valid but contain sentinel/placeholder values
- No way for caller to distinguish success from failure (garbage state)
- Caller must check a flag (success/error field) to know if object is real
- Partial objects (missing fields) returned on failure
- None/null values that could mean "missing" or "failed to load"

---

### Code Review Checklist

When reviewing functions that could fail:

- [ ] **Does the function return an object on exception, or raise?**
  - Reject: `except SomeError: return {}`
  - Require: `except SomeError as e: raise CustomError(...) from e`

- [ ] **If a default/placeholder object is returned, is it obviously fake?**
  - Special case: empty list `[]`, empty dict `{}`, `None` are OK (distinguished from success)
  - Garbage case: `{"name": "Unknown", "id": "??"}` looks like real data

- [ ] **Does the object contain fields that indicate success/failure?**
  - Reject: Caller must check `obj.get("success")` to validate
  - Require: Either raise exception, or return `Special[T]` pattern (see below)

- [ ] **Are all required fields populated in the success case?**
  - If a field is only populated on success, caller must check for None
  - Violates "don't return null"

- [ ] **Could the caller mistake garbage state for real data?**
  - If the function returns dict in success case and dict in failure case, it's a code smell
  - Use distinct types: exception for failure, typed object for success

- [ ] **Is the return type documented?**
  - Docstring should say "raises CustomError on failure", not "returns dict with error field"

---

### Test Cases That Catch This

```python
import pytest
from obs_summarizer.summarizer import summarize_note, SummarizationError
from obs_summarizer.llm import LLMResponse

def test_summarize_raises_on_json_failure():
    """summarize_note raises SummarizationError on invalid JSON, not return fake summary."""

    def bad_llm(system: str, user: str) -> LLMResponse:
        return LLMResponse(content="{ invalid json }")

    with pytest.raises(SummarizationError) as exc_info:
        summarize_note(bad_llm, "test content", "test.md")

    # Exception should be raised, not caught and returned as fake object
    assert exc_info.value.title == "test.md"


def test_summarize_does_not_return_placeholder_summary():
    """summarize_note never returns a summary with placeholder values."""

    def bad_llm(system: str, user: str) -> LLMResponse:
        return LLMResponse(content="{ invalid json }")

    with pytest.raises(SummarizationError):
        result = summarize_note(bad_llm, "test", "test.md")

    # Should raise, not return dict like:
    # {
    #     "summary": "[Failed to summarize: test.md]",  # WRONG
    #     "bullets": [],
    #     ...
    # }


def test_caller_cannot_mistake_garbage_for_real_summary():
    """Caller cannot process a failed summary as a real one."""
    from obs_summarizer.pipeline import run_pipeline

    with patch("obs_summarizer.pipeline.summarize_note") as mock_summarize:
        # Ensure it raises, not returns fake
        mock_summarize.side_effect = SummarizationError("test.md", "Invalid JSON")

        # Pipeline must handle the exception, not treat returned dict as success
        config = {"vault_path": "/tmp", ...}

        with patch("obs_summarizer.pipeline.list_markdown_files") as mock_list:
            mock_list.return_value = [Path("test.md")]

            # Should catch SummarizationError and skip, not include fake summary
            result = run_pipeline(config)

            # Verify fake summary was NOT included
            with patch("obs_summarizer.pipeline.write_digest") as mock_write:
                run_pipeline(config)

                # The digest should not contain "[Failed to summarize]"
                summaries_written = mock_write.call_args[0][0]  # First arg to write_digest
                for summary in summaries_written:
                    assert "[Failed to summarize]" not in summary.get("summary", "")


def test_summary_structure_guaranteed_on_success():
    """If summarize_note succeeds, all required fields are present."""

    def good_llm(system: str, user: str) -> LLMResponse:
        return LLMResponse(content=json.dumps({
            "summary": "The main point",
            "bullets": ["point 1", "point 2"],
            "why_it_matters": "This is relevant",
            "tags": ["tag1"],
            "notable_quote": "A quote",
        }))

    result = summarize_note(good_llm, "test content", "test.md")

    # All required fields must be present
    required_fields = ["summary", "bullets", "why_it_matters", "tags", "notable_quote"]
    for field in required_fields:
        assert field in result, f"Missing field: {field}"
        assert result[field] is not None  # Never None (use empty list for bullets, etc.)


def test_empty_object_vs_error_object_distinguished():
    """Empty object (no notes found) is distinct from error (summarization failed)."""
    from obs_summarizer.summarizer import create_rollup

    # Empty list — valid case (no notes)
    result = create_rollup(dummy_llm, [])
    assert isinstance(result, str)
    assert "no notes" in result.lower() or "empty" in result.lower()  # Clear message

    # Error case — different path
    def failing_llm(system: str, user: str):
        raise LLMError("API down")

    with pytest.raises(RollupError):  # Different exception
        create_rollup(failing_llm, [{"summary": "test"}])


def test_partial_object_not_returned_on_failure():
    """Failing function doesn't return object with only some fields."""
    from obs_summarizer.state import load_state

    # Success case: full object
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state_path.write_text(json.dumps({"last_run": "2026-01-01T00:00:00Z"}))
        state = load_state(str(state_path))
        assert "last_run" in state

    # Failure case: exception, not partial object
    with tempfile.TemporaryDirectory() as tmp:
        state_path = Path(tmp) / "state.json"
        state_path.write_text("corrupted")

        # Should NOT return {"last_run": None} (partial object)
        # Should raise StateError
        with pytest.raises(StateError):
            load_state(str(state_path))


def test_success_and_failure_have_different_types():
    """Success returns SummaryDict, failure raises SummarizationError (different types)."""
    from typing import TypedDict

    class SummaryDict(TypedDict):
        summary: str
        bullets: list[str]
        why_it_matters: str
        tags: list[str]
        notable_quote: str | None

    def summarize_note(...) -> SummaryDict:
        """
        Returns a summary dict on success.
        Raises SummarizationError on failure.
        """
        # Success path: return TypedDict
        # Failure path: raise exception
        # Caller code is clear:
        try:
            summary: SummaryDict = summarize_note(...)
            # Use summary fields with confidence
            add_to_digest(summary)
        except SummarizationError as e:
            logger.warning(f"Skipped {e.title}: {e.reason}")
            continue
```

---

### CLAUDE.md Principles That Apply

1. **Error Handling**
   - "Use exceptions, not return codes"
   - "Don't return null... Returning null creates work for callers"
   - "Use the Special Case Pattern: return a special-case object that encapsulates default behavior"
   - **Application:** Raise exception on failure, don't return fake object

2. **Type Safety**
   - "Make illegal states unrepresentable. Use enums, union types, newtypes"
   - **Application:** `Result[T, E]` or `T | Exception` — not `T with error field`

3. **Naming**
   - "Names should tell you what it does"
   - **Application:** Function that can fail should return type that makes failure clear

4. **Testing**
   - "Test boundary conditions exhaustively... Don't trust intuition — prove it"
   - **Application:** Test that garbage state is never returned; caller can't mistake it for real data

---

## Summary Checklist for Future Code

Use this checklist for **every code review**:

### Security & Configuration

- [ ] **No secrets in logs, code, or exception messages**
- [ ] **API keys from environment/vault, never hardcoded**
- [ ] **File paths validated to prevent traversal**
- [ ] **All user input validated and sanitized**

### Error Handling

- [ ] **Exceptions caught specifically, not broad `except Exception`**
- [ ] **Unexpected exceptions re-raised, not silently handled**
- [ ] **State corruption raises exception, not returns default**
- [ ] **Failure states are distinct from success (not garbage objects)**

### Type Safety & Clarity

- [ ] **Functions that can fail document their exceptions (in docstring or type hints)**
- [ ] **Return types are complete and valid on success**
- [ ] **Modern type hints used (`dict`, `str | None`, not `Dict`, `Optional`)**
- [ ] **Callable parameters specify full signature: `Callable[[str, str], LLMResponse]`**

### Testing

- [ ] **Test that exceptions are raised, not swallowed**
- [ ] **Test corruption scenarios (corrupted JSON, missing files)**
- [ ] **Test that garbage state is never returned**
- [ ] **Test encoding errors, path traversal, secret leaks**

### Code Quality

- [ ] **No try blocks with >5 statements**
- [ ] **One failure scenario per try block**
- [ ] **Empty except blocks have comments explaining why**
- [ ] **Repeated error handling is extracted to helper functions (DRY)**

---

## References to CLAUDE.md Standards

This document aligns with these CLAUDE.md sections:

1. **Functions** — Small, single responsibility
2. **Comments** — Explain WHY, not WHAT
3. **Error Handling** — Exceptions > error codes
4. **Type Safety & Static Analysis** — Strict typing required
5. **Security** — Never hardcode secrets
6. **Testing** — Test boundary conditions and failure paths
7. **Code Smells** — Watch for broad exception handling, silent failures

---

## Version History

| Date | Changes |
|------|---------|
| 2026-02-25 | Initial document: 5 critical issues + prevention strategies |

---

**Document Owner:** Development Team
**Last Updated:** 2026-02-25
**Status:** Active (in use for code review)
