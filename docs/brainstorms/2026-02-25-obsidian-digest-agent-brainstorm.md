# Obsidian Digest Agent — Brainstorm

**Date:** 2026-02-25
**Status:** Ready for planning

---

## What We're Building

A Python CLI agent that scans an Obsidian vault for recently modified notes, summarizes each one using an LLM, rolls all summaries into a single digest, and writes that digest as a new Obsidian note — so everything stays inside the vault.

The tool runs on demand (or via cron), is idempotent, and supports two LLM backends: Anthropic Claude API or a local model via LM Studio / Ollama (OpenAI-compatible endpoint), switchable via config.

---

## Core Workflow

```
Discover files (mtime > last checkpoint)
  → Per-file summarization (with cache)
    → Rollup digest
      → Write digest note to Obsidian
        → Update checkpoint
```

Mental model: **ETL + Idempotency**
- Extract: find files modified since last run
- Transform: summarize each note via LLM
- Load: write digest note + update checkpoint
- Idempotency: cache by (path + mtime hash) → no duplicate API calls

---

## Key Decisions

### 1. File Selection: mtime since last checkpoint

- Store `state.json` with `last_run_iso` timestamp
- On first run, default to last 24 hours
- Support optional `include_folders` filter (e.g. `Clippings/`, `Readwise/`)
- Support `exclude_globs` to skip templates, plugin folders, attachments

**Rationale:** Most robust without requiring any Obsidian plugin or tag discipline.

### 2. Output: Write digest as a new Obsidian note

- Digest note path: `{vault}/Daily Digests/YYYY-MM-DD-digest.md`
  (folder name configurable)
- Format: YAML frontmatter + grouped summary sections
- If a digest note already exists for that date, overwrite (idempotent re-runs)

**Rationale:** Keeps everything in Obsidian — searchable, linkable, no external service required.

### 3. LLM Backend: Config-driven switching

In `config.yaml`:
```yaml
llm_backend: claude       # or: local
claude_model: claude-sonnet-4-6
local_base_url: http://localhost:1234/v1   # LM Studio default
local_model: llama-3.2-3b-instruct        # or any Ollama model
```

Both backends speak the OpenAI-compatible chat completion format.
Claude via `anthropic` SDK; local via `openai` SDK pointed at local URL.

**Rationale:** Zero code changes to switch backends. Local mode is free, useful for drafts; Claude for higher-quality final digests.

### 4. Per-note summary format

Each note gets:
- 1 paragraph summary
- 5 key bullets
- "Why it matters" line
- 1–3 inferred tags
- Quote-worthy line (if present)

### 5. Per-file summary cache

Cache key: `sha256(filepath + mtime)`
Cache location: `.cache/summaries/<key>.json`
Effect: re-running never re-summarizes unchanged notes.

### 6. Token safety

- Strip YAML frontmatter before sending
- Cap input at configurable max tokens (default: 4000 tokens)
- Chunk-and-merge for large notes (e.g. long web clippings)

---

## Project Layout

```
obs-summarizer/
  agent.py          # CLI entrypoint
  summarizer.py     # per-note + rollup LLM calls
  file_scanner.py   # vault traversal + mtime filtering
  llm_client.py     # Claude / local backend abstraction
  config.yaml       # user configuration
  state.json        # checkpoint (gitignored)
  .cache/summaries/ # per-note summary cache (gitignored)
  docs/
  tests/
```

---

## Resolved Questions

| Question | Decision |
|---|---|
| File selection strategy | mtime since last checkpoint + optional include/exclude folders |
| Output destination | Write digest as new Obsidian note |
| LLM backend | Config-driven: `claude` or `local` (OpenAI-compatible) |

---

## Open Questions

None — all key decisions resolved.

---

## Out of Scope (for now)

- Slack / email delivery (can be added later as a second output adapter)
- Obsidian plugin integration
- Web UI or dashboard
- Automatic scheduling (user sets up cron/launchd themselves)
