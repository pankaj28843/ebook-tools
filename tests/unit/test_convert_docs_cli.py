"""Tests for convert-docs CLI guard rails."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ebook_tools.cli import convert_docs
from ebook_tools.epub_models import ConversionResult, PdfInfo


def _build_args(
    *,
    input_path: str | None,
    codename: str | None = None,
    output: str | None = None,
    inspect: bool = False,
    list_formats: bool = False,
    title: str | None = None,
    deployment_file: str | Path = "deployment.json",
    skip_deployment_update: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        input=input_path,
        codename=codename,
        output=output,
        inspect=inspect,
        list_formats=list_formats,
        title=title,
        deployment_file=deployment_file,
        skip_deployment_update=skip_deployment_update,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_requires_input() -> None:
    args = _build_args(input_path=None)

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_auto_derives_codename_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    epub_path = tmp_path / "Guide Book.epub"
    epub_path.write_text("stub", encoding="utf-8")
    output_dir = tmp_path / "output"

    conversion = ConversionResult(
        book_title="Guide",
        chapters_count=1,
        sections_count=2,
        output_directory=str(output_dir),
        chapters=[],
        table_of_contents_path=None,
        toc_json_path=None,
    )

    invoked_codename: dict[str, str] = {}

    async_mock = AsyncMock(return_value=conversion)
    monkeypatch.setattr(convert_docs, "convert_epub_to_markdown", async_mock)
    monkeypatch.setattr(convert_docs, "print_conversion_summary", lambda result: None)
    monkeypatch.setattr(convert_docs, "print_success_banner", lambda: None)

    def fake_update(manifest_path: Path, snippet: dict[str, str]) -> str:  # type: ignore[type-arg]
        invoked_codename["value"] = snippet["codename"]
        return "created"

    monkeypatch.setattr(convert_docs, "update_deployment_manifest", fake_update)
    deployment_file = tmp_path / "deployment.json"
    args = _build_args(input_path=str(epub_path), output=str(output_dir), deployment_file=str(deployment_file))

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 0
    assert invoked_codename["value"] == "guide-book"
    convert_docs.convert_epub_to_markdown.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_list_formats_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_list():
        captured["called"] = True

    monkeypatch.setattr(convert_docs, "list_supported_formats", fake_list)
    args = _build_args(input_path=None, list_formats=True)

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 0
    assert captured["called"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_inspect_pdf_invokes_helpers(monkeypatch: pytest.MonkeyPatch, tmp_path):
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

    monkeypatch.setattr(convert_docs, "inspect_pdf", AsyncMock(return_value=inspected))
    monkeypatch.setattr(convert_docs, "print_pdf_info", lambda info: None)
    args = _build_args(input_path=str(pdf_path), inspect=True)

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 0
    convert_docs.inspect_pdf.assert_awaited_once()  # type: ignore[attr-defined]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_main_async_runs_conversion(monkeypatch: pytest.MonkeyPatch, tmp_path):
    epub_path = tmp_path / "guide.epub"
    epub_path.write_text("stub", encoding="utf-8")
    output_dir = tmp_path / "output"

    conversion = ConversionResult(
        book_title="Guide",
        chapters_count=1,
        sections_count=2,
        output_directory=str(output_dir),
        chapters=[],
        table_of_contents_path=None,
        toc_json_path=None,
    )

    monkeypatch.setattr(convert_docs, "convert_epub_to_markdown", AsyncMock(return_value=conversion))
    monkeypatch.setattr(convert_docs, "print_conversion_summary", lambda result: None)
    monkeypatch.setattr(convert_docs, "print_success_banner", lambda: None)

    captured: dict[str, Path | dict[str, str]] = {}

    def fake_update(manifest_path: Path, snippet: dict[str, str]) -> str:  # type: ignore[type-arg]
        captured["manifest"] = manifest_path
        captured["snippet"] = snippet
        return "updated"

    monkeypatch.setattr(convert_docs, "update_deployment_manifest", fake_update)
    monkeypatch.setattr(convert_docs, "print_deployment_summary", lambda **kwargs: None)
    deployment_file = tmp_path / "deployment.json"
    args = _build_args(
        input_path=str(epub_path),
        codename="guide",
        output=str(output_dir),
        deployment_file=str(deployment_file),
    )

    exit_code = await convert_docs.main_async(args)

    assert exit_code == 0
    convert_docs.convert_epub_to_markdown.assert_awaited_once()  # type: ignore[attr-defined]
    assert Path(captured["manifest"]) == deployment_file
    assert captured["snippet"]["codename"] == "guide"


@pytest.mark.unit
def test_parse_cli_args_supports_positional_input_for_inspect():
    args = convert_docs.parse_cli_args(["--inspect", "book.epub"])

    assert args.input == "book.epub"
    assert args.inspect is True


@pytest.mark.unit
def test_parse_cli_args_supports_positional_input_for_conversion():
    args = convert_docs.parse_cli_args(["guide.epub", "--codename", "guide"])

    assert args.input == "guide.epub"
    assert args.codename == "guide"


@pytest.mark.unit
def test_update_deployment_manifest_creates_file(tmp_path) -> None:
    manifest = tmp_path / "deployment.json"
    entry = {
        "source_type": "filesystem",
        "codename": "sample",
        "docs_name": "Sample",
        "docs_root_dir": "./converted/sample",
    }

    status = convert_docs.update_deployment_manifest(manifest, entry)

    assert "created" in status
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data == {"tenants": [entry]}


@pytest.mark.unit
def test_update_deployment_manifest_replaces_existing_entry(tmp_path) -> None:
    manifest = tmp_path / "deployment.json"
    initial = {
        "source_type": "filesystem",
        "codename": "sample",
        "docs_name": "Sample",
        "docs_root_dir": "./converted/sample",
    }
    convert_docs.update_deployment_manifest(manifest, initial)

    updated = {
        "source_type": "filesystem",
        "codename": "sample",
        "docs_name": "Sample Updated",
        "docs_root_dir": "./converted/sample-updated",
    }

    status = convert_docs.update_deployment_manifest(manifest, updated)

    assert "updated" in status
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data == {"tenants": [updated]}


@pytest.mark.unit
def test_derive_codename_prefers_title(tmp_path) -> None:
    codename, source = convert_docs._derive_codename(None, "My Book", tmp_path / "book.epub")

    assert codename == "my-book"
    assert source == "title"
