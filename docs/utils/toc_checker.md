# toc_checker - EPUB TOC Comparator

## Overview

Utilities that convert EPUB navigation maps into normalized entries and compare them to either the Markdown README or the converter-emitted `toc.json`. This module makes it easy to detect missing or misordered chapters so we can align Markdown output with the source book structure.

## Key Components

### `TocEntry`
Represents a single TOC row with normalized helpers for diffing.

**Attributes:**
- `title` (str): Original label shown to readers.
- `href` (str | None): Relative link inside the EPUB or generated Markdown.
- `level` (int): Depth in the hierarchy (1 = top-level part).
- `source` (str): Indicates whether the entry originated from the EPUB navMap or Markdown README.

**Example:**
```python
entry = TocEntry(title="Welcome", href="001/index.md", level=1, source="markdown")
```

### `load_nav_entries`
Parses an EPUB file using `ebooklib` and returns a flattened TOC. Supports both modern `book.get_toc()` and legacy `book.toc` attributes so we can work across multiple ebooklib versions.

**Parameters:**
- `epub_path` (Path | str): Path to the `.epub` source.
- `max_depth` (int | None): Optional depth limit to skip deep subsections.

**Returns:**
- `list[TocEntry]`: Normalized entries in reading order.

**Example:**
```python
entries = load_nav_entries("~/books/designing_data_intensive_applications.epub", max_depth=2)
assert entries[0].title == "Foreword"
```

### `load_markdown_toc`
Reads `README.md` output from the converter and extracts headings/links into `TocEntry` rows.

**Parameters:**
- `readme_path` (Path | str): Path to generated README.
- `max_depth` (int | None): Optional limit for nested bullets/headings.

### `load_json_toc`
Parses `toc.json` artifacts generated during EPUB conversion. The helper trims whitespace, infers heading levels when the converter omits them, and returns normalized `TocEntry` rows with `source="json"`.

**Parameters:**
- `toc_path` (Path | str): Path to the converter output file.
- `max_depth` (int | None): Optional hierarchy cap.

### `compare_toc_entries`
Diffs two `TocEntry` lists with `difflib.SequenceMatcher` and reports missing items plus ordering mismatches.

**Returns:**
- `TocComparisonResult`: Contains the original sequences plus `missing_in_reference`, `missing_in_navmap`, and `order_mismatches`. `is_match` is `True` only when the structures align perfectly.

**Example:**
```python
nav_entries = load_nav_entries("./book.epub", max_depth=2)
reference_entries = load_json_toc("./output/toc.json", max_depth=2)
result = compare_toc_entries(nav_entries, reference_entries)
if not result.is_match:
    for entry in result.missing_in_reference:
        print("Missing chapter:", entry.title)
```

## Usage Patterns

1. Convert an EPUB with `convert-docs`.
2. Call `load_nav_entries` on the original EPUB, and `load_json_toc` (preferred) or `load_markdown_toc` on the generated artifacts.
3. Feed both lists into `compare_toc_entries` to identify gaps.
4. Optionally serialize `TocComparisonResult.as_dict()` to JSON for automation pipelines like `debug-epub-conversions`.

## Architecture

`toc_checker` is used by `check-epub-toc` and the `debug-epub-conversions` harness to validate conversions end-to-end. The module only depends on `ebooklib` and the standard library, keeping it lightweight for CLI usage.

## Testing

Unit coverage lives in `tests/unit/test_toc_checker.py` and verifies the `book.toc` fallback path, JSON parsing helpers, and comparison edge cases.

## Related Documentation

- [utils/epub_converter.md](./epub_converter.md)
- [architecture.md](../architecture.md)

## Common Issues

### AttributeError: "does not expose a TOC"
**Cause:** The EPUB object did not provide `get_toc()` or `toc`, which usually means the input file is corrupt or `ebooklib` could not parse its NCX/nav document.

**Solution:**
```bash
# Re-run conversion to confirm the EPUB is valid
uv run convert-docs --input path/to/book.epub --output /tmp/book-output
# If the error persists, open the EPUB with another reader to verify its TOC
```
