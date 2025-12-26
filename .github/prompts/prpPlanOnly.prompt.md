---
name: prpPlanOnly
description: Produce a PRP plan (no code changes) for an ebook-tools initiative.
argument-hint: brief="support footnotes" scope="epub converter + CLI"
---

## TechDocs Research
- Always run `mcp_techdocs_list_tenants()`.
- `mcp_techdocs_describe_tenant` for each tenant you’ll cite (`github-copilot`, `python`, `clean-code-book`, etc.).
- `mcp_techdocs_root_search` → `root_fetch` to capture references; cite them in the plan.

## Mission
- Draft/update a PRP per `.github/instructions/PRP-README.md`.
- Stay in planning mode: no edits to `src/`, `tests/`, or docs.

## Required Sections
1. **Goal / Why / Success** – Tie to CLI behavior (`convert-docs`, `check-epub-toc`) and measurable coverage/doc updates.
2. **Current State** – Reference concrete files/fixtures (e.g., `src/ebook_tools/epub_converter.py`, `tests/unit/test_epub_converter_structured_sections.py`). Include TechDocs citations.
3. **Implementation Blueprint** – Phase the work (parsing, transforms, CLI wiring, docs/tests) with file-level detail.
4. **Context & Anti-Patterns** – Note deterministic output, ASCII-only rules, avoidance of shared state, etc.
5. **Validation Loop** – List the exact commands (ruff, pytest w/ coverage, CLI smoke tests) per phase.
6. **Open Questions & Risks** – Document missing fixtures, dependency concerns, or required clarifications.

## Output
- Save the plan at `.github/ai-agent-plans/YYYY-MM-DD-<slug>-plan.md`.
- Reply with key highlights, TechDocs references, and blockers. Stop before writing code.
