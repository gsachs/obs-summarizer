# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install for development (editable install)
pip install -e ".[dev]"

# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_pipeline.py -v

# Run a single test by name
python -m pytest tests/test_summarizer.py -k "test_parse_json" -v

# Lint
ruff check src/ tests/

# Type check
mypy src/

# Run the CLI
obs-digest [--config PATH] [--since DATE] [--dry-run] [--no-cache] [--verbose]
```

## Architecture

This is an ETL pipeline that scans an Obsidian vault, summarizes notes via LLM, and writes a daily digest back into the vault.

**Data flow:** `cli.py` → `pipeline.py` → `scanner.py` + `state.py` + `cache.py` + `llm.py` + `summarizer.py` + `digest_writer.py`

### Key modules

- **`config.py`** — Loads and validates `config.yaml`. Enforces: `vault_path` exists, `llm_backend` is `"claude"` or `"local"`, API key comes from `ANTHROPIC_API_KEY` env var (never config), and `cache_dir`/`state_path` must be relative paths.

- **`pipeline.py`** — ETL orchestrator. The main sequence: load state → determine `since_dt` → discover files → (dry-run check) → LLM client → per-note summarize with cache → rollup digest → write note → save checkpoint. Checkpoint is only saved after a successful digest write.

- **`llm.py`** — Factory pattern: `create_llm_client(config)` returns a `Callable[[str, str], LLMResponse]`. Both Claude and local (OpenAI-compatible) backends implement the same interface. The local backend targets LM Studio/Ollama via the `openai` SDK with `api_key="not-needed"`.

- **`summarizer.py`** — Two LLM calls: `summarize_note()` for per-note summaries (returns structured JSON with `summary`, `bullets`, `why_it_matters`, `tags`, `notable_quote`), and `create_rollup()` for the cross-note digest. Handles LLM JSON parse failures with a retry using a stricter prompt.

- **`cache.py`** — Cache key is `sha256(path + ":" + mtime_ns)`. Cache files are JSON stored in `cache_dir/`. Corrupt cache entries are silently dropped and regenerated.

- **`state.py`** — `state.json` holds `last_run_iso`. Priority for `since` datetime: CLI arg → config `since_iso` → checkpoint → now (first run defaults to now, so first run finds no files — use `--since DATE` to backfill). State is written atomically via temp-file rename.

- **`scanner.py`** — Lists `.md` files in vault. Supports `include_folders` (whitelist) and `exclude_globs` (glob patterns to skip, e.g. `**/.obsidian/**`).

### LLM summary format

`summarize_note()` returns a dict:
```python
{
    "summary": str,           # 1-2 sentences
    "bullets": list[str],     # 5 key takeaways
    "why_it_matters": str,    # 1 sentence
    "tags": list[str],        # 1-3 topic tags
    "notable_quote": str|None,
    "path": str,              # added by pipeline
    "mtime_utc": str,         # added by pipeline
}
```

### Testing conventions

Tests mock LLM calls — `llm_call` is a `Callable[[str, str], LLMResponse]`, so tests pass a simple lambda or `MagicMock`. No real API calls in tests. `conftest.py` provides `tmp_vault`, `tmp_cache`, `tmp_state`, `sample_config`, and `sample_summary` fixtures.

Exit codes: `0` = success, `1` = error, `2` = no files found.
