#!/usr/bin/env python3
"""Document Conversion Script for ebook-tools.

🔄 Convert various document formats (EPUB, MOBI, PDF) to structured Markdown
        that can be shared directly from the filesystem—no tenant metadata needed.

Features:
- Emits EPUB/PDF conversions with configurable directory depth (default 2) so section files can live under chapter folders; pass `--max-output-depth=1` to keep the legacy flat layout
- Preserves the original reading order plus shared `images/` assets
- Derives a safe default output directory (`./converted-docs/<slug>`) when
    `--output` is omitted
- Non-interactive operation suitable for automation

Usage:
    # Convert EPUB to Markdown
    uv run convert-docs --input book.epub --output ~/docs/my-book

    # Convert with custom title
    uv run convert-docs --input guide.epub --output ~/docs/guide --title "My Programming Guide"

    # List supported formats
    uv run convert-docs --list-formats

    # Inspect file before conversion
    uv run convert-docs --inspect book.epub

    # Use custom output directory (alias: --output-dir)
    uv run convert-docs --input book.epub --output-dir ./docs/my-book

    # Use environment variables for output directory
    CONVERT_DOCS_OUTPUT_DIR=./books uv run convert-docs --input book.epub

    # Keep the legacy flat layout
    uv run convert-docs --input guide.epub --max-output-depth 1
"""

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import Sequence

from ebook_tools.epub_converter import EpubConverter, EpubConverterConfig
from ebook_tools.epub_models import ConversionResult, EpubInfo, PdfInfo
from ebook_tools.pdf_converter import PdfConverter, PdfConverterConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


SUPPORTED_FORMATS = {
    "epub": {
        "name": "EPUB",
        "description": "Electronic Publication format",
        "converter": "epub",
    },
    "pdf": {
        "name": "PDF",
        "description": "Portable Document Format (text-based, non-scanned)",
        "converter": "pdf",
    },
}


# Planned future format support
FUTURE_FORMATS = ["mobi"]
OUTPUT_DIR_ENV_VARS = ("CONVERT_DOCS_OUTPUT_DIR", "EBOOK_TOOLS_OUTPUT_DIR")


def _slugify_name(value: str | None) -> str:
    if not value:
        return "book"
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug or "book"


def _resolve_configured_output_dir(explicit_output: str | None) -> tuple[Path | None, str | None]:
    if explicit_output:
        return Path(explicit_output).expanduser().resolve(), "--output/--output-dir"

    for env_var in OUTPUT_DIR_ENV_VARS:
        value = os.environ.get(env_var)
        if value and value.strip():
            return Path(value.strip()).expanduser().resolve(), f"${env_var}"

    return None, None


def _determine_output_dir(input_path: Path, explicit_output: str | None) -> tuple[Path, bool, str | None]:
    configured_output, source = _resolve_configured_output_dir(explicit_output)
    if configured_output is not None:
        return configured_output, False, source

    default_base = Path.cwd() / "converted-docs"
    slug = _slugify_name(input_path.stem)
    return (default_base / slug).resolve(), True, None


def detect_format(file_path: Path) -> str | None:
    """Detect file format from extension."""
    suffix = file_path.suffix.lower().lstrip(".")
    return suffix if suffix in SUPPORTED_FORMATS else None


def print_banner():
    """Print script banner."""
    print("\n" + "=" * 80)
    print("📚 Document Conversion Script - ebook-tools")
    print("=" * 80 + "\n")


def print_success_banner():
    """Print success banner."""
    print("\n" + "=" * 80)
    print("✅ CONVERSION COMPLETE")
    print("=" * 80 + "\n")


def list_supported_formats():
    """List all supported formats."""
    print_banner()
    print("Supported document formats:\n")

    for ext, info in SUPPORTED_FORMATS.items():
        status = "✅ Available"
        print(f"  .{ext:8} - {info['name']:12} - {info['description']} [{status}]")

    print("\nCurrently supported:")
    print("  • EPUB: Full support with chapter/section extraction")
    print("  • PDF: Full support with outline-based chapter detection and markdown conversion")
    print("\nComing soon:")
    print("  • MOBI: Kindle format support")
    print()


async def inspect_epub(file_path: Path) -> EpubInfo | None:
    """Inspect EPUB file without conversion."""
    try:
        from ebooklib import epub

        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        book = epub.read_epub(str(file_path))

        # Extract metadata
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

        # Count chapters and images
        from ebooklib import ITEM_DOCUMENT, ITEM_IMAGE

        chapters = list(book.get_items_of_type(ITEM_DOCUMENT))
        images = list(book.get_items_of_type(ITEM_IMAGE))

        # Get file size
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
        import fitz  # PyMuPDF

        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return None

        doc = fitz.open(str(file_path))

        # Extract metadata
        metadata = doc.metadata
        title = metadata.get("title") or "Unknown Title"
        author = metadata.get("author")
        subject = metadata.get("subject")
        creator = metadata.get("creator")
        producer = metadata.get("producer")
        keywords = metadata.get("keywords")

        # Check for outline (TOC)
        outline = doc.get_toc(simple=False)
        has_outline = bool(outline)

        # Count pages and check for images
        pages_count = doc.page_count

        # Simple heuristic: check if any page has images
        has_images = False
        for page_num in range(min(5, pages_count)):  # Check first 5 pages only
            page = doc[page_num]
            images = page.get_images()
            if images:
                has_images = True
                break

        # Get file size
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


def print_pdf_info(info: PdfInfo):
    """Pretty print PDF info."""
    print("\n📄 PDF File Information:\n")
    print(f"  Title:       {info.title}")
    if info.author:
        print(f"  Author:      {info.author}")
    if info.subject:
        print(f"  Subject:     {info.subject}")
    if info.creator:
        print(f"  Creator:     {info.creator}")
    if info.producer:
        print(f"  Producer:    {info.producer}")
    if info.keywords:
        print(f"  Keywords:    {info.keywords}")
    print(f"  Pages:       {info.pages_count}")
    print(f"  Has TOC:     {'Yes' if info.has_outline else 'No'}")
    print(f"  Images:      {'Yes' if info.has_images else 'No'}")
    print(f"  File Size:   {info.file_size_mb} MB")
    print()


def print_epub_info(info: EpubInfo):
    """Pretty print EPUB info."""
    print("\n📖 EPUB File Information:\n")
    print(f"  Title:       {info.title}")
    if info.author:
        print(f"  Author:      {info.author}")
    if info.publisher:
        print(f"  Publisher:   {info.publisher}")
    if info.language:
        print(f"  Language:    {info.language}")
    if info.identifier:
        print(f"  Identifier:  {info.identifier}")
    print(f"  Chapters:    {info.chapters_count}")
    print(f"  Images:      {'Yes' if info.has_images else 'No'}")
    print(f"  File Size:   {info.file_size_mb} MB")

    if info.description:
        print("\n  Description:")
        # Wrap description to 72 chars
        desc_lines = info.description.split("\n")
        for line in desc_lines[:3]:  # Show first 3 lines
            if len(line) > 72:
                print(f"    {line[:69]}...")
            else:
                print(f"    {line}")
        if len(desc_lines) > 3:
            print(f"    ... ({len(desc_lines) - 3} more lines)")

    print()


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
        result = await converter.convert_epub_to_markdown(
            epub_path=input_path,
            output_dir=output_dir,
            book_title=title,
        )

        return result

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
        result = await converter.convert_pdf_to_markdown(
            pdf_path=input_path,
            output_dir=output_dir,
            book_title=title,
        )

        return result

    except Exception as e:
        logger.error(f"Conversion failed: {e}", exc_info=True)
        return None


def print_conversion_summary(result: ConversionResult):
    """Print conversion statistics."""
    print("\n📊 Conversion Statistics:\n")
    print(f"  Book Title:    {result.book_title}")
    print(f"  Chapters:      {result.chapters_count}")
    print(f"  Sections:      {result.sections_count}")
    print(f"  Output Dir:    {result.output_directory}")
    print("\n📁 Generated Files:\n")

    output_path = Path(result.output_directory)
    images_dir = output_path / "images"

    def _display_entry(path: Path) -> str:
        try:
            rel = path.relative_to(output_path)
        except ValueError:
            rel = path
        text = rel.as_posix()
        return f"{text}/" if path.is_dir() else text

    chapter_files: list[str] = []
    for chapter in result.chapters:
        chapter_path: Path | None = None
        if chapter.output_path:
            candidate = Path(chapter.output_path)
            if candidate.exists():
                chapter_path = candidate
        if chapter_path is None and chapter.sections:
            candidate = Path(chapter.sections[0].file_path)
            if candidate.exists():
                chapter_path = candidate
        if chapter_path is not None:
            chapter_files.append(_display_entry(chapter_path))

    unique_files = sorted(dict.fromkeys(chapter_files))
    preview_files = unique_files[:5]
    remaining = max(len(unique_files) - len(preview_files), 0)

    entries: list[str] = []
    if images_dir.exists():
        entries.append("images/")
    entries.extend(preview_files)
    if remaining:
        entries.append(f"... ({remaining} more chapter files)")
    if not entries:
        entries.append("(no markdown files emitted)")

    print(f"  {output_path.name}/")
    for idx, entry in enumerate(entries):
        connector = "└──" if idx == len(entries) - 1 else "├──"
        print(f"  {connector} {entry}")

    print()


async def main_async(args):  # noqa: PLR0911 - CLI function with multiple exit paths
    """Async main function."""
    print_banner()

    # Handle --list-formats
    if args.list_formats:
        list_supported_formats()
        return 0

    max_output_depth = getattr(args, "max_output_depth", None)
    if max_output_depth is None:
        max_output_depth = 2
    if max_output_depth < 1:
        logger.warning("max-output-depth %s is invalid; defaulting to 1", max_output_depth)
        max_output_depth = 1

    # Validate input file
    if not args.input:
        logger.error("❌ No input file specified. Use --input <file>")
        print("\nRun with --help for usage instructions")
        return 1

    input_path = Path(args.input).expanduser().resolve()

    if not input_path.exists():
        logger.error(f"❌ Input file not found: {input_path}")
        return 1

    # Detect format
    file_format = detect_format(input_path)
    if not file_format:
        logger.error(f"❌ Unsupported file format: {input_path.suffix}")
        print("\nRun with --list-formats to see supported formats")
        return 1

    print(f"📄 Input:  {input_path}")
    print(f"📝 Format: {SUPPORTED_FORMATS[file_format]['name']}")
    print()

    # Handle --inspect
    if args.inspect:
        if file_format == "epub":
            info = await inspect_epub(input_path)
            if info:
                print_epub_info(info)
                return 0
        elif file_format == "pdf":
            info = await inspect_pdf(input_path)
            if info:
                print_pdf_info(info)
                return 0
        return 1

    output_dir, auto_output, output_source = _determine_output_dir(input_path, args.output)
    if auto_output:
        logger.info(f"Using default output directory: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📂 Output: {output_dir}")
    if auto_output:
        print("    (auto-derived from input filename)")
    elif output_source:
        print(f"    (from {output_source})")

    if args.title:
        print(f"📖 Title: {args.title}")

    print(f"🗂️  Max Depth: {max_output_depth}")

    print("\n⏳ Starting conversion...\n")

    # Perform conversion based on format
    result = None
    if file_format == "epub":
        config = EpubConverterConfig(
            heading_style="ATX",
            strip_unwanted_tags=True,
            preserve_images=True,
            clean_filenames=True,
            max_output_depth=max_output_depth,
        )
        result = await convert_epub_to_markdown(
            input_path=input_path,
            output_dir=output_dir,
            title=args.title,
            config=config,
        )
    elif file_format == "pdf":
        config_pdf = PdfConverterConfig(
            preserve_images=True,
            clean_filenames=True,
            use_pdf_outlines=True,
            max_section_depth=2,
            code_language=None,
            max_output_depth=max_output_depth,
        )
        result = await convert_pdf_to_markdown(
            input_path=input_path,
            output_dir=output_dir,
            title=args.title,
            config=config_pdf,
        )

    if not result:
        logger.error("❌ Conversion failed")
        return 1

    # Print summary + success banner
    print_conversion_summary(result)
    print_success_banner()

    return 0


def parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments and support positional input paths."""

    parser = argparse.ArgumentParser(
        description="Convert EPUB/MOBI/PDF documents to structured Markdown for docs-mcp-server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Convert EPUB to Markdown
    %(prog)s --input book.epub --output ./docs/my-book

    # Convert with custom title
    %(prog)s --input guide.epub --output ./docs/guide --title "My Guide"

  # Inspect file before conversion
  %(prog)s --inspect book.epub

  # List supported formats
  %(prog)s --list-formats

For more information, see: https://github.com/pankaj28843/docs-mcp-server
        """,
    )

    parser.add_argument(
        "--input",
        "-i",
        help="Input file path (EPUB, MOBI, or PDF)",
    )

    parser.add_argument(
        "--output",
        "--output-dir",
        "-o",
        dest="output",
        help="Output directory for converted Markdown (default: ./converted-docs/<slug>; env: CONVERT_DOCS_OUTPUT_DIR or EBOOK_TOOLS_OUTPUT_DIR)",
    )

    parser.add_argument(
        "--title",
        "-t",
        help="Override book title (optional, uses metadata by default)",
    )

    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Inspect file metadata without converting",
    )

    parser.add_argument(
        "--list-formats",
        action="store_true",
        help="List all supported document formats",
    )

    parser.add_argument(
        "--max-output-depth",
        "--max-depth",
        dest="max_output_depth",
        type=int,
        default=2,
        help="Maximum directory depth for emitted Markdown (1 = legacy flat layout)",
    )

    parser.add_argument(
        "input_path",
        nargs="?",
        help="Optional positional input path (e.g., %(prog)s --inspect book.epub)",
    )

    args = parser.parse_args(argv)

    positional_value = getattr(args, "input_path", None)
    if positional_value and not args.input:
        args.input = positional_value
    elif positional_value and args.input and args.input != positional_value:
        logger.warning(
            "Positional input %s ignored because --input %s was provided",
            positional_value,
            args.input,
        )

    return args


def main(argv: Sequence[str] | None = None):
    """Main entry point."""
    args = parse_cli_args(argv)

    # Validate argument combinations
    if args.inspect and args.output:
        print("⚠️  --output is ignored when using --inspect")

    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
