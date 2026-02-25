"""Command-line interface."""

import argparse
import logging
import sys
from pathlib import Path

from obs_summarizer.config import ConfigError, load_config
from obs_summarizer.pipeline import run_pipeline


def setup_logging(verbose: bool) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="obs-digest",
        description="Summarize Obsidian notes and create a daily digest",
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Config file path (default: config.yaml)",
    )
    parser.add_argument(
        "--since",
        help="Process files modified since this date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be processed, without calling LLM",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore cached summaries, re-summarize everything",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed debug output",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(args.verbose)

    # Load config
    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Run pipeline
    try:
        return run_pipeline(
            config,
            since=args.since,
            dry_run=args.dry_run,
            no_cache=args.no_cache,
        )
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
