# utils/epub_converter.py - EPUB to Markdown Converter

## Overview

`EpubConverter` converts technical EPUB sources into a single-level Markdown directory. Every section becomes a numbered root file (for example, `001-chapter-slug-section-slug.md`) and all assets live under a shared `images/` folder. The converter still mirrors the logical reading order, but removes the nested folder/README/toc.json structure so downstream tooling can ingest a simple linear list of files.

## Key Components

### `EpubConverterConfig`
Configuration dataclass that keeps the converter predictable:
- `heading_style`: Passed to `markdownify` to keep headings in ATX or Setext form.
- `strip_unwanted_tags`: Removes `<script>`, `<style>`, etc. before Markdown conversion.
- `preserve_images`: Controls whether `<img>` tags are extracted to `images/` and rewritten to `images/<filename>`.
- `max_section_depth` / `clean_filenames`: Guard how deep we split on headings and keep filenames ASCII-safe.
- `code_language`: Optional fence hint for Markdown code blocks.

### `EpubConverter`
Owns the conversion pipeline: normalizes EPUB containers, iterates ebooklib `ITEM_DOCUMENT`s, splits each chapter into sections, converts HTML to Markdown, copies images, and finally flattens everything into the target output directory. Private helpers share caches (e.g., `_images_extracted`) so repeated lookups stay fast.

### `convert_epub_to_markdown(epub_path, output_dir, book_title=None) -> ConversionResult`
Public async entry point. It:
1. Validates the EPUB path and creates the output directory.
2. Calls `_prepare_epub_for_conversion` to inject case/Unicode-safe aliases before ebooklib parses the archive.
3. Streams each manifest document through `_process_chapter`, which collects introductions + `<h2..hN>` sections and writes temporary `section-temp-XXXX.md` files inside per-chapter working directories.
4. Invokes `_flatten_sections` to move every temporary section into the root output directory, assign deterministic numeric prefixes, update `EpubChapter.slug`, and delete the working directories.
5. Returns a `ConversionResult` populated with book/chapter/section metadata. TOC fields (`table_of_contents_path`, `toc_json_path`) remain `None` because the CLI no longer emits README/toc artifacts.

### `_flatten_sections`
Takes the ordered list of `EpubChapter` objects, computes global padding based on total section count, and renames each temp file to `NN-chapter-slug-section-slug.md`. The helper also truncates slugs to 80 characters, removes existing conflicts, and deletes the per-chapter working directories so only root-level Markdown files plus `images/` remain.

### `_process_chapter`, `_process_section`, `_process_introduction`
Operate on BeautifulSoup trees to gather intro text and each heading block. `_create_section_from_html` handles Markdown conversion, word/char counts, slug hints, and writing of temporary files before flattening.

### `_prepare_epub_for_conversion`
Builds lowercase + ASCII lookup tables for the original zip contents, locates `content.opf`, and clones the archive into a secure temp file whenever a manifest entry needs a normalized alias. Helpers such as `_build_name_maps`, `_load_opf_manifest`, `_collect_manifest_aliases`, `_find_alias`, and `_write_epub_with_aliases` keep this deterministic without mutating the source EPUB.

## Usage Patterns
- **CLI conversion**: `uv run convert-docs --input book.epub --output ~/converted/book` runs the converter, prints chapter/section counts, and previews the first few flattened filenames plus the shared `images/` folder.
- **Inspection**: `uv run convert-docs --inspect book.epub` reports metadata (title, images, chapter count) without writing Markdown, useful when diagnosing manifest issues before running the full pipeline.
- **Custom settings**: Instantiate `EpubConverter(EpubConverterConfig(preserve_images=False))` when you want to keep original `<img>` references or strip scripts differently; the flattening helper will still write numbered Markdown files.

## Architecture Notes
- `convert-docs` feeds CLI flags into `EpubConverter`, prints a flat-file preview, and writes deployment snippets so filesystem tenants can be registered automatically. Because outputs are flat, downstream ingestion no longer needs to walk per-chapter folders.
- `epub_models.py` defines the shared `EpubChapter`, `EpubSection`, and `ConversionResult` models. `EpubChapter.working_dir` tracks the temporary chapter directory solely so `_flatten_sections` can delete it.
- `pdf_converter.py` mirrors the same flattening logic to keep EPUB/PDF outputs identical (single directory + `images/`).

## Testing
Run the focused suite before shipping changes:
```bash
uv run ruff format .
uv run ruff check --fix .
timeout 60 uv run pytest tests/unit/test_epub_converter.py -k sections
timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing
```
For a manual smoke test, convert the sample EPUB and confirm the output directory only contains numbered Markdown files plus `images/`:
```bash
uv run convert-docs --input tests/data/sample.epub --output /tmp/sample-flat
ls -1 /tmp/sample-flat | head
```
This exercises EPUB normalization, section splitting, flattening, and image rewriting end to end.

## Common Issues

### Navigation metadata differs from output titles
`_apply_nav_titles` reconciles ebooklib's nav map with converted chapters by matching hrefs and normalized titles. If headings still diverge, inspect `ConversionResult.chapters` to see the pre/post titles and confirm the nav map actually references the same source files.

### Images render as broken links
Ensure `preserve_images=True` (default) and verify `output/images/` contains the expected assets. Markdown files reference `images/<filename>` regardless of their temporary location, so once flattening completes the relative links resolve. If an EPUB references remote or unusual schemes, consider disabling preservation and let downstream tooling retrieve the images.
