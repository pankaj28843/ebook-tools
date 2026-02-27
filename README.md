# ebook-tools

Standalone ebook and PDF to Markdown converters extracted from docs-mcp-server. Use these CLIs to build deterministic Markdown trees (`./converted-docs/<slug>` by default) without pulling the full MCP server dependencies.

## Quickstart

```bash
cd ebook-tools
uv sync
uv run convert-docs --help
```

Use `uv run convert-docs --input book.epub --output ./converted/my-book` (or `--output-dir`) to produce the Markdown tree.

When output is omitted, the CLI resolves output in this order:
1. `--output` / `--output-dir`
2. `CONVERT_DOCS_OUTPUT_DIR` (env var)
3. `EBOOK_TOOLS_OUTPUT_DIR` (env var)
4. `./converted-docs/<slug>` (default, relative to current working directory)

Path behavior:
- `./books` is resolved relative to the current working directory (`pwd`)
- `~/books` is resolved under your home directory

The `--max-output-depth` flag (default `2`) controls how many directory levels of Markdown files are emitted—set it to `1` to keep the legacy flat layout, and note that structured mode automatically collapses any would-be one-file directory back into a single Markdown file at the parent level. Additional helpers like `check-epub-toc` and `debug-epub-conversions` live in the same package.
