# tools/debug-epub-conversions - Batch EPUB Conversion Harness

## Overview

`debug-epub-conversions` automates smoke tests across a directory of EPUBs. For each book it runs `convert-docs`, captures logs, and (optionally) invokes `check-epub-toc` so we can validate TOC alignment at scale.

## Key Components

### `JobRunner`
Coordinates the workflow:
- Discovers `.epub` files under `--epub-dir` and enforces `--limit` when provided.
- Creates per-book output folders under `--output-base` and log files under `--logs-dir`.
- Calls `_build_convert_command` / `_build_toc_command` to run conversion and verification via `uv run`.
- Records each run as a `JobResult` and surfaces `convert_rc` / `toc_rc` for downstream filtering.

### `JobResult`
Dataclass capturing:
- `name`: slugified book codename.
- `epub_path`, `output_dir`, `convert_log`.
- `toc_report`: JSON report emitted by `check-epub-toc` when validation succeeds.
- Convenience property `ok` that returns `True` only when the conversion succeeded and, if run, the TOC checker passed.

### CLI Arguments
- `--epub-dir` (required): source directory of `.epub` files.
- `--output-base`: parent directory for per-book Markdown outputs (default `/tmp/docs-mcp-epub-runs`).
- `--logs-dir`: location for `*-convert.log` files and TOC reports.
- `--limit`: cap the number of EPUBs processed (handy for sampling large corpora).
- `--overwrite`: delete existing output folders before running.
- `--toc-depth`: depth passed to TOC checker comparisons.

## Usage Patterns
- **Bulk QA loop**:
  ```bash
  uv run debug-epub-conversions \
    --epub-dir ~/books/epub \
    --output-base /tmp/epub-out \
    --logs-dir /tmp/epub-logs \
    --overwrite
  ```
  Prints a JSON summary with total runs, successes, and names of books that failed conversion or TOC checks.
- **Focused regression**: combine `--limit` with curated directories to reproduce specific TOC issues quickly.

## Architecture
- Lives alongside other developer tooling at the repo root yet depends only on top-level scripts (`convert-docs`, `check-epub-toc`).
- Designed for long-running QA batches: all subprocess calls use `uv run` so they share the managed Python environment.
- Log layout mirrors what CI pipelines expect (`logs/<codename>-convert.log`, `logs/<codename>-toc.json`).

## Testing
Not currently covered by automated tests. Treat it as an operational helper; when modifying behavior, dry-run against a pair of small EPUBs and inspect the emitted JSON summary plus logs to ensure backwards-compatible reporting.

## Related Documentation
- [./check_epub_toc.md](./check_epub_toc.md)
- [../utils/epub_converter.md](../utils/epub_converter.md)
- [../utils/path_builder.md](../utils/path_builder.md)

## Common Issues

### Conversion fails immediately with "command not found"
**Cause:** `uv` is absent from PATH or the Poetry/uv environment was not bootstrapped.

**Solution:** Install uv (`pip install uv` or follow project onboarding) and rerun the harness.

### TOC report missing in results
**Cause:** `check-epub-toc` only writes `--json-report` when the conversion succeeds and the report flag is set.

**Solution:** Inspect `<logs>/<codename>-convert.log` for conversion errors. When success is expected, confirm the `toc_rc` column is `0`; otherwise the script skips storing `toc_report`.
