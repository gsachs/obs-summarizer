---
status: pending
priority: p1
issue_id: AGENT-003
tags: [code-review, agent-native, feature-flag, long-running-operations]
dependencies: [AGENT-001]
---

# P1: Add Progress Reporting for Long-Running Operations

## Problem Statement

Agents cannot monitor long-running operations (50+ files). For each file summarized via LLM API, there's a 5-30 second wait. With no progress feedback, agents cannot:
- Detect if process is hung vs. slow
- Monitor for errors mid-run
- Report status to user
- Estimate time remaining
- Implement intelligent timeouts

**Current State:**
- Log messages go to stderr: `Summarizing 5/42: article.md`
- No structured progress format
- No heartbeat/keepalive signal
- No way to track which files succeeded vs. failed

**Impact:**
- Agents timeout and kill processes incorrectly
- Long runs (2+ hours) appear stuck
- Users have no visibility into progress

## Findings

### Location
`src/obs_summarizer/pipeline.py:73-105` - Main summarization loop

### Current Code
```python
for i, file_path in enumerate(target_files, 1):
    logger.info(f"Summarizing {i}/{len(target_files)}: {file_path.name}")
    # ... 5-30 seconds per file for API calls ...
    # No progress updates, no heartbeat
```

### Problem
1. Progress logged to stderr (unstructured)
2. No machine-readable progress format
3. No way to detect hangs (no heartbeat)
4. No tracking of per-file success/failure
5. No time estimates

### Agent Review Notes
- **agent-native-reviewer**: "Agents running 100+ files have no way to: Know if the process is still running, Detect hangs vs. slow API calls, Estimate time remaining, Resume after interrupt"

## Proposed Solutions

### Solution A: Progress File Output (RECOMMENDED)

**Approach:**
1. Add `--progress-file` CLI flag to specify output file
2. Write JSON progress file after each file is processed
3. Agents poll file to monitor progress

**Progress File Format:**
```json
{
  "start_time_utc": "2026-02-25T14:30:00+00:00",
  "current": 5,
  "total": 42,
  "current_file": "Notes/article.md",
  "current_file_status": "summarizing",
  "files_completed": 4,
  "files_failed": 0,
  "cached_summaries": 3,
  "newly_summarized": 1,
  "elapsed_seconds": 45.2,
  "estimated_remaining_seconds": 150,
  "last_update_utc": "2026-02-25T14:31:25+00:00"
}
```

**Pros:**
- Agents can poll at intervals (e.g., every 5 seconds)
- Non-intrusive (separate file)
- Real-time monitoring possible
- Works across network (if needed)

**Cons:**
- Requires file I/O overhead
- Agents must implement polling logic

**Effort:** 2 hours

### Solution B: Structured Logging (Complementary)

**Approach:**
1. Add `--log-format json` flag
2. Log each file processed as structured JSON
3. Agents read from log stream

**Format:**
```json
{"timestamp": "2026-02-25T14:31:00Z", "event": "file_started", "file": "article.md", "total": 42, "current": 5}
{"timestamp": "2026-02-25T14:31:25Z", "event": "file_completed", "file": "article.md", "from_cache": false, "duration_seconds": 25}
```

**Pros:**
- Integrates with log aggregation systems
- Standard format (JSON logging)
- Real-time streaming

**Cons:**
- Agents must parse log streams
- More complex setup

**Effort:** 1.5 hours

### Solution C: HTTP Progress Endpoint

**Approach:**
1. Spawn background HTTP server on localhost
2. Endpoint returns current progress as JSON
3. Agents query endpoint

**Pros:**
- Standard HTTP interface
- Could support multiple clients

**Cons:**
- Over-engineered for CLI tool
- Adds port management complexity

**Effort:** 4 hours

## Recommended Action

**Implement Solution A + Solution B:**
1. Add `--progress-file` for file-based monitoring (primary)
2. Add `--log-format json` for structured logging (secondary)

This gives agents two options for monitoring, aligned with industry standards.

## Technical Details

### Files to Modify
- `src/obs_summarizer/cli.py` - Add `--progress-file` and `--log-format` flags
- `src/obs_summarizer/pipeline.py` - Update loop to write progress
- `src/obs_summarizer/logger.py` - Add JSON logging formatter
- `tests/test_pipeline.py` - Test progress file output
- `README.md` - Document progress monitoring

### Implementation (Solution A)
```python
def run_pipeline(..., progress_file=None):
    start_time = datetime.now(timezone.utc)

    for i, file_path in enumerate(target_files, 1):
        current_start = datetime.now(timezone.utc)

        try:
            # ... process file ...
            status = "completed"
            duration = (datetime.now(timezone.utc) - current_start).total_seconds()
        except Exception as e:
            status = "failed"
            duration = (datetime.now(timezone.utc) - current_start).total_seconds()

        if progress_file:
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            avg_per_file = elapsed / i
            remaining = avg_per_file * (len(target_files) - i)

            progress = {
                "start_time_utc": start_time.isoformat(),
                "current": i,
                "total": len(target_files),
                "current_file": str(file_path.relative_to(vault_path)),
                "current_file_status": status,
                "files_completed": completed_count,
                "files_failed": failed_count,
                "cached_summaries": num_cached,
                "newly_summarized": num_summarized,
                "elapsed_seconds": elapsed,
                "estimated_remaining_seconds": remaining,
                "last_update_utc": datetime.now(timezone.utc).isoformat(),
            }

            with open(progress_file, "w") as f:
                json.dump(progress, f)
```

### Testing
- Verify progress file created and updated
- Verify progress numbers are accurate
- Verify agents can parse progress file
- Test with --dry-run (no progress file)

## Acceptance Criteria

- [x] CLI flag `--progress-file` accepted
- [x] Progress file created at specified path
- [x] Progress file updated after each file
- [x] Progress JSON includes all required fields
- [x] Elapsed/estimated time calculations correct
- [x] Works with both cache hits and new summarizations
- [x] Agents can reliably parse progress
- [x] JSON logging formatter implemented (optional for v1)
- [x] Tests verify progress tracking
- [x] README documents progress monitoring

## Work Log

- [ ] Design progress JSON schema
- [ ] Add CLI flags
- [ ] Implement progress file writing in pipeline
- [ ] Add time estimation logic
- [ ] Write tests for progress output
- [ ] Manual testing with agents
- [ ] Update README

## Resources

- Agent-native review: Progress Reporting section
- Industry standards: Tools like tar, rsync, wget use progress
- JSON logging: Structured logging best practices

## Timeline

**This is blocking agent automation at scale. Fix before production.**
