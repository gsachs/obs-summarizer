---
status: pending
priority: p1
issue_id: AGENT-001
tags: [code-review, agent-native, feature-flag]
dependencies: []
---

# P1: Add Machine-Readable JSON Output Format for Agent Automation

## Problem Statement

Agents cannot reliably determine execution outcomes. The CLI currently prints human-friendly text to stderr with no structured format, forcing agents to:
- Parse unstructured text messages to extract file counts, cache hits, digest paths
- Struggle with identifying which files were actually processed
- Unable to programmatically verify results
- Cannot distinguish between "no files found" vs "processing error"

**Current Output:**
```
✓ Digest written: 10 articles (8 from cache, 2 summarized)
✓ Saved to: /vault/Daily Digests/2026-02-25-digest.md
```

This is human-readable but agents need structured data.

## Findings

### Location
- `/Users/dev0/sandbox/claude/obs-summarizer/src/obs_summarizer/pipeline.py:130-135`
- `/Users/dev0/sandbox/claude/obs-summarizer/src/obs_summarizer/cli.py:63-79`

### Agent Review Notes
- **agent-native-reviewer**: "Agents cannot reliably determine: Which files were processed, How many files were cached vs newly summarized, Whether the digest was actually written"
- **Status Impact**: BLOCKS agent automation (12/15 affordances currently available → 14/15 with this fix)

## Proposed Solutions

### Solution A: Add `--output-format json` Flag (RECOMMENDED)

**Approach:**
- Add CLI flag `--output-format [text|json]` with default: text
- Create `JSONResultFormat` dataclass with structured fields
- Print JSON to stdout when requested

**JSON Schema:**
```json
{
  "status": "success",
  "files_discovered": 42,
  "files_processed": 10,
  "cached_summaries": 8,
  "newly_summarized": 2,
  "digest_path": "/vault/Daily Digests/2026-02-25-digest.md",
  "duration_seconds": 45.2,
  "error": null
}
```

**Pros:**
- Agents can reliably parse with standard JSON libraries
- Backwards compatible (text format is default)
- Extensible for future fields

**Cons:**
- Requires changes to CLI and pipeline modules
- Need to track timing for duration_seconds

**Effort:** Medium (3-4 hours)

### Solution B: Add `--json` Short Flag Only

**Approach:**
- Simple boolean flag `--json` that toggles JSON mode
- Reuse existing print statements, add conditional formatting

**Pros:**
- Minimal changes
- Quick to implement

**Cons:**
- Less extensible
- Can't add other formats later without breaking compatibility

**Effort:** Small (1-2 hours)

### Solution C: Use Environment Variable `OBS_DIGEST_FORMAT`

**Approach:**
- Check env var to determine output format
- CLI flag can override env var

**Pros:**
- Agents can set once for all calls
- Compatible with shell scripts

**Cons:**
- Less explicit
- Requires documentation of env var

**Effort:** Small (1-2 hours)

## Recommended Action

**Implement Solution A** - `--output-format json` flag provides clarity, future extensibility, and is the industry standard for CLI tool integration.

## Technical Details

### Files to Modify
- `src/obs_summarizer/cli.py`: Add argparse for `--output-format`
- `src/obs_summarizer/pipeline.py`: Collect metrics (duration, file counts), return structured data
- `src/obs_summarizer/__init__.py`: Export `JSONResultFormat` dataclass

### Implementation Steps
1. Define `JSONResultFormat` dataclass in cli.py with typed fields
2. Update `run_pipeline()` to return result dict with metrics
3. Update cli.main() to format output based on flag
4. Print JSON to stdout (not stderr) for machine parsing

### Testing Requirements
- `test_cli.py`: New test for `--output-format json` flag
- Verify JSON is valid and contains all fields
- Verify text mode still works (backwards compatible)
- Test error cases (config error, no files found) produce appropriate JSON

## Acceptance Criteria

- [x] CLI accepts `--output-format json` flag
- [x] JSON output includes: status, files_discovered, files_processed, cached_summaries, newly_summarized, digest_path, duration_seconds
- [x] JSON is valid (can parse with json.loads())
- [x] Text format is default and unchanged
- [x] Exit codes still respected (0/1/2/3)
- [x] Tests verify JSON structure for all code paths
- [x] README updated with JSON output example

## Work Log

- [ ] Design dataclass structure for result
- [ ] Modify CLI argument parser
- [ ] Update pipeline to track metrics
- [ ] Update output formatting logic
- [ ] Write tests for JSON format
- [ ] Update README with examples
- [ ] Manual testing with agents

## Resources

- Agent-native review: /private/tmp/claude-503/.../ac5c14bbef9a1003a.output
- CLAUDE.md: Boundary clarity, machine-readable APIs
- Similar pattern: kubectl with `--output json` flag
