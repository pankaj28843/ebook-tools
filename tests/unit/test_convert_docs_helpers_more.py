"""Tests for convert_docs helper functions (inspect, print, etc.)."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from ebook_tools.cli import convert_docs
from ebook_tools.epub_models import Chapter, ConversionResult, EpubInfo, PdfInfo, Section


def _make_chapter(base: Path, idx: int, *, use_output_path: bool) -> Chapter:
    file_path = base / f"{idx:02d}-chapter.md"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(f"chapter {idx}", encoding="utf-8")

    section = Section(
        title=f"Section {idx}",
        filename=file_path.name,
        file_path=str(file_path),
        word_count=10,
        character_count=20,
        slug_hint=None,
        source_fragment=f"frag-{idx}",
    )

    return Chapter(
        title=f"Chapter {idx}",
        slug=f"chapter-{idx}",
        working_dir=str(base / f"work-{idx}"),
        output_filename=file_path.name if use_output_path else None,
        output_path=str(file_path) if use_output_path else None,
        sections=[] if use_output_path else [section],
        source_file=f"chapter{idx}.xhtml",
    )


def _make_conversion(base: Path, chapters: list[Chapter]) -> ConversionResult:
    base.mkdir(parents=True, exist_ok=True)
    return ConversionResult(
        book_title="Sample",
        chapters_count=len(chapters),
        sections_count=sum(len(ch.sections) for ch in chapters),
        output_directory=str(base),
        chapters=chapters,
    )


def _install_fake_ebooklib(monkeypatch: pytest.MonkeyPatch, book) -> None:
    fake_pkg = types.ModuleType("ebooklib")
    fake_epub_module = types.ModuleType("ebooklib.epub")

    def _read_epub(_path: str):
        return book

    fake_epub_module.read_epub = _read_epub
    fake_pkg.epub = fake_epub_module
    fake_pkg.ITEM_DOCUMENT = "doc"
    fake_pkg.ITEM_IMAGE = "img"

    monkeypatch.setitem(sys.modules, "ebooklib", fake_pkg)
    monkeypatch.setitem(sys.modules, "ebooklib.epub", fake_epub_module)


def _install_fake_fitz(monkeypatch: pytest.MonkeyPatch, doc) -> None:
    fake_module = types.ModuleType("fitz")
    fake_module.open = lambda _path: doc
    monkeypatch.setitem(sys.modules, "fitz", fake_module)


class FakeEpubBook:
    def __init__(self) -> None:
        self._meta = {
            ("DC", "title"): [("My Title", {})],
            ("DC", "creator"): [("Ada", {})],
            ("DC", "language"): [("en", {})],
            ("DC", "identifier"): [("ISBN-1", {})],
            ("DC", "publisher"): [("ACME", {})],
            ("DC", "description"): [
                (
                    "This is a very long description that exceeds the wrap threshold for display.\nline two\nline three\nline four",
                    {},
                )
            ],
        }
        self._items = {
            "doc": [object(), object()],
            "img": [object()],
        }

    def get_metadata(self, namespace: str, name: str):
        return self._meta.get((namespace, name), [])

    def get_items_of_type(self, item_type: str):
        return self._items.get(item_type, [])


class FakeFitzPage:
    def __init__(self, *, has_images: bool) -> None:
        self._has_images = has_images

    def get_images(self):
        return [("img",)] if self._has_images else []


class FakeFitzDoc:
    def __init__(self) -> None:
        self.metadata = {
            "title": "Docs",
            "author": "Pat",
            "subject": "Testing",
            "creator": "Suite",
            "producer": "Tools",
            "keywords": "convert",
        }
        self.page_count = 3

    def get_toc(self, simple: bool = False):
        return [[1, "Intro", 1]]

    def __getitem__(self, index: int) -> FakeFitzPage:
        return FakeFitzPage(has_images=index == 0)

    def close(self) -> None:
        return None


@pytest.mark.unit
def test_print_pdf_info_includes_optional_fields(capsys: pytest.CaptureFixture[str]) -> None:
    info = PdfInfo(
        title="Docs",
        author="Pat",
        subject="Testing",
        creator="Suite",
        producer="Tools",
        keywords="convert",
        pages_count=10,
        has_outline=True,
        has_images=True,
        file_size_mb=1.5,
    )

    convert_docs.print_pdf_info(info)

    output = capsys.readouterr().out
    assert "PDF File Information" in output
    assert "Pat" in output
    assert "Has TOC" in output


@pytest.mark.unit
def test_print_epub_info_shows_description(capsys: pytest.CaptureFixture[str]) -> None:
    info = EpubInfo(
        title="Title",
        author="Ada",
        language="en",
        identifier="ISBN",
        publisher="ACME",
        description="A short description of the book",
        chapters_count=5,
        has_images=True,
        file_size_mb=2.0,
    )

    convert_docs.print_epub_info(info)

    output = capsys.readouterr().out
    assert "EPUB File Information" in output
    assert "Description" in output


@pytest.mark.unit
def test_print_conversion_summary_lists_entries(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output_dir = tmp_path / "book"
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    chapters = [_make_chapter(output_dir, idx, use_output_path=idx % 2 == 0) for idx in range(1, 7)]
    result = _make_conversion(output_dir, chapters)

    convert_docs.print_conversion_summary(result)

    output = capsys.readouterr().out
    assert "images/" in output
    assert "book" in output


@pytest.mark.unit
def test_print_conversion_summary_when_no_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output_dir = tmp_path / "empty"
    output_dir.mkdir()
    result = _make_conversion(output_dir, [])

    convert_docs.print_conversion_summary(result)

    output = capsys.readouterr().out
    assert "Conversion Statistics" in output


@pytest.mark.unit
@pytest.mark.asyncio
async def test_convert_epub_to_markdown_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    result = _make_conversion(tmp_path, [])

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
    result = _make_conversion(tmp_path, [])

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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inspect_epub_returns_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    book = FakeEpubBook()
    _install_fake_ebooklib(monkeypatch, book)
    epub_path = tmp_path / "book.epub"
    epub_path.write_text("stub", encoding="utf-8")

    info = await convert_docs.inspect_epub(epub_path)

    assert info is not None
    assert info.title == "My Title"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inspect_epub_handles_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_ebooklib(monkeypatch, FakeEpubBook())

    info = await convert_docs.inspect_epub(tmp_path / "missing.epub")

    assert info is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inspect_epub_handles_exceptions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_ebooklib(monkeypatch, FakeEpubBook())
    epub_module = sys.modules["ebooklib.epub"]

    def _explode(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(epub_module, "read_epub", _explode)
    epub_path = tmp_path / "book.epub"
    epub_path.write_text("stub", encoding="utf-8")

    assert await convert_docs.inspect_epub(epub_path) is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inspect_pdf_returns_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    doc = FakeFitzDoc()
    _install_fake_fitz(monkeypatch, doc)
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_text("stub", encoding="utf-8")

    info = await convert_docs.inspect_pdf(pdf_path)

    assert info is not None
    assert info.has_outline is True
    assert info.has_images is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inspect_pdf_handles_missing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _install_fake_fitz(monkeypatch, FakeFitzDoc())

    info = await convert_docs.inspect_pdf(tmp_path / "missing.pdf")

    assert info is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_inspect_pdf_handles_exceptions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_module = types.ModuleType("fitz")

    def _explode(_path: str):
        raise RuntimeError("boom")

    fake_module.open = _explode
    monkeypatch.setitem(sys.modules, "fitz", fake_module)
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_text("stub", encoding="utf-8")

    assert await convert_docs.inspect_pdf(pdf_path) is None
