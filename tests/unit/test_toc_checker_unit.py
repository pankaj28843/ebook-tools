"""Focused tests for the TOC normalization helpers."""

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
