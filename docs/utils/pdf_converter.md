# utils/pdf_converter.py - PDF to Markdown Converter

## Overview

`PdfConverter` mirrors the EPUB pipeline for technical PDFs but now emits a deterministic Markdown tree whose depth is controlled by `max_output_depth`. By default (`2`) it creates numbered chapter directories (e.g., `01-chapter-slug/`) with one Markdown file per section plus a shared `images/` directory for extracted assets. Set `max_output_depth=1` to keep the legacy flat layout with numbered chapter files at the root, and note that structured mode will automatically collapse any would-be single-file directory back into a standalone Markdown file so the tree never contains lonely folders.

## Key Components

### `PdfConverterConfig`
Configuration knobs exposed through Pydantic. Highlights:
- `use_pdf_outlines` (bool): treat outline level-1 entries as chapters (falls back to a single chapter spanning the book).
- `max_section_depth` (int): deepest heading level allowed when splitting Markdown (default `2` = `##`).
- `preserve_images` / `clean_filenames`: govern asset extraction plus filesystem-safe names.
- `code_language` (str | None): optional fence annotation for converted code blocks.
- `heading_style`: forwarded to pymupdf4llm so ATX vs Setext headings stay consistent.
- `max_output_depth`: maximum directory depth for emitted Markdown (`1` keeps flattened chapter files, higher values create chapter directories with per-section files).

### `PdfConverter`
Owns the end-to-end pipeline:
1. Validates inputs, opens the PDF, and extracts metadata.
2. Builds chapter boundaries via `_extract_chapters_info` (outline-aware) and assigns temporary folders.
3. Uses `pymupdf4llm.to_markdown` to turn page ranges into Markdown, optionally tagging fences with `code_language` and normalizing image references.
4. Splits Markdown on level-2 headings, normalizes image links with `_fix_image_paths`, and writes temporary section files per chapter.
5. Runs `_write_structured_sections` (default) to rename each chapter staging folder into `NN-chapter-slug/` with numbered section files. When `max_output_depth=1`, `_flatten_sections` maintains the legacy root-level chapter files. Both helpers update `EpubChapter.output_path` and clean up the staging folders.
6. Returns a `ConversionResult` populated with book/chapter/section metadata (TOC paths stay `None`).

### `_write_structured_sections`
Default helper. It walks the ordered list of `EpubChapter` objects, renames each `chapter-temp-XXXX` folder to `NN-chapter-slug/`, and moves every staged section file into that directory using deterministic numbering (e.g., `01-section-alpha.md`). When a chapter emits zero or one Markdown files the helper skips directory creation and instead routes through the flattened writer so there are never directories containing a single `.md`. Section metadata keeps its own file paths while `chapter.output_path` references the directory root.

### `_flatten_sections`
Still available for flat mode. Computes padding based on chapter count, writes `# Chapter Title` followed by each section's Markdown, truncates slugs to 80 characters, and overwrites conflicting chapter files deterministically. Each `EpubSection.file_path` now points to the shared chapter file so downstream tooling can jump to anchors while inspecting metadata.

## Usage Patterns
- **CLI conversion**:
  ```bash
  uv run convert-docs --input ~/books/my.pdf --output /tmp/my-book
  ```
  Produces numbered chapter directories (plus `images/`) by default and prints a preview via `print_conversion_summary()`. Pass `--max-output-depth 1` to keep the legacy flat files. If `--output` is omitted the CLI defaults to `./converted-docs/<slug>` based on the input filename.
- **Outline debugging**: set `PdfConverterConfig(use_pdf_outlines=False)` when bookmarks are missing or malformed; the converter will fall back to a single chapter file covering the entire book.
- **Code-heavy books**: pass `code_language="python"` (or similar) so anonymous code fences receive a default language before chapter concatenation.

## Architecture
- Shares the `ConversionResult`/`EpubChapter` models with the EPUB pipeline. `working_dir` is a staging area until `_write_structured_sections` (default) or `_flatten_sections` (flat mode) emits the final paths and populates `output_path`.
- `convert-docs` wires CLI flags to this converter, prints both chapter/section counts, previews a handful of emitted directories/files, and writes to either the requested `--output` directory or the default `./converted-docs/<slug>`.
- The output directory contains numbered chapter folders (default) or flattened chapter files, plus the shared `images/` tree, so EPUB and PDF outputs remain structurally aligned.

## Testing
Unit coverage lives in `tests/unit/test_pdf_converter.py` and exercises config defaults, `_clean_filename` fallbacks, chapter extraction, and both output helpers. Extend that module when introducing new helpers, and keep the tests fast by mocking PyMuPDF objects. For end-to-end validation, run the converter against a known PDF and confirm you get numbered chapter directories (default) or flat files when invoking `--max-output-depth 1`.

## Common Issues

### Missing outline data yields a single chapter
**Cause:** `use_pdf_outlines` is `True`, but the source PDF lacks level-1 bookmarks.

**Solution:** Either disable outlines (`PdfConverterConfig(use_pdf_outlines=False)`) or fix the PDF metadata. The converter will fall back to a single chapter spanning the entire book.

### Broken image references in Markdown
**Cause:** PyMuPDF4LLM emitted bare filenames and the converter could not rewrite them relative to the shared `images/` directory.

**Solution:** Ensure `preserve_images=True` so `_fix_image_paths` rewrites links to `images/<name>.png`. If the PDF embeds unsupported formats, rerun with `preserve_images=False` and let downstream tooling fetch images separately.
