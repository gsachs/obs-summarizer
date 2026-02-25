---
status: pending
priority: p3
issue_id: REFACTOR-002
tags: [code-review, dead-code, pipeline, tokens]
dependencies: []
---

# P3: create_rollup Is Called But Its Result Is Never Used

## Problem Statement

`pipeline.py:120` calls `create_rollup(llm_client, per_note_summaries)`, storing the result in `rollup`. The variable `rollup` is never read. Meanwhile `format_digest_markdown` independently formats the digest. This silent token-burning dead assignment makes a live LLM API call and discards the output.

## Findings

### Location
`src/obs_summarizer/pipeline.py:119-125`

```python
rollup = create_rollup(llm_client, per_note_summaries)  # ← result never used

digest_content = format_digest_markdown(
    per_note_summaries,
    since_dt.isoformat(),
    len(target_files),
)
```

### Impact
- Every run makes an extra LLM API call that costs tokens and adds latency
- The `create_rollup` function in `summarizer.py` is 37 lines of code that produces no user-visible output
- The "## Top Insights" section in `digest_writer.py:139-141` renders a placeholder `_Cross-cutting themes across saved articles_` that never gets populated

This is YAGNI at its clearest: code that runs, costs money, and produces no output.

## Proposed Solutions

### Solution A: Delete the dead call (RECOMMENDED for now)
**Effort:** 5 minutes

Delete line 120 from `pipeline.py`:
```python
# DELETE: rollup = create_rollup(llm_client, per_note_summaries)
```

Also remove the "Top Insights" placeholder from `digest_writer.py:139-141` since it will never be populated:
```python
# DELETE:
if len(summaries) > 1:
    body += "\n---\n\n## Top Insights\n\n_Cross-cutting themes across saved articles_\n"
```

Optionally keep or delete `create_rollup` from `summarizer.py` depending on whether the feature is planned.

**Pros:** Removes token waste, removes dead placeholder
**Cons:** If rollup feature is planned, this needs to be re-added

### Solution B: Wire rollup output into the digest
**Effort:** 1-2 hours

Pass `rollup` into `format_digest_markdown` and render it in the "Top Insights" section:
```python
rollup = create_rollup(llm_client, per_note_summaries)
digest_content = format_digest_markdown(
    per_note_summaries,
    since_dt.isoformat(),
    len(target_files),
    rollup=rollup,  # new parameter
)
```

**Pros:** Enables the intended cross-cutting insights feature
**Cons:** More work; keep as a future feature if not currently needed

## Recommended Action

**Solution A** for now (stop the silent token waste). Document Solution B as a future feature in the README if cross-cutting insights are desired.

## Technical Details

### Files to Modify
- `src/obs_summarizer/pipeline.py` line 120 — delete dead assignment
- `src/obs_summarizer/digest_writer.py` lines 139-141 — delete empty placeholder
- `src/obs_summarizer/summarizer.py` lines 190-226 — optionally delete `create_rollup`

## Acceptance Criteria

- [ ] No `create_rollup` call in pipeline.py
- [ ] No empty "Top Insights" placeholder in digest output
- [ ] No extra LLM call per run
- [ ] All tests pass

## Work Log

## Resources

- Code-simplicity finding #6 (create_rollup dead assignment)
- Security-sentinel: INFO-003 (rollup output discarded)
