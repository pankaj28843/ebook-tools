---
name: bugFixRapidResponse
description: Apply a minimal, well-tested fix for a reported converter/CLI defect.
argument-hint: file="src/ebook_tools/epub_converter.py" repro="convert-docs --input ..." tests="tests/unit/test_epub_converter.py::test_case"
---

## TechDocs Research
- Run `mcp_techdocs_list_tenants()` then `mcp_techdocs_describe_tenant(codename="github-copilot")` or whichever tenant best explains the behavior (python for pathlib, clean-code-book for guard clauses).
- `mcp_techdocs_root_search`/`root_fetch` the precise topic before editing.

## Principles
- Reproduce the bug with the provided repro command or by extending an existing fixture.
- Keep diffs surgical: no opportunistic refactors beyond what unblocks the fix.
- Tests first: add or extend a failing unit test under `tests/unit/` that captures the regression.
- Follow `.github/copilot-instructions.md` (uv run for everything, 100% coverage, CLI smoke as needed).

## Flow
1. Confirm scope + repro (include logs or failing test output).
2. Add/adjust a unit test showing the failure.
3. Patch the smallest surface (prefer helper-level fixes over CLI plumbing).
4. Validate:
   ```bash
   timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing -k <test>
   uv run convert-docs --input ... --output ... --codename bugfix-smoke  # if the bug surfaced via CLI
   ```
5. Summarize root cause, fix, and commands executed.

No fix is complete without coverage + docs if user-facing behavior shifted.
