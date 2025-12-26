# utils/epub_converter.py - EPUB to Markdown Converter

## Overview

`EpubConverter` converts technical EPUB sources into a deterministic Markdown tree. By default (`max_output_depth=2`) every **chapter** becomes a numbered directory (for example, `01-chapter-slug/`) that contains one Markdown file per section while assets continue to live under a shared `images/` folder. Set `max_output_depth=1` to keep the legacy flattened layout where numbered chapter files sit at the root; structured mode automatically collapses chapters with zero or one emitted sections so operators never end up with single-file directories.

## Key Components

### `EpubConverterConfig`
Configuration dataclass that keeps the converter predictable:
- `heading_style`: Passed to `markdownify` to keep headings in ATX or Setext form.
- `strip_unwanted_tags`: Removes `<script>`, `<style>`, etc. before Markdown conversion.
- `preserve_images`: Controls whether `<img>` tags are extracted to `images/` and rewritten to `images/<filename>`.
- `max_section_depth` / `clean_filenames`: Guard how deep we split on headings and keep filenames ASCII-safe.
- `max_output_depth`: Governs how many directory levels the emitted Markdown tree uses (`1` = legacy flat files, `2+` = chapter folders with per-section files).
- `code_language`: Optional fence hint for Markdown code blocks.

### `EpubConverter`
Owns the conversion pipeline: normalizes EPUB containers, iterates ebooklib `ITEM_DOCUMENT`s, splits each chapter into sections, converts HTML to Markdown, copies images, and finally flattens everything into the target output directory. Private helpers share caches (e.g., `_images_extracted`) so repeated lookups stay fast.

### `convert_epub_to_markdown(epub_path, output_dir, book_title=None) -> ConversionResult`
Public async entry point. It:
1. Validates the EPUB path and creates the output directory.
2. Calls `_prepare_epub_for_conversion` to inject case/Unicode-safe aliases before ebooklib parses the archive.
3. Streams each manifest document through `_process_chapter`, which collects introductions + `<h2..hN>` sections and writes temporary `section-temp-XXXX.md` files inside per-chapter working directories.
4. Invokes `_write_structured_sections` (default) to rename the per-chapter staging folders into numbered directories (`NN-chapter-slug/`) containing one Markdown file per section. When `max_output_depth=1`, `_flatten_sections` preserves the legacy behavior by concatenating every section into a single root-level file. Both helpers update `EpubChapter.slug/output_path` and delete the temporary working directories.
5. Returns a `ConversionResult` populated with book/chapter/section metadata. TOC fields (`table_of_contents_path`, `toc_json_path`) remain `None` because the CLI no longer emits README/toc artifacts.

### `_write_structured_sections`
Runs when `max_output_depth > 1`. The helper renames each `chapter-temp-XXXX` folder to a deterministic directory (`NN-chapter-slug/`), then renames the staged section files to numbered Markdown files (for example, `01-introduction.md`, `02-deep-dive.md`). If a chapter only yields a single Markdown file, the helper skips directory creation and falls back to the flattened writer, ensuring no directory contains a lone `.md`. Every `EpubSection.file_path` now points to its own Markdown file, and `chapter.output_path` references the directory root so downstream tooling can glob subpaths.

### `_flatten_sections`
Retained for operators who request `max_output_depth=1`. It takes the ordered list of `EpubChapter` objects, computes padding based on chapter count, and emits one Markdown file per chapter by stitching the staged section files (with a leading `# Chapter Title` heading). It also updates every `EpubSection.file_path` to the shared chapter file, records `chapter.output_filename/output_path`, and deletes the temporary directories so only root-level Markdown files plus `images/` remain.

### `_process_chapter`, `_process_section`, `_process_introduction`
Operate on BeautifulSoup trees to gather intro text and each heading block. `_create_section_from_html` handles Markdown conversion, word/char counts, slug hints, and writing of temporary files before flattening.

### `_prepare_epub_for_conversion`
Builds lowercase + ASCII lookup tables for the original zip contents, locates `content.opf`, and clones the archive into a secure temp file whenever a manifest entry needs a normalized alias. Helpers such as `_build_name_maps`, `_load_opf_manifest`, `_collect_manifest_aliases`, `_find_alias`, and `_write_epub_with_aliases` keep this deterministic without mutating the source EPUB.

- **CLI conversion**: `uv run convert-docs --input book.epub --output ~/converted/book` runs the converter, prints chapter/section counts, and previews the first few emitted directories/files plus the shared `images/` folder. When `--output` is omitted, the CLI stores results under `./converted-docs/<slug>` derived from the input filename.
- **Inspection**: `uv run convert-docs --inspect book.epub` reports metadata (title, images, chapter count) without writing Markdown, useful when diagnosing manifest issues before running the full pipeline.
- **Custom settings**: Instantiate `EpubConverter(EpubConverterConfig(preserve_images=False))` when you want to keep original `<img>` references or strip scripts differently; the flattening helper will still write numbered Markdown files.

## Architecture Notes
- `convert-docs` feeds CLI flags into `EpubConverter`, prints a preview of the emitted directories/files, and writes to either the operator-provided `--output` directory or the default `./converted-docs/<slug>` derived from the source name. Downstream ingestion now sees numbered chapter directories (default) or flat files when operators pass `--max-output-depth=1`.
- `epub_models.py` defines the shared `EpubChapter`, `EpubSection`, and `ConversionResult` models. `EpubChapter.working_dir` stages sections, while `output_path` references the chapter directory (structured mode) or Markdown file (flat mode).
- `pdf_converter.py` mirrors the same chapter-level logic so EPUB/PDF outputs stay structurally aligned.

## Testing
Run the focused suite before shipping changes:
```bash
uv run ruff format .
uv run ruff check --fix .
timeout 60 uv run pytest tests/unit/test_epub_converter.py -k sections
timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing
```
For a manual smoke test, convert the sample EPUB and confirm the output directory contains numbered chapter folders (each with per-section Markdown files) plus `images/`:
```bash
uv run convert-docs --input tests/data/sample.epub --output /tmp/sample-structured
find /tmp/sample-structured -maxdepth 2 -type f | head
```
To verify the legacy flattened layout, rerun with `--max-output-depth 1`:
```bash
uv run convert-docs --input tests/data/sample.epub --output /tmp/sample-flat --max-output-depth 1
ls -1 /tmp/sample-flat | head
```
These smoke tests exercise EPUB normalization, section splitting, structured emission, and image rewriting end to end.

## Common Issues

### Navigation metadata differs from output titles
`_apply_nav_titles` reconciles ebooklib's nav map with converted chapters by matching hrefs and normalized titles. If headings still diverge, inspect `ConversionResult.chapters` to see the pre/post titles and confirm the nav map actually references the same source files.

### Images render as broken links
Ensure `preserve_images=True` (default) and verify `output/images/` contains the expected assets. Markdown files reference `images/<filename>` regardless of their temporary location, so once flattening completes the relative links resolve. If an EPUB references remote or unusual schemes, consider disabling preservation and let downstream tooling retrieve the images.
