# utils/pdf_converter.py - PDF to Markdown Converter

## Overview

`PdfConverter` mirrors the EPUB conversion pipeline for technical PDFs. It walks PyMuPDF page trees, splits content into deterministic chapter/section folders, rewrites image references, and now emits both a reviewer-friendly `README.md` and a structured `toc.json` so QA tools can compare PDF bookmarks against Markdown outputs without scraping.

## Key Components

### `PdfConverterConfig`
Configuration knobs exposed through Pydantic. Highlights:
- `use_pdf_outlines` (bool): whether to treat outline level-1 entries as chapters (falls back to a single chapter).
- `max_section_depth` (int): deepest heading level allowed when splitting Markdown (default `2` = `##`).
- `preserve_images` / `clean_filenames`: govern asset extraction plus filesystem-safe names.
- `code_language` (str | None): optional fence annotation for converted code blocks.
- `include_toc` (bool): toggles generation of both `README.md` and `toc.json` artifacts in `_generate_toc`.

### `PdfConverter`
Owns the end-to-end pipeline:
1. Validates inputs, opens the PDF, extracts metadata.
2. Builds chapter boundaries via `_extract_chapters_info` (outline-aware) and assigns temporary folders.
3. Uses `pymupdf4llm.to_markdown` to turn page ranges into Markdown, optionally tagging fences with `code_language`.
4. Splits Markdown on level-2 headings, normalizes image references with `_fix_image_paths`, and emits numbered section files. Every filename flows through `_clean_filename`, which now guarantees an `unnamed` fallback so slug generation stays deterministic even when titles are only punctuation.
5. Runs `_apply_chapter_numbering`/`_generate_toc` so resulting folders match the deterministic naming conventions documented in `path_builder.md`.
6. Returns a `ConversionResult` populated with chapter stats plus both TOC paths (`table_of_contents_path`, `toc_json_path`).

### `_generate_toc`
Shared helper that writes `README.md` with nested bullet links and `toc.json` containing:
- `entries`: chapter + section metadata (title, href, level, type).
- Aggregate statistics (`total_words`, `chapters_count`, etc.).
These artifacts drive CI comparisons through `ebook_tools.toc_checker` and user tooling such as `check-epub-toc`.

## Usage Patterns
- **One-off conversion**:
  ```bash
  uv run convert-docs --input ~/books/my.pdf --output /tmp/my-book
  ```
  Prints both TOC paths so you can open `/tmp/my-book/README.md` or parse `/tmp/my-book/toc.json`. Pass `--codename my-book` if you need a specific tenant name.
- **Bookmarks debugging**: disable `use_pdf_outlines` to flatten odd PDFs while inspecting the generated `toc.json` to see detected sections.
- **Code-heavy books**: set `PdfConverterConfig(code_language="python")` to ensure downstream renderers highlight anonymous fences consistently.

## Architecture
- Sits alongside `EpubConverter` under `src/ebook_tools/` and feeds the same `ConversionResult` dataclass defined in `epub_models.py`.
- `convert-docs` wires CLI flags to this converter and surfaces the resulting TOC paths for operators.
- The CLI automatically updates `deployment.json` (or the file passed to `--deployment-file`) once a conversion succeeds. Use `--skip-deployment-update` if you only need artifacts on disk.
- The JSON TOC output integrates with `ebook_tools.toc_checker` plus the `check-epub-toc` CLI so navMap/bookmark parity checks work for PDFs too.

## Testing
Unit coverage lives in `tests/unit/test_pdf_converter.py` and exercises the config defaults, `_clean_filename` fallback, chapter extraction logic, and async helpers such as `_create_section_file`. Extend that module when introducing new helpers, and keep the fast tests by mocking PyMuPDF objects instead of opening real PDFs. For end-to-end validation, still run the converter against a known PDF and compare the generated `toc.json` via `check-epub-toc --toc-json`.

## Related Documentation
- [../architecture.md](../architecture.md)
- [../implementation.md](../implementation.md)
- [./epub_converter.md](./epub_converter.md)
- [./path_builder.md](./path_builder.md)
- [../tools/check_epub_toc.md](../tools/check_epub_toc.md)

## Common Issues

### Missing outline data yields a single chapter
**Cause:** `use_pdf_outlines` is `True`, but the source PDF lacks level-1 bookmarks.

**Solution:** Either disable outlines (`PdfConverterConfig(use_pdf_outlines=False)`) or fix the PDF metadata. The converter will fall back to a single chapter spanning the entire book.

### Broken image references in Markdown
**Cause:** PyMuPDF4LLM emitted bare filenames and the converter could not rewrite them relative to chapter folders.

**Solution:** Ensure `preserve_images=True` so `_fix_image_paths` can rewrite links to `../images/<name>.png`. If the PDF embeds unsupported formats, rerun with `preserve_images=False` to keep the original links intact for a later ingestion step.
