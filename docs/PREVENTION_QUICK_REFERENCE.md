# Prevention Quick Reference Card

**One-page guide for code reviewers and developers**

---

## 5 Critical Issues: Red Flags & Fixes

### 1. API Key Exposure
**Red Flag:** `logger.info(f"key={api_key}")` or `except: logger.error(f"Failed with key {key}")`

**Fix:**
```python
# ✓ Load from environment
api_key = os.getenv("ANTHROPIC_API_KEY")
# ✗ Never log it
# ✓ Wrap exceptions to strip secrets
try:
    client = Anthropic(api_key=api_key)
except APIError as e:
    raise MyError(str(e).replace(api_key, "***")) from e
```

---

### 2. Path Traversal
**Red Flag:** `Path(vault) / user_input` without validation, or `os.path.join(vault, user_input)`

**Fix:**
```python
# ✓ Validate path stays in bounds
user_input = "../../../etc/passwd"  # Reject this
try:
    path = (vault / user_input).resolve()
    if not path.is_relative_to(vault):
        raise SecurityError("Path outside vault")
except ValueError:  # is_relative_to raises ValueError
    raise SecurityError("Path outside vault")

# ✓ Check for .. and /
if ".." in Path(user_input).parts or user_input.startswith("/"):
    raise SecurityError("Invalid path")
```

---

### 3. Broad Exception Handling
**Red Flag:** `except Exception as e:` or bare `except:` or `except: pass`

**Fix:**
```python
# ✗ WRONG: Catches everything
try:
    process_file()
except Exception:
    logger.warning("Failed")
    continue

# ✓ RIGHT: Catch specific exceptions
try:
    content = file_path.read_text(encoding="utf-8")
except UnicodeDecodeError:
    logger.warning("Bad encoding, skipping")
    continue
except FileNotFoundError:
    logger.error("File disappeared")
    return 1
except Exception as e:
    logger.error(f"Unexpected: {e}", exc_info=True)
    raise
```

---

### 4. Silent State Corruption
**Red Flag:** `except (JSONDecodeError, IOError): return {}` or `return {"last_run": None}`

**Fix:**
```python
# ✗ WRONG: Treats corruption as first-run
def load_state(path):
    try:
        return json.load(open(path))
    except:
        return {"last_run": None}  # Lost checkpoint!

# ✓ RIGHT: Fail loudly on corruption
def load_state(path):
    if not path.exists():
        return {"last_run": None}  # First-run OK

    try:
        return json.load(open(path))
    except (JSONDecodeError, IOError) as e:
        raise StateError(f"Corrupted: {path}") from e
```

---

### 5. Fake Summary Objects
**Red Flag:** `except JSONDecodeError: return {"summary": "[Failed]", ...}` or `return {"error": str(e)}`

**Fix:**
```python
# ✗ WRONG: Returns fake summary (caller can't tell)
def summarize(text):
    try:
        return json.loads(llm_response)
    except:
        return {"summary": "[Failed]", "bullets": []}  # Looks real!

# ✓ RIGHT: Raise exception, not garbage
class SummarizationError(Exception):
    pass

def summarize(text):
    try:
        return json.loads(llm_response)
    except JSONDecodeError as e:
        raise SummarizationError(f"Invalid JSON: {e}") from e
```

---

## Code Review Checklist (30 seconds)

```
SECURITY
☐ No secrets logged or in exception messages
☐ File paths validated: .resolve().is_relative_to(root)
☐ No absolute paths or .. in user input

ERROR HANDLING
☐ No bare except Exception: ...
☐ Unexpected exceptions re-raised
☐ Expected exceptions documented in docstring
☐ No empty except blocks

STATE MANAGEMENT
☐ Corruption raises exception (not returns default)
☐ First-run vs. corrupted are distinct
☐ Atomic writes (temp file → rename)

TYPE SAFETY
☐ No Callable without full signature
☐ No Dict/List (use dict/list)
☐ No Optional[X] (use X | None)
☐ Raises: section in docstring
```

---

## Test Coverage (What Tests Must Exist)

| Issue | Test Name | What It Checks |
|-------|-----------|----------------|
| #1 | `test_no_api_keys_in_logs()` | Secrets never logged |
| #2 | `test_path_traversal_blocked()` | `../` attempts rejected |
| #3 | `test_pipeline_reraises_unexpected_exception()` | Unexpected exceptions propagate |
| #4 | `test_state_corruption_raises_exception()` | Corrupted state raises, not returns default |
| #5 | `test_summarize_raises_on_json_failure()` | Exception raised, not fake object |

---

## CLAUDE.md Sections That Apply

| Issue | Section | Key Principle |
|-------|---------|---------------|
| #1 | Security | "Never hardcode secrets. Use environment variables" |
| #2 | Security | "Validate all input. Use allow-lists" |
| #3 | Error Handling | "Extract try/catch into functions. Error handling is one thing" |
| #4 | Don't Return Null | "Return empty collection or throw exception" |
| #5 | Type Safety | "Make illegal states unrepresentable" |
| All | Functions | "Fail fast with guard clauses" |
| All | Comments | "Explain WHY, not WHAT" |

---

## Anti-Patterns Summary

```python
# ❌ NEVER DO THIS
except Exception:           # Too broad
    pass                    # Silent failure
    logger.warning(f"...{secret}...")  # Exposed

return {"error": e}         # Fake success object
return None                 # Ambiguous (miss vs failure)
return default_state        # Hides corruption

Path(root) / user_input     # No validation
path.read_text(errors="ignore")  # Silent corruption

open(path).read()           # Unhandled encoding error

# ✅ ALWAYS DO THIS
except SpecificError:       # Named exception
    logger.warning(...)     # With context
    raise                   # Re-raise unexpected

raise CustomError(...)      # Explicit failure
raise ValueError(...)       # Type-safe failure

path = (root / user_input).resolve()
if not path.is_relative_to(root):
    raise SecurityError()

try:
    content = path.read_text(encoding="utf-8")
except UnicodeDecodeError:
    logger.warning("Bad encoding")
    return None
```

---

## One-Line Rules

1. **Secrets**: Environment variables only, never logged
2. **Paths**: Validate with `.resolve().is_relative_to(root)`
3. **Exceptions**: Specific types, re-raise unexpected, document in Raises:
4. **State**: Corruption raises exception, first-run returns default
5. **Objects**: Raise exception on failure, don't return fake objects

---

## Quick Grep Patterns to Search For

Run these to find issues:

```bash
# Find broad exception catches
grep -n "except Exception" *.py
grep -n "except:" *.py
grep -n "except.*pass" *.py

# Find potential secret logging
grep -n "logger.*api_key\|logger.*secret\|logger.*password" *.py
grep -n "f.*{.*key\|f.*{.*password" *.py

# Find path operations without validation
grep -n "Path.*user\|os.path.join\|os.path.abspath" *.py
grep -n "/" | grep -v "http\|#"  # String concatenation

# Find fake objects returned
grep -n "return.*\[\]\|return {}" *.py
grep -n "return.*error\|return.*failed" *.py

# Find silent failures
grep -n "except.*: return\|except.*: return None" *.py
```

---

## When to Ask for Changes

### Always ask for changes:
- [ ] `except Exception`
- [ ] `except:` (bare)
- [ ] No validation on file paths
- [ ] No `.is_relative_to()` check
- [ ] Secrets in logs or exception messages
- [ ] Fake objects returned on failure
- [ ] Corrupted state returns default instead of raising

### Ask for clarification:
- [ ] `except SomeError: pass` — Why is this intentional?
- [ ] Unusual return type (dict vs exception) — Why not raise?
- [ ] State returns default — Is this first-run or corruption?

### Can approve with comment:
- [ ] Old-style type hints (`Dict` vs `dict`) — File issue for refactor
- [ ] Missing docstring `Raises:` section — Good to add
- [ ] Logs at wrong level (INFO vs WARNING) — Minor

---

## Common Mistakes to Catch

| Mistake | Catch It | Fix It |
|---------|----------|--------|
| `except: pass` | Search for "except:" | Raise or log |
| `logger.info(f"...{key}...")` | Search for logger + api/secret | Don't log secrets |
| `Path(root) / user_input` | Search for `Path.*user\|os.path.join` | `.resolve().is_relative_to()` |
| `return None` on error | Search for `except.*return None` | Raise exception |
| `return {` in except | Search for `except.*return {` | Raise exception |
| `errors="ignore"` | Search for `errors="ignore"` | Catch UnicodeDecodeError |
| No docstring `Raises:` | Check docstrings | Add Raises: section |

---

## Examples in This Codebase

```python
# ✓ Good examples to follow:

# llm.py — Specific exception handling
def _is_retryable(e: Exception) -> bool:
    return isinstance(e, (anthropic.RateLimitError, ...))

# pipeline.py — Specific catches
except (SummarizationError, json.JSONDecodeError) as e:
    logger.warning(...)
    continue
except FileNotFoundError:
    logger.error(...)
    return 1

# state.py — Fail loudly on corruption
except (json.JSONDecodeError, IOError) as e:
    raise StateError(...) from e

# summarizer.py — Raise exception, not return fake
try:
    return json.loads(response.content)
except json.JSONDecodeError as e:
    raise SummarizationError(title, ...) from e
```

---

## When in Doubt, Check CLAUDE.md

The 5 issues correspond directly to CLAUDE.md sections:

- **Error Handling** (entire section) — Issue #3, #4, #5
- **Security** (entire section) — Issue #1, #2
- **Comments** — Issue #1, #3 (explain WHY exceptions are swallowed)
- **Type Safety** — Issue #5 (make illegal states unrepresentable)
- **Don't Return Null** — Issue #4, #5
- **Functions** — Issue #3 (small try blocks)

If a code review question isn't covered by this card, check CLAUDE.md.

---

**Version:** 1.0
**Last Updated:** 2026-02-25
**Owner:** Development Team
