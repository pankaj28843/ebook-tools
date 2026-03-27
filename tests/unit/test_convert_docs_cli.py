"""Tests for the convert-docs CLI (Typer-based)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ebook_tools.cli import convert_docs
from ebook_tools.converter_base import make_slug
from ebook_tools.epub_models import Chapter, ConversionResult, Section


def _make_conversion(output_dir: Path) -> ConversionResult:
    return ConversionResult(
        book_title="Guide",
        chapters_count=1,
        sections_count=2,
        output_directory=str(output_dir),
        chapters=[],
    )


# --- make_slug tests ---


@pytest.mark.unit
def test_make_slug_handles_blanks() -> None:
    assert "book" in make_slug("My Book!")
    assert make_slug("   ") == "untitled"


@pytest.mark.unit
def test_make_slug_defaults_for_none() -> None:
    assert make_slug(None) == "untitled"


# --- determine_output_dir tests ---


@pytest.mark.unit
def test_determine_output_dir_prefers_explicit_value(tmp_path: Path) -> None:
    derived, auto, source = convert_docs.determine_output_dir(
        tmp_path / "sample.epub",
        str(tmp_path / "custom"),
    )

    assert auto is False
    assert source == "--output"
    # Now creates a book-slug subfolder under the explicit dir
    assert derived.parent == (tmp_path / "custom").resolve()


@pytest.mark.unit
def test_determine_output_dir_derives_slug(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CONVERT_DOCS_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("EBOOK_TOOLS_OUTPUT_DIR", raising=False)

    derived, auto, source = convert_docs.determine_output_dir(tmp_path / "Guide Book.epub", explicit_output=None)

    assert auto is True
    assert source is None
    assert derived == (tmp_path / "converted-books" / "guide-book").resolve()


@pytest.mark.unit
def test_determine_output_dir_uses_env_var(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CONVERT_DOCS_OUTPUT_DIR", str(tmp_path / "books"))
    monkeypatch.chdir(tmp_path)

    derived, auto, source = convert_docs.determine_output_dir(tmp_path / "Guide Book.epub", explicit_output=None)

    assert auto is False
    assert source == "$CONVERT_DOCS_OUTPUT_DIR"
    # Creates a slug subfolder under the env var dir
    assert "guide-book" in str(derived)


@pytest.mark.unit
def test_determine_output_dir_with_title(tmp_path: Path) -> None:
    derived, auto, source = convert_docs.determine_output_dir(
        tmp_path / "sample.epub",
        str(tmp_path / "out"),
        book_title="My Custom Title",
    )

    assert "my-custom-title" in str(derived)


# --- detect_format tests ---


@pytest.mark.unit
def test_detect_format_identifies_known_extensions(tmp_path: Path) -> None:
    epub_path = tmp_path / "story.epub"
    epub_path.write_text("stub", encoding="utf-8")
    assert convert_docs.detect_format(epub_path) == "epub"

    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("stub", encoding="utf-8")
    assert convert_docs.detect_format(txt_path) is None


# --- print_conversion_summary tests ---


class TestConvertDocsSummary:
    @pytest.mark.unit
    def test_print_conversion_summary_handles_external_paths(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        output_dir = tmp_path / "converted"
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        outside_file = tmp_path / "outside.md"
        outside_file.write_text("# Chapter", encoding="utf-8")

        section = Section(
            title="Intro",
            filename="section-temp-0001.md",
            file_path=str(outside_file),
            word_count=5,
            character_count=20,
            slug_hint="intro",
            source_fragment=None,
            level=2,
        )
        chapter = Chapter(
            title="Detached",
            slug="detached",
            working_dir=str(tmp_path / "chapter-temp-0001"),
            output_filename=None,
            output_path=str(outside_file),
            sections=[section],
            source_file="chapter.xhtml",
        )

        result = ConversionResult(
            book_title="Guide",
            chapters_count=1,
            sections_count=1,
            output_directory=str(output_dir),
            chapters=[chapter],
        )

        convert_docs.print_conversion_summary(result)
        captured = capsys.readouterr().out
        assert "outside.md" in captured
        assert "images/" in captured


# --- convert helper tests ---


@pytest.mark.unit
@pytest.mark.asyncio
async def test_convert_epub_to_markdown_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = _make_conversion(tmp_path)

    class StubConverter:
        def __init__(self, config) -> None:
            self.config = config

        async def convert_epub_to_markdown(self, **kwargs):
            return result

    monkeypatch.setattr(convert_docs, "EpubConverter", StubConverter)

    converted = await convert_docs.convert_epub_to_markdown(tmp_path / "book.epub", tmp_path)

    assert converted == result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_convert_epub_to_markdown_handles_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class ExplodingConverter:
        def __init__(self, config) -> None:
            self.config = config

        async def convert_epub_to_markdown(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(convert_docs, "EpubConverter", ExplodingConverter)

    converted = await convert_docs.convert_epub_to_markdown(tmp_path / "book.epub", tmp_path)

    assert converted is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_convert_pdf_to_markdown_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = _make_conversion(tmp_path)

    class StubConverter:
        def __init__(self, config) -> None:
            self.config = config

        async def convert_pdf_to_markdown(self, **kwargs):
            return result

    monkeypatch.setattr(convert_docs, "PdfConverter", StubConverter)

    converted = await convert_docs.convert_pdf_to_markdown(tmp_path / "book.pdf", tmp_path)

    assert converted == result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_convert_pdf_to_markdown_handles_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class ExplodingConverter:
        def __init__(self, config) -> None:
            self.config = config

        async def convert_pdf_to_markdown(self, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(convert_docs, "PdfConverter", ExplodingConverter)

    converted = await convert_docs.convert_pdf_to_markdown(tmp_path / "book.pdf", tmp_path)

    assert converted is None
