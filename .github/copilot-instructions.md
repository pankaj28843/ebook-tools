# AI Coding Agent Instructions for ebook-tools

> Internal guidance for GitHub Copilot agents working in this repository. Reference README.md and docs/ for user-facing material.

## Project Snapshot
- **Purpose**: Convert EPUB and PDF sources into clean Markdown/tenant trees plus navigation metadata so other services can consume them.
- **Entry points**: `convert-docs`, `check-epub-toc`, and `debug-epub-conversions` (all exposed via `uv run <script>` or `uv run python -m ebook_tools.cli.<name>`).
- **Code layout**: Core logic in `src/ebook_tools/` (EPUB/PDF converters, TOC checker, CLI shims); fixtures in `tests/data/`; exhaustive tests live under `tests/unit/`.

## Core Philosophy
1. **Deterministic pipelines** – conversions must be reproducible byte-for-byte when given the same input.
2. **Minimal, clean code** – prefer straightforward helpers over abstraction layers; delete unused code aggressively.
3. **100% test coverage at all times** – every change must keep coverage at 100% for `src/ebook_tools` and add tests for new behavior.
4. **Fail loudly** – propagate exceptions with context; never silence errors during conversion.
5. **CLI-first workflows** – anything an operator needs must be runnable via the provided CLIs; no hidden scripts.
6. **Research before guessing** – use TechDocs MCP tools (see below) to ground design choices, especially around EPUB/PDF standards and Copilot automation patterns.

## Primary Surfaces
- `src/ebook_tools/epub_converter.py` – EPUB parsing, section splitting, metadata extraction.
- `src/ebook_tools/pdf_converter.py` – PDF to Markdown conversion via PyMuPDF/PyMuPDF4LLM.
- `src/ebook_tools/toc_checker.py` – validation utilities for TOCs/nav docs.
- `src/ebook_tools/cli/` – thin argparse entrypoints (`convert_docs`, `check_epub_toc`, `debug_epub_conversions`). Keep them declarative; push logic into core modules.
- `docs/tools/*.md` – operator runbooks. Update them whenever CLI flags or behaviors change.

## Must-Follow Rules
- Use `uv run` for every Python command (`uv run convert-docs --help`, `uv run pytest ...`). Never call `python`, `pip`, or `pytest` directly.
- Wrap every pytest invocation with `timeout 60` and collect coverage: `timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing`.
- Non-trivial efforts (multiple files, refactors, features) require a PRP plan stored under `.github/ai-agent-plans/YYYY-MM-DD-<slug>-plan.md` per `.github/instructions/PRP-README.md`.
- Default to ASCII output when editing files; only introduce Unicode if the file already uses it and it is required by the format.
- Never skip updating docs/tests. Code without matching docs/tests is rejected.

## TechDocs Research Workflow
Use the MCP TechDocs tools before inventing APIs or heuristics:
1. `mcp_techdocs_list_tenants()` – discover available sources.
2. `mcp_techdocs_describe_tenant(codename="github-copilot")` (or other relevant tenants) – review `test_queries`, `url_prefixes`, and patterns. For example, `github-copilot` covers https://docs.github.com/en/copilot and suggests queries like "Who can use this feature?".
3. `mcp_techdocs_root_search(tenant_codename="python", query="pathlib TemporaryDirectory")` – fetch precise references for stdlib usage, file handling, etc.
4. `mcp_techdocs_root_fetch(...)` – read the authoritative document before coding.
Document key takeaways in comments or plan files so future agents know which sources informed the implementation.

## Patterns & Anti-Patterns
- **Preferred patterns**: streaming reads, `pathlib.Path`, dataclasses/pydantic models for structured metadata, pure functions for content transforms, `TemporaryDirectory` or in-memory buffers for tests.
- **Anti-patterns**: shared mutable globals, implicit I/O in constructors, hiding file writes behind threads, flaky tests relying on randomness, introducing new CLIs without docs, or skipping coverage just because `pyproject.toml` defaults to `--no-cov`.

## Definition of Done
A change is complete only if **all** conditions hold:
1. Imports and typing pass `uv run ruff check --fix .` and formatting passes `uv run ruff format .` (run on the entire repo unless scope dictates otherwise).
2. `timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing` is green with 100% coverage maintained. Add focused `-k` runs for new/changed areas.
3. Run at least one CLI smoke test relevant to your change (e.g., `uv run convert-docs --input tests/data/sample.epub --output /tmp/out --codename smoke-test` or `uv run check-epub-toc --nav tests/data/sample/nav.xhtml`).
4. Update docs under `docs/tools/` or `docs/utils/` when behavior, flags, or troubleshooting steps change.
5. No stray files, no TODO/FIXME placeholders, no commented-out experiments.

## Validation Loop (Default)
1. `uv run ruff format .`
2. `uv run ruff check --fix .`
3. `timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing`
4. CLI smoke test(s) for the affected commands.
5. Re-run targeted tests (`timeout 60 uv run pytest tests/unit/test_epub_converter.py -k scenario`) if you touched a narrow area.
6. `git status` to verify only intentional files changed.

## Working Notes & Plans
- Keep work logs inside the relevant plan file when a task spans multiple steps or hand-offs. Follow the PRP template in `.github/instructions/PRP-README.md`.
- When you discover a repeatable pitfall, append it to the "Learning Log" section at the end of this file with the provided before/after pattern format.

Stay concise, keep diffs focused, and let the existing test suite guide you.

## Learning Log
- *Add entries here using*: `**[Category] – LEARNED YYYY-MM-DD:** ❌ Anti-pattern → ✅ Correct pattern.`
