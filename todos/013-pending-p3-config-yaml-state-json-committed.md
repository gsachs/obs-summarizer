---
status: pending
priority: p3
issue_id: SEC-NEW-004
tags: [code-review, security, git, config]
dependencies: []
---

# P3: config.yaml and state.json Are Committed to the Repository

## Problem Statement

The live `config.yaml` (containing vault filesystem path and LLM endpoint) and `state.json` (containing last-run timestamp) are committed to git, despite both being listed in `.gitignore`. They should be untracked.

## Findings

### config.yaml
```yaml
vault_path: /Users/dev0/obsidian/sachinotes
include_folders: ["Clippings"]
local_base_url: http://localhost:1234/v1
local_model: ministral-3-14b-reasoning
```
No API keys (SEC-CRITICAL-001 fix is working), but the local filesystem path and LLM endpoint are exposed.

### state.json
```json
{"last_run_iso": "2026-02-25T16:01:47.558531+00:00"}
```
Exposes operational metadata and creates a shared checkpoint problem if two people pull the branch.

### Root Cause
Both files were likely committed before `.gitignore` was set up, or were added explicitly with `git add -f`. The `.gitignore` correctly lists them but doesn't remove them from tracking.

## Proposed Solutions

### Solution A: Remove from git index, keep local files
**Effort:** 5 minutes

```bash
git rm --cached config.yaml state.json
git commit -m "chore: untrack config.yaml and state.json (already in .gitignore)"
```

The files remain locally on disk (git only removes the tracking, not the file).

**Pros:** Clean, correct, immediate
**Cons:** None

## Recommended Action

**Solution A** — `git rm --cached` both files.

## Technical Details

### Commands
```bash
git rm --cached config.yaml state.json
git commit -m "chore: untrack config.yaml and state.json (already in .gitignore)"
```

### .gitignore already has
```
config.yaml
state.json
```

So after `git rm --cached`, they will be correctly ignored on all future checkouts.

## Acceptance Criteria

- [ ] `git ls-files config.yaml state.json` returns empty
- [ ] Both files still exist locally (not deleted from disk)
- [ ] `.gitignore` lists both
- [ ] No sensitive data in repo history (already true — no API keys present)

## Work Log

## Resources

- Security-sentinel: FINDING-LOW-001, FINDING-LOW-002
