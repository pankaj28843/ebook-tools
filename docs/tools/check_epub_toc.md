# tools/check-epub-toc - EPUB TOC Comparator CLI

## Overview

`check-epub-toc` is a command-line harness that loads an EPUB's navMap and compares it to converter outputs (`toc.json` or `README.md`). It relies on `ebook_tools.toc_checker` for parsing so operators can spot missing or reordered chapters long before ingesting the corpus.

## Key Components

### CLI Arguments
- `--epub` (required): path to the source EPUB used by `convert-docs`.
- `--output`: points to the converter output directory so the tool auto-locates `README.md` and `toc.json`.
- `--readme`, `--toc-json`: explicit overrides when artifacts live elsewhere.
- `--max-depth`: limits hierarchy depth (defaults to `2`).
- `--json-report`: writes a structured diff so automation (e.g., CI, dashboards) can consume the comparison.
- `--quiet`: suppresses success logs but still prints discrepancies.

### Reference loading helpers
`_collect_reference_candidates`, `_try_load_reference`, and `_load_reference_entries` encapsulate the logic for preferring JSON artifacts but gracefully falling back to Markdown. On failure, explicit CLI paths raise early while inferred paths are skipped so batch jobs keep running.

### Result reporting
`print_summary` prints ✅/❌ style logs plus per-section diagnostics: missing entries, unexpected navMap items, and ordering mismatches. When `--json-report` is set, the script serializes `TocComparisonResult.as_dict()` alongside the reference label.

## Usage Patterns
- **Quick check after conversion**:
  ```bash
  uv run check-epub-toc --epub ~/books/designing.epub --output /tmp/designing
  ```
  Uses `/tmp/designing/toc.json` by default and fails the process if discrepancies remain.
- **Report-only mode**:
  ```bash
  uv run check-epub-toc \
    --epub book.epub \
    --toc-json /tmp/book/toc.json \
    --json-report /tmp/book/toc-report.json \
    --quiet
  ```
  Ideal for CI jobs that need machine-readable artifacts.

## Architecture
- Thin wrapper around `ebook_tools.toc_checker` and therefore inherits all parsing/normalization logic.
- Lives at the repo root so both developers and automation scripts can invoke it without importing project modules.
- Consumed by `debug-epub-conversions` for bulk validation.

## Testing
No dedicated tests; the heavy lifting sits inside `ebook_tools.toc_checker`, which is covered by `tests/unit/test_toc_checker.py`. When extending the CLI, add integration-style tests that shell out via `uv run check-epub-toc ...` and assert on exit codes plus JSON reports.

## Related Documentation
- [../utils/toc_checker.md](../utils/toc_checker.md)
- [./debug_epub_conversions.md](./debug_epub_conversions.md)
- [../utils/epub_converter.md](../utils/epub_converter.md)

## Common Issues

### "Reference file not found"
**Cause:** `--output`, `--toc-json`, or `--readme` pointed to a directory missing converter artifacts.

**Solution:** Re-run `convert-docs`, verify the paths, or supply whichever artifact did get generated.

### `AttributeError: The provided EPUB book does not expose a TOC`
**Cause:** The EPUB lacks navMap metadata or `ebooklib` cannot parse it.

**Solution:** Inspect the EPUB in another reader, fix the NCX/nav document, or regenerate the source file before comparing.
