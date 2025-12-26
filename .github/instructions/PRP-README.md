## PRP Guidance for ebook-tools

Product Requirement Prompts (PRPs) capture just enough context for an AI agent to land a vertical slice safely. Use this doc whenever a task spans multiple modules, introduces new flags, or touches both code and docs.

### When to Write a PRP
Create a plan file under `.github/ai-agent-plans/YYYY-MM-DD-<slug>-plan.md` when:
- Multiple files/modules must change (e.g., converter + CLI + docs/test updates).
- Behavior or CLI flags shift, requiring docs/tools updates.
- Work may hand off between agents or exceed a short session.
Skip PRPs for surgical edits confined to one file with obvious scope.

### Required Sections
1. **Goal / Why / Success** – Describe the target behavior, cite affected CLI(s), and state measurable success (e.g., "convert-docs handles footnotes" + tests passing + docs updated).
2. **Current State** – Summarize existing helpers/fixtures with file links such as `src/ebook_tools/epub_converter.py` or `tests/unit/test_epub_converter.py`. Capture constraints (deterministic output, ASCII-only, dependency choices).
3. **Implementation Blueprint** – Break the work into phases (parsing, transformation, CLI plumbing, docs/tests). Reference concrete files and functions.
4. **Context & Anti-Patterns** – List known pitfalls (e.g., mutating shared state, skipping coverage, nondeterministic filenames) and cite TechDocs evidence when relevant.
5. **Validation Loop** – Enumerate exact commands per phase (formatting, linting, coverage tests, CLI smoke examples like `uv run convert-docs --input ...`).
6. **Risks & Open Questions** – Record blockers, required sample files, or pending approvals.

### Authoring Tips
- Keep plans concise (aim for <1 screen). Use bullet lists or tables when they aid scanning.
- Link to supporting files using workspace-relative paths so future agents can jump directly to them.
- Capture TechDocs takeaways inline with tenant + URI (e.g., `github-copilot – https://docs.github.com/en/copilot/...`).
- Update the plan after each major step so a hand-off can continue without re-reading the repo.

### Validation Checklist Template
```bash
uv run ruff format .
uv run ruff check --fix .
timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing
uv run convert-docs --input tests/data/sample.epub --output /tmp/out
uv run check-epub-toc --nav tests/data/sample/nav.xhtml
```

A PRP isn’t bureaucracy—it’s the minimum packet of reasoning needed for GitHub Copilot to finish the job reliably.
