---
name: researchIdeation
description: Explore solution options (no code) for an ebook-tools question using TechDocs + repo intel.
argument-hint: topic="improve PDF chunking" focus="src/ebook_tools/pdf_converter.py"
---

## TechDocs Research (mandatory)
1. `mcp_techdocs_list_tenants()`
2. `mcp_techdocs_describe_tenant` for the most relevant sources (e.g., `python`, `github-copilot`, `clean-code-book`).
3. `mcp_techdocs_root_search` to find precise patterns.
4. `mcp_techdocs_root_fetch` at least one result and capture the URL + insight.

## Goals
- Clarify the problem, constraints, and candidate approaches before touching code.
- Cross-reference existing helpers/tests (use `file_search`, `grep_search`, `read_file`).
- End with actionable recommendations + next prompt selection (bug fix, feature slice, refactor, etc.).

## Workflow
1. Restate the question + business impact.
2. Gather repo evidence (cite files like `src/ebook_tools/pdf_converter.py#LXX`).
3. Summarize TechDocs findings with tenant + URL references.
4. Propose options (status quo, incremental tweak, new helper) with trade-offs.
5. Recommend the next step/prompt and list any prerequisites.

## Output
- Narrative covering problem → research → recommendation.
- Bullet list of evidence with links (repo paths + TechDocs URLs).
- Explicit open questions/risks. No code edits.
