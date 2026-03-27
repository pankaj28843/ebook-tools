#!/usr/bin/env python3
"""CLI utility to compare EPUB navMap entries with generated Markdown TOC."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from ebook_tools import toc_checker

logger = logging.getLogger("ebook_tools.check_epub_toc")
console = Console()

app = typer.Typer(
    name="check-epub-toc",
    help="Compare an EPUB's built-in TOC with generated reference data (toc.json or README.md).",
)


def _resolve_toc_json_path(toc_json: str | None, output_dir: Path | None) -> Path | None:
    if toc_json:
        return Path(toc_json).expanduser()
    if output_dir:
        return output_dir / "toc.json"
    return None


def _resolve_readme_path(readme: str | None, output_dir: Path | None) -> Path | None:
    if readme:
        return Path(readme).expanduser()
    if output_dir:
        return output_dir / "README.md"
    return None


def _label_for_kind(kind: str) -> str:
    return "toc.json" if kind == "json" else "README.md"


def _collect_reference_candidates(
    toc_json: str | None, readme: str | None, output_dir: Path | None,
) -> list[tuple[str, Path, bool]]:
    candidates: list[tuple[str, Path, bool]] = []

    toc_json_path = _resolve_toc_json_path(toc_json, output_dir)
    if toc_json_path is not None:
        candidates.append(("json", toc_json_path, bool(toc_json)))

    readme_path = _resolve_readme_path(readme, output_dir)
    if readme_path is not None:
        candidates.append(("markdown", readme_path, bool(readme)))

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


def _load_reference_entries(
    toc_json: str | None, readme: str | None, output_dir: Path | None, max_depth: int,
) -> tuple[list[toc_checker.TocEntry], str]:
    candidates = _collect_reference_candidates(toc_json, readme, output_dir)
    if not candidates:
        console.print("[red]Provide --toc-json, --readme, or --output so a reference TOC can be located[/red]")
        raise typer.Exit(1)

    for kind, path, is_explicit in candidates:
        entries, error = _try_load_reference(kind, path, max_depth=max_depth)
        if entries is not None:
            label = f"{_label_for_kind(kind)} ({path})"
            return entries, label
        if is_explicit and error:
            console.print(f"[red]{error}[/red]")
            raise typer.Exit(1)

    console.print("[red]Unable to load any reference TOC entries; ensure toc.json or README.md exists[/red]")
    raise typer.Exit(1)


def print_summary(result: toc_checker.TocComparisonResult, quiet: bool, reference_label: str) -> None:
    if result.is_match:
        if not quiet:
            console.print(f"[green]navMap entries match {reference_label} ordering.[/green]")
            console.print(f"Entries compared: {len(result.nav_entries)}")
        return

    console.print(f"[red bold]Discrepancies detected between navMap and {reference_label}[/red bold]")
    if result.missing_in_reference:
        console.print(f"\n[red]Missing from {reference_label}:[/red]")
        for entry in result.missing_in_reference:
            console.print(f"  - {entry.title} (level {entry.level})")
    if result.missing_in_navmap:
        console.print(f"\n[red]Extra entries in navMap relative to {reference_label}:[/red]")
        for entry in result.missing_in_navmap:
            console.print(f"  - {entry.title} (level {entry.level})")
    if result.order_mismatches:
        console.print("\n[red]Out-of-order entries:[/red]")
        for mismatch in result.order_mismatches:
            console.print(
                f"  - navMap '{mismatch.nav_entry.title}' vs reference '{mismatch.reference_entry.title}'"
            )


@app.command()
def check(
    epub: Annotated[Path, typer.Option("--epub", help="Path to the source EPUB", exists=True)],
    output: Annotated[Optional[str], typer.Option(help="Directory holding the Markdown export")] = None,
    readme: Annotated[Optional[str], typer.Option(help="Explicit path to README.md")] = None,
    toc_json: Annotated[Optional[str], typer.Option("--toc-json", help="Path to toc.json")] = None,
    max_depth: Annotated[int, typer.Option(help="Maximum TOC depth to compare")] = 2,
    json_report: Annotated[Optional[str], typer.Option(help="Path to write JSON comparison report")] = None,
    quiet: Annotated[bool, typer.Option(help="Suppress successful match output")] = False,
):
    """Compare an EPUB's built-in TOC with generated reference data."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    epub_path = epub.expanduser()
    output_dir = Path(output).expanduser() if output else None

    reference_entries, reference_label = _load_reference_entries(toc_json, readme, output_dir, max_depth)
    nav_entries = toc_checker.load_nav_entries(epub_path, max_depth=max_depth)
    result = toc_checker.compare_toc_entries(nav_entries, reference_entries)

    print_summary(result, quiet=quiet, reference_label=reference_label)

    if json_report:
        report_path = Path(json_report).expanduser()
        report_payload = result.as_dict() | {"reference_label": reference_label}
        report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
        if not quiet:
            console.print(f"Report written to {report_path}")

    raise typer.Exit(0 if result.is_match else 1)


def main(argv: list[str] | None = None) -> int:
    """Main entry point."""
    try:
        if argv is not None:
            app(argv)
        else:
            app()
        return 0
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0


if __name__ == "__main__":
    sys.exit(main())
