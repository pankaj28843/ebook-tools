# ebook-tools

Standalone ebook and PDF to Markdown converters extracted from docs-mcp-server. Use these CLIs to build filesystem tenants (`mcp-data/<codename>`) without pulling the full MCP server dependencies.

## Quickstart

```bash
cd ebook-tools
uv sync
uv run convert-docs --help
```

Use `uv run convert-docs --input book.epub --output ./mcp-data/my-book` to produce the Markdown tree; the CLI will derive a codename automatically (override with `--codename my-book`) and update `deployment.json` unless you pass `--skip-deployment-update`. Additional helpers like `check-epub-toc` and `debug-epub-conversions` live in the same package.
