from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ebook_tools.cli import convert_docs
from ebook_tools.epub_models import ConversionResult, PdfInfo


def _build_args(
    *,
    input_path: str | None,
    output: str | None = None,
    inspect: bool = False,
    list_formats: bool = False,
    title: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        input=input_path,
        output=output,
        inspect=inspect,
        list_formats=list_formats,
        title=title,
    )


def _make_conversion(output_dir: Path) -> ConversionResult:
    return ConversionResult(
        book_title="Guide",
        chapters_count=1,
        sections_count=2,
        output_directory=str(output_dir),
        chapters=[],
        table_of_contents_path=None,
        toc_json_path=None,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_requires_input() -> None:
    args = _build_args(input_path=None)

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_uses_default_output_slug(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    epub_path = tmp_path / "Guide Book.epub"
    epub_path.write_text("stub", encoding="utf-8")
    conversion = _make_conversion(tmp_path / "output")

    convert_mock = AsyncMock(return_value=conversion)
    monkeypatch.setattr(convert_docs, "convert_epub_to_markdown", convert_mock)
    monkeypatch.setattr(convert_docs, "print_conversion_summary", lambda result: None)
    monkeypatch.setattr(convert_docs, "print_success_banner", lambda: None)
    monkeypatch.chdir(tmp_path)

    args = _build_args(input_path=str(epub_path))

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 0
    convert_mock.assert_awaited_once()
    derived_output = convert_mock.await_args.kwargs["output_dir"]
    assert derived_output == tmp_path / "converted-docs" / "guide-book"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_respects_explicit_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    epub_path = tmp_path / "guide.epub"
    epub_path.write_text("stub", encoding="utf-8")
    desired_output = tmp_path / "custom"
    conversion = _make_conversion(desired_output)

    convert_mock = AsyncMock(return_value=conversion)
    monkeypatch.setattr(convert_docs, "convert_epub_to_markdown", convert_mock)
    monkeypatch.setattr(convert_docs, "print_conversion_summary", lambda result: None)
    monkeypatch.setattr(convert_docs, "print_success_banner", lambda: None)

    args = _build_args(input_path=str(epub_path), output=str(desired_output))

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 0
    convert_mock.assert_awaited_once()
    assert convert_mock.await_args.kwargs["output_dir"] == desired_output.resolve()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_list_formats_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_list() -> None:
        captured["called"] = True

    monkeypatch.setattr(convert_docs, "list_supported_formats", fake_list)
    args = _build_args(input_path=None, list_formats=True)

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 0
    assert captured["called"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_inspect_pdf_invokes_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF")

    inspected = PdfInfo(
        title="Sample",
        author=None,
        subject=None,
        creator=None,
        producer=None,
        keywords=None,
        pages_count=10,
        has_outline=False,
        has_images=False,
        file_size_mb=0.1,
    )

    inspect_mock = AsyncMock(return_value=inspected)
    monkeypatch.setattr(convert_docs, "inspect_pdf", inspect_mock)
    monkeypatch.setattr(convert_docs, "print_pdf_info", lambda info: None)
    args = _build_args(input_path=str(pdf_path), inspect=True)

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 0
    inspect_mock.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_runs_conversion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    epub_path = tmp_path / "guide.epub"
    epub_path.write_text("stub", encoding="utf-8")
    output_dir = tmp_path / "output"
    conversion = _make_conversion(output_dir)

    convert_mock = AsyncMock(return_value=conversion)
    monkeypatch.setattr(convert_docs, "convert_epub_to_markdown", convert_mock)
    monkeypatch.setattr(convert_docs, "print_conversion_summary", lambda result: None)
    monkeypatch.setattr(convert_docs, "print_success_banner", lambda: None)

    args = _build_args(input_path=str(epub_path), output=str(output_dir))

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 0
    convert_mock.assert_awaited_once()


@pytest.mark.unit
def test_parse_cli_args_supports_positional_input_for_inspect() -> None:
    args = convert_docs.parse_cli_args(["--inspect", "book.epub"])

    assert args.input == "book.epub"
    assert args.inspect is True


@pytest.mark.unit
def test_parse_cli_args_supports_positional_input_for_conversion() -> None:
    args = convert_docs.parse_cli_args(["guide.epub"])

    assert args.input == "guide.epub"


@pytest.mark.unit
def test_slugify_name_handles_blanks() -> None:
    assert convert_docs._slugify_name("My Book!") == "my-book"
    assert convert_docs._slugify_name("   ") == "book"


@pytest.mark.unit
def test_determine_output_dir_prefers_explicit_value(tmp_path: Path) -> None:
    derived, auto = convert_docs._determine_output_dir(
        tmp_path / "sample.epub",
        str(tmp_path / "custom"),
    )

    assert auto is False
    assert derived == (tmp_path / "custom").resolve()
