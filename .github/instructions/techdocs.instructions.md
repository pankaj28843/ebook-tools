# TechDocs MCP Instructions (ebook-tools)

> TechDocs provides instant access to authoritative documentation for Python, clean code, Copilot customization, and other references we lean on while evolving the ebook conversion toolchain.

## Quick Reference

| Tool | When to Use | Example |
|------|-------------|---------|
| `mcp_techdocs_list_tenants` | Discover available sources and confirm a tenant exists | Kick off any research session |
| `mcp_techdocs_describe_tenant` | Pull `test_queries`, `url_prefixes`, and scope | `mcp_techdocs_describe_tenant(codename="github-copilot")` |
| `mcp_techdocs_root_search` | Find relevant passages | `query="TemporaryDirectory pathlib"` on `python` |
| `mcp_techdocs_root_fetch` | Read the full document that a search result references | After search returns a high-score URI |
| `mcp_techdocs_root_browse` | Explore filesystem tenants like books | `tenant_codename="clean-code-book"` |

## Priority Tenants for ebook-tools

| Codename | Why it matters | Sample Queries |
|----------|----------------|----------------|
| `github-copilot` | Official Copilot instructions; keep this file in sync with supported features. `describe_tenant` reveals prefix `https://docs.github.com/en/copilot` plus queries like "Who can use this feature?" |
| `python` | Pathlib, tempfile, text processing patterns used across converters. | `TemporaryDirectory`, `pathlib Path write_text` |
| `pytest` | Fixture design, timeout usage, async helpers for our 100% coverage rule. | `tmp_path fixture`, `parametrize` |
| `clean-code-book` | Guidance for simplifying helpers and naming conversions. | `meaningful names`, `functions` |
| `ai-engineering` | Prompting + evaluation ideas when we extend debug tooling. | `context windows`, `guardrails` |

## Default Research Flow
1. **List + describe** – Run `mcp_techdocs_list_tenants()` and then `mcp_techdocs_describe_tenant(...)` for the top candidate (often `github-copilot` or `python`). Capture notable `test_queries`, `url_prefixes`, and whether `supports_browse` is available.
2. **Search narrowly** – Use precise phrases instead of broad terms. Example: `mcp_techdocs_root_search(tenant_codename="python", query="TemporaryDirectory cleanup")`.
3. **Fetch once confident** – Only call `root_fetch` for results with meaningful scores or when the snippet directly answers your question. Paste relevant excerpts (with tenant + URI) into PRP plan notes or inline comments if they teach a unique pattern.
4. **Record learnings** – Update plan files or docs with the tenant name + URL so future agents can retrace the reasoning.

## Best Practices
- Always cite the tenant when a pattern comes from TechDocs (e.g., `github-copilot – Managing requests for GitHub Copilot Business`).
- Re-run `mcp_techdocs_describe_tenant` when you notice stale guidance; tenants evolve and may introduce fresh `test_queries`.
- Use filesystem tenants' `root_browse` when hunting through long-form books (clean-code-book, clean-architecture-book) for design direction.
- Prefer TechDocs evidence over guesswork when adding CLI flags, adjusting output formats, or tuning metadata requirements.

## Troubleshooting
| Issue | Fix |
|-------|-----|
| Searches return zero hits | Double-check `describe_tenant` for suggested `test_queries`, or widen the query slightly. |
| Need implementation examples | Run `root_fetch` for the highest-scoring URI and copy the relevant snippet into your plan/notes. |
| Unsure which tenant fits | Start with `list_tenants` and filter by topic keywords (python, epub, copilot, etc.). |
| Want to confirm coverage of this instruction set | Use `mcp_techdocs_describe_tenant(codename="github-copilot")` and ensure the test queries still match what we reference here. |

Stay disciplined: research first, then code. Document what you found so the next agent can stand on your shoulders.
