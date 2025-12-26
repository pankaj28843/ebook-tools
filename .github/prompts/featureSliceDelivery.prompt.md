---
name: featureSliceDelivery
description: Ship a vertical slice (converter logic + CLI flag + tests + docs) for ebook-tools.
argument-hint: feature="footnote support" scope="epub_converter.py, convert_docs CLI" verification="uv run convert-docs --help"
---

## TechDocs Research
- Run `mcp_techdocs_list_tenants()` → `mcp_techdocs_describe_tenant` for `github-copilot`, `python`, or any tenant backing the design.
- Use `mcp_techdocs_root_search`/`root_fetch` for exact patterns (e.g., `python` tenant for `pathlib` usage).
- Note findings in your plan before coding.

## Delivery Flow
1. **Plan** – Ensure a PRP exists (or draft via `prpPlanOnly`). Capture feature goal, success criteria, and affected files.
2. **Model/Helpers** – Update converters (`src/ebook_tools/*.py`) with deterministic helpers. Favor pure functions.
3. **CLI Wiring** – Extend argparse in `src/ebook_tools/cli/*.py` and keep surfaces thin (delegate to helpers immediately).
4. **Docs/Metadata** – Update `docs/tools/` to reflect new flags/behaviors and mention troubleshooting tips.
5. **Tests** – Add/extend cases under `tests/unit/` (cover success + failure). Keep coverage at 100%.
6. **Validation**
   ```bash
   uv run ruff format .
   uv run ruff check --fix .
   timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing
   uv run convert-docs --input tests/data/sample.epub --output /tmp/out --codename feature-smoke [--new-flag]
   ```

## Output
- Summaries grouped by layer (helpers, CLI, tests, docs) with file references.
- Commands executed + outcomes.
- Follow-up steps if further validation or fixtures are needed.
