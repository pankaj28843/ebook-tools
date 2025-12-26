---
name: coverageHandoff
description: Continue a coverage push on ebook-tools, updating the shared plan file.
argument-hint: planPath=".github/ai-agent-plans/coverage.md" target="tests/unit/"
---

## TechDocs Research
Mandatory sequence before editing:
1. `mcp_techdocs_list_tenants()`
2. `mcp_techdocs_describe_tenant` for the tenant you expect to cite (typically `pytest` or `python`).
3. `mcp_techdocs_root_search` for the exact topic (fixtures, TemporaryDirectory, etc.).
4. `mcp_techdocs_root_fetch` the most relevant result and log takeaways in the plan.

## Workflow
1. **Load the plan** – Read the referenced markdown plan entirely. Note the latest iteration, coverage numbers, and open checkboxes.
2. **Select the next slice** – Choose the path/test listed as next priority. Update the plan with your intent before coding.
3. **Implement tests** – Add cases in `tests/unit/` targeting untested helpers. Keep assertions behavioral and deterministic.
4. **Validation loop**
   ```bash
   timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing -k <focus>
   timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing
   ```
5. **Plan update** – Record what you covered, commands run, coverage deltas, and remaining tasks. Mention TechDocs references used.

## Output Expectations
- Summary referencing the plan file + section you updated.
- Status of commands (pass/fail) and any follow-up required.
- Next steps for the following agent.
