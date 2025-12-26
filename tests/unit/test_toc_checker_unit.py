"""Focused tests for the TOC normalization helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from ebook_tools import toc_checker


pytestmark = pytest.mark.unit


def test_parse_markdown_toc_respects_headings_and_list_links() -> None:
    markdown = (
        "# [Intro](intro.md)\n#### [Chapter](chap/ch1.md)\n- [Section](chap/ch1#section)\n  - [Deep](chap/ch1#deep)\n"
    )

    entries = toc_checker.parse_markdown_toc(markdown)

    titles = [entry.title for entry in entries]
    assert titles == ["Intro", "Chapter", "Section", "Deep"]
    assert entries[0].source == "markdown"
    assert entries[-1].level == 3  # list indent increases the level


def test_parse_markdown_toc_applies_max_depth_filter() -> None:
    markdown = "#### [Deep](deep.md)\n- [Sibling](sib.md)\n"
    entries = toc_checker.parse_markdown_toc(markdown, max_depth=1)
    assert entries == []


def test_normalize_title_trims_numbers_whitespace_and_case() -> None:
    raw = "  10.2. Chapter  Name \n"
    norm = toc_checker.normalize_title(raw)
    assert norm == "chapter name"


def test_compare_toc_entries_reports_match_when_titles_align() -> None:
    nav_entries = [
        toc_checker.TocEntry("1. Intro", "intro.html", 1, "navmap"),
        toc_checker.TocEntry("2. Features", "features.html", 1, "navmap"),
    ]
    ref_entries = [
        toc_checker.TocEntry("Intro", "intro.html", 1, "markdown"),
        toc_checker.TocEntry("Features", "features.html", 1, "markdown"),
    ]

    result = toc_checker.compare_toc_entries(nav_entries, ref_entries)
    assert result.is_match
    assert not result.missing_in_navmap
    assert not result.missing_in_reference
    assert not result.order_mismatches


def test_compare_toc_entries_detects_order_mismatches_and_missing_entries() -> None:
    nav_entries = [
        toc_checker.TocEntry("Intro", "intro.html", 1, "navmap"),
        toc_checker.TocEntry("Setup", "setup.html", 1, "navmap"),
    ]
    ref_entries = [
        toc_checker.TocEntry("Setup", "setup.html", 1, "markdown"),
        toc_checker.TocEntry("Intro", "intro.html", 1, "markdown"),
        toc_checker.TocEntry("Advanced", "advanced.html", 1, "markdown"),
    ]

    result = toc_checker.compare_toc_entries(nav_entries, ref_entries)
    assert not result.is_match
    assert result.missing_in_navmap and result.missing_in_navmap[0].title == "Setup"
    # Ensure order mismatch entries correspond to misaligned pairs
    assert result.order_mismatches
    mismatch = result.order_mismatches[0]
    assert mismatch.nav_entry.title == "Setup"
    assert mismatch.reference_entry.title == "Advanced"


def test_extract_nav_entries_respects_max_depth() -> None:
    class Node:
        def __init__(self, title: str, href: str | None = None) -> None:
            self.title = title
            self.href = href

    nav_map = [
        (Node("Chapter 1", "chapter-1.xhtml"), [Node("Section 1", "section-1.xhtml")]),
        Node("Appendix", "appendix.xhtml"),
    ]

    entries = toc_checker.extract_nav_entries(nav_map, max_depth=1)

    titles = [entry.title for entry in entries]
    assert "Chapter 1" in titles
    assert "Appendix" in titles
    assert "Section 1" not in titles


def test_load_markdown_toc_respects_max_depth(tmp_path: Path) -> None:
    readme = tmp_path / "README.md"
    readme.write_text(
        "# [Intro](intro.md)\n- [Section](intro#section)\n  - [Deep](intro#deep)\n",
        encoding="utf-8",
    )

    entries = toc_checker.load_markdown_toc(readme, max_depth=2)

    assert [entry.title for entry in entries] == ["Intro", "Section"]
