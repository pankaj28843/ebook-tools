---
name: testHardening
description: Improve or add tests for ebook-tools without touching production code.
argument-hint: target="epub section splitting" focus="unit"
---

## TechDocs Research
- Run `mcp_techdocs_list_tenants()` then `mcp_techdocs_describe_tenant` for `pytest` (fixtures, parametrization) and any other tenant informing the scenario.
- `mcp_techdocs_root_search`/`root_fetch` relevant snippets; cite them in your summary.

## Policies
- Follow `.github/instructions/tests.instructions.md` (100% coverage, deterministic tests, no docstrings).
- Exercise converters through pure helpers; reserve CLI execution for smoke steps in the final validation.

## Steps
1. **Gap analysis** – Identify missing behaviors (edge metadata, malformed nav, PDF page ordering) using existing tests + fixtures.
2. **Design** – Outline inputs/expected outputs; duplicate fixtures via `tmp_path` when modifying files.
3. **Implement** – Add tests under `tests/unit/` (no production changes). Keep assertions on observable behavior.
4. **Validation**
   ```bash
   timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing -k <target>
   timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing
   ```
5. **Report** – Mention new cases, commands run, and remaining blind spots.

Keep output concise; highlight coverage gains and next areas to harden.
