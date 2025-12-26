---
applyTo:
  - "src/ebook_tools/epub_converter.py"
  - "src/ebook_tools/pdf_converter.py"
  - "src/ebook_tools/toc_checker.py"
  - "src/ebook_tools/cli/**"
---

# Conversion & TOC Instructions (ebook-tools)

## Pipeline Overview
1. **Source ingestion** – EPUB via ebooklib, PDF via PyMuPDF/PyMuPDF4LLM.
2. **Structured extraction** – Normalize metadata, headings, and sections into Markdown blocks.
3. **Navigation sanity checks** – Validate nav maps/TOCs before writing files.
4. **Filesystem emission** – Write deterministic Markdown trees plus tenant metadata for downstream tools.

## Key Files
- `src/ebook_tools/epub_converter.py`: EPUB parsing + section splitting helpers.
- `src/ebook_tools/pdf_converter.py`: PDF normalization, chunk sizing, Markdown emission.
- `src/ebook_tools/toc_checker.py`: Shared nav validation, link resolution, and reporting.
- `src/ebook_tools/cli/*.py`: Argparse shells that call the core helpers.

## Implementation Principles
- Stream large blobs; avoid loading entire books into memory when chunking.
- Normalize paths with pathlib.Path; never hard-code /tmp or assume POSIX-only layouts.
- Keep helpers pure where possible—functions should accept raw bytes/paths and return data structures, leaving I/O to the caller.
- Use dataclasses or TypedDicts for structured metadata to avoid loose dict juggling.
- Prefer explicit filters (whitelists for chapters/sections) over implicit heuristics so regressions show up in fixtures.

## EPUB Guidance
- Parse spine items deterministically—respect the manifest order rather than guessing from filenames.
- Preserve anchor IDs when generating Markdown headers so TOC links remain intact.
- Strip scripting/style tags early; unit tests under tests/unit/test_epub_converter_* expect sanitized HTML before Markdown conversion.

## PDF Guidance
- Delegate text extraction to PyMuPDF4LLM primitives and focus on chunk/window sizing.
- Always record page numbers in emitted metadata to help downstream diagnostics.
- Guard every external dependency import with informative errors so CLI failures explain which package is missing.

## TOC Checker Notes
- The checker must reject malformed nav maps loudly—never silently drop items.
- Prefer small, composable validators (e.g., ensure_unique_targets, ensure_depth_consistency).
- Tests in tests/unit/test_toc_checker*.py cover both happy paths and edge cases; extend them whenever logic changes.

## Testing & Validation
```bash
# Focused converter tests
timeout 60 uv run pytest tests/unit/test_epub_converter.py -k section
timeout 60 uv run pytest tests/unit/test_pdf_converter.py -k chunk

# Full suite with coverage
timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing

# CLI smoke (EPUB)
uv run convert-docs --input tests/data/sample.epub --output /tmp/out --codename sample

# CLI smoke (TOC)
uv run check-epub-toc --nav tests/data/sample/nav.xhtml
```

## Anti-Patterns
- Relying on random UUIDs or timestamps in output (breaks determinism).
- Mutating shared module-level state (breaks parallel CLI runs).
- Sprinkling sleeps/retries into converters instead of validating inputs.
- Skipping Markdown sanitization because "tests pass"—always extend fixtures instead.
- Adding new CLI flags without updating docs under docs/tools/.
