from __future__ import annotations

import argparse
import asyncio
import logging
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ebook_tools.cli import convert_docs
from ebook_tools.epub_models import ConversionResult, EpubInfo, PdfInfo


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
async def test_main_async_errors_when_path_missing(tmp_path: Path) -> None:
    phantom = tmp_path / "missing.epub"
    args = _build_args(input_path=str(phantom))

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_rejects_unknown_format(tmp_path: Path) -> None:
    unknown = tmp_path / "readme.txt"
    unknown.write_text("stub", encoding="utf-8")
    args = _build_args(input_path=str(unknown))

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
async def test_main_async_inspect_epub_prints_metadata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    epub_path = tmp_path / "book.epub"
    epub_path.write_text("stub", encoding="utf-8")
    inspected = EpubInfo(
        title="Story",
        author="Ada",
        language="en",
        identifier="urn:isbn",
        publisher="ACME",
        description="About",
        chapters_count=3,
        has_images=True,
        file_size_mb=1.0,
    )

    inspect_mock = AsyncMock(return_value=inspected)
    captured: dict[str, object] = {}

    def fake_print(info: EpubInfo) -> None:
        captured["info"] = info

    monkeypatch.setattr(convert_docs, "inspect_epub", inspect_mock)
    monkeypatch.setattr(convert_docs, "print_epub_info", fake_print)
    args = _build_args(input_path=str(epub_path), inspect=True)

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 0
    assert captured["info"] is inspected
    inspect_mock.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_inspect_epub_returns_error_when_metadata_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    epub_path = tmp_path / "book.epub"
    epub_path.write_text("stub", encoding="utf-8")
    inspect_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(convert_docs, "inspect_epub", inspect_mock)
    args = _build_args(input_path=str(epub_path), inspect=True)

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 1
    inspect_mock.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_inspect_pdf_returns_error_when_metadata_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF")
    inspect_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(convert_docs, "inspect_pdf", inspect_mock)
    args = _build_args(input_path=str(pdf_path), inspect=True)

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 1
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
@pytest.mark.asyncio
async def test_main_async_prints_title_when_provided(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    epub_path = tmp_path / "guide.epub"
    epub_path.write_text("stub", encoding="utf-8")
    output_dir = tmp_path / "output"
    conversion = _make_conversion(output_dir)

    convert_mock = AsyncMock(return_value=conversion)
    monkeypatch.setattr(convert_docs, "convert_epub_to_markdown", convert_mock)
    monkeypatch.setattr(convert_docs, "print_conversion_summary", lambda result: None)
    monkeypatch.setattr(convert_docs, "print_success_banner", lambda: None)

    args = _build_args(input_path=str(epub_path), output=str(output_dir), title="Manual")

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 0
    assert "📖 Title: Manual" in capsys.readouterr().out
    convert_mock.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_runs_pdf_conversion(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "guide.pdf"
    pdf_path.write_text("stub", encoding="utf-8")
    output_dir = tmp_path / "out"
    conversion = _make_conversion(output_dir)

    convert_mock = AsyncMock(return_value=conversion)
    monkeypatch.setattr(convert_docs, "convert_pdf_to_markdown", convert_mock)
    monkeypatch.setattr(convert_docs, "print_conversion_summary", lambda result: None)
    monkeypatch.setattr(convert_docs, "print_success_banner", lambda: None)

    args = _build_args(input_path=str(pdf_path), output=str(output_dir))

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 0
    convert_mock.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_returns_error_when_conversion_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    epub_path = tmp_path / "guide.epub"
    epub_path.write_text("stub", encoding="utf-8")
    convert_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(convert_docs, "convert_epub_to_markdown", convert_mock)

    args = _build_args(input_path=str(epub_path), output=str(tmp_path / "out"))

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 1
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
def test_parse_cli_args_warns_when_conflicting_inputs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        args = convert_docs.parse_cli_args(["--input", "first.epub", "second.epub"])

    assert args.input == "first.epub"
    assert "Positional input second.epub ignored" in caplog.text


@pytest.mark.unit
def test_slugify_name_handles_blanks() -> None:
    assert convert_docs._slugify_name("My Book!") == "my-book"
    assert convert_docs._slugify_name("   ") == "book"


@pytest.mark.unit
def test_slugify_name_defaults_for_none() -> None:
    assert convert_docs._slugify_name(None) == "book"


@pytest.mark.unit
def test_determine_output_dir_prefers_explicit_value(tmp_path: Path) -> None:
    derived, auto = convert_docs._determine_output_dir(
        tmp_path / "sample.epub",
        str(tmp_path / "custom"),
    )

    assert auto is False
    assert derived == (tmp_path / "custom").resolve()


@pytest.mark.unit
def test_determine_output_dir_derives_slug(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    derived, auto = convert_docs._determine_output_dir(tmp_path / "Guide Book.epub", explicit_output=None)

    assert auto is True
    assert derived == (tmp_path / "converted-docs" / "guide-book").resolve()


@pytest.mark.unit
def test_detect_format_identifies_known_extensions(tmp_path: Path) -> None:
    epub_path = tmp_path / "story.epub"
    epub_path.write_text("stub", encoding="utf-8")
    assert convert_docs.detect_format(epub_path) == "epub"

    txt_path = tmp_path / "notes.txt"
    txt_path.write_text("stub", encoding="utf-8")
    assert convert_docs.detect_format(txt_path) is None


@pytest.mark.unit
def test_main_warns_when_inspect_with_output(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_args = SimpleNamespace(
        input=None,
        output="~/out",
        inspect=True,
        list_formats=False,
        title=None,
    )
    monkeypatch.setattr(convert_docs, "parse_cli_args", lambda argv: fake_args)

    called: dict[str, object] = {}

    def fake_run(coro):
        called["coro"] = coro
        return 0

    monkeypatch.setattr(convert_docs.asyncio, "run", fake_run)

    with pytest.raises(SystemExit) as excinfo:
        convert_docs.main([])

    assert excinfo.value.code == 0
    assert "--output is ignored" in capsys.readouterr().out
    assert "coro" in called


@pytest.mark.unit
def test_module_entrypoint_invokes_main(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_namespace = SimpleNamespace(
        input=None,
        output=None,
        inspect=False,
        list_formats=True,
        title=None,
        input_path=None,
    )

    def fake_parse_args(self, argv=None):
        return fake_namespace

    monkeypatch.setattr(argparse.ArgumentParser, "parse_args", fake_parse_args, raising=False)

    called: dict[str, object] = {}

    def fake_asyncio_run(coro):
        called["coro"] = coro
        return 0

    monkeypatch.setattr(asyncio, "run", fake_asyncio_run)

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("ebook_tools.cli.convert_docs", run_name="__main__")

    assert excinfo.value.code == 0
    assert "coro" in called
