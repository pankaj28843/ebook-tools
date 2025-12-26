"""Unit tests for the TOC comparison utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import pytest

from ebook_tools import toc_checker


class _FakeNavNode:
    def __init__(self, title: str, href: str | None = None) -> None:
        self.title = title
        self.href = href


@pytest.mark.unit
class TestLoadNavEntries:
    """Tests for ``load_nav_entries``."""

    def test_falls_back_to_toc_attribute(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Older ebooklib versions only expose ``book.toc``; ensure we handle that."""

        epub_path = tmp_path / "book.epub"
        epub_path.write_bytes(b"not-used")

        class _FakeBook:
            toc: ClassVar[list[_FakeNavNode]] = [_FakeNavNode("Chapter 1", "chapter-1.xhtml")]

        def _fake_read_epub(path: str) -> Any:
            assert path == str(epub_path)
            return _FakeBook()

        import ebooklib.epub as epub_module  # Imported lazily by the production code but needed for monkeypatching

        monkeypatch.setattr(epub_module, "read_epub", _fake_read_epub)

        entries = toc_checker.load_nav_entries(epub_path)

        assert len(entries) == 1
        assert entries[0].title == "Chapter 1"
        assert entries[0].href == "chapter-1.xhtml"

    def test_raises_when_toc_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """Fail fast when neither ``get_toc`` nor ``toc`` are available."""

        epub_path = tmp_path / "book.epub"
        epub_path.write_bytes(b"not-used")

        class _BookWithoutToc:
            pass

        def _fake_read_epub(path: str) -> Any:
            assert path == str(epub_path)
            return _BookWithoutToc()

        import ebooklib.epub as epub_module

        monkeypatch.setattr(epub_module, "read_epub", _fake_read_epub)

        with pytest.raises(AttributeError, match="does not expose a TOC"):
            toc_checker.load_nav_entries(epub_path)


@pytest.mark.unit
class TestJsonTocParsing:
    def test_parse_json_toc_filters_and_normalizes_entries(self) -> None:
        payload = {
            "entries": [
                {"title": "  Intro  ", "href": " intro.html ", "level": "1"},
                {"title": "Chapter 2", "depth": 5},  # filtered by max_depth
                "not-a-dict",
            ]
        }

        entries = toc_checker.parse_json_toc(payload, max_depth=2)

        assert len(entries) == 1
        assert entries[0].title == "Intro"
        assert entries[0].href == "intro.html"
        assert entries[0].source == "json"

    def test_load_json_toc_reads_file(self, tmp_path: Path) -> None:
        toc_path = tmp_path / "toc.json"
        toc_path.write_text(json.dumps({"entries": [{"title": "Intro", "level": 1}]}), encoding="utf-8")

        entries = toc_checker.load_json_toc(toc_path, max_depth=1)

        assert len(entries) == 1
        assert entries[0].title == "Intro"


@pytest.mark.unit
class TestCompareTocEntries:
    def test_reports_missing_in_reference(self) -> None:
        nav_entries = [
            toc_checker.TocEntry("1. Intro", "intro.html", 1, "navmap"),
            toc_checker.TocEntry("2. Getting Started", "getting-started.html", 1, "navmap"),
            toc_checker.TocEntry("Appendix", "appendix.html", 1, "navmap"),
        ]

        reference_entries = [
            toc_checker.TocEntry("Intro", "intro.html", 1, "markdown"),
            toc_checker.TocEntry("Advanced Topics", "advanced.html", 1, "markdown"),
        ]

        result = toc_checker.compare_toc_entries(nav_entries, reference_entries)

        assert not result.is_match
        assert [entry.title for entry in result.missing_in_reference] == ["Appendix"]
        assert not result.missing_in_navmap
        assert [m.reference_entry.title for m in result.order_mismatches] == ["Advanced Topics"]

    def test_reports_missing_in_navmap(self) -> None:
        nav_entries = [toc_checker.TocEntry("Intro", "intro.html", 1, "navmap")]
        reference_entries = [
            toc_checker.TocEntry("Intro", "intro.html", 1, "markdown"),
            toc_checker.TocEntry("Glossary", "glossary.html", 1, "markdown"),
        ]

        result = toc_checker.compare_toc_entries(nav_entries, reference_entries)

        assert not result.is_match
        assert [entry.title for entry in result.missing_in_navmap] == ["Glossary"]
