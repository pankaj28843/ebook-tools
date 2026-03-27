# ebook-tools

Convert EPUB and PDF books into structured Markdown trees. Each book gets a cleanly slugified output directory with chapters split into numbered files and optional nested section directories.

## Install

### From GitHub (as a CLI tool)

```bash
uv tool install git+https://github.com/pankaj28843/ebook-tools.git
```

This makes `convert-docs`, `check-epub-toc`, and `debug-epub-conversions` available globally.

### From a local clone

```bash
git clone https://github.com/pankaj28843/ebook-tools.git
cd ebook-tools
uv tool install --editable .
```

Use `--force` to reinstall / upgrade:

```bash
uv tool install --force --editable .
```

### For development

```bash
git clone https://github.com/pankaj28843/ebook-tools.git
cd ebook-tools
uv sync --extra dev
uv run pytest
```

## Usage

### Convert a book

```bash
# Simplest form — output goes to ./converted-books/<book-slug>/
convert-docs book.epub

# Specify a parent output directory
convert-docs book.epub -o ~/books

# Convert a PDF
convert-docs document.pdf -o ~/books

# Flat layout (no chapter subdirectories)
convert-docs book.epub --max-depth 1

# Override the book title (affects the slug)
convert-docs book.epub -o ~/books -t "My Custom Title"
```

### Inspect metadata

```bash
convert-docs --inspect book.epub
convert-docs --inspect document.pdf
```

### List supported formats

```bash
convert-docs --list-formats
```

## Output Structure

The CLI always creates a slugified subfolder for each book under the parent output directory:

```
<parent-dir>/<book-slug>/
├── images/
├── 01-introduction.md
├── 02-getting-started/
│   ├── 1-overview.md
│   └── 2-installation.md
├── 03-core-concepts/
│   ├── 1-introduction.md
│   ├── 2-architecture.md
│   └── 3-patterns.md
└── 04-conclusion.md
```

- Chapters with multiple sections become directories (`02-getting-started/`)
- Chapters with a single section collapse to a flat file (`01-introduction.md`)
- Images are extracted to a shared `images/` directory
- `--max-depth 1` produces a fully flat layout (one `.md` per chapter)

### Output directory resolution

The parent directory is resolved in priority order:

1. `--output` / `-o` flag
2. `CONVERT_DOCS_OUTPUT_DIR` environment variable
3. `EBOOK_TOOLS_OUTPUT_DIR` environment variable
4. `./converted-books/` (default, relative to cwd)

## Additional CLIs

### check-epub-toc

Compare an EPUB's built-in table of contents against generated reference data:

```bash
check-epub-toc --epub book.epub --output ./converted-output
check-epub-toc --epub book.epub --toc-json ./output/toc.json --json-report report.json
```

### debug-epub-conversions

Batch convert a directory of EPUB files with per-book logging and TOC validation:

```bash
debug-epub-conversions --epub-dir ~/epubs --output-base /tmp/conversions --logs-dir /tmp/logs
debug-epub-conversions --epub-dir ~/epubs --limit 5 --overwrite
```

## Architecture

- **`converter_base.py`** — shared base class with output emission logic (flat vs structured), slugification via `python-slugify`, and file numbering
- **`epub_converter.py`** — EPUB to Markdown using `ebooklib` + `markdownify`, with spine-ordered chapter iteration and nav-title alignment
- **`pdf_converter.py`** — PDF to Markdown using `PyMuPDF` + `pymupdf4llm`, with outline-based chapter detection
- **`epub_models.py`** — Pydantic models (`Chapter`, `Section`, `ConversionResult`, `EpubInfo`, `PdfInfo`)
- **`toc_checker.py`** — TOC comparison utilities using `SequenceMatcher`
- **CLIs** — built with `Typer` and `Rich` for formatted output

## Dependencies

| Package | Purpose |
|---------|---------|
| `ebooklib` | EPUB reading and metadata extraction |
| `beautifulsoup4` | HTML parsing for EPUB content |
| `markdownify` | HTML to Markdown conversion |
| `pymupdf` | PDF text and image extraction |
| `pymupdf4llm` | PDF to Markdown with layout analysis |
| `pydantic` | Data validation and config models |
| `python-slugify` | Unicode-aware filename slugification |
| `typer` | CLI framework with auto-generated help |
| `rich` | Formatted terminal output |
