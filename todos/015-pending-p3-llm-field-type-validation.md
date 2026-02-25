---
status: pending
priority: p3
issue_id: ROBUST-001
tags: [code-review, validation, llm, python]
dependencies: []
---

# P3: LLM Response Fields Not Type-Validated After JSON Parse

## Problem Statement

After successfully parsing LLM JSON, the field values are not validated for type correctness. An LLM returning `{"bullets": "not a list", "tags": 42}` would pass JSON parsing and `setdefault`, then crash with a `TypeError` deep inside `digest_writer.py` when iterating `bullets` or joining `tags` — far from the source.

## Findings

### Location
`src/obs_summarizer/summarizer.py:181-185`

```python
summary.setdefault("summary", "")
summary.setdefault("bullets", [])
summary.setdefault("why_it_matters", "")
summary.setdefault("tags", [])
summary.setdefault("notable_quote", None)
```

`setdefault` only fills in missing keys — it doesn't validate types of present keys.

### Failure Scenario
LLM returns:
```json
{"summary": 12345, "bullets": "one thing", "tags": {"topic": "privacy"}}
```

- `json.loads` succeeds
- `setdefault` does nothing (keys are present)
- `digest_writer.py:125`: `for bullet in bullets` — `bullets` is a string, so iterates over characters
- `digest_writer.py:135`: `" ".join(f"#{tag}" for tag in tags)` — `tags` is a dict, iterates over keys

The error surfaces in `digest_writer.py`, not `summarizer.py` where the LLM call was made. This makes debugging confusing.

## Proposed Solutions

### Solution A: Add type coercion after setdefault (RECOMMENDED)
**Effort:** 20 minutes

```python
# After setdefault calls, validate and coerce types:
def _ensure_list_of_strings(val: Any, field: str) -> list:
    if isinstance(val, list):
        return [str(item) for item in val]
    if isinstance(val, str):
        return [val]  # single item → list
    raise ValueError(f"LLM field '{field}' must be a list, got {type(val).__name__}: {val!r}")

summary["bullets"] = _ensure_list_of_strings(summary.get("bullets", []), "bullets")
summary["tags"] = _ensure_list_of_strings(summary.get("tags", []), "tags")
if not isinstance(summary.get("summary", ""), str):
    raise ValueError(f"LLM field 'summary' must be a string, got {type(summary['summary']).__name__}")
```

**Pros:** Catches type issues at the source (summarizer), clear error message, pipeline catches ValueError and skips file
**Cons:** Adds 10-15 lines

### Solution B: Type-check only and raise
**Effort:** 15 minutes

```python
if not isinstance(summary.get("bullets", []), list):
    raise ValueError(f"LLM returned non-list 'bullets': {summary['bullets']!r}")
if not isinstance(summary.get("tags", []), list):
    raise ValueError(f"LLM returned non-list 'tags': {summary['tags']!r}")
```

**Pros:** Simpler, no coercion
**Cons:** Stricter — `"bullets": "one thing"` fails rather than being coerced to `["one thing"]`

## Recommended Action

**Solution A** — coerce lists for robustness (LLMs sometimes return a single string instead of a 1-element list). Raise on clearly wrong types.

## Technical Details

### Files to Modify
- `src/obs_summarizer/summarizer.py` — add type validation after setdefault block
- `tests/test_summarizer.py` — add test for invalid field types

## Acceptance Criteria

- [ ] `{"bullets": "single string"}` is coerced to `["single string"]`
- [ ] `{"tags": {"key": "val"}}` raises `ValueError`
- [ ] `{"summary": 12345}` raises `ValueError`
- [ ] Error is raised in `summarizer.py`, not `digest_writer.py`
- [ ] All 67 tests pass

## Work Log

## Resources

- Security-sentinel: FINDING-LOW-003
