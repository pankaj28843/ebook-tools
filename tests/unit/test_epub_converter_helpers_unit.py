"""Unit tests for EpubConverter helper methods."""

from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup
import pytest

from ebook_tools import toc_checker
from ebook_tools import epub_converter as epub_mod
from ebook_tools.epub_converter import EpubConverter, EpubConverterConfig
from ebook_tools.epub_models import EpubChapter, EpubSection


@pytest.fixture
def converter() -> EpubConverter:
    return EpubConverter(EpubConverterConfig(max_output_depth=1))


@pytest.mark.unit
class TestEpubConverterLowLevel:
    def test_normalize_path_and_fragment_helpers(self) -> None:
        assert epub_mod._normalize_path_value(None) is None
        assert epub_mod._normalize_path_value(".\\OPS\\ch01.xhtml") == "ops/ch01.xhtml"
        assert epub_mod._fragment_from_href_value("chapter.xhtml#sec1") == "sec1"
        assert epub_mod._fragment_from_href_value("chapter.xhtml") is None
        assert epub_mod._path_from_href_value("OPS/ch1.xhtml#sec1") == "ops/ch1.xhtml"

    def test_prepare_epub_for_conversion_builds_aliases(self, tmp_path: Path) -> None:
        converter = EpubConverter()
        epub_path = tmp_path / "alias.epub"
        container_xml = (
            "<?xml version='1.0'?>"
            "<container xmlns='urn:oasis:names:tc:opendocument:xmlns:container' version='1.0'>"
            "<rootfiles><rootfile full-path='OPS/content.opf' media-type='application/oebps-package+xml'/></rootfiles>"
            "</container>"
        )
        opf_xml = (
            "<package xmlns='http://www.idpf.org/2007/opf' version='3.0'>"
            "<manifest><item id='sec1' href='text/section.xhtml' media-type='application/xhtml+xml'/></manifest>"
            "</package>"
        )
        (tmp_path / "OPS/Text").mkdir(parents=True)
        (tmp_path / "OPS/Text/Section.xhtml").write_text("<html></html>", encoding="utf-8")
        (tmp_path / "META-INF").mkdir(exist_ok=True)
        (tmp_path / "META-INF/container.xml").write_text(container_xml, encoding="utf-8")
        (tmp_path / "OPS/content.opf").write_text(opf_xml, encoding="utf-8")

        from zipfile import ZipFile

        with ZipFile(epub_path, "w") as zf:
            zf.write(tmp_path / "META-INF/container.xml", arcname="META-INF/container.xml")
            zf.write(tmp_path / "OPS/content.opf", arcname="OPS/content.opf")
            zf.write(tmp_path / "OPS/Text/Section.xhtml", arcname="OPS/Text/Section.xhtml")

        normalized, temp = converter._prepare_epub_for_conversion(epub_path)
        assert normalized is not None
        assert normalized != epub_path
        assert temp is not None
        assert normalized.exists()
        normalized.unlink()


@pytest.mark.unit
class TestEpubConverterHelpers:
    """Validates filename cleaning, slug creation, and numbering logic."""

    def test_make_slug_strips_special_characters(self) -> None:
        from ebook_tools.converter_base import make_slug

        slug = make_slug(' Intro: "Setup"? <Guide> ')
        assert "intro" in slug
        assert "setup" in slug
        assert "guide" in slug

    def test_make_slug_uses_fallback_when_text_invalid(self) -> None:
        from ebook_tools.converter_base import make_slug

        assert make_slug(None, fallback="section") == "section"
        assert make_slug("", fallback="missing") == "missing"

    def test_flatten_sections_moves_files_to_output(self, converter: EpubConverter, tmp_path: Path) -> None:
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
            slug="temp",
            working_dir=str(chapter_dir),
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
            slug="temp",
            working_dir=str(chapter2_dir),
            sections=[section2],
            source_file="ch02.xhtml",
        )

        converter._flatten_sections([chapter, chapter2], tmp_path)

        first_chapter_path = Path(chapter.output_path)
        second_chapter_path = Path(chapter2.output_path)

        assert first_chapter_path.parent == tmp_path
        assert second_chapter_path.parent == tmp_path
        assert first_chapter_path.name == "1-getting-started.md"
        assert second_chapter_path.name == "2-advanced.md"
        first_content = first_chapter_path.read_text(encoding="utf-8")
        second_content = second_chapter_path.read_text(encoding="utf-8")
        assert "# Getting Started" in first_content
        assert "intro" in first_content
        assert "content" in second_content

        assert chapter.sections[0].file_path == str(first_chapter_path)
        assert chapter2.sections[0].file_path == str(second_chapter_path)

        assert not Path(chapter.working_dir).exists()
        assert not Path(chapter2.working_dir).exists()

    def test_structured_sections_create_chapter_directory(self, tmp_path: Path) -> None:
        config = EpubConverterConfig(max_output_depth=2)
        structured_converter = EpubConverter(config)

        chapter_dir = tmp_path / "chapter-temp-0001"
        chapter_dir.mkdir()
        section_path = chapter_dir / "section-temp-0001.md"
        section_path.write_text("intro", encoding="utf-8")
        section_two_path = chapter_dir / "section-temp-0002.md"
        section_two_path.write_text("content", encoding="utf-8")
        section = EpubSection(
            title="Introduction",
            filename=section_path.name,
            file_path=str(section_path),
            word_count=10,
            character_count=50,
            slug_hint="introduction",
            source_fragment=None,
        )
        section_two = EpubSection(
            title="Deep Dive",
            filename=section_two_path.name,
            file_path=str(section_two_path),
            word_count=12,
            character_count=60,
            slug_hint="deep-dive",
            source_fragment=None,
        )
        chapter = EpubChapter(
            title="Structured",
            slug="temp",
            working_dir=str(chapter_dir),
            sections=[section, section_two],
            source_file="ch01.xhtml",
        )

        existing_dir = tmp_path / "1-structured"
        existing_dir.mkdir()
        (existing_dir / "old.md").write_text("stale", encoding="utf-8")

        structured_converter._write_structured_sections([chapter], tmp_path)

        final_dir = Path(chapter.output_path)
        assert final_dir.is_dir()
        files = sorted(final_dir.glob("*.md"))
        assert [f.name for f in files] == ["1-introduction.md", "2-deep-dive.md"]
        assert Path(section.file_path) == files[0]
        assert Path(section_two.file_path) == files[1]

    def test_structured_sections_collapse_single_section(self, tmp_path: Path) -> None:
        config = EpubConverterConfig(max_output_depth=2)
        structured_converter = EpubConverter(config)

        chapter_dir = tmp_path / "chapter-temp-0001"
        chapter_dir.mkdir()
        section_path = chapter_dir / "section-temp-0001.md"
        section_path.write_text("only section", encoding="utf-8")
        section = EpubSection(
            title="Only",
            filename=section_path.name,
            file_path=str(section_path),
            word_count=5,
            character_count=20,
            slug_hint="only",
            source_fragment=None,
        )
        chapter = EpubChapter(
            title="Single",
            slug="temp",
            working_dir=str(chapter_dir),
            sections=[section],
            source_file="ch-single.xhtml",
        )

        structured_converter._write_structured_sections([chapter], tmp_path)

        final_path = Path(chapter.output_path)
        assert final_path.is_file()
        assert final_path.parent == tmp_path
        assert final_path.name == "1-single.md"
        assert Path(section.file_path) == final_path

    def test_determine_padding_and_format_number(self, converter: EpubConverter) -> None:
        assert converter._determine_padding(9) == 1
        assert converter._determine_padding(12) == 2
        assert converter._format_number(3, 1) == "3"
        assert converter._format_number(3, 2) == "03"

    def test_intro_candidates_prefers_body_children(self, converter: EpubConverter) -> None:
        soup = BeautifulSoup("<body><p>alpha</p></body>", "html.parser")
        nodes = list(converter._intro_candidates(soup, None))
        assert any(getattr(node, "name", None) == "p" for node in nodes)

    def test_intro_candidates_falls_back_to_root_children(self, converter: EpubConverter) -> None:
        soup = BeautifulSoup("<custom>beta</custom>", "html.parser")
        if soup.body is not None:
            soup.body.decompose()
        nodes = list(converter._intro_candidates(soup, None))
        assert nodes

    @pytest.mark.asyncio
    async def test_create_section_from_html_skips_blank_input(
        self,
        converter: EpubConverter,
        tmp_path: Path,
    ) -> None:
        chapter_dir = tmp_path / "chapter"
        chapter_dir.mkdir()
        result = await converter._create_section_from_html("   ", "Empty", "empty", chapter_dir, 1, level=2)
        assert result is None

    @pytest.mark.asyncio
    async def test_create_section_from_html_skips_blank_markdown(
        self,
        converter: EpubConverter,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        chapter_dir = tmp_path / "chapter"
        chapter_dir.mkdir()

        def fake_markdownify(*_args, **_kwargs):
            return "  "

        monkeypatch.setattr("ebook_tools.epub_converter.markdownify.markdownify", fake_markdownify)
        result = await converter._create_section_from_html("<p>content</p>", "Title", "title", chapter_dir, 1, level=3)
        assert result is None

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

    def test_apply_nav_titles_matches_href_and_titles(self, converter: EpubConverter, tmp_path: Path) -> None:
        chapter_dir = tmp_path / "chap"
        chapter_dir.mkdir()
        chapter = EpubChapter(
            title="Temp",
            slug="temp",
            working_dir=str(chapter_dir),
            sections=[],
            source_file="OPS/Ch01.xhtml",
        )
        chapter_two = EpubChapter(
            title="02 SECOND",
            slug="temp",
            working_dir=str(chapter_dir),
            sections=[],
            source_file="",
        )
        nav_entries = [
            toc_checker.TocEntry(title="Chapter One", href="OPS/ch01.xhtml", level=1, source="nav"),
            toc_checker.TocEntry(title="02. Second", href=None, level=1, source="nav"),
        ]

        converter._apply_nav_titles([chapter, chapter_two], nav_entries)

        assert chapter.title == "Chapter One"
        assert chapter_two.title == "02. Second"

    def test_move_section_file_handles_missing_source(self, converter: EpubConverter, tmp_path: Path) -> None:
        destination = tmp_path / "dest"
        destination.mkdir()
        section = EpubSection(
            title="Missing",
            filename="section-temp-0001.md",
            file_path=str(tmp_path / "ghost.md"),
            word_count=0,
            character_count=0,
            slug_hint="missing",
            source_fragment=None,
        )

        converter._move_section_file(section=section, destination_dir=destination, section_index=1, padding=1)

        assert not any(destination.iterdir())

    def test_move_section_file_replaces_existing(self, converter: EpubConverter, tmp_path: Path) -> None:
        destination = tmp_path / "dest"
        destination.mkdir()
        source_path = tmp_path / "section-temp-0001.md"
        source_path.write_text("First", encoding="utf-8")
        final_path = destination / "1-section.md"
        final_path.write_text("Old", encoding="utf-8")
        section = EpubSection(
            title="Section",
            filename=source_path.name,
            file_path=str(source_path),
            word_count=1,
            character_count=5,
            slug_hint="section",
            source_fragment=None,
        )

        converter._move_section_file(section=section, destination_dir=destination, section_index=1, padding=1)

        assert Path(section.file_path).read_text(encoding="utf-8") == "First"


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
