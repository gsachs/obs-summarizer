---
status: pending
priority: p1
issue_id: BUG-001
tags: [code-review, bug, pipeline, cache]
dependencies: []
---

# P1: Cache Hit Count Reporting Is Inverted (Behavioral Bug)

## Problem Statement

The cache hit / fresh-summarized count calculation in `pipeline.py` is backwards. It will always report `num_summarized = 0` and `num_cached = total`, even when everything was freshly summarized.

## Findings

### Location
`src/obs_summarizer/pipeline.py:133-134`

### Bug
```python
num_cached = len([s for s in per_note_summaries if "path" in s])
num_summarized = len(per_note_summaries) - num_cached
```

### Why This Is Wrong
- `pipeline.py:94` sets `summary["path"] = str(file_path)` on **every freshly-summarized note**
- Cache hits are loaded at line 83 via `load_cache()` — these cached dicts **also have "path"** because the key was stored when they were originally summarized
- Therefore `"path" in s` is True for BOTH fresh summaries AND cache hits
- `num_cached` will always equal `len(per_note_summaries)` → `num_summarized = 0` always

The display at lines 135-139:
```python
logger.info(f"Successfully processed {len(per_note_summaries)} files")
logger.info(f"  - {num_summarized} newly summarized")
logger.info(f"  - {num_cached} from cache")
```
...always shows 0 newly summarized and all from cache.

### Root Cause
The `"path"` key was used as a proxy for "fresh summary" but the cache also contains `"path"` from its prior write at line 94. The correct proxy needs a different key or an explicit counter.

## Proposed Solutions

### Solution A: Track counts in the loop (RECOMMENDED)
**Effort:** 15 minutes

```python
# In the per-file loop, add counters:
cached_count = 0
summarized_count = 0

for i, file_path in enumerate(target_files, 1):
    # Check cache
    cached = load_cache(...)
    if cached:
        per_note_summaries.append(cached)
        cached_count += 1
        continue

    # Summarize
    summary = summarize_note(...)
    summary["path"] = str(file_path)
    per_note_summaries.append(summary)
    save_cache(...)
    summarized_count += 1

# Use counters in report
logger.info(f"  - {summarized_count} newly summarized")
logger.info(f"  - {cached_count} from cache")
```

**Pros:** Accurate, clear intent, no post-hoc inference needed
**Cons:** None

### Solution B: Use a sentinel key unique to fresh summaries
**Effort:** 5 minutes

Add `summary["_fresh"] = True` after summarization (line 94). In cache, this key is never stored. Then:
```python
num_summarized = len([s for s in per_note_summaries if s.get("_fresh")])
```

**Pros:** Minimal change
**Cons:** Sentinel key is a code smell; Solution A is cleaner

## Recommended Action

**Solution A** — track counts in the loop. It's explicit and doesn't require post-hoc inference from a proxy key.

## Technical Details

### Files to Modify
- `src/obs_summarizer/pipeline.py` — add counters in loop body (lines ~79-96)

## Acceptance Criteria

- [ ] `num_summarized` correctly counts files processed via LLM
- [ ] `num_cached` correctly counts files loaded from cache
- [ ] Counters add up to `len(per_note_summaries)`
- [ ] All 67 tests pass
- [ ] A test exists that verifies correct count reporting

## Work Log

## Resources

- Kieran Python reviewer finding #5
- Code-simplicity finding #5
