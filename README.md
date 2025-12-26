# ebook-tools

Standalone ebook and PDF to Markdown converters extracted from docs-mcp-server. Use these CLIs to build deterministic Markdown trees (`./converted-docs/<slug>` by default) without pulling the full MCP server dependencies.

## Quickstart

```bash
cd ebook-tools
uv sync
uv run convert-docs --help
```

Use `uv run convert-docs --input book.epub --output ./converted/my-book` to produce the Markdown tree. When `--output` is omitted the CLI writes to `./converted-docs/<slug>` based on the input filename, so operators can run quick conversions without planning directories. Additional helpers like `check-epub-toc` and `debug-epub-conversions` live in the same package.
