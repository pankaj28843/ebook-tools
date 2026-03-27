"""Unit tests for PDF to Markdown converter."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ebook_tools.cli import convert_docs
from ebook_tools.epub_models import EpubChapter, EpubSection
from ebook_tools.pdf_converter import PdfConverter, PdfConverterConfig, detect_pdf_type, _page_needs_ocr


class _FakeOcrPage:
    """A fake page that simulates a scanned page (no text, large image)."""

    def __init__(self, text: str = "", image_coverage: float = 0.9):
        self._text = text
        self._image_coverage = image_coverage

    def get_text(self, mode: str = "text"):
        return self._text

    def get_image_info(self):
        if self._image_coverage > 0:
            return [{"bbox": (0, 0, 612 * self._image_coverage, 792)}]
        return []

    @property
    def rect(self):
        import fitz
        return fitz.Rect(0, 0, 612, 792)


@pytest.mark.unit
class TestOcrDetection:
    def test_page_needs_ocr_with_text(self):
        page = _FakeOcrPage(text="A" * 100)
        assert _page_needs_ocr(page) is False

    def test_page_needs_ocr_scanned(self):
        page = _FakeOcrPage(text="", image_coverage=0.8)
        assert _page_needs_ocr(page) is True

    def test_page_needs_ocr_no_images(self):
        page = _FakeOcrPage(text="", image_coverage=0.0)
        assert _page_needs_ocr(page) is False

    def test_detect_pdf_type_text(self):
        class FakeDoc:
            page_count = 5
            def __getitem__(self, idx):
                return _FakeOcrPage(text="A" * 200)
        assert detect_pdf_type(FakeDoc()) == "text"

    def test_detect_pdf_type_scanned(self):
        class FakeDoc:
            page_count = 5
            def __getitem__(self, idx):
                return _FakeOcrPage(text="", image_coverage=0.9)
        assert detect_pdf_type(FakeDoc()) == "scanned"

    def test_detect_pdf_type_mixed(self):
        class FakeDoc:
            page_count = 4
            def __getitem__(self, idx):
                if idx < 1:
                    return _FakeOcrPage(text="", image_coverage=0.9)
                return _FakeOcrPage(text="A" * 200)
        assert detect_pdf_type(FakeDoc()) == "mixed"

    def test_detect_pdf_type_empty(self):
        class FakeDoc:
            page_count = 0
        assert detect_pdf_type(FakeDoc()) == "text"

    def test_ocr_config_language(self):
        config = PdfConverterConfig(ocr_language="deu+eng", ocr_dpi=400)
        assert config.ocr_language == "deu+eng"
        assert config.ocr_dpi == 400


class _FakePage:
    def __init__(self, has_images: bool):
        self._has_images = has_images

    def get_images(self):
        return [("img",)] if self._has_images else []


class _FakePdfDoc:
    def __init__(self, metadata: dict, toc: list[list], images_per_page: list[bool]):
        self.metadata = metadata
        self._toc = toc
        self._images = images_per_page
        self.page_count = len(images_per_page)
        self.closed = False

    def get_toc(self, simple: bool = False):
        return self._toc

    def __getitem__(self, idx: int):
        return _FakePage(self._images[idx])

    def close(self):
        self.closed = True


@pytest.mark.unit
@pytest.mark.asyncio
class TestPdfInspection:
    """Unit tests for the lightweight PDF inspection helper."""

    async def test_inspect_pdf_extracts_metadata(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        pdf_path = tmp_path / "book.pdf"
        pdf_path.write_bytes(b"data" * 1024)
        fake_doc = _FakePdfDoc(
            metadata={
                "title": "Sample PDF",
                "author": "Doc Writer",
                "subject": "Testing",
                "creator": "CI",
                "producer": "PyMuPDF",
                "keywords": "tests",
            },
            toc=[[1, "Chapter 1", 1]],
            images_per_page=[True, False, False],
        )
        fake_module = SimpleNamespace(open=lambda _: fake_doc)
        monkeypatch.setitem(sys.modules, "fitz", fake_module)

        info = await convert_docs.inspect_pdf(pdf_path)

        assert info is not None
        assert info.title == "Sample PDF"
        assert info.author == "Doc Writer"
        assert info.has_outline is True
        assert info.has_images is True
        assert info.pages_count == 3
        expected_size = round(pdf_path.stat().st_size / (1024 * 1024), 2)
        assert info.file_size_mb == expected_size
        assert fake_doc.closed is True

    async def test_inspect_pdf_handles_missing_metadata(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        pdf_path = tmp_path / "empty.pdf"
        pdf_path.write_bytes(b"0" * 10)
        fake_doc = _FakePdfDoc(metadata={}, toc=[], images_per_page=[False, False])
        fake_module = SimpleNamespace(open=lambda _: fake_doc)
        monkeypatch.setitem(sys.modules, "fitz", fake_module)

        info = await convert_docs.inspect_pdf(pdf_path)

        assert info is not None
        assert info.title == "Unknown Title"
        assert info.has_outline is False
        assert info.has_images is False


@pytest.mark.unit
class TestPdfConverterConfig:
    """Test PdfConverterConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = PdfConverterConfig()
        assert config.preserve_images is True
        assert config.clean_filenames is True
        assert config.use_pdf_outlines is True
        assert config.max_section_depth == 2
        assert config.code_language is None
        assert config.heading_style == "ATX"
        assert config.max_output_depth == 2
        assert config.ocr_language == "eng"
        assert config.ocr_dpi == 300

    def test_custom_config(self):
        """Test custom configuration values."""
        config = PdfConverterConfig(
            preserve_images=False,
            clean_filenames=False,
            use_pdf_outlines=False,
            max_section_depth=3,
            code_language="python",
            heading_style="setext",
            max_output_depth=1,
        )
        assert config.preserve_images is False
        assert config.clean_filenames is False
        assert config.use_pdf_outlines is False
        assert config.max_section_depth == 3
        assert config.code_language == "python"
        assert config.heading_style == "setext"
        assert config.max_output_depth == 1


@pytest.mark.unit
class TestPdfConverter:
    """Test PdfConverter class."""

    def test_init_default_config(self):
        """Test converter initialization with default config."""
        converter = PdfConverter()
        assert converter.config is not None
        assert isinstance(converter.config, PdfConverterConfig)

    def test_init_custom_config(self):
        """Test converter initialization with custom config."""
        config = PdfConverterConfig(preserve_images=False)
        converter = PdfConverter(config)
        assert converter.config == config
        assert converter.config.preserve_images is False

    def test_make_slug(self):
        """Test slug generation via make_slug."""
        from ebook_tools.converter_base import make_slug

        # Basic slugification
        assert make_slug("Chapter 1: Introduction") == "chapter-1-introduction"

        # Special characters
        assert make_slug("Chapter 1: Introduction!?") == "chapter-1-introduction"

        # Leading/trailing cleanup
        assert make_slug("- Introduction -") == "introduction"

        # Empty after cleaning
        assert make_slug("!!!", fallback="unnamed") == "unnamed"

        # Long name (truncate to max_length)
        long_name = "a " * 50
        result = make_slug(long_name, max_length=80)
        assert len(result) <= 80

    def test_extract_book_title_with_metadata(self):
        """Test book title extraction from PDF metadata."""
        converter = PdfConverter()

        # Mock document with title metadata
        mock_doc = Mock()
        mock_doc.metadata = {"title": "My Book Title"}

        result = converter._extract_book_title(mock_doc)
        assert result == "My Book Title"

    def test_extract_book_title_without_metadata(self):
        """Test book title fallback when no metadata."""
        converter = PdfConverter()

        # Mock document without title
        mock_doc = Mock()
        mock_doc.metadata = {}

        result = converter._extract_book_title(mock_doc)
        assert result == "Untitled PDF"

    def test_split_markdown_by_heading_simple(self):
        """Test splitting markdown by ## headings."""
        converter = PdfConverter()

        md_text = """# Chapter 1

Some intro text.

## Section 1

Section 1 content.

## Section 2

Section 2 content.
"""

        sections = converter._split_markdown_by_heading(md_text, "Chapter 1")
        assert len(sections) == 3

        titles = [title for title, _, _ in sections]
        levels = [level for _, _, level in sections]

        assert titles == ["Introduction", "Section 1", "Section 2"]
        assert levels == [2, 2, 2]
        assert "Some intro text" in sections[0][1]
        assert "Section 1 content" in sections[1][1]
        assert "Section 2 content" in sections[2][1]

    def test_split_markdown_by_heading_no_sections(self):
        """Test markdown without ## headings."""
        converter = PdfConverter()

        md_text = """# Chapter 1

All content in one section."""

        sections = converter._split_markdown_by_heading(md_text, "Chapter 1")
        assert len(sections) == 1
        title, content, level = sections[0]
        assert title == "Chapter 1"
        assert "All content in one section" in content
        assert level == 2

    def test_split_markdown_by_heading_no_intro(self):
        """Test markdown starting with ## heading."""
        converter = PdfConverter()

        md_text = """## Section 1

Section 1 content.

## Section 2

Section 2 content.
"""

        sections = converter._split_markdown_by_heading(md_text, "Chapter 1")
        assert len(sections) == 2
        titles = [title for title, _, _ in sections]
        assert titles == ["Section 1", "Section 2"]


class TestPdfConverterFlattening:
    """Covers the flattened output helpers."""

    def test_flatten_sections_orders_files(self, tmp_path: Path):
        converter = PdfConverter(PdfConverterConfig(max_output_depth=1))
        chapter_dir = tmp_path / "chapter-temp-0001"
        chapter_dir.mkdir()
        section_one = chapter_dir / "section-temp-0001.md"
        section_two = chapter_dir / "section-temp-0002.md"
        section_one.write_text("alpha", encoding="utf-8")
        section_two.write_text("beta", encoding="utf-8")

        chapter = EpubChapter(
            title="Intro Chapter",
            slug="temp",
            working_dir=str(chapter_dir),
            sections=[
                EpubSection(
                    title="Alpha Overview",
                    filename=section_one.name,
                    file_path=str(section_one),
                    word_count=10,
                    character_count=20,
                    slug_hint="alpha",
                ),
                EpubSection(
                    title="Second Section",
                    filename=section_two.name,
                    file_path=str(section_two),
                    word_count=5,
                    character_count=12,
                    slug_hint=None,
                ),
            ],
            source_file="book.pdf",
        )

        converter._flatten_sections([chapter], tmp_path)

        generated = sorted(tmp_path.glob("*.md"))
        assert len(generated) == 1
        assert generated[0].name == "1-intro-chapter.md"
        content = generated[0].read_text(encoding="utf-8")
        assert "alpha" in content
        assert "beta" in content
        assert not Path(chapter.working_dir).exists()

    def test_flatten_sections_replaces_existing_files(self, tmp_path: Path):
        converter = PdfConverter(PdfConverterConfig(max_output_depth=1))
        existing = tmp_path / "1-intro-chapter.md"
        existing.write_text("old", encoding="utf-8")

        chapter_dir = tmp_path / "chapter-temp-0001"
        chapter_dir.mkdir()
        section_path = chapter_dir / "section-temp-0001.md"
        section_path.write_text("alpha", encoding="utf-8")

        section = EpubSection(
            title="Intro",
            filename=section_path.name,
            file_path=str(section_path),
            word_count=5,
            character_count=12,
            slug_hint="intro",
        )

        chapter = EpubChapter(
            title="Intro Chapter",
            slug="temp",
            working_dir=str(chapter_dir),
            sections=[section],
            source_file="book.pdf",
        )

        converter._flatten_sections([chapter], tmp_path)

        new_file = tmp_path / "1-intro-chapter.md"
        assert new_file.exists()
        new_content = new_file.read_text(encoding="utf-8")
        assert "# Intro Chapter" in new_content
        assert "alpha" in new_content

    def test_add_code_language_hints(self):
        """Test adding language hints to code fences."""
        converter = PdfConverter()

        md_text = """Some text.

```
def hello():
    print("world")
```

More text.

```
another code block
```
"""

        result = converter._add_code_language_hints(md_text, "python")

        # Should add python to opening code fences (``` at start of line)
        # Regex replaces ```\s*$ which matches both opening and closing ```
        # So we get ```python for both opening and closing
        assert "```python" in result
        # Count should be 4 (2 opening + 2 closing)
        assert result.count("```python") == 4

    def test_fix_image_paths(self):
        """Test fixing image paths in markdown."""
        converter = PdfConverter(PdfConverterConfig(preserve_images=True))

        content = """# Chapter

    Some text.

    ![Figure 1](image1.png)

    More text.

    ![Figure 2](image2.png)
    """

        result = converter._fix_image_paths(content)

        # Images should be rewritten to the root images/ folder
        assert "![Figure 1](images/image1.png)" in result
        assert "![Figure 2](images/image2.png)" in result

    def test_fix_image_paths_preserves_absolute_paths(self):
        """Test that absolute paths are not modified."""
        converter = PdfConverter(PdfConverterConfig(preserve_images=True))

        content = """![Absolute](/absolute/path/image.png)
![Relative already](../images/existing.png)
"""

        result = converter._fix_image_paths(content)

        # Should not modify absolute or already-relative paths
        assert "![Absolute](/absolute/path/image.png)" in result
        assert "![Relative already](../images/existing.png)" in result

    def test_fix_image_paths_disabled(self):
        """Test that image path fixing is skipped when disabled."""
        converter = PdfConverter(PdfConverterConfig(preserve_images=False))

        content = "![Figure](image.png)"
        result = converter._fix_image_paths(content)

        # Should not modify when preserve_images is False
        assert result == content

    def test_flatten_sections_zero_pads_double_digit_chapters(self, tmp_path: Path):
        converter = PdfConverter(PdfConverterConfig(max_output_depth=1))
        chapters: list[EpubChapter] = []

        for idx in range(1, 13):
            chapter_dir = tmp_path / f"chapter-temp-{idx:04d}"
            chapter_dir.mkdir()
            section_path = chapter_dir / "section-temp-0001.md"
            section_path.write_text(f"Section {idx}", encoding="utf-8")

            section = EpubSection(
                title=f"Section {idx}",
                filename=section_path.name,
                file_path=str(section_path),
                word_count=2,
                character_count=10,
                slug_hint=f"section-{idx}",
            )

            chapters.append(
                EpubChapter(
                    title=f"Chapter {idx}",
                    slug="temp",
                    working_dir=str(chapter_dir),
                    sections=[section],
                    source_file="book.pdf",
                )
            )

        converter._flatten_sections(chapters, tmp_path)

        expected_files = [f"{idx:02d}-chapter-{idx}.md" for idx in range(1, 13)]
        assert sorted(f.name for f in tmp_path.glob("*.md")) == expected_files

        for idx, chapter in enumerate(chapters, start=1):
            expected = expected_files[idx - 1]
            assert chapter.output_filename == expected
            assert Path(chapter.output_path).name == expected
            assert chapter.sections[0].filename == expected
            assert Path(chapter.sections[0].file_path).name == expected

    def test_structured_output_creates_chapter_directories(self, tmp_path: Path):
        converter = PdfConverter(PdfConverterConfig(max_output_depth=2))
        chapter_dir = tmp_path / "chapter-temp-0001"
        chapter_dir.mkdir()
        section_path = chapter_dir / "section-temp-0001.md"
        section_path.write_text("Section One", encoding="utf-8")
        section_two_path = chapter_dir / "section-temp-0002.md"
        section_two_path.write_text("Section Two", encoding="utf-8")

        section = EpubSection(
            title="Section One",
            filename=section_path.name,
            file_path=str(section_path),
            word_count=2,
            character_count=10,
            slug_hint="section-one",
        )
        section_two = EpubSection(
            title="Section Two",
            filename=section_two_path.name,
            file_path=str(section_two_path),
            word_count=2,
            character_count=10,
            slug_hint="section-two",
        )

        chapter = EpubChapter(
            title="Chapter One",
            slug="temp",
            working_dir=str(chapter_dir),
            sections=[section, section_two],
            source_file="book.pdf",
        )

        converter._write_structured_sections([chapter], tmp_path)

        final_dir = Path(chapter.output_path)
        assert final_dir.is_dir()
        files = sorted(final_dir.glob("*.md"))
        assert [f.name for f in files] == ["1-section-one.md", "2-section-two.md"]
        assert Path(section.file_path) == files[0]
        assert Path(section_two.file_path) == files[1]

    def test_structured_output_collapses_single_section(self, tmp_path: Path):
        converter = PdfConverter(PdfConverterConfig(max_output_depth=2))

        chapter_dir = tmp_path / "chapter-temp-0001"
        chapter_dir.mkdir()
        section_path = chapter_dir / "section-temp-0001.md"
        section_path.write_text("Only section", encoding="utf-8")

        section = EpubSection(
            title="Solo",
            filename=section_path.name,
            file_path=str(section_path),
            word_count=2,
            character_count=10,
            slug_hint="solo",
        )

        chapter = EpubChapter(
            title="Single",
            slug="temp",
            working_dir=str(chapter_dir),
            sections=[section],
            source_file="book.pdf",
        )

        converter._write_structured_sections([chapter], tmp_path)

        final_path = Path(chapter.output_path)
        assert final_path.is_file()
        assert final_path.parent == tmp_path
        assert final_path.name == "1-single.md"
        assert Path(section.file_path) == final_path

    def test_split_markdown_by_heading_groups_sections(self):
        """Split text with intro and multiple headings into sections."""
        converter = PdfConverter()
        md_text = """This is the introduction paragraph.
It should become the Introduction section.

## First Section
Content for the first section.

## Second Section
Content for the second section."""

        sections = converter._split_markdown_by_heading(md_text, "Chapter Title")
        titles = [title for title, _, _ in sections]
        levels = [level for _, _, level in sections]

        assert titles == ["Introduction", "First Section", "Second Section"]
        assert levels == [2, 2, 2]
        assert "introduction paragraph" in sections[0][1].lower()
        assert "first section" in sections[1][1]
        assert "Second Section" in sections[2][1]

    def test_split_markdown_by_heading_without_sections_returns_full_content(self):
        """If no headings appear, return a single section using the chapter title."""
        converter = PdfConverter()
        content = "Just a body of text with no headings."

        sections = converter._split_markdown_by_heading(content, "Solo Chapter")

        assert sections == [("Solo Chapter", content, 2)]

    def test_extract_chapters_info_with_outline(self):
        """Test chapter extraction from PDF outline."""
        converter = PdfConverter(PdfConverterConfig(use_pdf_outlines=True))

        # Mock document with outline
        mock_doc = Mock()
        mock_doc.page_count = 100
        mock_doc.get_toc.return_value = [
            [1, "Chapter 1", 1],  # Level 1, page 1
            [2, "Section 1.1", 5],  # Level 2, page 5
            [1, "Chapter 2", 20],  # Level 1, page 20
            [1, "Chapter 3", 50],  # Level 1, page 50
        ]

        chapters_info = converter._extract_chapters_info(mock_doc)

        assert len(chapters_info) == 3

        # Chapter 1: pages 0-19 (0-indexed, end before chapter 2)
        assert chapters_info[0] == ("Chapter 1", 0, 19)

        # Chapter 2: pages 19-49
        assert chapters_info[1] == ("Chapter 2", 19, 49)

        # Chapter 3: pages 49-100 (to end)
        assert chapters_info[2] == ("Chapter 3", 49, 100)

    def test_extract_chapters_info_handles_extended_outline_payload(self):
        converter = PdfConverter(PdfConverterConfig(use_pdf_outlines=True))

        mock_doc = Mock()
        mock_doc.page_count = 75
        mock_doc.get_toc.return_value = [
            [1, "Chapter 1", 1, "dest", None, None],
            [1, "Chapter 2", 30, "dest", None, None],
        ]

        chapters_info = converter._extract_chapters_info(mock_doc)

        assert chapters_info == [
            ("Chapter 1", 0, 29),
            ("Chapter 2", 29, 75),
        ]

    def test_extract_chapters_info_without_outline(self):
        """Test chapter extraction fallback when no outline."""
        converter = PdfConverter(PdfConverterConfig(use_pdf_outlines=True))

        # Mock document without outline
        mock_doc = Mock()
        mock_doc.page_count = 50
        mock_doc.get_toc.return_value = []

        chapters_info = converter._extract_chapters_info(mock_doc)

        # Should return single "Full Document" chapter
        assert len(chapters_info) == 1
        assert chapters_info[0] == ("Full Document", 0, 50)

    def test_extract_chapters_info_outline_disabled(self):
        """Test chapter extraction when outline use is disabled."""
        converter = PdfConverter(PdfConverterConfig(use_pdf_outlines=False))

        # Mock document with outline (but disabled in config)
        mock_doc = Mock()
        mock_doc.page_count = 50
        mock_doc.get_toc.return_value = [
            [1, "Chapter 1", 1],
            [1, "Chapter 2", 20],
        ]

        chapters_info = converter._extract_chapters_info(mock_doc)

        # Should ignore outline and return full document
        assert len(chapters_info) == 1
        assert chapters_info[0] == ("Full Document", 0, 50)

    def test_extract_chapters_info_handles_outline_without_level_one_entries(self):
        converter = PdfConverter(PdfConverterConfig(use_pdf_outlines=True))

        mock_doc = Mock()
        mock_doc.page_count = 42
        mock_doc.get_toc.return_value = [
            [2, "Section 1.1", 5],
            [3, "Section 1.1.1", 7],
        ]

        chapters_info = converter._extract_chapters_info(mock_doc)

        assert chapters_info == [("Full Document", 0, 42)]


@pytest.mark.unit
@pytest.mark.asyncio
class TestPdfConverterAsync:
    """Test async methods of PdfConverter."""

    async def test_convert_pdf_to_markdown_file_not_found(self):
        """Test error handling when PDF file doesn't exist."""
        converter = PdfConverter()

        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            await converter.convert_pdf_to_markdown(
                pdf_path="/nonexistent/file.pdf",
                output_dir="/tmp/output",
            )

    async def test_create_section_file_empty_content(self):
        """Test that empty sections are not created."""
        converter = PdfConverter()

        result = await converter._create_section_file(
            section_title="Empty Section",
            section_content="",
            section_index=1,
            chapter_dir=Path("/tmp/chapter"),
            level=2,
        )

        assert result is None

    async def test_create_section_file_whitespace_only(self):
        """Test that whitespace-only sections are not created."""
        converter = PdfConverter()

        result = await converter._create_section_file(
            section_title="Whitespace Section",
            section_content="   \n\n   ",
            section_index=1,
            chapter_dir=Path("/tmp/chapter"),
            level=2,
        )

        assert result is None

    async def test_create_section_file_persists_content(self, tmp_path: Path):
        converter = PdfConverter()
        chapter_dir = tmp_path / "chapter"
        chapter_dir.mkdir()

        raw_content = "Intro copy.\n\n![Diagram](fig.png)"
        expected_content = converter._fix_image_paths(raw_content)

        section = await converter._create_section_file(
            section_title="Fancy Section",
            section_content=raw_content,
            section_index=3,
            chapter_dir=chapter_dir,
            level=2,
        )

        assert section is not None
        file_path = Path(section.file_path)
        assert file_path.exists()
        assert file_path.read_text(encoding="utf-8") == expected_content
        assert section.filename == "section-temp-0003.md"
        assert section.slug_hint == "fancy-section"
        assert section.word_count == len(expected_content.split())
        assert section.character_count == len(expected_content)

    async def test_convert_pdf_to_markdown_reports_markdown_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Ensure failures from pymupdf4llm surface to the caller."""
        pdf_path = tmp_path / "book.pdf"
        pdf_path.write_text("fake", encoding="utf-8")
        output_dir = tmp_path / "converted"

        class FakeDoc:
            def __init__(self):
                self.metadata = {"title": "Failure"}
                self.page_count = 1

            def get_toc(self, simple: bool = False):
                return []

            def close(self):
                pass

        fake_doc = FakeDoc()
        monkeypatch.setattr("ebook_tools.pdf_converter.fitz.open", lambda _: fake_doc)

        def failing_markdown(*args, **kwargs):
            raise RuntimeError("markdown extraction failed")

        monkeypatch.setattr("ebook_tools.pdf_converter.pymupdf4llm.to_markdown", failing_markdown)

        converter = PdfConverter()
        with pytest.raises(RuntimeError, match="markdown extraction failed"):
            await converter.convert_pdf_to_markdown(pdf_path, output_dir)

    @pytest.mark.asyncio
    async def test_convert_pdf_to_markdown_discards_empty_chapters(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Empty markdown extraction should drop temporary chapter folders."""
        pdf_path = tmp_path / "book.pdf"
        pdf_path.write_text("fake", encoding="utf-8")
        output_dir = tmp_path / "converted"

        class FakeDoc:
            def __init__(self):
                self.metadata = {"title": "Empty"}
                self.page_count = 4
                self.closed = False

            def get_toc(self, simple: bool = False):
                return [[1, "Lone Chapter", 1]]

            def close(self):
                self.closed = True

        fake_doc = FakeDoc()
        monkeypatch.setattr("ebook_tools.pdf_converter.fitz.open", lambda _: fake_doc)
        monkeypatch.setattr("ebook_tools.pdf_converter.pymupdf4llm.to_markdown", lambda *args, **kwargs: "   ")

        removed_paths: list[Path] = []

        def fake_rmtree(path: str | Path, ignore_errors: bool = True):
            removed_paths.append(Path(path))

        monkeypatch.setattr("ebook_tools.pdf_converter.shutil.rmtree", fake_rmtree)

        converter = PdfConverter(PdfConverterConfig(preserve_images=False))
        result = await converter.convert_pdf_to_markdown(pdf_path, output_dir)

        assert fake_doc.closed is True
        assert result.chapters_count == 0
        assert removed_paths, "Empty chapter folders should be cleaned up"

    @pytest.mark.asyncio
    async def test_convert_pdf_to_markdown_emits_structured_directories(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """End-to-end conversion should create chapter directories by default."""
        pdf_path = tmp_path / "book.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")
        output_dir = tmp_path / "output"

        class FakeDoc:
            def __init__(self):
                self.metadata = {"title": "PDF Title"}
                self.page_count = 10
                self.closed = False

            def get_toc(self, simple: bool = False):
                return [
                    [1, "Chapter One", 1],
                    [1, "Chapter Two", 3],
                ]

            def close(self):
                self.closed = True

        class MarkdownStub:
            def __init__(self):
                self.calls = 0

            def __call__(
                self,
                doc,
                *,
                pages,
                page_chunks,
                write_images,
                image_path,
                image_format,
            ):
                self.calls += 1
                assert isinstance(pages, list)
                assert page_chunks is False
                return "## Section Alpha\nBody\n## Section Beta\nMore"

        fake_doc = FakeDoc()
        markdown_stub = MarkdownStub()

        monkeypatch.setattr("ebook_tools.pdf_converter.fitz.open", lambda _: fake_doc)
        monkeypatch.setattr("ebook_tools.pdf_converter.pymupdf4llm.to_markdown", markdown_stub)

        converter = PdfConverter(PdfConverterConfig(preserve_images=False))
        result = await converter.convert_pdf_to_markdown(pdf_path, output_dir)

        assert fake_doc.closed is True
        assert result.book_title == "PDF Title"
        assert result.chapters_count == 2
        assert result.sections_count == 4
        chapter_dirs = sorted(path.name for path in output_dir.iterdir() if path.is_dir())
        assert chapter_dirs == ["1-chapter-one", "2-chapter-two"]

        first_chapter = result.chapters[0]
        assert first_chapter.slug == "chapter-one"
        assert not Path(first_chapter.working_dir).exists()
        assert first_chapter.output_filename is None
        chapter_root = Path(first_chapter.output_path)
        assert chapter_root.exists() and chapter_root.is_dir()
        section_files = sorted(f.name for f in chapter_root.glob("*.md"))
        assert section_files == ["1-section-alpha.md", "2-section-beta.md"]
        first_section = first_chapter.sections[0]
        assert first_section.filename == "1-section-alpha.md"
        assert Path(first_section.file_path) == chapter_root / "1-section-alpha.md"

    async def test_convert_pdf_to_markdown_supports_flat_mode(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pdf_path = tmp_path / "book.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")
        output_dir = tmp_path / "flat"

        class FakeDoc:
            def __init__(self):
                self.metadata = {"title": "PDF Title"}
                self.page_count = 4
                self.closed = False

            def get_toc(self, simple: bool = False):
                return [[1, "Only Chapter", 1]]

            def close(self):
                self.closed = True

        fake_doc = FakeDoc()

        def markdown_stub(doc, *, pages, page_chunks, write_images, image_path, image_format):
            return "## Section Alpha\nBody\n## Section Beta\nMore"

        monkeypatch.setattr("ebook_tools.pdf_converter.fitz.open", lambda _: fake_doc)
        monkeypatch.setattr("ebook_tools.pdf_converter.pymupdf4llm.to_markdown", markdown_stub)

        converter = PdfConverter(PdfConverterConfig(preserve_images=False, max_output_depth=1))
        result = await converter.convert_pdf_to_markdown(pdf_path, output_dir)

        flattened = sorted(f.name for f in output_dir.glob("*.md"))
        assert flattened == ["1-only-chapter.md"]
        assert result.chapters_count == 1

        chapter = result.chapters[0]
        assert chapter.output_filename == "1-only-chapter.md"
        assert Path(chapter.output_path).name == "1-only-chapter.md"

    @pytest.mark.asyncio
    async def test_convert_pdf_to_markdown_propagates_fitz_errors(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """fitz.open errors should bubble up for caller handling."""
        pdf_path = tmp_path / "locked.pdf"
        pdf_path.write_text("data", encoding="utf-8")
        output_dir = tmp_path / "out"

        monkeypatch.setattr(
            "ebook_tools.pdf_converter.fitz.open",
            Mock(side_effect=RuntimeError("password protected")),
        )

        converter = PdfConverter()

        with pytest.raises(RuntimeError):
            await converter.convert_pdf_to_markdown(pdf_path, output_dir)
