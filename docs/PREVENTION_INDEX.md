# Prevention & Best Practices Index

**Complete guide to preventing the 5 critical issues identified in code review**

---

## Documents in This Set

### 1. PREVENTION_QUICK_REFERENCE.md (ONE PAGE)
**Purpose:** Quick lookup for code reviewers
**Audience:** Developers during code review
**Size:** 1 page
**Use when:** You need to quickly identify a red flag or remember the fix

**Contents:**
- 5 critical issues with red flags and fixes
- 30-second checklist
- Test coverage requirements
- CLAUDE.md mapping
- Grep patterns to find issues
- Common mistakes to catch

**Start here if:** You're reviewing code and need quick reference

---

### 2. PREVENTION_STRATEGIES.md (COMPREHENSIVE)
**Purpose:** Deep dive into each issue with prevention patterns
**Audience:** Development team, code reviewers, architects
**Size:** 44 KB (detailed)
**Use when:** You want to understand an issue deeply or design tests

**Contents for each of 5 issues:**
1. Pattern to Watch For (anti-patterns with code examples)
2. Code Review Checklist (detailed items to verify)
3. Test Cases (complete, runnable examples)
4. CLAUDE.md Principles (which standards apply)

**Includes:**
- Security, path traversal, exception handling details
- State management and type safety sections
- Complete test code you can copy-paste
- Cross-module prevention checklist
- Version history

**Start here if:** You want to master one issue or write tests

---

### 3. ISSUE_PREVENTION_MAPPING.md (REFERENCE)
**Purpose:** Maps issues to fixed code and prevention mechanisms
**Audience:** Code review leads, architects, maintainers
**Size:** Detailed reference
**Use when:** You need to verify a fix or understand how issues interconnect

**Contents:**
- Quick reference table (issue → problem → fix → test)
- Before/after code for each issue
- How issues interconnect (dependency diagram)
- Code review priority order
- Related standards and references

**Start here if:** You've fixed an issue and want to verify it's correct

---

## Quick Answer Guide

### "I'm reviewing a PR and found suspicious code. What do I check?"

1. Open **PREVENTION_QUICK_REFERENCE.md**
2. Search for the pattern (e.g., "except Exception")
3. Find the red flag match
4. Use the fix section to request changes

### "I want to write tests to catch this issue"

1. Open **PREVENTION_STRATEGIES.md**
2. Find the issue number
3. Scroll to "Test Cases That Catch This"
4. Copy-paste the test code
5. Modify for your codebase

### "An issue was fixed. How do I verify the fix is complete?"

1. Open **ISSUE_PREVENTION_MAPPING.md**
2. Find the issue number
3. Compare your code to the "After (CORRECT)" section
4. Check that it doesn't match the "Before (WRONG)" pattern
5. Verify tests exist from "Test Case" section

### "Which CLAUDE.md principle applies here?"

1. Open **PREVENTION_QUICK_REFERENCE.md**
2. Find the "CLAUDE.md Sections That Apply" table
3. Or open **PREVENTION_STRATEGIES.md** and scroll to "CLAUDE.md Principles"

### "I need to brief the team on these issues"

1. Show the **Quick Reference** (overview)
2. Then dive into **Strategies** (details)
3. Use **Mapping** document (fix verification)

---

## The 5 Critical Issues at a Glance

| # | Issue | Pattern | Prevention | Test |
|---|-------|---------|-----------|------|
| 1 | **API Key Exposure** | `logger.info(f"key={key}")` | Load from env, don't log | `test_no_api_keys_in_logs()` |
| 2 | **Path Traversal** | `Path(root) / user_input` | `.resolve().is_relative_to()` | `test_path_traversal_blocked()` |
| 3 | **Broad Exception Handling** | `except Exception: pass` | Specific exceptions only | `test_pipeline_reraises_unexpected()` |
| 4 | **Silent State Corruption** | `except: return {}` | Raise exception on corruption | `test_state_corruption_raises()` |
| 5 | **Fake Summary Objects** | `except: return {"error": ...}` | Raise exception, not garbage | `test_summarize_raises_on_json_failure()` |

---

## How to Use These Documents

### For Code Review

**Reviewer Checklist:**
1. Read **PREVENTION_QUICK_REFERENCE.md** (5 min)
2. Run grep patterns to find red flags
3. Check against specific issue rules
4. Request changes if needed
5. Verify tests exist from "Test Coverage" section

### For Development

**Developer Workflow:**
1. Reference **PREVENTION_QUICK_REFERENCE.md** while coding
2. Run grep patterns before committing
3. Write tests from **PREVENTION_STRATEGIES.md** examples
4. Have each function's `Raises:` documented

### For Architecture/Design

**Architect Tasks:**
1. Review **ISSUE_PREVENTION_MAPPING.md** for issue interconnections
2. Use **PREVENTION_STRATEGIES.md** checklist for PR review criteria
3. Ensure CI/CD runs tests from each section
4. Brief team using progression: Quick Ref → Strategies → Mapping

### For Onboarding

**New Team Member:**
1. Read this index (5 min)
2. Skim **PREVENTION_QUICK_REFERENCE.md** (10 min)
3. Study one **PREVENTION_STRATEGIES.md** issue in depth (30 min)
4. Review fixed code from **ISSUE_PREVENTION_MAPPING.md** (15 min)
**Total: 1 hour to understand critical issues**

---

## Integration with CI/CD

### Pre-Commit Hooks

```bash
#!/bin/bash
# Catch issues before commit

# Issue #3: Bare except
if git diff --cached | grep -E "except\s*:" && ! grep "except.*:" .pre-commit-ignore; then
    echo "ERROR: Bare except: found (use specific exception)"
    exit 1
fi

# Issue #1: API keys in code
if git diff --cached | grep -E "api_key\s*=\s*['\"]" && ! grep "test" <file>; then
    echo "ERROR: Hardcoded API key found"
    exit 1
fi

# Issue #2: String concatenation for paths
if git diff --cached | grep -E "Path\(.*\)\s*/\s*[a-z_]" | grep -v "resolve"; then
    echo "ERROR: Path operation without .resolve() validation"
    exit 1
fi
```

### GitHub Actions / CI

```yaml
- name: Run Issue Prevention Tests
  run: |
    pytest -k "no_api_keys" -v
    pytest -k "path_traversal" -v
    pytest -k "broad_exception" -v
    pytest -k "state_corruption" -v
    pytest -k "fake_summary" -v
```

---

## Document Relationships

```
PREVENTION_INDEX.md (this file)
├── Overview of all documents
├── Quick answer guide
└── Integration instructions

├─→ PREVENTION_QUICK_REFERENCE.md
│   ├── 5 issues with red flags/fixes
│   ├── 30-second checklist
│   ├── Grep patterns to find issues
│   └── For: Quick lookups during code review
│
├─→ PREVENTION_STRATEGIES.md
│   ├── Deep dive into each issue
│   ├── Code review checklist (detailed)
│   ├── Complete test examples
│   ├── CLAUDE.md principle mapping
│   └── For: Learning/writing tests
│
└─→ ISSUE_PREVENTION_MAPPING.md
    ├── Before/after code for each issue
    ├── How issues interconnect
    ├── Fix verification checklist
    ├── Code review priority order
    └── For: Verifying fixes/design decisions
```

---

## When Each Document Was Created

| Document | Date | Scope | Status |
|----------|------|-------|--------|
| PREVENTION_STRATEGIES.md | 2026-02-25 | All 5 issues + tests + CLAUDE.md | Active |
| ISSUE_PREVENTION_MAPPING.md | 2026-02-25 | Issue tracking + before/after | Active |
| PREVENTION_QUICK_REFERENCE.md | 2026-02-25 | Quick lookup + grep patterns | Active |

---

## Key Principles Reinforced

These documents emphasize 5 key principles from CLAUDE.md:

1. **Error Handling is Critical**
   - Use specific exception types
   - Don't catch `Exception` broadly
   - Re-raise unexpected errors
   - [Detailed in PREVENTION_STRATEGIES.md #3]

2. **Security Requires Vigilance**
   - Never log secrets
   - Validate all input (especially paths)
   - Use environment variables
   - [Detailed in PREVENTION_STRATEGIES.md #1 and #2]

3. **Fail Loudly, Not Silently**
   - Raise exceptions on corruption
   - Don't return fake/partial objects
   - Log with context for debugging
   - [Detailed in PREVENTION_STRATEGIES.md #4 and #5]

4. **Type Safety Matters**
   - Modern type hints required
   - Callable parameters must specify signature
   - Make illegal states unrepresentable
   - [Detailed across all documents]

5. **Tests Are First-Class**
   - Each issue has test examples
   - Copy-paste test code from PREVENTION_STRATEGIES.md
   - Run tests in CI before merge
   - [Complete test code provided]

---

## Next Steps

### Immediate (This Sprint)

- [ ] Team reads PREVENTION_QUICK_REFERENCE.md (15 min)
- [ ] Add prevention tests to CI/CD
- [ ] Review existing code for issues using grep patterns
- [ ] Update PR template with checklist

### Short Term (Next 2 Sprints)

- [ ] Study PREVENTION_STRATEGIES.md for each issue
- [ ] Write unit tests for each prevention pattern
- [ ] Document any additional patterns found
- [ ] Brief team on interconnections (ISSUE_PREVENTION_MAPPING.md)

### Long Term (Ongoing)

- [ ] Enforce in code review (update review guidelines)
- [ ] Monitor for new patterns (add to grep list)
- [ ] Update docs when issues evolve
- [ ] Use CLAUDE.md as source of truth

---

## References

**Related Documents in This Project:**

- `CRITICAL_ISSUES.md` — Original issue descriptions
- `FIXES_REFERENCE.md` — Complete fixed code (copy-pasteable)
- `KIERAN_REVIEW.md` — Full code review with detailed analysis
- `CLAUDE.md` — Coding standards this project follows

**External Standards:**

- Python typing: [PEP 484](https://www.python.org/dev/peps/pep-0484/)
- Security: [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- Error handling: [Clean Code by Robert C. Martin](https://www.oreilly.com/library/view/clean-code/9780136083238/)

---

## Contact & Questions

For questions about these documents:

1. Check the **Quick Reference** first (fastest)
2. Then check **PREVENTION_STRATEGIES.md** for details
3. Use **ISSUE_PREVENTION_MAPPING.md** to verify fixes

---

**Document Version:** 1.0
**Created:** 2026-02-25
**Status:** Active (in use for code review)
**Owner:** Development Team
**Last Updated:** 2026-02-25

---

## Quick Navigation

**Looking for...?**

- Red flags to watch for → **PREVENTION_QUICK_REFERENCE.md**
- Complete test examples → **PREVENTION_STRATEGIES.md** (Test Cases section)
- Before/after code → **ISSUE_PREVENTION_MAPPING.md**
- CLAUDE.md mapping → Any document (search "CLAUDE.md")
- Grep patterns → **PREVENTION_QUICK_REFERENCE.md** (bottom section)
- PR review checklist → **PREVENTION_QUICK_REFERENCE.md** (top section)

