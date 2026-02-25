---
status: complete
priority: p2
issue_id: REFACTOR-001
tags: [code-review, refactoring, testability, python]
dependencies: [006]
---

# P2: extract_json Should Be Module-Level and Simplified

## Problem Statement

`extract_json` is a 55-line nested function defined inside `summarize_note`. It closes over nothing from the outer scope, cannot be unit-tested in isolation, shadows the outer `content` parameter, and raises `json.JSONDecodeError` where `ValueError` is the semantically correct exception.

## Findings

Both code-simplicity-reviewer and kieran-python-reviewer flagged this independently.

### Problem 1: Nested function with no closure use
`extract_json` (summarizer.py:90-145) is defined inside `summarize_note`, called twice (lines 148, 170), and is entirely self-contained. It closes over nothing. Nested functions of this size should be at module level.

### Problem 2: Shadows outer `content` parameter
```python
def summarize_note(llm_call, content, title, max_chars=16000):
    ...
    def extract_json(content: str) -> dict:  # ← shadows outer `content`
```
Even though the inner function doesn't access the outer `content`, this is a trap for future maintainers.

### Problem 3: Raises wrong exception type
```python
raise json.JSONDecodeError(
    f"Could not extract valid JSON from response",
    original_content[:500], 0
)
```
`json.JSONDecodeError.__init__` expects `(msg, doc, pos)` where `doc` is the full unparsed document. The 500-char truncation is misleading. More importantly, this is an application-level failure — `ValueError` is correct, and `pipeline.py:103` explicitly catches `ValueError`. Using `JSONDecodeError` means the outer `except json.JSONDecodeError` in the retry block catches this artificially raised error as if it were a real parse failure.

### Problem 4: Method 2 (markdown code block) is redundant with retry prompt
The retry prompt at line 155 now explicitly says "DO NOT include markdown code blocks." If Method 1 (direct parse) fails, the retry fires with a stricter prompt. Method 2 exists to handle a case the retry already addresses.

## Proposed Solutions

### Solution A: Module-level helper, simplified to 2 methods (RECOMMENDED)
**Effort:** 45 minutes

```python
# At module level in summarizer.py (or a new _utils.py)
def _parse_json(text: str) -> dict:
    """Extract JSON object from LLM response text.

    Handles:
    - Clean JSON responses (direct parse)
    - JSON embedded in prose or after preamble text (brace extraction)
    """
    text = text.strip()

    # Method 1: Direct parse (ideal case)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Method 2: Extract first {...} object (handles preamble text or trailing text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Cannot parse JSON from LLM response: {text[:200]!r}")
```

Replace both calls to `extract_json(...)` in `summarize_note` with `_parse_json(...)`.

**Pros:** Module-level, independently testable, correct exception type, ~40 lines → ~15 lines
**Cons:** Removes Method 2 (markdown code block); the retry prompt directly prevents this case, and the brace-extraction in Method 2 covers it anyway

### Solution B: Minimal fix — move to module level and fix exception type only
**Effort:** 20 minutes

Same as Solution A but keep all 3 extraction methods (minus the O(n²) loop deleted in todo-006).

**Pros:** Conservative change
**Cons:** Keeps the redundant Method 2

## Recommended Action

**Solution A** — simplified module-level `_parse_json`. Combined with todo-006 (delete O(n²) loop first), this simplifies the JSON parsing to the minimum needed.

## Technical Details

### Files to Modify
- `src/obs_summarizer/summarizer.py` — extract nested function, simplify
- `tests/test_summarizer.py` — add direct tests for `_parse_json`:

```python
def test_parse_json_direct():
    result = _parse_json('{"key": "value"}')
    assert result == {"key": "value"}

def test_parse_json_with_preamble():
    result = _parse_json('Here is the JSON: {"key": "value"} — done.')
    assert result == {"key": "value"}

def test_parse_json_invalid():
    with pytest.raises(ValueError):
        _parse_json("not json at all")
```

## Acceptance Criteria

- [ ] `_parse_json` is at module level (not nested)
- [ ] Raises `ValueError` (not `JSONDecodeError`) on failure
- [ ] Does not shadow any outer variable name
- [ ] Has 3+ direct unit tests
- [ ] All existing 67 tests still pass
- [ ] `summarize_note` calls `_parse_json` in both parse attempts

## Work Log

## Resources

- Kieran Python reviewer finding #2 (extract_json nested function)
- Code-simplicity finding #3 (extract_json complexity)
- Depends on: todo-006 (delete O(n²) loop first)
