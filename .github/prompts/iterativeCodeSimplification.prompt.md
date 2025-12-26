---
name: iterativeCodeSimplification
description: Run successive passes to shrink/simplify converter logic without changing behavior.
argument-hint: file="src/ebook_tools/pdf_converter.py" verify="timeout 60 uv run pytest --maxfail=1 --disable-warnings -k pdf_converter"
---

## TechDocs Research
- `mcp_techdocs_list_tenants()` → `mcp_techdocs_describe_tenant("clean-code-book")` or `python` depending on the refactor goal.
- Use `mcp_techdocs_root_search`/`root_fetch` for the specific technique you plan to apply (e.g., guard clauses, comprehensions).

## Intent
- Reduce branching/LOC while preserving determinism.
- Improve error handling clarity (guard clauses > nested `if`s).
- Leave naming polish for `cleanCodeRefactor` unless necessary for comprehension.

## Working Style
1. Snapshot metrics (function length, number of branches) before each pass.
2. Make one small change per iteration (e.g., extract `_chunk_pages`, replace manual loops with comprehensions, share `build_output_path`).
3. After each pass run the verify command plus `uv run ruff check <file>`.
4. Log iteration results (what changed, LOC delta, commands run) in the final response.

## Validation Checklist
```bash
uv run ruff format <file>
uv run ruff check --fix <file>
<verify command>
timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing -k <area>
```

## Output
- Table or bullet list summarizing each pass and verification status.
- Remaining cleanup ideas (if any) for follow-up prompts.
