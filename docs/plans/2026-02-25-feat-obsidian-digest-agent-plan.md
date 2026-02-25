---
title: "feat: Build Obsidian Digest Agent"
type: feat
status: active
date: 2026-02-25
origin: docs/brainstorms/2026-02-25-obsidian-digest-agent-brainstorm.md
---

# feat: Build Obsidian Digest Agent

## Overview

A Python CLI tool that scans an Obsidian vault for recently modified markdown notes, summarizes each via LLM (Claude API or local model), rolls up all summaries into a single digest, and writes it as a new Obsidian note. Idempotent, cached, config-driven.

(see brainstorm: `docs/brainstorms/2026-02-25-obsidian-digest-agent-brainstorm.md`)

## Problem Statement / Motivation

Saving articles and notes into Obsidian is easy. Reviewing them is hard. Notes accumulate faster than they get read. A daily digest that surfaces what was saved — with key takeaways — closes the loop between saving and learning.

## Proposed Solution

A Python CLI pipeline following the ETL + Idempotency mental model from the brainstorm:

```
Discover files (mtime > checkpoint) → Summarize each (cached) → Rollup → Write digest → Update checkpoint
```

Two LLM backends switchable via config: Anthropic Claude API (`anthropic` SDK) and local models via LM Studio/Ollama (`openai` SDK pointed at local endpoint).

## Technical Approach

### Project Structure

```
obs-summarizer/
  src/obs_summarizer/
    __init__.py
    cli.py              # CLI entrypoint (argparse)
    config.py           # Config loading + validation
    scanner.py          # Vault traversal + mtime filtering
    cache.py            # Per-note summary cache
    state.py            # Checkpoint management
    llm.py              # LLM backend abstraction (Claude + local)
    summarizer.py       # Per-note + rollup prompts
    digest_writer.py    # Write digest note to vault
    pipeline.py         # Orchestrates the ETL flow
  tests/
    test_scanner.py
    test_cache.py
    test_state.py
    test_llm.py
    test_summarizer.py
    test_digest_writer.py
    test_pipeline.py
    test_cli.py
    conftest.py         # Shared fixtures (tmp vault, mock LLM)
  config.example.yaml   # Checked in; user copies to config.yaml
  pyproject.toml
  README.md
```

### Dependencies

```toml
[project]
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40",
    "openai>=1.50",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.8",
    "mypy>=1.13",
]

[project.scripts]
obs-digest = "obs_summarizer.cli:main"
```

### Implementation Phases

#### Phase 1: Foundation (config, scanner, state, cache)

No LLM calls. Pure filesystem and config logic. Fully testable without network.

**1a. Config loading + validation** — `config.py`

- Load `config.yaml` via PyYAML
- Validate required fields at startup: `vault_path` must exist and be readable
- Validate `llm_backend` is `"claude"` or `"local"`
- If `llm_backend: claude`, check `ANTHROPIC_API_KEY` env var is set
- If `llm_backend: local`, validate `local_base_url` is present
- Sensible defaults: `cache_dir: .cache/summaries`, `state_path: state.json`, `digest_folder: Daily Digests`, `max_input_chars: 16000`

```yaml
# config.example.yaml
vault_path: ~/Obsidian/MyVault
include_folders:           # optional — empty means entire vault
  - Clippings
  - Readwise
exclude_globs:
  - "**/.obsidian/**"
  - "**/templates/**"
llm_backend: claude        # or: local
claude_model: claude-sonnet-4-6
local_base_url: http://localhost:1234/v1
local_model: llama-3.2-3b-instruct
digest_folder: Daily Digests
max_input_chars: 16000     # ~4000 tokens
```

**1b. File scanner** — `scanner.py`

- Walk vault using `pathlib.Path.rglob("*.md")`
- Apply include_folders filter (restrict roots)
- Apply exclude_globs filter
- Skip symlinks (`path.is_symlink()` check)
- Skip 0-byte files
- Filter by mtime > `since_dt`
- Return sorted list of paths (oldest first)

**1c. State management** — `state.py`

- Load `state.json`; return default `{"last_run_iso": null}` if missing
- Handle corrupt JSON gracefully: log warning, treat as first run
- Save state atomically (write to temp file, then rename)
- All timestamps in UTC with timezone info

**1d. Cache** — `cache.py`

- Cache key: `sha256(str(filepath) + str(mtime_ns))` — use nanosecond mtime for precision
- Load: return `None` on missing or corrupt JSON (log warning, regenerate)
- Save: create dirs, write JSON
- Invalidation happens naturally: if file mtime changes, key changes, old cache is orphaned

#### Phase 2: LLM Backend + Summarization

**2a. LLM client abstraction** — `llm.py`

Two concrete implementations behind a common interface:

```python
# llm.py
from dataclasses import dataclass

@dataclass
class LLMResponse:
    content: str

def create_llm_client(config: dict) -> callable:
    """Return a function that takes (system, user) and returns LLMResponse."""
    backend = config["llm_backend"]
    if backend == "claude":
        return _create_claude_client(config)
    elif backend == "local":
        return _create_local_client(config)
    raise ValueError(f"Unknown backend: {backend}")
```

- Claude client: uses `anthropic.Anthropic().messages.create()`
- Local client: uses `openai.OpenAI(base_url=...).chat.completions.create()`
- Both return `LLMResponse` with `content: str`
- Retry on transient errors (429, 500, 503) with exponential backoff (3 attempts, 2/4/8s)
- Configurable timeout (default 60s)

**2b. Summarizer** — `summarizer.py`

Per-note prompt:

```
Summarize this note. Return a JSON object with these fields:
- summary: 1 paragraph (2-3 sentences)
- bullets: array of 5 key takeaways
- why_it_matters: 1 sentence on relevance
- tags: array of 1-3 topic tags
- notable_quote: a quote-worthy line from the text, or null
```

Rollup prompt:

```
You are creating a daily reading digest. Below are summaries of articles saved today.
Group them by theme. For each theme, write a brief overview. End with "Top Insights"
(3-5 cross-cutting takeaways).
```

- Strip YAML frontmatter before sending
- Truncate content at `max_input_chars` with `[... truncated]` marker
- Parse JSON response; on parse failure, retry once with stricter prompt

**No chunking in v1.** If a note exceeds `max_input_chars`, truncate. Chunking adds significant complexity and can be added later if needed. The `[... truncated]` marker makes the truncation visible in the summary.

#### Phase 3: Pipeline + Digest Writer + CLI

**3a. Digest writer** — `digest_writer.py`

- Output path: `{vault}/{digest_folder}/YYYY-MM-DD-digest.md`
- Create `digest_folder` directory if it doesn't exist
- Format: YAML frontmatter + markdown body

```markdown
---
type: digest
date: 2026-02-25
articles_count: 7
generated_by: obs-digest
---

# Daily Digest — February 25, 2026

## Theme: AI & Machine Learning

### Article Title
> Notable quote from the article

**Summary:** One paragraph summary here.

**Key takeaways:**
- Bullet 1
- Bullet 2
...

**Why it matters:** One sentence.

**Tags:** #ai #machine-learning

---

## Top Insights

1. Cross-cutting insight 1
2. Cross-cutting insight 2
...
```

- Overwrite if digest for same date exists (idempotent)

**3b. Pipeline orchestrator** — `pipeline.py`

```python
def run_pipeline(config, since=None, dry_run=False, no_cache=False):
    # 1. Resolve since_dt from arg, config, or state
    # 2. Discover files
    # 3. If dry_run: print file list and exit
    # 4. For each file: check cache (unless no_cache), summarize, cache result
    #    - Log progress: "Summarizing 3/12: article-name.md"
    #    - On LLM error: log warning, skip file, continue
    # 5. Rollup
    # 6. Write digest
    # 7. Update checkpoint (only after successful write)
    # 8. Print summary: "Digest written: 12 articles, 3 from cache, 9 summarized"
```

Key decisions:
- **Partial failure tolerance:** skip failed files, continue with rest, log which files failed
- **Checkpoint only after digest write succeeds** (from brainstorm)
- **Progress output to stderr**, digest content to stdout (allows piping)

**3c. CLI** — `cli.py`

```
usage: obs-digest [--config PATH] [--since DATE] [--dry-run] [--no-cache] [--verbose]

Options:
  --config PATH    Config file path (default: config.yaml)
  --since DATE     Process files modified since this date (YYYY-MM-DD)
  --dry-run        List files that would be processed, without calling LLM
  --no-cache       Ignore cached summaries, re-summarize everything
  --verbose        Show detailed progress and debug info
```

- Uses `argparse`
- `--since` overrides both config `since_iso` and checkpoint
- `--dry-run` prints file list with mtimes, then exits
- Exit codes: 0 = success, 1 = error, 2 = no files found

#### Phase 4: Testing + Polish

- Unit tests for each module (scanner, cache, state, config, summarizer, digest_writer)
- Integration test: full pipeline with mock LLM client
- `.gitignore`: add `state.json`, `.cache/`, `config.yaml`, `__pycache__/`, `.venv/`
- `README.md`: quick start (copy config, set API key, run)
- `config.example.yaml`: documented example config

## Acceptance Criteria

- [ ] `obs-digest --dry-run` lists vault files modified since last run
- [ ] `obs-digest` summarizes each file, writes digest to vault, updates checkpoint
- [ ] Re-running immediately produces same digest (cache hit, no API calls)
- [ ] Editing a note and re-running re-summarizes only that note
- [ ] `llm_backend: local` works with LM Studio or Ollama endpoint
- [ ] `llm_backend: claude` works with Anthropic API key
- [ ] Switching backends requires only a config change
- [ ] `--since 2026-02-20` processes files from that date regardless of checkpoint
- [ ] `--no-cache` forces re-summarization
- [ ] Invalid config fails fast with clear error message
- [ ] All modules have unit tests
- [ ] Full pipeline has integration test with mock LLM

## Success Metrics

- Run completes in under 2 minutes for 20 notes (Claude backend)
- Cache hit rate is 100% on idempotent re-runs
- Digest is readable, grouped by theme, with clear takeaways

## Dependencies & Risks

| Risk | Mitigation |
|------|------------|
| Large notes exceed token limits | Truncate at `max_input_chars` with visible marker; chunking deferred to v2 |
| API rate limits on large batches | Exponential backoff (3 retries); skip on persistent failure |
| Corrupt cache/state files | Graceful recovery: log warning, treat as missing |
| Obsidian sync conflicts | Atomic writes; digest overwrite is idempotent |
| Local LLM quality varies | Claude recommended for production; local for drafts |

## Sources & References

### Origin

- **Brainstorm document:** [docs/brainstorms/2026-02-25-obsidian-digest-agent-brainstorm.md](docs/brainstorms/2026-02-25-obsidian-digest-agent-brainstorm.md) — Key decisions carried forward: mtime-based file selection, digest output to Obsidian, config-driven LLM backend switching

### Design Decisions from Brainstorm

| Decision | Source |
|----------|--------|
| File selection: mtime since checkpoint | Brainstorm: Key Decision #1 |
| Output: Obsidian note in `Daily Digests/` | Brainstorm: Key Decision #2 |
| LLM backend: config-driven Claude/local | Brainstorm: Key Decision #3 |
| Summary format: paragraph + bullets + tags | Brainstorm: Key Decision #4 |
| Cache by sha256(path + mtime) | Brainstorm: Key Decision #5 |
| Strip frontmatter, cap input length | Brainstorm: Key Decision #6 |

### Edge Cases Addressed (from spec-flow analysis)

- Symlinks: skipped during scan
- Corrupt cache/state: graceful recovery, treat as missing
- API failures: retry with backoff, skip on persistent failure
- Empty files / frontmatter-only: skipped during scan
- Config validation: fail fast at startup
- First run: default to last 24 hours

### Out of Scope (deferred)

- Slack / email / webhook output adapters
- Note chunking for very large files (truncate in v1)
- Concurrent/async API calls
- Obsidian plugin integration
- Cost estimation
