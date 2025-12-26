# utils/pdf_converter.py - PDF to Markdown Converter

## Overview

`PdfConverter` mirrors the EPUB pipeline for technical PDFs but now emits **one numbered Markdown file per chapter** (e.g., `001-chapter-slug.md`). Sections are still parsed so we retain metadata, yet the filesystem stays compact: a handful of chapter files at the root plus a shared `images/` directory for extracted assets.

## Key Components

### `PdfConverterConfig`
Configuration knobs exposed through Pydantic. Highlights:
- `use_pdf_outlines` (bool): treat outline level-1 entries as chapters (falls back to a single chapter spanning the book).
- `max_section_depth` (int): deepest heading level allowed when splitting Markdown (default `2` = `##`).
- `preserve_images` / `clean_filenames`: govern asset extraction plus filesystem-safe names.
- `code_language` (str | None): optional fence annotation for converted code blocks.
- `heading_style`: forwarded to pymupdf4llm so ATX vs Setext headings stay consistent.

### `PdfConverter`
Owns the end-to-end pipeline:
1. Validates inputs, opens the PDF, and extracts metadata.
2. Builds chapter boundaries via `_extract_chapters_info` (outline-aware) and assigns temporary folders.
3. Uses `pymupdf4llm.to_markdown` to turn page ranges into Markdown, optionally tagging fences with `code_language` and normalizing image references.
4. Splits Markdown on level-2 headings, normalizes image links with `_fix_image_paths`, and writes temporary section files per chapter.
5. Runs `_flatten_sections` to concatenate those section files into `NN-chapter-slug.md`, update `EpubChapter.output_path`, and delete the staging folders so only root-level chapter files + `images/` remain.
6. Returns a `ConversionResult` populated with book/chapter/section metadata (TOC paths stay `None`).

### `_flatten_sections`
Parallel to the EPUB helper: computes padding based on chapter count, writes `# Chapter Title` followed by each section's Markdown, truncates slugs to 80 characters, and overwrites conflicting chapter files deterministically. Each `EpubSection.file_path` now points to the shared chapter file so downstream tooling can jump to anchors while inspecting metadata.

## Usage Patterns
- **CLI conversion**:
  ```bash
  uv run convert-docs --input ~/books/my.pdf --output /tmp/my-book
  ```
  Produces numbered chapter files (plus `images/`) and prints a preview via `print_conversion_summary()`. If `--output` is omitted the CLI defaults to `./converted-docs/<slug>` based on the input filename.
- **Outline debugging**: set `PdfConverterConfig(use_pdf_outlines=False)` when bookmarks are missing or malformed; the converter will fall back to a single chapter file covering the entire book.
- **Code-heavy books**: pass `code_language="python"` (or similar) so anonymous code fences receive a default language before chapter concatenation.

## Architecture
- Shares the `ConversionResult`/`EpubChapter` models with the EPUB pipeline. `working_dir` is just a staging area until `_flatten_sections` emits the chapter-level file and populates `output_path`.
- `convert-docs` wires CLI flags to this converter, prints both chapter/section counts, and writes to either the requested `--output` directory or the default `./converted-docs/<slug>`.
- The root directory always contains numbered chapter files plus `images/`, keeping EPUB and PDF outputs structurally identical for downstream ingestion.

## Testing
Unit coverage lives in `tests/unit/test_pdf_converter.py` and exercises config defaults, `_clean_filename` fallbacks, chapter extraction, and `_flatten_sections`. Extend that module when introducing new helpers, and keep the tests fast by mocking PyMuPDF objects. For end-to-end validation, run the converter against a known PDF and confirm the root directory only contains chapter files + `images/`.

## Common Issues

### Missing outline data yields a single chapter
**Cause:** `use_pdf_outlines` is `True`, but the source PDF lacks level-1 bookmarks.

**Solution:** Either disable outlines (`PdfConverterConfig(use_pdf_outlines=False)`) or fix the PDF metadata. The converter will fall back to a single chapter spanning the entire book.

### Broken image references in Markdown
**Cause:** PyMuPDF4LLM emitted bare filenames and the converter could not rewrite them relative to the shared `images/` directory.

**Solution:** Ensure `preserve_images=True` so `_fix_image_paths` rewrites links to `images/<name>.png`. If the PDF embeds unsupported formats, rerun with `preserve_images=False` and let downstream tooling fetch images separately.
