---
status: pending
priority: p1
issue_id: SEC-NEW-001
tags: [code-review, security, performance, dos]
dependencies: []
---

# P1: O(n²) JSON Extraction Loop — DoS Risk

## Problem Statement

A backward-scanning fallback loop in `extract_json` calls `json.loads` up to O(n) times on progressively longer substrings. On a 16,000-character LLM response, this could execute `json.loads` tens of thousands of times, hanging the pipeline for minutes per file.

## Findings

### Location
`src/obs_summarizer/summarizer.py:133-139`

### Vulnerable Code
```python
# Lines 133-139 — dead AND dangerous
for i in range(brace_end, brace_start, -1):
    if content[i] == "}":
        try:
            candidate = content[brace_start:i+1]
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
```

### Why It's a Bug
- This loop is only reached when `content[brace_start:brace_end+1]` (maximal span) already failed to parse
- A shorter sub-string of structurally invalid JSON will also fail — trimming the tail cannot fix structural invalidity
- This loop is functionally dead AND O(n²): O(n) iterations each calling O(n) `json.loads`
- A malformed or prompt-injected note (see todo-012) could cause the loop to run for minutes

### Both review agents agreed this is HIGH severity:
- security-sentinel: "O(n²) total... hanging the pipeline for minutes or longer on a single file"
- code-simplicity-reviewer: "dead code that adds complexity... the loop will almost always produce the same parse error repeatedly"

## Proposed Solutions

### Solution A: Delete the loop entirely (RECOMMENDED)
**Effort:** 5 minutes (7-line deletion)

```python
# BEFORE (lines 110-140)
brace_start = content.find("{")
if brace_start >= 0:
    brace_end = content.rfind("}")
    if brace_end > brace_start:
        json_str = content[brace_start:brace_end+1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Try to find a valid JSON endpoint... (DELETE ALL OF THIS)
            for i in range(brace_end, brace_start, -1):
                if content[i] == "}":
                    try:
                        candidate = content[brace_start:i+1]
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        pass

# AFTER — clean, correct, O(n) at worst
brace_start = content.find("{")
if brace_start >= 0:
    brace_end = content.rfind("}")
    if brace_end > brace_start:
        try:
            return json.loads(content[brace_start:brace_end+1])
        except json.JSONDecodeError:
            pass
```

**Pros:** Eliminates DoS risk, no functional loss, simpler code
**Cons:** None

### Solution B: Cap the loop at a fixed number of iterations
**Effort:** 10 minutes

Replace `range(brace_end, brace_start, -1)` with `range(brace_end, max(brace_start, brace_end - 10), -1)` to limit iterations to 10.

**Pros:** Preserves the intent if there's a believed edge case
**Cons:** Arbitrary cap, structurally invalid JSON won't become valid by truncation anyway

## Recommended Action

Delete lines 131-139 (the loop and its containing comment). The maximal-span `json.loads` at line 117 is sufficient. If that fails, the retry fires.

## Technical Details

### Files to Modify
- `src/obs_summarizer/summarizer.py` lines 131-139 (delete)

### Lines to delete
```python
                except json.JSONDecodeError:
                    # Try to find a valid JSON endpoint by looking for closing patterns
                    # In case there are multiple closing braces
                    for i in range(brace_end, brace_start, -1):
                        if content[i] == "}":
                            try:
                                candidate = content[brace_start:i+1]
                                return json.loads(candidate)
                            except json.JSONDecodeError:
                                pass
```
Replace with just: `except json.JSONDecodeError: pass`

## Acceptance Criteria

- [ ] The backward-scanning loop at summarizer.py:133-139 is deleted
- [ ] `extract_json` still handles direct JSON, markdown-wrapped JSON, and brace-extracted JSON
- [ ] All 67 tests still pass
- [ ] No performance regression on valid responses

## Work Log

## Resources

- Security finding: FINDING-HIGH-001 from security-sentinel
- Simplicity finding from code-simplicity-reviewer
- Related: todo-010 (extract_json refactor)
