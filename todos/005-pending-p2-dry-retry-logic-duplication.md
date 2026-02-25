---
status: pending
priority: p2
issue_id: CODE-002
tags: [code-review, dry-violation, refactoring]
dependencies: []
---

# P2: Extract Duplicated Exponential Backoff Retry Logic

## Problem Statement

The exponential backoff retry pattern is duplicated in two nearly-identical functions, violating the DRY principle ("Don't Repeat Yourself") from CLAUDE.md.

**Current State:**
- `_create_claude_client()` has retry loop (lines 49-75) ~28 lines
- `_create_local_client()` has retry loop (lines 92-120) ~28 lines
- Same logic, slight differences in exception types

**Issue:**
- When retry strategy changes, both must be updated (2x maintenance burden)
- Risk of inconsistent behavior between backends
- Code smell indicating abstraction is missing

## Findings

### Location
`src/obs_summarizer/llm.py` lines 49-75 (Claude) and 92-120 (Local)

### Code Duplication
```python
# CLAUDE version (lines 49-75):
for attempt in range(3):
    try:
        response = client.messages.create(...)
        return LLMResponse(content=response.content[0].text)
    except anthropic.RateLimitError as e:
        if attempt < 2:
            wait_time = 2 ** (attempt + 1)
            logger.warning(f"Rate limited. Retrying in {wait_time}s...")
            time.sleep(wait_time)
        else:
            raise
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        if attempt < 2:
            wait_time = 2 ** (attempt + 1)
            logger.warning(f"Connection error. Retrying in {wait_time}s...")
            time.sleep(wait_time)
        else:
            raise

# LOCAL version (lines 92-120):
for attempt in range(3):
    try:
        response = client.chat.completions.create(...)
        return LLMResponse(content=response.choices[0].message.content)
    except openai.RateLimitError as e:
        if attempt < 2:
            wait_time = 2 ** (attempt + 1)
            logger.warning(f"Rate limited. Retrying in {wait_time}s...")
            time.sleep(wait_time)
        else:
            raise
    # ... similar pattern continues
```

### CLAUDE.md Violation
From CLAUDE.md: "**Don't Repeat Yourself (DRY).** Duplication is the root of all evil in software. Every piece of knowledge must have a single, unambiguous, authoritative representation."

### Review Notes
- **pattern-recognition-specialist**: "Retry logic appears in two nearly-identical functions (28 lines each). DRY principle violation: Could be extracted into shared retry decorator/helper"
- **code-simplicity-reviewer**: "30+ lines of identical retry logic in llm.py"

## Proposed Solutions

### Solution A: Retry Decorator (RECOMMENDED)

**Approach:**
1. Create reusable `@retry` decorator
2. Decorator handles exponential backoff logic
3. Pass specific exception types to catch

**Code:**
```python
def retry(max_attempts=3, base_delay=2, exception_types=()):
    """Decorator: retry with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exception_types as e:
                    if attempt < max_attempts - 1:
                        wait_time = base_delay ** (attempt + 1)
                        logger.warning(f"{e.__class__.__name__}. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        raise
        return wrapper
    return decorator

# Usage:
@retry(exception_types=(anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APITimeoutError))
def _make_claude_api_call(client, system, user):
    response = client.messages.create(...)
    return LLMResponse(content=response.content[0].text)
```

**Pros:**
- Single source of truth for retry logic
- Reusable across all API calls
- Clear intent via decorator
- Easy to adjust retry strategy

**Cons:**
- Requires Python 3.7+ (functools)
- Decorator syntax less familiar to some

**Effort:** 1.5 hours

### Solution B: Retry Helper Function

**Approach:**
1. Create `_retry_with_backoff()` helper
2. Pass callable and exception types
3. Call from both client factories

**Code:**
```python
def _retry_with_backoff(func, exception_types, max_attempts=3):
    """Execute func with exponential backoff retry on specific exceptions."""
    for attempt in range(max_attempts):
        try:
            return func()
        except exception_types as e:
            if attempt < max_attempts - 1:
                wait_time = 2 ** (attempt + 1)
                logger.warning(f"{e.__class__.__name__}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise

# Usage:
def _create_claude_client(config):
    client = anthropic.Anthropic(api_key=..., timeout=60)

    def make_call(system, user):
        return _retry_with_backoff(
            lambda: _make_claude_call(client, system, user),
            exception_types=(anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.APITimeoutError)
        )

    return make_call
```

**Pros:**
- Simpler than decorator
- No magic, explicit control flow
- Easy to debug

**Cons:**
- Lambda wrapping slightly awkward
- Not as clean as decorator

**Effort:** 1 hour

### Solution C: Extract Common API Calling Logic

**Approach:**
1. Extract the API call part (not just retry)
2. Create `_call_api_with_retry()` that abstracts both backends

**Pros:**
- Goes beyond retry logic
- Better long-term maintainability

**Cons:**
- More invasive refactoring
- Risk of introducing bugs

**Effort:** 2-3 hours

## Recommended Action

**Implement Solution A** - Retry decorator is the most elegant and maintainable approach. It's a standard Python pattern and makes the intent crystal clear.

## Technical Details

### Files to Modify
- `src/obs_summarizer/llm.py` - Add decorator, refactor both clients

### Implementation Steps
1. Import `functools`
2. Define `@retry` decorator
3. Extract `_make_claude_call()` function (contains just API call, not retry)
4. Extract `_make_local_call()` function
5. Decorate both with `@retry(...)`
6. Delete old retry loop code

### Testing
- All existing tests should pass (decorator is transparent)
- No new tests needed (test retry logic separately)
- Verify behavior identical before/after

## Acceptance Criteria

- [x] Retry decorator defined and tested
- [x] Both backends use decorator (no code duplication)
- [x] Retry behavior identical to original
- [x] Exception types properly handled
- [x] Exponential backoff values unchanged (2, 4, 8 seconds)
- [x] All existing tests pass
- [x] Code is simpler (fewer lines total)

## Work Log

- [ ] Create retry decorator
- [ ] Extract API call functions
- [ ] Apply decorator to both
- [ ] Run tests to verify
- [ ] Manual testing with both backends

## Resources

- Python functools documentation
- Decorator patterns in Python
- Retry libraries: tenacity, retry2 (reference)
- CLAUDE.md: DRY principle

## Timeline

This refactoring improves code quality but is not blocking. Can be done after security fixes.
