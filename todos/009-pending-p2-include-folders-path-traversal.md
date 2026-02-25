---
status: pending
priority: p2
issue_id: SEC-NEW-002
tags: [code-review, security, path-traversal, scanner]
dependencies: []
---

# P2: include_folders Entries Not Validated Against Vault Boundary

## Problem Statement

`scanner.py` joins `include_folders` config entries directly to the vault path without any validation. An entry like `../../etc` would cause the scanner to read markdown files from outside the vault and send their contents to the LLM.

## Findings

### Location
`src/obs_summarizer/scanner.py:26-29`

### Vulnerable Code
```python
if include_folders:
    roots = [vault / folder for folder in include_folders]
```

### Attack Vector
Config file:
```yaml
include_folders: ["../../etc"]
```
→ `roots = [vault / "../../etc"]` → resolves to `/etc` → scanner reads all `.md` files from `/etc` and sends to LLM.

### Asymmetry With Fixed Code
`digest_writer.py` was correctly fixed with three-layer path validation (resolve + relative_to). The same validation was not applied to the input scanning path. This is an inconsistency: output paths are validated, input paths are not.

## Proposed Solutions

### Solution A: Apply same pattern as digest_writer.py (RECOMMENDED)
**Effort:** 30 minutes

```python
# scanner.py — add validation after building roots
if include_folders:
    roots = []
    for folder in include_folders:
        resolved = (vault / folder).resolve()
        try:
            resolved.relative_to(vault)
        except ValueError:
            raise ValueError(
                f"include_folders entry '{folder}' resolves outside vault boundary.\n"
                f"Vault: {vault}\n"
                f"Resolved: {resolved}"
            )
        roots.append(resolved)
```

**Pros:** Same pattern as existing security fix, consistent
**Cons:** None

### Solution B: Reject absolute paths and `..` in config validation
**Effort:** 20 minutes

Add validation in `config.py` when loading `include_folders`:
```python
for folder in config.get("include_folders", []):
    if folder.startswith("/") or ".." in Path(folder).parts:
        raise ConfigError(f"include_folders entry must be relative: {folder}")
```

**Pros:** Catches it at config load before scanner runs
**Cons:** String check is imprecise (doesn't handle symlinks); should complement, not replace, Solution A

## Recommended Action

**Solution A** in `scanner.py` — identical pattern to the existing `digest_writer.py` fix.

## Technical Details

### Files to Modify
- `src/obs_summarizer/scanner.py` lines 26-29
- `tests/test_scanner.py` — add traversal rejection test

## Acceptance Criteria

- [ ] `include_folders: ["../../etc"]` raises ValueError
- [ ] `include_folders: ["/absolute/path"]` raises ValueError
- [ ] `include_folders: ["Clippings"]` works correctly
- [ ] `include_folders: ["Clippings/Sub"]` works correctly
- [ ] All existing scanner tests pass
- [ ] New test covers traversal attempt

## Work Log

## Resources

- Security-sentinel: FINDING-MEDIUM-004
- Known Pattern: Same fix applied to digest_writer.py (docs/solutions/security-issues/critical-security-and-python-error-handling.md)
