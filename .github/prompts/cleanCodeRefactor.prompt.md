---
name: cleanCodeRefactor
description: Rename/simplify converter helpers without changing behavior.
argument-hint: path="src/ebook_tools/epub_converter.py" brief="clarify spine parsing"
---

## TechDocs Research
- `mcp_techdocs_list_tenants()` → `mcp_techdocs_describe_tenant("clean-code-book")` for naming/structure cues.
- Pull supporting snippets with `mcp_techdocs_root_search`/`root_fetch` if you cite a pattern.

## Guardrails
- Honor `.github/copilot-instructions.md`: uv run commands only, 100% coverage, CLI smoke if logic might shift.
- Keep docstrings as-is unless the user requests wording changes; prefer intent-revealing names.
- Do not shuffle modules or split files unless explicitly asked.

## Flow
1. Confirm scope (rename vs. helper extraction) and note untouched areas in final summary.
2. Apply one idea at a time (e.g., flatten conditional, extract `build_section_metadata`).
3. Update usages via `grep_search`/`list_code_usages` so nothing breaks.
4. Validate:
   ```bash
   timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing -k <target>
   uv run ruff check --fix <path>
   ```
5. Report key renames, structural tweaks, and commands executed.

If you discover logic bugs, switch to `bugFixRapidResponse` or draft a plan before touching behavior.
