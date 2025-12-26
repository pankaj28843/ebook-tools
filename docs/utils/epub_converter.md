# utils/epub_converter.py - EPUB to Markdown Converter

## Overview

`EpubConverter` turns a technical EPUB into a deterministic Markdown tree that mirrors the book's logical table of contents (TOC). The converter splits chapters into numbered folders, emits numbered section files, normalizes image assets, and (optionally) emits both a human-readable `README.md` TOC and a structured `toc.json` artifact so downstream tooling can diff the generated outline against the source EPUB's navigation map without scraping Markdown.

## Key Components

### `EpubConverterConfig`
Configuration dataclass living alongside the converter. Important fields:
- `heading_style`: Passed to `markdownify` so exported headings stay in ATX or Setext form.
- `preserve_images`: Toggles image extraction into `images/` and rewrites `<img src>` links.
- `max_section_depth`, `strip_unwanted_tags`, `clean_filenames`: Guard content splitting and filesystem-safe naming.
- `include_toc`: Controls whether `_generate_toc` writes the `README.md` and `toc.json` TOC pair, which together power human review and machine comparisons.

### `EpubConverter`
Orchestrates the entire pipeline: normalizes the EPUB archive, iterates ebooklib `ITEM_DOCUMENT`s, breaks them into sections, converts HTML to Markdown, rewrites filenames, and optionally writes a TOC summary. All helpers are private methods on the class so they can share caches (e.g., `_images_extracted`).

### `convert_epub_to_markdown(epub_path, output_dir, book_title=None) -> ConversionResult`
Public async entry point. It:
1. Validates inputs and creates the output directory.
2. Calls `_prepare_epub_for_conversion` to add missing aliases so ebooklib can read non-ASCII manifests.
3. Streams each chapter through `_process_chapter`, picking out `<h2>` sections and creating temporary `section-temp-XXXX.md` files.
4. Applies `_apply_chapter_numbering`/`_apply_section_numbering` to convert the temporary placeholders into deterministic `NN-chapter-slug/MM.section-slug.md` files. This deterministic labeling is what allows TOC diffs between EPUB metadata and rendered Markdown.
5. Generates the optional `README.md` + `toc.json` pair via `_generate_toc` and returns a `ConversionResult` (see `src/ebook_tools/epub_models.py`) containing chapter metadata, section stats, the Markdown TOC path (`table_of_contents_path`), and the JSON diagnostic path (`toc_json_path`) for comparison tooling.

### `_process_chapter`, `_process_section`, `_process_introduction`
Operate on BeautifulSoup nodes to gather chapter intro text plus each `<h2>` segment. `_create_section_from_html` handles Markdown conversion, word counts, slug hints, and temporary filenames so numbering can run later.

### `_prepare_epub_for_conversion`
Scans the EPUB manifest for entries whose casing or Unicode normalization prevents ebooklib from resolving them. The method now delegates to a set of helpers that build case-insensitive lookup tables, parse the OPF manifest, and collect alias targets before repackaging the archive with `tempfile.NamedTemporaryFile` so no insecure `mktemp` artifacts linger on disk. When aliases are required it writes a hardened temporary `.epub` with the additional entries, ensuring later steps always see every XHTML asset and minimizing false TOC mismatches.

### Manifest normalization helpers
- `_build_name_maps` snapshots the original zip namelist into lowercase and ASCII lookup tables so we can resolve manifest references despite casing or diacritics.
- `_load_opf_manifest` finds the container's rootfile, resolves it through the lookup tables, and returns both the parsed XML tree and its directory for downstream path joins.
- `_collect_manifest_aliases` walks the manifest, comparing each `href` against the available zip entries and mapping any missing targets to their normalized counterpart via `_find_alias`.
- `_write_epub_with_aliases` clones the source EPUB into a secure temp file, injecting each alias so ebooklib can read the asset without mutating the original archive.

### `_generate_toc`
Writes `README.md` that lists every chapter and section, including deterministic links (e.g., `01-intro/01.01-overview.md`), plus `toc.json` which stores the same hierarchy alongside aggregate stats (chapter/section counts, total words). `ConversionResult.table_of_contents_path` references the Markdown file while `ConversionResult.toc_json_path` references the JSON artifact so both humans and automated QA tooling can consume the TOC without re-parsing Markdown.

## Usage Patterns
- **One-off conversion**: `uv run convert-docs --input path/to/book.epub --output out/book` calls `EpubConverter.convert_epub_to_markdown` under the hood (the CLI derives a codename automatically, or override it with `--codename book`), then prints the TOC paths so you can inspect both `README.md` and `toc.json` alongside the original EPUB.
- **Dry-run/inspection**: `uv run convert-docs --input path/to/book.epub --inspect` loads the EPUB, prints the computed chapter/section list (sourced from `ConversionResult.chapters`), and notes missing sections so you can debug TOC mismatches without writing files.
- **TOC comparison workflow**: Use the emitted `README.md` for quick visual inspection and `toc.json` (backed by `ConversionResult.toc_json_path`) for programmatic diffs against the EPUB's navMap/navPoint order. Because numbering is deterministic, you can script comparisons by sorting on `chapter.folder_name`/`section.filename` and lining that up with ebooklib's TOC entries without scraping Markdown.
- **Custom configuration**: Instantiate `EpubConverter(EpubConverterConfig(preserve_images=False, include_toc=False))` when creating custom pipelines (e.g., bulk conversions where you only need Markdown bodies and a separate external TOC comparator).

## Architecture
- `convert-docs` wires CLI flags to `EpubConverter` and surfaces the `ConversionResult` for operators (printing chapter stats, the TOC path, and diff-friendly metadata).
- The CLI now updates `deployment.json` automatically after conversion; point it at another manifest with `--deployment-file /path/to/manifest.json` or opt out entirely via `--skip-deployment-update` when you only need the Markdown tree.
- `epub_models.py` defines the `EpubChapter`, `EpubSection`, and `ConversionResult` schemas that this converter populates. Downstream systems (e.g., filesystem keyword sampling) rely on these models when traversing converted docs.
- `docs/utils/path_builder.md` documents the deterministic naming rules that `_apply_chapter_numbering` and `_apply_section_numbering` honor. EPUB and PDF converters both rely on those conventions so mixed-format corpora look uniform.
- Multi-format parity: `pdf_converter.py` shares the same numbering helpers and `ConversionResult` contract, which keeps TOC comparison logic identical regardless of input format.

## Testing
Run the fast suite under `tests/unit/test_epub_converter*.py` before shipping changes. For manual smoke tests, convert a known EPUB and inspect the emitted TOC:
```bash
uv run convert-docs --input path/to/sample.epub --output /tmp/sample-book
cat /tmp/sample-book/README.md
jq '.' /tmp/sample-book/toc.json
```
This manual loop exercises `_prepare_epub_for_conversion`, numbering logic, and TOC generation in one pass. When adding tests, place them under `tests/unit/test_epub_converter.py` and assert against `ConversionResult` rather than private helpers.

## Related Documentation
- [../architecture.md](../architecture.md) - System-level view showing where format converters plug into the ingestion pipeline.
- [../implementation.md](../implementation.md) - Describes worker orchestration and how `convert-docs` is invoked in automation flows.
- [./path_builder.md](./path_builder.md) - Canonical reference for deterministic folder/section naming shared by EPUB and PDF converters.

## Common Issues

### "Missing manifest entries" during conversion
**Cause:** EPUB archives sometimes omit lowercase/ASCII duplicates, so ebooklib cannot resolve a chapter referenced in the OPF manifest.

**Solution:** `_prepare_epub_for_conversion` already injects aliases, but if the error persists rerun the converter with `--inspect` to confirm the offending `source_file`. Manually add a symlink or repackage the EPUB:
```bash
tmpdir=$(mktemp -d)
unzip -q book.epub -d "$tmpdir"
cp "$tmpdir/path/Actual.xhtml" "$tmpdir/path/actual.xhtml"
(cd "$tmpdir" && zip -qr ../book-fixed.epub .)
uv run convert-docs --input book-fixed.epub --output out/book --codename book
```

### Images render as broken links
**Cause:** `preserve_images` defaults to `True`, but some EPUBs store images outside the manifest or reuse relative paths that clash after slugification.

**Solution:** Inspect `output/images/` to confirm extraction, then ensure section Markdown files reference the normalized paths. If the EPUB uses external URLs or special schemes, temporarily disable image preservation (`--skip-images`) so Markdown retains the original `<img>` links for downstream fetchers.
