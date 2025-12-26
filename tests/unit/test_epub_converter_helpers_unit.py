"""Unit tests for EpubConverter helper methods."""

from __future__ import annotations

import json
from pathlib import Path

from bs4 import BeautifulSoup
import pytest

from ebook_tools.epub_converter import EpubConverter
from ebook_tools.epub_models import EpubChapter, EpubSection
from ebook_tools.toc_checker import TocEntry


@pytest.fixture
def converter() -> EpubConverter:
    return EpubConverter()


@pytest.mark.unit
class TestEpubConverterHelpers:
    """Validates filename cleaning, slug creation, and numbering logic."""

    def test_clean_filename_strips_special_characters(self, converter: EpubConverter) -> None:
        cleaned = converter._clean_filename(' Intro: "Setup"? <Guide> ')
        assert cleaned == "intro-setup-guide"

    def test_slugify_uses_fallback_when_text_invalid(self, converter: EpubConverter) -> None:
        slug = converter._slugify("???", fallback="section")
        assert slug == "section"
        assert converter._slugify(None, fallback="missing") == "missing"

    def test_apply_chapter_numbering_updates_directories(self, converter: EpubConverter, tmp_path: Path) -> None:
        chapter_dir = tmp_path / "chapter-temp-0001"
        chapter_dir.mkdir()
        section_path = chapter_dir / "section-temp-0001.md"
        section_path.write_text("intro", encoding="utf-8")
        section = EpubSection(
            title="Introduction",
            filename=section_path.name,
            file_path=str(section_path),
            word_count=10,
            character_count=50,
            slug_hint="Introduction",
            source_fragment=None,
        )
        chapter = EpubChapter(
            title="Getting Started",
            folder_name=chapter_dir.name,
            folder_path=str(chapter_dir),
            sections=[section],
            source_file="ch01.xhtml",
        )

        chapter2_dir = tmp_path / "chapter-temp-0002"
        chapter2_dir.mkdir()
        section2_path = chapter2_dir / "section-temp-0001.md"
        section2_path.write_text("content", encoding="utf-8")
        section2 = EpubSection(
            title="???",
            filename=section2_path.name,
            file_path=str(section2_path),
            word_count=8,
            character_count=40,
            slug_hint=None,
            source_fragment=None,
        )
        chapter2 = EpubChapter(
            title="Advanced",
            folder_name=chapter2_dir.name,
            folder_path=str(chapter2_dir),
            sections=[section2],
            source_file="ch02.xhtml",
        )

        converter._apply_chapter_numbering([chapter, chapter2])

        first_dir = Path(chapter.folder_path)
        second_dir = Path(chapter2.folder_path)
        assert first_dir.name == "getting-started"
        assert second_dir.name == "advanced"

        first_section_path = Path(chapter.sections[0].file_path)
        second_section_path = Path(chapter2.sections[0].file_path)
        assert first_section_path.exists()
        assert first_section_path.name.startswith("1.1-introduction")
        assert second_section_path.exists()
        assert second_section_path.name.startswith("2.1-section")

    def test_determine_padding_and_format_number(self, converter: EpubConverter) -> None:
        assert converter._determine_padding(9) == 1
        assert converter._determine_padding(12) == 2
        assert converter._format_number(3, 1) == "3"
        assert converter._format_number(3, 2) == "03"

    def test_fix_image_paths_updates_known_sources(self, converter: EpubConverter) -> None:
        converter._images_extracted = {"images/raw.png": "images/extracted/raw.png"}
        html = '<p><img src="images/raw.png" alt="example"/></p>'

        updated = converter._fix_image_paths(html)

        assert "images/extracted/raw.png" in updated
        assert "images/raw.png" not in updated

    @pytest.mark.asyncio
    async def test_collect_sections_handles_intro_and_multiple_sections(
        self,
        converter: EpubConverter,
        tmp_path: Path,
    ) -> None:
        soup = BeautifulSoup(
            """
            <h1>Chapter Zero</h1>
            <p>Introductory paragraph.</p>
            <h2 id="setup">Getting Started</h2>
            <p>Alpha content.</p>
            <h2>Deep Dive</h2>
            <p>Beta content.</p>
            """,
            "html.parser",
        )

        sections = await converter._collect_sections(soup, "Chapter Zero", soup.find("h1"), tmp_path)

        titles = [section.title for section in sections]
        assert titles == ["Introduction", "Getting Started", "Deep Dive"]
        assert all(Path(section.file_path).exists() for section in sections)
        assert sections[1].source_fragment == "setup"

    def test_extract_images_populates_map(self, converter: EpubConverter, tmp_path: Path) -> None:
        class DummyItem:
            def __init__(self, name: str, content: bytes) -> None:
                self._name = name
                self._content = content

            def get_content(self) -> bytes:
                return self._content

            def get_name(self) -> str:
                return self._name

        class DummyBook:
            def __init__(self, items):
                self._items = items

            def get_items_of_type(self, _item_type):
                return self._items

        images = [DummyItem("images/logo.png", b"pngdata")]
        book = DummyBook(images)

        converter._extract_images(book, tmp_path)

        image_path = tmp_path / "images" / "logo.png"
        assert image_path.exists()
        assert converter._images_extracted["images/logo.png"] == "images/logo.png"

    def test_extract_fragment_id_handles_list_attributes(self, converter: EpubConverter) -> None:
        soup = BeautifulSoup("<h2></h2>", "html.parser")
        tag = soup.h2
        tag.attrs["id"] = ["first", "second"]

        assert converter._extract_fragment_id(tag) == "first"

    @pytest.mark.asyncio
    async def test_collect_sections_without_headings_returns_full_chapter(
        self,
        converter: EpubConverter,
        tmp_path: Path,
    ) -> None:
        soup = BeautifulSoup("<html><body><p>Only text</p></body></html>", "html.parser")
        chapter_dir = tmp_path / "chapter"
        chapter_dir.mkdir()

        sections = await converter._collect_sections(soup, "Chapter Intro", None, chapter_dir)

        assert len(sections) == 1
        section = sections[0]
        assert section.title == "Chapter Intro"
        assert Path(section.file_path).exists()


@pytest.mark.unit
class TestEpubConverterTocGeneration:
    """Validates table-of-contents helpers and nav alignment."""

    def test_generate_toc_writes_markdown_and_json(self, converter: EpubConverter, tmp_path: Path) -> None:
        chapters = [
            EpubChapter(
                title="Chapter One",
                folder_name="chapter-one",
                folder_path=str(tmp_path / "chapter-one"),
                sections=[
                    EpubSection(
                        title="Intro",
                        filename="1.1-intro.md",
                        file_path=str(tmp_path / "chapter-one" / "1.1-intro.md"),
                        word_count=100,
                        character_count=500,
                        slug_hint="intro",
                        source_fragment="intro",
                    )
                ],
                source_file="ch01.xhtml",
            ),
            EpubChapter(
                title="Chapter Two",
                folder_name="chapter-two",
                folder_path=str(tmp_path / "chapter-two"),
                sections=[],
                source_file="ch02.xhtml",
            ),
        ]

        toc_path, json_path = converter._generate_toc(
            chapters=chapters,
            output_dir=tmp_path,
            book_title="Sample Book",
            nav_entries=None,
        )

        rendered = toc_path.read_text(encoding="utf-8")
        assert "# Sample Book" in rendered
        assert "- **Chapters:** 2" in rendered

        parsed = json.loads(json_path.read_text(encoding="utf-8"))
        assert parsed["book_title"] == "Sample Book"
        assert parsed["chapters"] == 2
        assert parsed["entries"][0]["href"].startswith("chapter-one")

    def test_build_json_entries_aligns_nav_entries(self, converter: EpubConverter) -> None:
        chapter = EpubChapter(
            title="Guide",
            folder_name="guide",
            folder_path="/tmp/guide",
            sections=[
                EpubSection(
                    title="Deep Dive",
                    filename="1.1-deep-dive.md",
                    file_path="/tmp/guide/1.1-deep-dive.md",
                    word_count=120,
                    character_count=600,
                    slug_hint="deep-dive",
                    source_fragment="deep-dive",
                )
            ],
            source_file="guide.xhtml",
        )
        nav_entries = [
            TocEntry(title="Guide", href="guide.xhtml", level=1, source="navmap"),
            TocEntry(title="Deep Dive", href="guide.xhtml#deep-dive", level=2, source="navmap"),
        ]

        entries = converter._build_json_entries([chapter], nav_entries)

        assert entries[0]["href"] == "guide/"
        assert entries[1]["href"] == "guide/1.1-deep-dive.md"
        assert entries[0]["title"] == "Guide"
        assert entries[1]["title"] == "Deep Dive"


@pytest.mark.unit
class TestEpubConverterNavParsing:
    """Validate navMap extraction helpers."""

    def test_load_nav_entries_handles_nested_sections(self, converter: EpubConverter) -> None:
        class NavItem:
            def __init__(self, title: str, href: str | None = None):
                self.title = title
                self.href = href

        class FakeBook:
            def get_toc(self):
                return [
                    (
                        NavItem("Chapter One", "Ch01.xhtml"),
                        [
                            NavItem("Section 1.1", "Ch01.xhtml#sec1"),
                            (
                                NavItem("Nested Group", None),
                                [NavItem("Section 1.2", "Ch01.xhtml#sec2")],
                            ),
                        ],
                    ),
                    NavItem("Chapter Two"),
                ]

        entries = converter._load_nav_entries(FakeBook())

        titles = [entry.title for entry in entries]
        assert titles == ["Chapter One", "Section 1.1", "Nested Group", "Section 1.2", "Chapter Two"]
        assert entries[0].level == 1
        assert entries[1].level == 2
        assert entries[2].href is None

    def test_load_nav_entries_uses_toc_fallback_on_error(self, converter: EpubConverter) -> None:
        class FakeNavItem:
            def __init__(self, title: str, href: str):
                self.title = title
                self.href = href

        class FakeBook:
            def get_toc(self):
                raise RuntimeError("boom")

            @property
            def toc(self):
                return [FakeNavItem("Fallback Chapter", "fallback.xhtml")]

        entries = converter._load_nav_entries(FakeBook())

        assert len(entries) == 1
        assert entries[0].title == "Fallback Chapter"
        assert entries[0].href == "fallback.xhtml"

    def test_load_nav_entries_returns_empty_when_missing(self, converter: EpubConverter) -> None:
        class FakeBook:
            pass

        entries = converter._load_nav_entries(FakeBook())

        assert entries == []

    def test_load_nav_entries_handles_ncx_sequence(self, converter: EpubConverter) -> None:
        class NavItem:
            def __init__(self, title: str, href: str | None = None):
                self.title = title
                self.href = href

        class FakeBook:
            def get_toc(self):
                return (
                    (
                        NavItem("Chapter One", "chapter.xhtml"),
                        [
                            NavItem("Section A", "chapter.xhtml#section-a"),
                            (
                                NavItem("Section B", "chapter.xhtml#section-b"),
                                [NavItem("Subsection B1", "chapter.xhtml#section-b1")],
                            ),
                        ],
                    ),
                )

        entries = converter._load_nav_entries(FakeBook())

        titles = [entry.title for entry in entries]
        assert titles == ["Chapter One", "Section A", "Section B", "Subsection B1"]

    def test_load_nav_entries_returns_empty_on_extraction_error(self, converter: EpubConverter, monkeypatch) -> None:
        class FakeBook:
            def get_toc(self):
                return []

        def raise_error(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "ebook_tools.epub_converter.toc_checker.extract_nav_entries",
            raise_error,
        )

        assert converter._load_nav_entries(FakeBook()) == []


class TestEpubConverterNavigationAlignment:
    def test_build_json_entries_derives_missing_entries(self, converter: EpubConverter) -> None:
        section = EpubSection(
            title="Intro",
            filename="1.1-intro.md",
            file_path="/tmp/1.1-intro.md",
            word_count=10,
            character_count=40,
            slug_hint="intro",
            source_fragment="intro",
        )
        chapter_one = EpubChapter(
            title="Guide",
            folder_name="1-guide",
            folder_path="/tmp/1-guide",
            sections=[section],
            source_file="guide.xhtml",
        )
        chapter_two = EpubChapter(
            title="Advanced",
            folder_name="2-advanced",
            folder_path="/tmp/2-advanced",
            sections=[
                EpubSection(
                    title="Deep Dive",
                    filename="2.1-deep-dive.md",
                    file_path="/tmp/2-advanced/2.1-deep-dive.md",
                    word_count=15,
                    character_count=80,
                    slug_hint="deep-dive",
                    source_fragment="deep-dive",
                )
            ],
            source_file="advanced.xhtml",
        )

        nav_entries = [
            TocEntry(title="Guide", href="guide.xhtml", level=1, source="navmap"),
        ]

        entries = converter._build_json_entries([chapter_one, chapter_two], nav_entries)

        derived = [entry for entry in entries if entry.get("derived_only")]
        assert any(e["href"].endswith("2-advanced/") for e in derived)
        assert any(e.get("derived_only") for e in derived)
