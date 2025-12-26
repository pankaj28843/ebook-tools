#!/usr/bin/env python3
"""CLI utility to compare EPUB navMap entries with generated Markdown TOC."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from ebook_tools import toc_checker

logger = logging.getLogger("ebook_tools.check_epub_toc")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare an EPUB's built-in TOC with generated reference data (toc.json or README.md)",
    )
    parser.add_argument("--epub", required=True, help="Path to the source EPUB used for conversion")
    parser.add_argument(
        "--output",
        help="Directory that holds the Markdown export (used to locate README.md)",
    )
    parser.add_argument(
        "--readme",
        help="Explicit path to README.md if it is not located under --output",
    )
    parser.add_argument(
        "--toc-json",
        help="Path to toc.json emitted by convert-docs (defaults to <output>/toc.json when --output is supplied)",
    )
    parser.add_argument("--max-depth", type=int, default=2, help="Maximum TOC depth to compare (default: 2)")
    parser.add_argument(
        "--json-report",
        help="Optional path to write a JSON report containing the detailed comparison",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress successful match output (still prints mismatches)",
    )
    return parser.parse_args(argv)


def _resolve_output_dir(args: argparse.Namespace) -> Path | None:
    if args.output:
        return Path(args.output).expanduser()
    return None


def _resolve_toc_json_path(args: argparse.Namespace) -> Path | None:
    if args.toc_json:
        return Path(args.toc_json).expanduser()
    output_dir = _resolve_output_dir(args)
    if output_dir:
        return output_dir / "toc.json"
    return None


def _resolve_readme_path(args: argparse.Namespace) -> Path | None:
    if args.readme:
        return Path(args.readme).expanduser()
    output_dir = _resolve_output_dir(args)
    if output_dir:
        return output_dir / "README.md"
    return None


def _label_for_kind(kind: str) -> str:
    return "toc.json" if kind == "json" else "README.md"


def _collect_reference_candidates(args: argparse.Namespace) -> list[tuple[str, Path, bool]]:
    candidates: list[tuple[str, Path, bool]] = []

    toc_json_path = _resolve_toc_json_path(args)
    if toc_json_path is not None:
        candidates.append(("json", toc_json_path, bool(args.toc_json)))

    readme_path = _resolve_readme_path(args)
    if readme_path is not None:
        candidates.append(("markdown", readme_path, bool(args.readme)))

    return candidates


def _try_load_reference(
    kind: str,
    path: Path,
    max_depth: int,
) -> tuple[list[toc_checker.TocEntry] | None, str | None]:
    if not path.exists():
        return None, f"Reference file not found: {path}"

    loader = toc_checker.load_json_toc if kind == "json" else toc_checker.load_markdown_toc
    entries = loader(path, max_depth=max_depth)
    if entries:
        return entries, None
    return None, f"Reference file contained no TOC entries: {path}"


def _load_reference_entries(args: argparse.Namespace) -> tuple[list[toc_checker.TocEntry], str]:
    candidates = _collect_reference_candidates(args)
    if not candidates:
        raise SystemExit("Provide --toc-json, --readme, or --output so a reference TOC can be located")

    for kind, path, is_explicit in candidates:
        entries, error = _try_load_reference(kind, path, max_depth=args.max_depth)
        if entries is not None:
            label = f"{_label_for_kind(kind)} ({path})"
            return entries, label
        if is_explicit and error:
            raise SystemExit(error)

    raise SystemExit("Unable to load any reference TOC entries; ensure toc.json or README.md exists")


def print_summary(result: toc_checker.TocComparisonResult, quiet: bool, reference_label: str) -> None:
    if result.is_match:
        if not quiet:
            logger.info("✅ navMap entries match %s ordering.", reference_label)
            logger.info("Entries compared: %s", len(result.nav_entries))
        return

    logger.error("❌ Discrepancies detected between navMap and %s", reference_label)
    if result.missing_in_reference:
        logger.error("\nMissing from %s:", reference_label)
        for entry in result.missing_in_reference:
            logger.error("  - %s (level %s)", entry.title, entry.level)
    if result.missing_in_navmap:
        logger.error("\nExtra entries in navMap relative to %s:", reference_label)
        for entry in result.missing_in_navmap:
            logger.error("  - %s (level %s)", entry.title, entry.level)
    if result.order_mismatches:
        logger.error("\nOut-of-order entries:")
        for mismatch in result.order_mismatches:
            logger.error(
                "  - navMap '%s' vs reference '%s'",
                mismatch.nav_entry.title,
                mismatch.reference_entry.title,
            )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    args = parse_args(argv)

    epub_path = Path(args.epub).expanduser()
    if not epub_path.exists():
        logger.error("❌ EPUB not found: %s", epub_path)
        return 2

    reference_entries, reference_label = _load_reference_entries(args)

    nav_entries = toc_checker.load_nav_entries(epub_path, max_depth=args.max_depth)
    result = toc_checker.compare_toc_entries(nav_entries, reference_entries)

    print_summary(result, quiet=args.quiet, reference_label=reference_label)

    if args.json_report:
        report_path = Path(args.json_report).expanduser()
        report_payload = result.as_dict() | {"reference_label": reference_label}
        report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
        if not args.quiet:
            logger.info("Report written to %s", report_path)

    return 0 if result.is_match else 1


if __name__ == "__main__":
    sys.exit(main())
