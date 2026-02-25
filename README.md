# Obsidian Digest Agent

Scan your Obsidian vault for recently saved notes, summarize each one using Claude (or a local model), and create a daily digest. Everything stays in Obsidian.

## Quick Start

### 1. Install

**From GitHub (recommended):**

```bash
pip install git+https://github.com/gsachs/obs-summarizer.git
```

**From a specific branch or tag:**

```bash
pip install git+https://github.com/gsachs/obs-summarizer.git@main
pip install git+https://github.com/gsachs/obs-summarizer.git@v1.0.0
```

**For local development (editable install):**

```bash
git clone https://github.com/gsachs/obs-summarizer.git
cd obs-summarizer
pip install -e .
```

### 2. Configure

Copy the example config and customize it:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:

```yaml
vault_path: ~/Obsidian/MyVault          # Your Obsidian vault path

# Optional: restrict to specific folders
include_folders: []
# - Clippings
# - Readwise

# Exclude files matching these patterns
exclude_globs:
  - "**/.obsidian/**"
  - "**/templates/**"

# Choose LLM backend
llm_backend: claude                     # or: local
claude_model: claude-sonnet-4-6
local_base_url: http://localhost:1234/v1   # LM Studio or Ollama
local_model: llama-3.2-3b-instruct

# Digest output folder (created inside vault)
digest_folder: Daily Digests
```

### 3. Set API key (Claude backend only)

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### 4. Run

```bash
obs-digest
```

First run processes all files (checkpoint defaults to now). Use `--since` to process historical files:

```bash
obs-digest --since 2026-02-20
```

## How It Works

1. **Extract**: Scan vault for files modified since last run (or checkpoint)
2. **Transform**: Summarize each note via LLM (1 paragraph, 5 bullets, why it matters, tags)
3. **Load**: Write digest to `{vault}/Daily Digests/YYYY-MM-DD-digest.md`
4. **Update**: Save checkpoint (only after successful write)

### Caching

- Per-note summaries cached by `sha256(path + mtime)`
- Re-run immediately = no API calls (all cache hits)
- Edit a note = only that note gets re-summarized

### Error Handling

- Partial failure tolerance: skip failed files, continue with rest
- Exponential backoff retry on transient errors (429, 500, 503)
- Graceful recovery from corrupted cache/state files

## CLI Options

```bash
obs-digest [--config PATH] [--since DATE] [--dry-run] [--no-cache] [--verbose]

Options:
  --config PATH    Config file (default: config.yaml)
  --since DATE     Process files since this date (YYYY-MM-DD)
  --dry-run        List files without summarizing
  --no-cache       Ignore cache, re-summarize everything
  --verbose        Show debug output
```

Exit codes:
- `0` = success
- `1` = error
- `2` = no files found

## Two LLM Backends

### Claude (Recommended)

- Higher quality summaries
- Faster
- Requires API key (set `ANTHROPIC_API_KEY`)
- Config: `llm_backend: claude`

### Local (Free)

- Uses LM Studio or Ollama on your machine
- Zero API costs
- Runs offline
- Lower quality (depends on model)
- Config: `llm_backend: local` + `local_base_url`

Switch backends by changing `config.yaml` — no code changes needed.

## Example Digest Output

```markdown
---
type: digest
date: 2026-02-25
articles_count: 3
generated_by: obs-digest
---

# Daily Digest — February 25, 2026

## Ai

### Article 1
> "The future of AI is not in scale, but in alignment."

**Summary:** This article discusses how scaling alone won't solve AI safety concerns...

**Key takeaways:**
- Scaling has diminishing returns without alignment
- Safety-critical systems need formal verification
- Interpretability research is underexplored
- The path to AGI requires solving these problems first

**Why it matters:** As AI systems become more capable, alignment becomes critical.

**Tags:** #ai #safety #alignment

---

## Top Insights

_Cross-cutting themes across saved articles_
```

## Architecture

```
src/obs_summarizer/
  config.py         - Config loading + validation
  scanner.py        - Vault file discovery
  state.py          - Checkpoint management
  cache.py          - Per-note summary caching
  llm.py            - Claude + local backend abstraction
  summarizer.py     - Per-note + rollup prompting
  digest_writer.py  - Digest note generation
  pipeline.py       - ETL orchestration
  cli.py            - CLI entry point
```

## Testing

Run full test suite:

```bash
python3 -m pytest tests/ -v
```

Test coverage: 78 tests across all modules.

## Project Status

✅ Phase 1: Foundation modules (config, scanner, state, cache)
✅ Phase 2: LLM backend + summarization (Claude + local)
✅ Phase 3: Pipeline + digest writer + CLI
✅ Phase 4: Testing + documentation

### What's Next

- Slack/email adapters (additional output formats)
- Note chunking (handle very large files)
- Async LLM calls (faster for large batches)
- Obsidian plugin (run from command palette)

## License

MIT — see [LICENSE](LICENSE).

## Contributing

Bug reports, suggestions, and pull requests welcome.
