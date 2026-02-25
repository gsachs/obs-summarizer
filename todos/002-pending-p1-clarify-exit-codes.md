---
status: pending
priority: p1
issue_id: AGENT-002
tags: [code-review, agent-native, reliability]
dependencies: [AGENT-001]
---

# P1: Clarify and Enforce Exit Code Semantics

## Problem Statement

Current exit codes are poorly defined and inconsistently enforced. Agents cannot reliably distinguish between error types, making retry logic impossible to implement correctly.

**Current State:**
- README documents `0/1/2` but code implementation inconsistent
- Exit code 2 ("no files found") is not tested
- Generic `Exception` handlers return exit code 1 for all errors
- No distinction between: config validation errors, API errors, file system errors, data corruption

**Impact:**
- Agents cannot determine if failure is transient (retry) or permanent (abort)
- Agents cannot implement exponential backoff intelligently
- Cannot log and alert properly on different error types

## Findings

### Locations
- `src/obs_summarizer/pipeline.py:52-54` - Returns 2 if no files
- `src/obs_summarizer/cli.py:74-79` - Generic Exception handling returns 1
- `tests/test_cli.py` - No test for exit code 2

### Agent Review Notes
- **agent-native-reviewer**: "Agents cannot distinguish between 'no files' and 'processing error' consistently"
- **Code-simplicity**: Multiple return paths unclear

## Proposed Solutions

### Solution A: Comprehensive Exit Code System (RECOMMENDED)

**Exit Codes:**
```
0 = success (digest written, all files processed)
1 = fatal error (config invalid, API key missing, vault path not found)
2 = no files found (expected behavior, not an error)
3 = partial failure (some files processed, some failed)
4 = configuration error (invalid config.yaml, missing required field)
5 = authentication error (API key invalid or missing)
6 = file system error (vault path not accessible)
7 = transient error (rate limit, timeout - agent should retry)
```

**Approach:**
- Define custom exception hierarchy for each error type
- Catch and convert to appropriate exit code in cli.main()
- Document exit codes in CLI help and README

**Pros:**
- Agents can implement intelligent retry logic (retry on 7, abort on 1/4/5/6)
- Clear semantics for each failure mode
- Enables proper error reporting and alerting

**Cons:**
- More code to maintain
- Requires updating all error paths

**Effort:** Medium-Large (4-6 hours)

### Solution B: Minimal Exit Codes (Lean Approach)

**Exit Codes:**
```
0 = success
1 = error
2 = no files found
```

**Approach:**
- Keep simple, just ensure consistency
- Test all paths to verify exit codes
- Document clearly in README

**Pros:**
- Minimal changes
- Still addresses agent needs

**Cons:**
- Agents cannot distinguish error types
- Less useful for advanced retry strategies

**Effort:** Small (1-2 hours)

### Solution C: Add `--strict` Mode

**Approach:**
- Default: lenient mode (2 = no files is OK)
- `--strict` mode: return 1 if no files found (treat as error)
- Agents can use `--strict` when appropriate

**Pros:**
- Backwards compatible
- Flexible for different use cases

**Cons:**
- Adds flag complexity
- Doesn't address other error type distinctions

**Effort:** Small (1-2 hours)

## Recommended Action

**Implement Solution A** - Comprehensive exit codes enable agent automation and improve operational reliability. The custom exception hierarchy also improves code clarity per CLAUDE.md principles.

## Technical Details

### Files to Modify
- `src/obs_summarizer/config.py`: Raise `ConfigError` with context
- `src/obs_summarizer/cli.py`: Add exception handler for each error type
- `src/obs_summarizer/pipeline.py`: Replace generic returns with typed exceptions
- `tests/test_cli.py`: Test all exit code paths

### Implementation Steps
1. Define custom exception classes (ConfigError, AuthError, FileSystemError, TransientError)
2. Update config.py to raise typed exceptions
3. Update pipeline.py to catch and re-raise typed exceptions
4. Update cli.main() to catch each exception type and return corresponding code
5. Add tests for all 8 exit codes

### Exception Hierarchy
```python
class ObsDigestError(Exception):
    """Base exception for obs-digest errors."""
    exit_code: int

class ConfigError(ObsDigestError):
    exit_code = 4

class AuthError(ObsDigestError):
    exit_code = 5

class FileSystemError(ObsDigestError):
    exit_code = 6

class TransientError(ObsDigestError):
    exit_code = 7
```

## Acceptance Criteria

- [x] Exit codes defined and documented (0/1/2/3/4/5/6/7)
- [x] Custom exception hierarchy implemented
- [x] All error paths tested with correct exit codes
- [x] README updated with exit code reference table
- [x] CLI --help documents exit codes
- [x] Agents can implement retry logic based on exit codes
- [x] test_cli.py has tests for all 8 exit codes

## Work Log

- [ ] Define exception hierarchy
- [ ] Update config module to raise typed exceptions
- [ ] Update pipeline module error handling
- [ ] Update CLI exception handling
- [ ] Write comprehensive exit code tests
- [ ] Update README and help text
- [ ] Manual testing with agents

## Resources

- Agent-native review: Exit code semantics section
- CLAUDE.md: Exception handling principles
- Unix/Linux exit code conventions
- Ansible/Kubernetes exit code patterns (references for agents)
