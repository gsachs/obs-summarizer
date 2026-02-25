---
status: pending
priority: p1
issue_id: TEST-001
tags: [code-review, testing, pipeline]
dependencies: []
---

# P1: Pipeline Is Critically Under-Tested

## Problem Statement

`test_pipeline.py` has only 2 tests, both checking the same early-exit path ("no files found"). The pipeline is the integration core of the application — happy path, cache hits, error handling, digest writing, and dry-run are all untested.

## Findings

### Current Tests (both exit-code-2 only)
```
test_run_pipeline_no_files       — patches scanner to return [], checks exit code 2
test_run_pipeline_with_since_no_files — uses future date, checks exit code 2
```

### Untested Paths
- **Happy path**: LLM is called, digest is written, state is saved, exit code 0
- **Cache hit path** (lines 79-84): file found in cache, not re-summarized
- **Per-file summarization failure** (lines 103-106): expected error skips file, continues
- **Unexpected error escalation** (lines 107-110): unknown error logs + re-raises
- **Dry run** (lines 59-63): `--dry-run` flag, no files written
- **State checkpoint**: `save_state` is called with updated timestamp after run

### Why This Is P1
The pipeline orchestrates all components. If a refactor breaks the happy path or exception handling, no test catches it. Two unit tests that both assert the same exit code give near-zero confidence in pipeline correctness.

## Proposed Solutions

### Solution A: Add targeted mock-based pipeline tests (RECOMMENDED)
**Effort:** 2-3 hours

```python
from unittest.mock import patch, MagicMock, call

def test_run_pipeline_happy_path(tmp_path, sample_config):
    """Happy path: one file summarized, digest written, state saved."""
    vault = tmp_path / "vault"
    vault.mkdir()
    sample_config["vault_path"] = str(vault)
    sample_config["digest_folder"] = "Digests"

    mock_file = vault / "Note.md"
    mock_file.write_text("# Note\nContent")

    with patch("obs_summarizer.pipeline.list_markdown_files", return_value=[mock_file]), \
         patch("obs_summarizer.pipeline.load_cache", return_value=None), \
         patch("obs_summarizer.pipeline.summarize_note", return_value={"summary": "s", "bullets": [], "why_it_matters": "", "tags": [], "notable_quote": None}), \
         patch("obs_summarizer.pipeline.save_cache") as mock_save_cache, \
         patch("obs_summarizer.pipeline.write_digest_note") as mock_write, \
         patch("obs_summarizer.pipeline.save_state") as mock_save_state:

        result = run_pipeline(sample_config)

    assert result == 0
    mock_write.assert_called_once()
    mock_save_state.assert_called_once()


def test_run_pipeline_cache_hit(tmp_path, sample_config):
    """Cache hit path: file loaded from cache, LLM not called."""
    cached = {"summary": "cached", "bullets": [], "tags": [], "why_it_matters": "", "notable_quote": None, "path": "/some/file.md"}
    with patch("obs_summarizer.pipeline.list_markdown_files", return_value=[Path("/some/file.md")]), \
         patch("obs_summarizer.pipeline.load_cache", return_value=cached), \
         patch("obs_summarizer.pipeline.summarize_note") as mock_summarize, \
         patch("obs_summarizer.pipeline.write_digest_note"), \
         patch("obs_summarizer.pipeline.save_state"):
        result = run_pipeline(sample_config)

    mock_summarize.assert_not_called()
    assert result == 0


def test_run_pipeline_summarization_failure_skips_file(tmp_path, sample_config):
    """Expected error (ValueError) skips file and continues."""
    files = [Path("/vault/A.md"), Path("/vault/B.md")]
    summaries = [{"summary": "ok", ...}]

    with patch("obs_summarizer.pipeline.list_markdown_files", return_value=files), \
         patch("obs_summarizer.pipeline.load_cache", return_value=None), \
         patch("obs_summarizer.pipeline.summarize_note", side_effect=[ValueError("bad json"), summaries[0]]), \
         patch("obs_summarizer.pipeline.write_digest_note"), \
         patch("obs_summarizer.pipeline.save_state"):
        result = run_pipeline(sample_config)

    assert result == 0  # pipeline continues despite one failure


def test_run_pipeline_dry_run(tmp_path, sample_config):
    """Dry run does not write digest or save state."""
    with patch("obs_summarizer.pipeline.list_markdown_files", return_value=[Path("/vault/A.md")]), \
         patch("obs_summarizer.pipeline.load_cache", return_value=None), \
         patch("obs_summarizer.pipeline.summarize_note", return_value={...}), \
         patch("obs_summarizer.pipeline.write_digest_note") as mock_write, \
         patch("obs_summarizer.pipeline.save_state") as mock_save_state:
        result = run_pipeline(sample_config, dry_run=True)

    mock_write.assert_not_called()
    mock_save_state.assert_not_called()
```

**Pros:** Directly tests all pipeline code paths, catches regressions
**Cons:** Mocking-heavy; doesn't test actual integration between components

## Recommended Action

**Solution A** — add at minimum 4 new tests: happy path, cache hit, summarization failure skip, dry run.

## Technical Details

### Files to Modify
- `tests/test_pipeline.py` — add 4+ new tests

## Acceptance Criteria

- [ ] Happy path test: LLM called, digest written, state saved, exit code 0
- [ ] Cache hit test: LLM NOT called when cache hit
- [ ] Summarization failure test: single-file failure skips and continues
- [ ] Dry-run test: no writes, no state save
- [ ] All new tests pass

## Work Log

## Resources

- Kieran Python reviewer finding #16 (test_pipeline.py critically under-tested)
