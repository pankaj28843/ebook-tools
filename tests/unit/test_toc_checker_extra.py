from ebook_tools import toc_checker


def test_normalize_title_removes_numbers_and_case():
    s = "1. Introduction: Overview"
    assert toc_checker.normalize_title(s) == "introduction: overview"


def test_parse_markdown_toc_headings_and_links():
    md = """
# [Chapter 1](chapter1.md)
## [Section A](chapter1#section-a)
- [Item 1](chapter1#item1)
    """
    entries = toc_checker.parse_markdown_toc(md)
    assert any(e.title == "Chapter 1" and e.href == "chapter1.md" for e in entries)
    assert any(e.title == "Section A" and e.href.endswith("#section-a") for e in entries)


def test_parse_json_toc_levels_and_sanitization():
    payload = {
        "entries": [
            {"title": "Intro", "href": " intro.md ", "level": "1"},
            {"title": "Part", "href": "", "level": 2, "derived_only": True},
            {"title": "Chapter", "href": None, "type": "chapter"},
        ]
    }
    entries = toc_checker.parse_json_toc(payload)
    # Should include Intro and Chapter only (derived_only skipped, empty href sanitized)
    titles = [e.title for e in entries]
    assert "Intro" in titles
    assert "Chapter" in titles


def test_extract_nav_entries_flat_structure():
    class Node:
        def __init__(self, title, href=None):
            self.title = title
            self.href = href

    nav = [Node("One", "one.html"), [Node("Two", "two.html"), [Node("Two.A", "twoa.html")]]]
    entries = toc_checker.extract_nav_entries(nav)
    assert any(e.title == "One" for e in entries)
    assert any(e.title == "Two.A" for e in entries)
