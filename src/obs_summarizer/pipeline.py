"""Main ETL pipeline orchestration."""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

from obs_summarizer.cache import load_cache, make_cache_key, save_cache
from obs_summarizer.digest_writer import format_digest_markdown, write_digest_note
from obs_summarizer.llm import create_llm_client
from obs_summarizer.scanner import filter_files_since, list_markdown_files
from obs_summarizer.state import get_since_datetime, load_state, save_state
from obs_summarizer.summarizer import create_rollup, summarize_note

logger = logging.getLogger(__name__)


def run_pipeline(
    config: Dict,
    since: Optional[str] = None,
    dry_run: bool = False,
    no_cache: bool = False,
) -> int:
    """Execute the ETL pipeline.

    Args:
        config: Configuration dictionary
        since: Optional ISO date to override checkpoint
        dry_run: If True, discover files but don't summarize/write
        no_cache: If True, ignore cache and re-summarize everything

    Returns:
        Exit code (0 = success, 1 = error, 2 = no files found)
    """
    try:
        # Step 1: Load state
        state = load_state(config["state_path"])

        # Step 2: Determine since_dt
        since_dt = get_since_datetime(config, since_iso=since, state=state)
        logger.info(f"Processing files modified since: {since_dt.isoformat()}")

        # Step 3: Discover files
        all_files = list_markdown_files(
            config["vault_path"],
            include_folders=config.get("include_folders"),
            exclude_globs=config.get("exclude_globs"),
        )
        target_files = filter_files_since(all_files, since_dt)

        if not target_files:
            logger.info("No new files found.")
            return 2

        logger.info(f"Found {len(target_files)} files to process")

        # Step 4: Dry run mode
        if dry_run:
            for f in target_files:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                print(f"{f.relative_to(config['vault_path'])}\t{mtime.isoformat()}")
            return 0

        # Step 5: Create LLM client
        llm_client = create_llm_client(config)

        # Step 6: Summarize each file
        per_note_summaries = []
        cache_dir = config["cache_dir"]
        max_input_chars = config["max_input_chars"]

        for i, file_path in enumerate(target_files, 1):
            try:
                # Check cache unless no_cache is set
                mtime_ns = int(file_path.stat().st_mtime_ns)
                cache_key = make_cache_key(str(file_path), mtime_ns)

                if not no_cache:
                    cached = load_cache(cache_dir, cache_key)
                    if cached:
                        logger.debug(f"Cache hit: {file_path.name}")
                        per_note_summaries.append(cached)
                        continue

                # Summarize this file
                logger.info(f"Summarizing {i}/{len(target_files)}: {file_path.name}")
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                summary = summarize_note(
                    llm_client, content, file_path.stem, max_chars=max_input_chars
                )

                # Add metadata
                summary["path"] = str(file_path)
                summary["mtime_utc"] = datetime.fromtimestamp(
                    file_path.stat().st_mtime, tz=timezone.utc
                ).isoformat()

                # Cache it
                save_cache(cache_dir, cache_key, summary)
                per_note_summaries.append(summary)

            except (ValueError, KeyError, TypeError, OSError) as e:
                # Expected errors: LLM response format, file I/O, config issues
                logger.warning(f"Failed to summarize {file_path.name}: {e}. Skipping.")
                continue
            except Exception as e:
                # Unexpected errors should fail the pipeline, not silently skip
                logger.error(f"Unexpected error processing {file_path.name}: {e}", exc_info=True)
                raise

        if not per_note_summaries:
            logger.error("No summaries generated (all files failed)")
            return 1

        logger.info(f"Generated {len(per_note_summaries)} summaries")

        # Step 7: Create rollup digest
        logger.info("Creating rollup digest...")
        rollup = create_rollup(llm_client, per_note_summaries)

        # Step 8: Format and write digest
        digest_md = format_digest_markdown(per_note_summaries)
        digest_path = write_digest_note(
            config["vault_path"], config["digest_folder"], digest_md
        )

        # Step 9: Update checkpoint (only after successful write)
        state["last_run_iso"] = datetime.now(timezone.utc).isoformat()
        save_state(state, config["state_path"])

        # Step 10: Report
        num_cached = len([s for s in per_note_summaries if "path" in s])
        num_summarized = len(per_note_summaries) - num_cached
        print(
            f"✓ Digest written: {len(per_note_summaries)} articles "
            f"({num_cached} from cache, {num_summarized} summarized)",
            file=sys.stderr,
        )
        print(f"✓ Saved to: {digest_path}", file=sys.stderr)

        return 0

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return 1
