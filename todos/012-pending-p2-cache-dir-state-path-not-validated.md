---
status: pending
priority: p2
issue_id: SEC-NEW-003
tags: [code-review, security, path-traversal, config]
dependencies: []
---

# P2: cache_dir and state_path Accept Arbitrary Absolute Paths

## Problem Statement

`cache_dir` and `state_path` config values are accepted without validation. Setting them to absolute paths like `/etc/cron.d` or `/etc/sudoers` would cause the application to write JSON files to arbitrary locations. `digest_folder` was validated (SEC-HIGH-001 fix) but these two paths were not.

## Findings

### Location
`src/obs_summarizer/config.py:91-92`

```python
config.setdefault("cache_dir", ".cache/summaries")
config.setdefault("state_path", "state.json")
```

### Attack Vectors
```yaml
# config.yaml
cache_dir: /etc/cron.d
state_path: /etc/sudoers
```

`cache.py:58-62` calls `mkdir(parents=True, exist_ok=True)` then `open(cache_file, "w")`.
`state.py:60` calls `path.parent.mkdir(parents=True, exist_ok=True)`.

### Inconsistency with Existing Fixes
`digest_folder` → validated with three-layer check (resolve + relative_to)
`cache_dir` → no validation
`state_path` → no validation

This inconsistency makes the security model harder to reason about.

## Proposed Solutions

### Solution A: Reject absolute paths in config validation (RECOMMENDED)
**Effort:** 30 minutes

```python
# config.py — add after setdefault calls
for path_key in ("cache_dir", "state_path"):
    path_val = config[path_key]
    if Path(path_val).is_absolute():
        raise ConfigError(
            f"'{path_key}' must be a relative path, got: {path_val}\n"
            f"Relative paths are resolved from the working directory."
        )
```

**Pros:** Consistent with digest_folder approach, catches misconfiguration early
**Cons:** Prevents legitimate use of absolute paths for cache/state (edge case)

### Solution B: Log a warning for absolute paths but allow them
**Effort:** 10 minutes

```python
if Path(path_val).is_absolute():
    logger.warning(f"'{path_key}' is an absolute path: {path_val}. Ensure this is intentional.")
```

**Pros:** Non-breaking, less restrictive
**Cons:** Doesn't prevent the attack; security by warning is not security

## Recommended Action

**Solution A** — reject absolute paths. This is a local desktop tool; there's no legitimate reason to write cache or state files outside the project directory via config.

## Technical Details

### Files to Modify
- `src/obs_summarizer/config.py` — add validation after setdefault calls
- `tests/test_config.py` — add test for absolute path rejection

## Acceptance Criteria

- [ ] `cache_dir: /etc/cron.d` raises ConfigError
- [ ] `state_path: /etc/sudoers` raises ConfigError
- [ ] Default relative paths (`.cache/summaries`, `state.json`) still work
- [ ] All 67 tests pass
- [ ] New test covers rejection of absolute paths

## Work Log

## Resources

- Security-sentinel: FINDING-MEDIUM-003
- Related: SEC-HIGH-001 fix in docs/solutions/security-issues/critical-security-and-python-error-handling.md
