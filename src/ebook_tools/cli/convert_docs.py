#!/usr/bin/env python3
"""Document Conversion Script for ebook-tools.

🔄 Convert various document formats (EPUB, MOBI, PDF) to structured Markdown
    that can be served via filesystem tenants managed in deployment.json.

Features:
- Converts EPUB/MOBI/PDF to organized Markdown directory
- Each chapter becomes a folder with section files
- Generates table of contents (README.md)
- Preserves images and code blocks
- Updates deployment.json automatically (or provides a snippet when skipped)
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

    # Use custom output directory (default: ./converted-docs)
    uv run convert-docs --input book.epub --output ./docs/my-book

After conversion:
1. The script updates deployment.json (override via --deployment-file)
2. Pass --skip-deployment-update if you only want the Markdown tree
3. Restart docs-mcp-server (or any consumer expecting filesystem tenants)
4. Your book is now available at http://localhost:42042/{codename}/mcp
"""

import argparse
import asyncio
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Sequence

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


def _slugify_codename(value: str | None) -> str | None:
    """Normalize a value into a codename-friendly slug."""
    if not value:
        return None

    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug or None


def _derive_codename(
    provided_codename: str | None,
    title: str | None,
    input_path: Path,
) -> tuple[str, str]:
    """Return a codename plus the source that produced it."""

    candidates = (
        ("flag", provided_codename),
        ("title", title),
        ("filename", input_path.stem),
    )
    for source, candidate in candidates:
        slug = _slugify_codename(candidate)
        if slug:
            return slug, source

    return "book", "fallback"


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
    codename: str,
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
    codename: str,
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


def generate_deployment_snippet(
    codename: str,
    docs_name: str,
    output_dir: Path,
) -> dict[str, Any]:
    """Generate deployment.json snippet for the converted docs."""
    # Convert absolute path to relative from project root or ~/relative if it's under home directory
    absolute_path = output_dir.resolve()
    cwd_path = Path.cwd()
    home_path = Path.home()

    try:
        # First try to make it relative to current working directory (project root)
        relative_to_cwd = absolute_path.relative_to(cwd_path)
        docs_root_path = f"./{relative_to_cwd}"
    except ValueError:
        try:
            # If not under cwd, try to make it relative to home directory
            relative_to_home = absolute_path.relative_to(home_path)
            docs_root_path = f"~/{relative_to_home}"
        except ValueError:
            # If neither works, use absolute path
            docs_root_path = str(absolute_path)

    return {
        "source_type": "filesystem",
        "codename": codename,
        "docs_name": docs_name,
        "docs_root_dir": docs_root_path,
    }


def _load_manifest(manifest_path: Path) -> tuple[dict[str, Any], bool]:
    if not manifest_path.exists():
        return {"tenants": []}, True

    try:
        with manifest_path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"deployment manifest {manifest_path} is not valid JSON") from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"deployment manifest {manifest_path} must contain a top-level JSON object")

    tenants = data.get("tenants")
    if tenants is None:
        data["tenants"] = []
    elif not isinstance(tenants, list):
        raise RuntimeError(f"deployment manifest {manifest_path} must store 'tenants' as a list")

    return data, False


def update_deployment_manifest(manifest_path: Path, tenant_entry: dict[str, Any]) -> str:
    """Create or update the deployment manifest with the provided tenant."""

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    data, created = _load_manifest(manifest_path)
    tenants: list[Any] = data["tenants"]
    codename = tenant_entry["codename"]

    replaced = False
    for index, tenant in enumerate(tenants):
        if isinstance(tenant, dict) and tenant.get("codename") == codename:
            tenants[index] = tenant_entry
            replaced = True
            break

    if not replaced:
        tenants.append(tenant_entry)

    with manifest_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
        file.write("\n")

    if created:
        return f"created new manifest with tenant '{codename}'"

    if replaced:
        return f"updated tenant '{codename}'"

    return f"appended tenant '{codename}'"


def print_deployment_summary(action: str, manifest_path: Path, codename: str, skipped: bool) -> None:
    """Print a succinct deployment summary."""

    print("📦 Deployment Manifest:\n")
    print(f"  File:   {manifest_path}")
    print(f"  Tenant: {codename}")
    if skipped:
        print("  Action: skipped (--skip-deployment-update)")
    else:
        print(f"  Action: {action}")
    print()


def print_conversion_summary(result: ConversionResult):
    """Print conversion statistics."""
    print("\n📊 Conversion Statistics:\n")
    print(f"  Book Title:    {result.book_title}")
    print(f"  Chapters:      {result.chapters_count}")
    print(f"  Sections:      {result.sections_count}")
    print(f"  Output Dir:    {result.output_directory}")

    if result.table_of_contents_path:
        print(f"  TOC README:    {result.table_of_contents_path}")
    if result.toc_json_path:
        print(f"  TOC JSON:      {result.toc_json_path}")

    print("\n📁 Generated Structure:\n")

    # Show directory tree (first 3 chapters)
    output_path = Path(result.output_directory)
    chapters_to_show = min(3, len(result.chapters))

    print(f"  {output_path.name}/")
    toc_artifacts = []
    if result.table_of_contents_path:
        toc_artifacts.append("README.md (table of contents)")
    if result.toc_json_path:
        toc_artifacts.append("toc.json (machine-readable TOC)")

    for idx, artifact in enumerate(toc_artifacts):
        is_last_artifact = idx == len(toc_artifacts) - 1 and chapters_to_show == 0
        prefix = "└──" if is_last_artifact else "├──"
        print(f"  {prefix} {artifact}")

    for i, chapter in enumerate(result.chapters[:chapters_to_show]):
        is_last = i == len(result.chapters) - 1 and len(result.chapters) <= chapters_to_show
        prefix = "└──" if is_last else "├──"

        print(f"  {prefix} {chapter.folder_name}/")

        sections_to_show = min(3, len(chapter.sections))
        for j, section in enumerate(chapter.sections[:sections_to_show]):
            is_last_section = j == len(chapter.sections) - 1 and len(chapter.sections) <= sections_to_show
            section_prefix = "    └──" if is_last_section else "    ├──"
            print(f"  {section_prefix} {section.filename}")

        if len(chapter.sections) > sections_to_show:
            print(f"      └── ... ({len(chapter.sections) - sections_to_show} more sections)")

    if len(result.chapters) > chapters_to_show:
        print(f"  └── ... ({len(result.chapters) - chapters_to_show} more chapters)")

    print()


async def main_async(args):  # noqa: PLR0911 - CLI function with multiple exit paths
    """Async main function."""
    print_banner()

    # Handle --list-formats
    if args.list_formats:
        list_supported_formats()
        return 0

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

    codename, codename_source = _derive_codename(args.codename, args.title, input_path)

    # Determine output directory
    if args.output:
        output_dir = Path(args.output).expanduser().resolve()
    else:
        # Default: ./mcp-data/{codename} (in current project directory)
        default_base = Path.cwd() / "converted-docs"
        output_dir = default_base / codename
        logger.info(f"Using default output directory: {output_dir}")

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"📂 Output: {output_dir}")
    codename_notes = {
        "flag": "",
        "title": " (auto-derived from title)",
        "filename": " (auto-derived from filename)",
        "fallback": " (auto-derived fallback)",
    }
    note = codename_notes.get(codename_source, "")
    print(f"🏷️  Codename: {codename}{note}")

    if args.title:
        print(f"📖 Title: {args.title}")

    print("\n⏳ Starting conversion...\n")

    # Perform conversion based on format
    result = None
    if file_format == "epub":
        config = EpubConverterConfig(
            heading_style="ATX",
            strip_unwanted_tags=True,
            preserve_images=True,
            include_toc=True,
            clean_filenames=True,
        )
        result = await convert_epub_to_markdown(
            input_path=input_path,
            output_dir=output_dir,
            codename=codename,
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
            include_toc=True,
        )
        result = await convert_pdf_to_markdown(
            input_path=input_path,
            output_dir=output_dir,
            codename=codename,
            title=args.title,
            config=config_pdf,
        )

    if not result:
        logger.error("❌ Conversion failed")
        return 1

    # Print summary + success banner
    print_conversion_summary(result)
    print_success_banner()

    deployment_file_arg = getattr(args, "deployment_file", Path("deployment.json"))
    deployment_file = Path(deployment_file_arg).expanduser().resolve()
    snippet = generate_deployment_snippet(
        codename=codename,
        docs_name=args.title or result.book_title,
        output_dir=output_dir,
    )

    skipped = bool(getattr(args, "skip_deployment_update", False))
    if skipped:
        action = "skipped"
    else:
        action = update_deployment_manifest(deployment_file, snippet)

    print_deployment_summary(action=action, manifest_path=deployment_file, codename=codename, skipped=skipped)

    return 0


def parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments and support positional input paths."""

    parser = argparse.ArgumentParser(
        description="Convert EPUB/MOBI/PDF documents to structured Markdown for docs-mcp-server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert EPUB to Markdown
  %(prog)s --input book.epub --output ./docs/my-book --codename my-book

  # Convert with custom title
  %(prog)s --input guide.epub --output ./docs/guide --codename guide --title "My Guide"

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
        "-o",
        help="Output directory for converted Markdown (default: ./mcp-data/{codename})",
    )

    parser.add_argument(
        "--codename",
        "-c",
        help="Tenant codename for deployment.json (required for conversion)",
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
        "--deployment-file",
        type=Path,
        default=Path("deployment.json"),
        help="Path to the deployment manifest to update (default: ./deployment.json)",
    )

    parser.add_argument(
        "--skip-deployment-update",
        action="store_true",
        help="Skip writing deployment manifest updates after conversion",
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
    if args.inspect and args.codename:
        print("⚠️  --codename is ignored when using --inspect")

    if args.inspect and args.output:
        print("⚠️  --output is ignored when using --inspect")

    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
