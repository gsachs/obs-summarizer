---
status: pending
priority: p1
issue_id: SEC-CRITICAL-001
tags: [code-review, security, critical, blocking]
dependencies: []
---

# P1 CRITICAL: API Key Exposure via Configuration Override

## Problem Statement

**CRITICAL SECURITY VULNERABILITY** - The code allows API keys to be stored in `config.yaml`, which could be accidentally committed to git. This exposes the user's Anthropic API key to attackers.

**Current Risk:**
- Users could store `ANTHROPIC_API_KEY: sk-ant-...` directly in config.yaml
- Config files are often checked into version control
- Leaked API key allows attackers to:
  - Access Claude API on user's account
  - Incur charges on user's billing
  - Access any data passed through API calls

**CVSS Score:** 8.1 (High)

## Findings

### Location
`src/obs_summarizer/llm.py` line 41

### Current Code
```python
api_key = config.get("api_key")  # Allow override; defaults to env var
client = anthropic.Anthropic(api_key=api_key, timeout=timeout)
```

### Problem
1. Code checks config for `api_key` parameter
2. Users might put API key in config.yaml thinking it's safer than environment variables
3. No validation prevents this dangerous practice
4. Even if not in config, API key in memory accessible via stack traces in debug output

### Security Review Notes
- **security-sentinel**: "Users could store ANTHROPIC_API_KEY directly in config.yaml (checked into git). Attack: User accidentally commits config.yaml with api_key: sk-ant-..., Attacker finds key in public git repository"
- **OWASP Impact**: Information disclosure, unauthorized access

## Proposed Solutions

### Solution A: Remove `config.get("api_key")` Entirely (RECOMMENDED)

**Approach:**
1. Delete line 41: `api_key = config.get("api_key")`
2. Always use environment variable only: `api_key = os.environ.get("ANTHROPIC_API_KEY")`
3. Add validation in config loading to REJECT if `api_key` key exists in config
4. Update README to clearly state API keys MUST come from environment

**Pros:**
- Eliminates ability to store secrets in config files
- Simplest, safest approach
- Follows security best practice: "secrets from env, config from files"

**Cons:**
- Users can't pass API key via config (by design)

**Effort:** 30 minutes

### Solution B: Add Config Validation with Clear Error

**Approach:**
1. Keep env var as primary source
2. In config loading, check if `api_key` key exists
3. Raise `ConfigError` if found: "ERROR: api_key cannot be in config.yaml. Set ANTHROPIC_API_KEY environment variable instead."
4. Add documentation with examples

**Pros:**
- Helps users understand the mistake
- Clearer error message than silent failure

**Cons:**
- Adds validation code
- Still doesn't prevent accidental commits

**Effort:** 20 minutes

## Recommended Action

**Implement Solution A + Solution B combo:**
1. Remove `config.get("api_key")` line (Solution A)
2. Add validation in config loading to detect and reject if present (Solution B)

This eliminates the vulnerability while providing helpful error messages if someone tries to add the key to config.

## Technical Details

### Files to Modify
- `src/obs_summarizer/llm.py` - Remove api_key from config
- `src/obs_summarizer/config.py` - Add validation to reject api_key
- `src/obs_summarizer/cli.py` - Add documentation and error handling
- `README.md` - Clarify that API keys must be environment variables only
- `config.example.yaml` - Remove any api_key field

### Implementation
```python
# config.py - add validation
def load_and_validate_config(config_path):
    config = yaml.safe_load(...)

    # SECURITY: Reject api_key in config file
    if "api_key" in config:
        raise ConfigError(
            "SECURITY ERROR: api_key must NOT be in config.yaml\n"
            "Set ANTHROPIC_API_KEY environment variable instead:\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "See README.md for details"
        )

    return config
```

```python
# llm.py - remove config override
def _create_claude_client(config: Dict) -> Callable:
    # ONLY use environment variable, never config file
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise AuthError(
            "ANTHROPIC_API_KEY environment variable not set\n"
            "Set it with: export ANTHROPIC_API_KEY=sk-ant-..."
        )

    client = anthropic.Anthropic(api_key=api_key, timeout=60)
    ...
```

### Testing
- `test_config.py`: Add test that rejects api_key in config
- `test_cli.py`: Add test for helpful error message when API key not set
- `test_llm.py`: Verify API key always comes from environment

## Acceptance Criteria

- [x] Removed `config.get("api_key")` from llm.py
- [x] Config validation rejects `api_key` key with clear error message
- [x] API key MUST come from ANTHROPIC_API_KEY environment variable
- [x] Error messages guide users to set environment variable
- [x] README documents "Never put secrets in config.yaml"
- [x] config.example.yaml has NO api_key field
- [x] Tests verify API key from env only
- [x] .gitignore includes config.yaml (prevent accidental commits)

## Work Log

- [ ] Remove config.get("api_key") from llm.py
- [ ] Add validation in config.py to reject api_key
- [ ] Add helpful error message in cli.py
- [ ] Update README with security section
- [ ] Remove api_key from config.example.yaml
- [ ] Write tests for validation
- [ ] Update .gitignore
- [ ] Manual testing

## Resources

- Security audit report: /private/tmp/claude-503/.../aa2e410fda9f2651e.output
- OWASP: Secrets Management Best Practices
- 12-Factor App: Configuration as Environment Variables
- CLAUDE.md: "Never hardcode secrets"

## Timeline

**This is BLOCKING production use. Fix immediately before any deployment.**
