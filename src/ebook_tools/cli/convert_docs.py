#!/usr/bin/env python3
"""Document Conversion CLI for ebook-tools.

Convert various document formats (EPUB, PDF) to structured Markdown
that can be shared directly from the filesystem.

Features:
- Emits EPUB/PDF conversions with configurable directory depth (default 2)
- Preserves the original reading order plus shared `images/` assets
- Creates a slugified book subfolder under the output directory
- Non-interactive operation suitable for automation
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.tree import Tree

from ebook_tools.converter_base import make_slug
from ebook_tools.epub_converter import EpubConverter, EpubConverterConfig
from ebook_tools.epub_models import ConversionResult, EpubInfo, PdfInfo
from ebook_tools.pdf_converter import PdfConverter, PdfConverterConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(
    name="convert-docs",
    help="Convert EPUB/PDF documents to structured Markdown.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)


SUPPORTED_FORMATS = {
    "epub": {
        "name": "EPUB",
        "description": "Electronic Publication format",
    },
    "pdf": {
        "name": "PDF",
        "description": "Portable Document Format (text-based, non-scanned)",
    },
}

OUTPUT_DIR_ENV_VARS = ("CONVERT_DOCS_OUTPUT_DIR", "EBOOK_TOOLS_OUTPUT_DIR")


def _resolve_output_parent(explicit_output: str | None) -> tuple[Path | None, str | None]:
    """Resolve the parent output directory from explicit flag or env vars."""
    if explicit_output:
        return Path(explicit_output).expanduser().resolve(), "--output"

    for env_var in OUTPUT_DIR_ENV_VARS:
        value = os.environ.get(env_var)
        if value and value.strip():
            return Path(value.strip()).expanduser().resolve(), f"${env_var}"

    return None, None


def determine_output_dir(input_path: Path, explicit_output: str | None, book_title: str | None = None) -> tuple[Path, bool, str | None]:
    """Determine the final output directory, always including a book-slug subfolder.

    The output structure is always: <parent_dir>/<book-slug>/
    - With --output or env var: <specified_dir>/<book-slug>/
    - Default: ./converted-books/<book-slug>/
    """
    parent_dir, source = _resolve_output_parent(explicit_output)

    if parent_dir is None:
        parent_dir = Path.cwd() / "converted-books"
        auto = True
        source = None
    else:
        auto = False

    slug = make_slug(book_title) if book_title else make_slug(input_path.stem)
    output_dir = (parent_dir / slug).resolve()

    return output_dir, auto, source


def detect_format(file_path: Path) -> str | None:
    """Detect file format from extension."""
    suffix = file_path.suffix.lower().lstrip(".")
    return suffix if suffix in SUPPORTED_FORMATS else None


async def inspect_epub(file_path: Path) -> EpubInfo | None:
    """Inspect EPUB file without conversion."""
    try:
        from ebooklib import epub, ITEM_DOCUMENT, ITEM_IMAGE

        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        book = epub.read_epub(str(file_path))

        title_data = book.get_metadata("DC", "title")
        title = title_data[0][0] if title_data and title_data[0] else "Unknown Title"

        author_data = book.get_metadata("DC", "creator")
        author = author_data[0][0] if author_data and author_data[0] else None

        language_data = book.get_metadata("DC", "language")
        language = language_data[0][0] if language_data and language_data[0] else None

        identifier_data = book.get_metadata("DC", "identifier")
        identifier = identifier_data[0][0] if identifier_data and identifier_data[0] else None

        publisher_data = book.get_metadata("DC", "publisher")
        publisher = publisher_data[0][0] if publisher_data and publisher_data[0] else None

        description_data = book.get_metadata("DC", "description")
        description = description_data[0][0] if description_data and description_data[0] else None

        chapters = list(book.get_items_of_type(ITEM_DOCUMENT))
        images = list(book.get_items_of_type(ITEM_IMAGE))

        file_size_mb = file_path.stat().st_size / (1024 * 1024)

        return EpubInfo(
            title=title,
            author=author,
            language=language,
            identifier=identifier,
            publisher=publisher,
            description=description,
            chapters_count=len(chapters),
            has_images=len(images) > 0,
            file_size_mb=round(file_size_mb, 2),
        )

    except Exception as e:
        logger.error(f"Failed to inspect EPUB: {e}")
        return None


async def inspect_pdf(file_path: Path) -> PdfInfo | None:
    """Inspect PDF file without conversion."""
    try:
        import fitz

        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        doc = fitz.open(str(file_path))

        metadata = doc.metadata
        title = metadata.get("title") or "Unknown Title"
        author = metadata.get("author")
        subject = metadata.get("subject")
        creator = metadata.get("creator")
        producer = metadata.get("producer")
        keywords = metadata.get("keywords")

        outline = doc.get_toc(simple=False)
        has_outline = bool(outline)

        pages_count = doc.page_count

        has_images = False
        for page_num in range(min(5, pages_count)):
            page = doc[page_num]
            images = page.get_images()
            if images:
                has_images = True
                break

        file_size_mb = file_path.stat().st_size / (1024 * 1024)

        doc.close()

        return PdfInfo(
            title=title,
            author=author,
            subject=subject,
            creator=creator,
            producer=producer,
            keywords=keywords,
            pages_count=pages_count,
            has_outline=has_outline,
            has_images=has_images,
            file_size_mb=round(file_size_mb, 2),
        )

    except Exception as e:
        logger.error(f"Failed to inspect PDF: {e}")
        return None


def print_epub_info(info: EpubInfo) -> None:
    """Pretty print EPUB info using rich."""
    lines = [f"[bold]Title:[/bold]       {info.title}"]
    if info.author:
        lines.append(f"[bold]Author:[/bold]      {info.author}")
    if info.publisher:
        lines.append(f"[bold]Publisher:[/bold]   {info.publisher}")
    if info.language:
        lines.append(f"[bold]Language:[/bold]    {info.language}")
    if info.identifier:
        lines.append(f"[bold]Identifier:[/bold]  {info.identifier}")
    lines.append(f"[bold]Chapters:[/bold]    {info.chapters_count}")
    lines.append(f"[bold]Images:[/bold]      {'Yes' if info.has_images else 'No'}")
    lines.append(f"[bold]File Size:[/bold]   {info.file_size_mb} MB")

    if info.description:
        desc = info.description[:200] + "..." if len(info.description) > 200 else info.description
        lines.append(f"\n[bold]Description:[/bold]\n{desc}")

    console.print(Panel("\n".join(lines), title="EPUB File Information"))


def print_pdf_info(info: PdfInfo) -> None:
    """Pretty print PDF info using rich."""
    lines = [f"[bold]Title:[/bold]       {info.title}"]
    if info.author:
        lines.append(f"[bold]Author:[/bold]      {info.author}")
    if info.subject:
        lines.append(f"[bold]Subject:[/bold]     {info.subject}")
    if info.creator:
        lines.append(f"[bold]Creator:[/bold]     {info.creator}")
    if info.producer:
        lines.append(f"[bold]Producer:[/bold]    {info.producer}")
    if info.keywords:
        lines.append(f"[bold]Keywords:[/bold]    {info.keywords}")
    lines.append(f"[bold]Pages:[/bold]       {info.pages_count}")
    lines.append(f"[bold]Has TOC:[/bold]     {'Yes' if info.has_outline else 'No'}")
    lines.append(f"[bold]Images:[/bold]      {'Yes' if info.has_images else 'No'}")
    lines.append(f"[bold]File Size:[/bold]   {info.file_size_mb} MB")

    console.print(Panel("\n".join(lines), title="PDF File Information"))


def print_conversion_summary(result: ConversionResult) -> None:
    """Print conversion statistics using rich."""
    output_path = Path(result.output_directory)
    images_dir = output_path / "images"

    tree = Tree(f"[bold]{output_path.name}/[/bold]")
    if images_dir.exists():
        tree.add("images/")

    chapter_entries: list[str] = []
    for chapter in result.chapters:
        chapter_path = None
        if chapter.output_path:
            candidate = Path(chapter.output_path)
            if candidate.exists():
                chapter_path = candidate
        if chapter_path is None and chapter.sections:
            candidate = Path(chapter.sections[0].file_path)
            if candidate.exists():
                chapter_path = candidate
        if chapter_path is not None:
            try:
                rel = chapter_path.relative_to(output_path)
            except ValueError:
                rel = chapter_path
            text = rel.as_posix()
            entry = f"{text}/" if chapter_path.is_dir() else text
            chapter_entries.append(entry)

    unique_entries = sorted(dict.fromkeys(chapter_entries))
    for entry in unique_entries[:5]:
        tree.add(entry)
    remaining = max(len(unique_entries) - 5, 0)
    if remaining:
        tree.add(f"... ({remaining} more)")

    console.print()
    console.print(Panel(
        f"[bold]Book Title:[/bold]    {result.book_title}\n"
        f"[bold]Chapters:[/bold]      {result.chapters_count}\n"
        f"[bold]Sections:[/bold]      {result.sections_count}\n"
        f"[bold]Output Dir:[/bold]    {result.output_directory}",
        title="Conversion Statistics",
    ))
    console.print(tree)
    console.print()


async def convert_epub_to_markdown(
    input_path: Path,
    output_dir: Path,
    title: str | None = None,
    config: EpubConverterConfig | None = None,
) -> ConversionResult | None:
    """Convert EPUB to Markdown using EpubConverter."""
    try:
        logger.info(f"Converting {input_path} to {output_dir}")
        converter = EpubConverter(config or EpubConverterConfig())
        return await converter.convert_epub_to_markdown(
            epub_path=input_path,
            output_dir=output_dir,
            book_title=title,
        )
    except Exception as e:
        logger.error(f"Conversion failed: {e}", exc_info=True)
        return None


async def convert_pdf_to_markdown(
    input_path: Path,
    output_dir: Path,
    title: str | None = None,
    config: PdfConverterConfig | None = None,
) -> ConversionResult | None:
    """Convert PDF to Markdown using PdfConverter."""
    try:
        logger.info(f"Converting {input_path} to {output_dir}")
        converter = PdfConverter(config or PdfConverterConfig())
        return await converter.convert_pdf_to_markdown(
            pdf_path=input_path,
            output_dir=output_dir,
            book_title=title,
        )
    except Exception as e:
        logger.error(f"Conversion failed: {e}", exc_info=True)
        return None


@app.command("list-formats")
def list_formats_cmd():
    """List all supported document formats."""
    console.print("\n[bold]Supported document formats:[/bold]\n")
    for ext, info in SUPPORTED_FORMATS.items():
        console.print(f"  .{ext:<8} - {info['name']:<12} - {info['description']}")
    console.print("\n[dim]Coming soon: MOBI (Kindle format)[/dim]\n")


@app.command("inspect")
def inspect_cmd(
    input_file: Annotated[Path, typer.Argument(help="Path to the EPUB or PDF file to inspect", exists=True)],
):
    """Inspect file metadata without converting."""
    file_format = detect_format(input_file)
    if not file_format:
        console.print(f"[red]Unsupported file format: {input_file.suffix}[/red]")
        raise typer.Exit(1)

    input_path = input_file.expanduser().resolve()

    if file_format == "epub":
        info = asyncio.run(inspect_epub(input_path))
        if info:
            print_epub_info(info)
        else:
            raise typer.Exit(1)
    elif file_format == "pdf":
        info = asyncio.run(inspect_pdf(input_path))
        if info:
            print_pdf_info(info)
        else:
            raise typer.Exit(1)


@app.command("convert")
def convert_cmd(
    input_file: Annotated[Path, typer.Argument(help="Path to the EPUB or PDF file to convert", exists=True)],
    output: Annotated[Optional[str], typer.Option(
        "--output", "-o",
        help="Parent output directory (book subfolder created automatically; env: CONVERT_DOCS_OUTPUT_DIR)",
    )] = None,
    title: Annotated[Optional[str], typer.Option(
        "--title", "-t",
        help="Override book title (uses metadata by default)",
    )] = None,
    max_output_depth: Annotated[int, typer.Option(
        "--max-depth",
        help="Maximum directory depth for emitted Markdown (1 = flat layout)",
        min=1,
    )] = 2,
):
    """Convert an EPUB or PDF file to structured Markdown."""
    input_path = input_file.expanduser().resolve()

    file_format = detect_format(input_path)
    if not file_format:
        console.print(f"[red]Unsupported file format: {input_path.suffix}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[bold]Input:[/bold]  {input_path}")
    console.print(f"[bold]Format:[/bold] {SUPPORTED_FORMATS[file_format]['name']}")

    output_dir, auto_output, output_source = determine_output_dir(input_path, output, title)

    output_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold]Output:[/bold] {output_dir}")
    if auto_output:
        console.print("[dim]  (auto-derived from input filename)[/dim]")
    elif output_source:
        console.print(f"[dim]  (from {output_source})[/dim]")

    if title:
        console.print(f"[bold]Title:[/bold]  {title}")

    console.print(f"[bold]Depth:[/bold]  {max_output_depth}")
    console.print("\nStarting conversion...\n")

    result = None
    if file_format == "epub":
        config = EpubConverterConfig(
            heading_style="ATX",
            strip_unwanted_tags=True,
            preserve_images=True,
            clean_filenames=True,
            max_output_depth=max_output_depth,
        )
        result = asyncio.run(convert_epub_to_markdown(
            input_path=input_path,
            output_dir=output_dir,
            title=title,
            config=config,
        ))
    elif file_format == "pdf":
        config_pdf = PdfConverterConfig(
            preserve_images=True,
            clean_filenames=True,
            use_pdf_outlines=True,
            max_section_depth=2,
            code_language=None,
            max_output_depth=max_output_depth,
        )
        result = asyncio.run(convert_pdf_to_markdown(
            input_path=input_path,
            output_dir=output_dir,
            title=title,
            config=config_pdf,
        ))

    if not result:
        console.print("[red bold]Conversion failed[/red bold]")
        raise typer.Exit(1)

    print_conversion_summary(result)
    console.print("[green bold]Conversion complete![/green bold]\n")


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    input_file: Annotated[Optional[Path], typer.Argument(help="Path to file (shortcut for 'convert' command)")] = None,
    output: Annotated[Optional[str], typer.Option(
        "--output", "-o",
        help="Parent output directory",
    )] = None,
    title: Annotated[Optional[str], typer.Option(
        "--title", "-t",
        help="Override book title",
    )] = None,
    max_output_depth: Annotated[int, typer.Option(
        "--max-depth",
        help="Maximum directory depth (1 = flat)",
        min=1,
    )] = 2,
    inspect: Annotated[bool, typer.Option(
        "--inspect",
        help="Inspect file metadata without converting",
    )] = False,
    list_formats: Annotated[bool, typer.Option(
        "--list-formats",
        help="List supported formats",
    )] = False,
):
    """Convert EPUB/PDF documents to structured Markdown.

    Shortcut: convert-docs <file.epub> converts directly.
    """
    if ctx.invoked_subcommand is not None:
        return

    if list_formats:
        list_formats_cmd()
        return

    if input_file is None:
        console.print(ctx.get_help())
        return

    if not input_file.exists():
        console.print(f"[red]File not found: {input_file}[/red]")
        raise typer.Exit(1)

    if inspect:
        inspect_cmd(input_file)
        return

    convert_cmd(input_file, output=output, title=title, max_output_depth=max_output_depth)


def main():
    """Main entry point."""
    app()


if __name__ == "__main__":
    main()
