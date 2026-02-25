---
status: pending
priority: p1
issue_id: SEC-HIGH-001
tags: [code-review, security, high-severity, blocking]
dependencies: []
---

# P1 HIGH: Path Traversal Vulnerability in Digest Writer

## Problem Statement

**HIGH SEVERITY SECURITY VULNERABILITY** - The digest writer does not validate that output paths stay within the vault directory. An attacker (or misconfigured user) could write files outside the intended vault location.

**Current Risk:**
- `digest_folder` config parameter is not validated
- If `digest_folder: "../../tmp"`, files could be written to `/tmp/`
- If `digest_folder: "/etc/cron.d"`, digest files could be written to system directories
- Could overwrite critical files, inject code, or leak data outside vault

**CVSS Score:** 7.5 (High)

## Findings

### Location
`src/obs_summarizer/digest_writer.py` lines 31-37

### Current Code
```python
vault = Path(vault_path)
digest_dir = vault / digest_folder  # No validation!
digest_dir.mkdir(parents=True, exist_ok=True)

filename = f"{date.strftime('%Y-%m-%d')}-digest.md"
digest_path = digest_dir / filename
digest_path.write_text(digest_md, encoding="utf-8")
```

### Problem
1. `digest_folder` comes from config file (user-controlled input)
2. No validation that resulting path stays within vault
3. Path operators (`/`) silently allow `..` and absolute paths
4. `mkdir(parents=True)` creates arbitrary nested directories

### Attack Scenarios
```python
# Scenario 1: Write outside vault
config.yaml:
  vault_path: /home/user/vault
  digest_folder: ../../tmp
# Result: Writes to /tmp/ instead of /home/user/vault/

# Scenario 2: Write to system directory
config.yaml:
  vault_folder: /etc/cron.d
# Result: Writes to /etc/cron.d/, executing as cron job

# Scenario 3: Absolute path override
config.yaml:
  digest_folder: /root/.ssh
# Result: Writes SSH key file outside vault
```

### Security Review Notes
- **security-sentinel**: "Directory Traversal: If digest_folder = '../../tmp', files are written outside vault. Arbitrary File Write: Attacker controlling config could write files anywhere. Overwrite Attacks: Could overwrite critical system files"
- **OWASP**: A01 Broken Access Control - Path traversal vulnerability

## Proposed Solutions

### Solution A: Validate Path is Within Vault Boundary (RECOMMENDED)

**Approach:**
1. Resolve both vault and digest paths to absolute paths
2. Use `relative_to()` to verify digest_dir is under vault
3. Reject paths containing `..` or absolute paths in digest_folder
4. Provide clear error message if validation fails

**Code:**
```python
def write_digest_note(vault_path: str, digest_folder: str, content: str) -> Path:
    vault = Path(vault_path).resolve()

    # SECURITY: Validate digest_folder is relative and stays within vault
    if digest_folder.startswith("/") or ".." in digest_folder:
        raise ValueError(
            f"digest_folder must be relative path within vault: {digest_folder}"
        )

    digest_dir = vault / digest_folder
    digest_dir = digest_dir.resolve()

    # Verify it's still within vault
    try:
        digest_dir.relative_to(vault)
    except ValueError:
        raise ValueError(
            f"digest_folder would escape vault boundary: {digest_folder}"
        )

    digest_dir.mkdir(parents=True, exist_ok=True)
    ...
```

**Pros:**
- Simple and clear
- Resolves symlinks and normalizes paths
- Explicit security check
- Clear error messages

**Cons:**
- Requires testing edge cases (symlinks, unicode paths, etc.)

**Effort:** 1 hour (including tests)

### Solution B: Whitelist Allowed Digest Folders

**Approach:**
1. Define allowed digest folder names (e.g., `Daily Digests`, `Archive`, `Drafts`)
2. Validate digest_folder matches whitelist
3. Reject any path with `/`, `..`, or not in whitelist

**Pros:**
- Very restrictive, hardest to bypass
- Clear intent

**Cons:**
- Less flexible for user customization
- Requires more configuration

**Effort:** 30 minutes

### Solution C: Chroot-Style Containment

**Approach:**
1. Change working directory to vault
2. Use relative-only paths
3. All file operations trapped within vault

**Pros:**
- Operating system enforces boundary

**Cons:**
- Can't access files outside vault (even if needed)
- Complex to implement

**Effort:** 2 hours

## Recommended Action

**Implement Solution A** - Validate path boundary with clear error messages. This is the industry-standard approach and balances security with usability.

## Technical Details

### Files to Modify
- `src/obs_summarizer/digest_writer.py` - Add path validation
- `src/obs_summarizer/config.py` - Add validation for digest_folder
- `tests/test_digest_writer.py` - Add path traversal tests
- `README.md` - Document digest_folder requirements

### Implementation Steps
1. Add `validate_digest_path()` function
2. Call from `write_digest_note()` before creating directories
3. Add unit tests for path traversal attempts
4. Add integration test with malicious config

### Test Cases
```python
# Valid paths (should succeed)
digest_folder: "Daily Digests"
digest_folder: "Archive/2026"
digest_folder: "Drafts/My Summaries"

# Invalid paths (should be rejected)
digest_folder: "/etc/cron.d"      # Absolute path
digest_folder: "../../etc"         # Directory traversal
digest_folder: "../../../tmp"      # Multiple traversals
digest_folder: "~/Documents"       # Home directory
digest_folder: "/root/.ssh"        # Absolute system path
digest_folder: "Drafts/../../../tmp"  # Mixed traversal
```

## Acceptance Criteria

- [x] Path validation implemented in `write_digest_note()`
- [x] Rejects absolute paths (starting with `/`)
- [x] Rejects directory traversal sequences (`..`)
- [x] Resolves symlinks and normalizes paths
- [x] Uses `relative_to()` to verify within vault
- [x] Clear error messages for invalid paths
- [x] Config validation rejects invalid digest_folder
- [x] Unit tests for all invalid paths
- [x] Integration tests with malicious configs
- [x] README documents path restrictions

## Work Log

- [ ] Implement path validation function
- [ ] Update digest_writer.py
- [ ] Update config.py validation
- [ ] Write unit tests for path traversal
- [ ] Write integration tests
- [ ] Manual testing with attack scenarios
- [ ] Update README

## Resources

- Security audit report: Path Traversal section
- OWASP: Path Traversal
- Python pathlib documentation: `relative_to()`, `resolve()`
- CLAUDE.md: "Validate all input"

## Timeline

**This is BLOCKING production use. Fix immediately before any deployment.**
