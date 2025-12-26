---
name: addSourceBundle
description: Add a new EPUB/PDF source, convert it with convert-docs, and capture docs/tests updates.
argument-hint: input="tests/data/sample.epub" codename="my-book" output="./mcp-data/my-book"
---

## TechDocs Research
Use `#techdocs` before touching converters:
1. `mcp_techdocs_list_tenants()`
2. `mcp_techdocs_describe_tenant(codename="github-copilot")` (or `python`/`clean-code-book`) for patterns.
3. `mcp_techdocs_root_search(...)` for EPUB/PDF nuances, then `root_fetch` to read the high-score doc.
Document the takeaways inside your PRP or plan notes.

## Ground Rules
- Follow `.github/copilot-instructions.md` (uv run only, 100% coverage, CLI smoke tests).
- Keep outputs deterministic: no timestamps, random suffixes, or machine-dependent paths.
- Update docs under `docs/tools/` when new flags or workflows appear.

## Steps
1. **Gather inputs**
   - Normalize the slug (`codename`) and destination (`./mcp-data/{codename}`).
   - Inspect the source (EPUB/PDF) to confirm metadata quality; note quirks in the plan.
2. **Run conversion**
   ```bash
   uv run convert-docs --input <input> --output <output> --codename <codename>
   ```
   - Capture logs; treat warnings as bugs until disproven.
3. **Validate navigation**
   ```bash
   uv run check-epub-toc --nav <output>/nav.xhtml
   ```
4. **Add/Update tests**
   - Cover any new parsing branches (e.g., unusual `<nav>` depth) under `tests/unit/`.
   - Re-run `timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing`.
5. **Docs + hand-off**
   - Update the relevant doc (e.g., `docs/tools/convert_docs.md`) with sample command + troubleshooting note.
   - Share paths plus validation status in your final response.

Keep responses short: highlight what changed, where output lives, and which commands were run.
