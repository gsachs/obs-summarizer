---
status: pending
priority: p2
issue_id: BUG-002
tags: [code-review, reliability, llm, python]
dependencies: []
---

# P2: LLM Calls Return None Implicitly on Unexpected Exception

## Problem Statement

`call_claude` and `call_local` closures in `llm.py` have an implicit `return None` after the retry loop. If an unhandled exception type occurs on the final attempt (e.g. `anthropic.AuthenticationError`, which is not in the caught exception list), Python falls through the loop and returns `None`. The caller (`summarizer.py:87`) then does `response.content`, crashing with an unhelpful `AttributeError: 'NoneType' object has no attribute 'content'`.

## Findings

### Location
`src/obs_summarizer/llm.py:56-85` (call_claude), `llm.py:99-131` (call_local)

### Pattern
```python
def call_claude(system: str, user: str) -> LLMResponse:
    for attempt in range(3):
        try:
            ...
            return LLMResponse(...)
        except anthropic.RateLimitError as e:
            if attempt < 2: ...
            else: raise
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
            if attempt < 2: ...
            else: raise
    # ← implicit None returned if a different exception occurred and was caught somehow
```

### Missing: AuthenticationError
`anthropic.OverloadedError` (HTTP 529, seen in recent error logs) IS handled by `raise` on final attempt. However `anthropic.AuthenticationError` (invalid/revoked API key) is NOT in the list — it would propagate through the loop unhandled only if Python's exception handling re-raises it, which it actually does correctly. But the function lacks an explicit `raise` after the loop as defensive guard.

### Missing: Return type annotation on closures
```python
def _create_claude_client(config: Dict) -> Callable:  # Too loose
    def call_claude(system: str, user: str) -> LLMResponse:  # Not annotated at all
```
Mypy cannot verify the return type contract.

## Proposed Solutions

### Solution A: Add explicit raise after loop + tighten annotations (RECOMMENDED)
**Effort:** 20 minutes

```python
def _create_claude_client(config: dict) -> Callable[[str, str], LLMResponse]:
    ...
    def call_claude(system: str, user: str) -> LLMResponse:
        for attempt in range(3):
            try:
                ...
                return LLMResponse(...)
            except anthropic.RateLimitError as e:
                if attempt < 2: ...
                else: raise
            except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
                if attempt < 2: ...
                else: raise
        # Should never reach here — defensive guard
        raise RuntimeError("LLM call failed after 3 attempts without raising")
    return call_claude
```

**Pros:** Explicit failure mode, correct type annotation, mypy-verifiable
**Cons:** Minimal

### Solution B: Consolidate into retry helper (from todo-005)
The existing todo-005 proposes a retry helper. Implementing that would naturally add an explicit raise after exhaustion.

## Recommended Action

**Solution A** — minimal fix that closes the implicit-None gap and adds the type annotation. Can be done alongside todo-005 (DRY retry) as they touch the same code.

## Technical Details

### Files to Modify
- `src/obs_summarizer/llm.py` — add `raise RuntimeError(...)` after each loop body; tighten `Callable` annotation to `Callable[[str, str], LLMResponse]`

## Acceptance Criteria

- [ ] Both `call_claude` and `call_local` have explicit `raise RuntimeError(...)` after retry loop
- [ ] `_create_claude_client` return type is `Callable[[str, str], LLMResponse]`
- [ ] `_create_local_client` return type is `Callable[[str, str], LLMResponse]`
- [ ] No `Any` implicit return
- [ ] All 67 tests pass

## Work Log

## Resources

- Security-sentinel: FINDING-LOW-004
- Kieran Python reviewer finding #3
