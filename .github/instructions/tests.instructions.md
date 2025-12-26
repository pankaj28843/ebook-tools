---
applyTo:
  - "tests/**"
---

# Test Instructions (ebook-tools)

## General Rules
- Every change must preserve **100% coverage** for `src/ebook_tools`.
- All tests belong under `tests/unit/`; integration behavior is expressed through CLI smoke runs, not slow suites.
- Use `@pytest.mark.unit` for every test function and keep them deterministic (no randomness, timestamps, or filesystem leakage).
- Prefer behavior-focused assertions (output Markdown, metadata, exceptions) over implementation details or mock call counts.
- Keep docstrings out of tests—descriptive function names are enough.

## Fixtures & Data
- Reuse `tests/data/` artifacts (sample EPUB/PDF/nav files). Clone when mutating; never modify the fixtures in-place.
- Use `tmp_path`/`tmp_path_factory` for filesystem writes; clean up temporary directories explicitly when CLIs create nested output.
- Favor helper factories inside tests when multiple cases share arrangements (e.g., `make_epub(pathlib.Path, spine)`), but keep them local to the test module to avoid premature abstractions.

## Designing Cases
- Cover **happy path, edge path, and failure path** for each helper or CLI option you touch.
- Validate Markdown output via string comparisons or snapshot helpers that normalize whitespace.
- When asserting exceptions, check the message so regressions are obvious.
- Prefer parametrized loops in the body of a single test over `pytest.mark.parametrize` to keep stacks smaller.

## CLI Testing Guidance
- Exercise CLI entrypoints through the public scripts (e.g., `uv run convert-docs ...`) only during smoke tests. Unit tests should call the underlying helper (e.g., `Converter.convert_epub(...)`).
- Use `argparse.Namespace` objects or dedicated helper builders when you need to pass structured CLI options into lower layers.

## Commands
```bash
# Fast focused checks
timeout 60 uv run pytest tests/unit/test_epub_converter.py -k headings
timeout 60 uv run pytest tests/unit/test_toc_checker.py -k invalid

# Full coverage run
timeout 60 uv run pytest --maxfail=1 --disable-warnings --cov=src/ebook_tools --cov-report=term-missing
```

## Anti-Patterns
- Mocking internal helpers instead of the true boundary (filesystem, third-party libraries).
- Reading/writing outside tmp paths or `tests/data` copies.
- Allowing flaky waits/sleeps; if ordering matters, refactor the code rather than the test.
- Skipping coverage "temporarily"—tests and docs must land with the code.
