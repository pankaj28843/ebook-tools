#!/usr/bin/env python3
"""Batch EPUB conversion harness using convert-docs + TOC checker."""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

LOG = logging.getLogger("ebook_tools.debug_epub_conversions")


@dataclass(slots=True)
class JobResult:
    """Holds status for a single EPUB conversion run."""

    name: str
    epub_path: Path
    output_dir: Path
    convert_rc: int
    convert_log: Path
    toc_rc: int | None
    toc_report: Path | None

    @property
    def ok(self) -> bool:
        return self.convert_rc == 0 and (self.toc_rc in (0, None))


class JobRunner:
    """Coordinates conversion and TOC validation for a list of EPUB files."""

    def __init__(
        self,
        epub_dir: Path,
        output_dir: Path,
        logs_dir: Path,
        limit: int | None,
        overwrite: bool,
        toc_depth: int,
    ) -> None:
        self.epub_dir = epub_dir
        self.output_dir = output_dir
        self.logs_dir = logs_dir
        self.limit = limit
        self.overwrite = overwrite
        self.toc_depth = toc_depth

    def run(self) -> list[JobResult]:
        epub_files = self._find_epubs()
        if self.limit is not None:
            epub_files = epub_files[: self.limit]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        results: list[JobResult] = []
        for index, epub_path in enumerate(epub_files, start=1):
            book_slug = self._slugify(epub_path.stem)
            job_output = self.output_dir / book_slug
            job_log = self.logs_dir / f"{book_slug}-convert.log"
            toc_report = self.logs_dir / f"{book_slug}-toc.json"

            if job_output.exists() and self.overwrite:
                shutil.rmtree(job_output)
            job_output.mkdir(parents=True, exist_ok=True)

            LOG.info("[%s/%s] Converting %s", index, len(epub_files), epub_path.name)
            convert_cmd = self._build_convert_command(epub_path, job_output)
            convert_rc = self._run_and_capture(convert_cmd, job_log)
            toc_rc: int | None = None

            if convert_rc == 0:
                LOG.info("    Running TOC checker for %s", book_slug)
                toc_cmd = self._build_toc_command(epub_path, job_output, toc_report)
                toc_rc = self._run_and_capture(toc_cmd, job_log, append=True)
            else:
                LOG.error("    Conversion failed for %s (see %s)", book_slug, job_log)

            results.append(
                JobResult(
                    name=book_slug,
                    epub_path=epub_path,
                    output_dir=job_output,
                    convert_rc=convert_rc,
                    convert_log=job_log,
                    toc_rc=toc_rc,
                    toc_report=toc_report if toc_rc == 0 else None,
                )
            )

        return results

    def _find_epubs(self) -> list[Path]:
        return sorted([p for p in self.epub_dir.iterdir() if p.suffix.lower() == ".epub"])

    def _build_convert_command(self, epub_path: Path, job_output: Path) -> list[str]:
        return [
            "uv",
            "run",
            "convert-docs",
            "--input",
            str(epub_path),
            "--output",
            str(job_output),
        ]

    def _build_toc_command(self, epub_path: Path, job_output: Path, report_path: Path) -> list[str]:
        toc_json_path = job_output / "toc.json"
        return [
            "uv",
            "run",
            "check-epub-toc",
            "--epub",
            str(epub_path),
            "--toc-json",
            str(toc_json_path),
            "--max-depth",
            str(self.toc_depth),
            "--quiet",
            "--json-report",
            str(report_path),
        ]

    def _run_and_capture(self, cmd: list[str], log_path: Path, append: bool = False) -> int:
        mode = "a" if append else "w"
        with log_path.open(mode, encoding="utf-8") as log_file:
            log_file.write(f"$ {' '.join(cmd)}\n")
            log_file.flush()
            proc = subprocess.run(cmd, check=False, stdout=log_file, stderr=subprocess.STDOUT)
            log_file.write(f"\n[exit {proc.returncode}]\n")
            return proc.returncode

    def _slugify(self, text: str) -> str:
        value = text.strip().lower()
        value = re.sub(r"[^a-z0-9]+", "-", value)
        value = re.sub(r"-+", "-", value)
        return value.strip("-") or "book"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch convert many EPUB files using convert-docs")
    parser.add_argument("--epub-dir", type=Path, required=True, help="Directory containing source EPUB files")
    parser.add_argument(
        "--output-base",
        type=Path,
        default=Path("/tmp/ebook-tools-epub-runs"),
        help="Base directory where each EPUB output will be stored",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=Path("/tmp/ebook-tools-epub-logs"),
        help="Directory for per-book conversion logs",
    )
    parser.add_argument("--limit", type=int, help="Only process the first N EPUB files")
    parser.add_argument("--overwrite", action="store_true", help="Delete output directory before each run")
    parser.add_argument(
        "--toc-depth",
        type=int,
        default=2,
        help="Depth passed to check_epub_toc --max-depth",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = parse_args(argv)

    if not args.epub_dir.exists():
        LOG.error("EPUB directory not found: %s", args.epub_dir)
        return 2

    runner = JobRunner(
        epub_dir=args.epub_dir,
        output_dir=args.output_base,
        logs_dir=args.logs_dir,
        limit=args.limit,
        overwrite=args.overwrite,
        toc_depth=args.toc_depth,
    )
    results = runner.run()

    summary = {
        "total": len(results),
        "success": sum(1 for r in results if r.ok),
        "convert_failures": [r.name for r in results if r.convert_rc != 0],
        "toc_failures": [r.name for r in results if r.convert_rc == 0 and (r.toc_rc or 0) != 0],
    }
    print(json.dumps(summary, indent=2))  # noqa: T201

    return 0 if summary["success"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
