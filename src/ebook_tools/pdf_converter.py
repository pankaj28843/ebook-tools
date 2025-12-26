"""
PDF to Structured Markdown Converter

This module provides functionality to convert PDF technical books into structured Markdown files.
Each chapter becomes a folder, and each section within the chapter becomes a separate .md file.

The conversion leverages PyMuPDF (fitz) for text extraction and pymupdf4llm for markdown conversion.
It preserves the original book's logical structure including:
- Headings (h1, h2, h3, etc.) detected by font size analysis
- Paragraphs and text formatting (bold, italic)
- Lists (ordered and unordered)
- Code blocks and inline code
- Links and images
- Tables

Typical usage:
    converter = PdfConverter()
    result = await converter.convert_pdf_to_markdown("book.pdf", "output_dir")
    print(f"Converted {result.chapters_count} chapters with {result.sections_count} sections")
"""

import json
from collections import defaultdict
from pathlib import Path
import re
import shutil


try:
    import fitz  # PyMuPDF
except ImportError as e:
    raise ImportError("PyMuPDF is required for PDF conversion. Install with: uv add pymupdf") from e

try:
    import pymupdf4llm
except ImportError as e:
    raise ImportError("pymupdf4llm is required for PDF to Markdown conversion. Install with: uv add pymupdf4llm") from e

from pydantic import BaseModel, Field

from .epub_models import ConversionResult, EpubChapter, EpubSection


class PdfConverterConfig(BaseModel):
    """Configuration for PDF conversion process."""

    preserve_images: bool = Field(default=True, description="Extract and preserve images from PDF")
    clean_filenames: bool = Field(default=True, description="Clean filenames to be filesystem-safe")
    use_pdf_outlines: bool = Field(default=True, description="Use PDF bookmarks/outlines to detect chapters")
    max_section_depth: int = Field(default=2, description="Maximum heading depth (2 = split at h2)")
    code_language: str | None = Field(default=None, description="Default language for code blocks")
    include_toc: bool = Field(default=True, description="Generate table of contents")
    heading_style: str = Field(default="ATX", description="Heading style for markdown (ATX uses # syntax)")


class PdfConverter:
    """
    Converts PDF files to structured Markdown directories.

    This converter follows a similar pattern to EpubConverter:
    1. Load PDF using PyMuPDF (fitz)
    2. Extract outline/TOC if available to identify chapters
    3. Use pymupdf4llm to convert pages to Markdown
    4. Split by sections (h2 headings)
    5. Save organized folder structure
    6. Extract and organize images
    """

    def __init__(self, config: PdfConverterConfig | None = None):
        """Initialize the converter with optional configuration."""
        self.config = config or PdfConverterConfig()
        self._images_extracted: dict[str, str] = {}  # Maps original names to extracted paths

    async def convert_pdf_to_markdown(
        self, pdf_path: str | Path, output_dir: str | Path, book_title: str | None = None
    ) -> ConversionResult:
        """
        Convert a PDF file to structured Markdown.

        Args:
            pdf_path: Path to the PDF file
            output_dir: Directory where Markdown files will be created
            book_title: Optional title override (defaults to PDF metadata)

        Returns:
            ConversionResult with statistics and file paths
        """
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Load the PDF
        doc = fitz.open(str(pdf_path))

        # Extract book metadata
        book_title = book_title or self._extract_book_title(doc)

        # Create images directory if needed
        images_dir = output_dir / "images"
        if self.config.preserve_images:
            images_dir.mkdir(exist_ok=True)

        # Extract chapters using outline or fallback to single chapter
        chapters_info = self._extract_chapters_info(doc)

        # Process each chapter
        chapters = []
        total_sections = 0
        temp_chapter_index = 1

        for chap_title, start_page, end_page in chapters_info:
            chapter = await self._process_chapter(
                doc,
                chap_title,
                start_page,
                end_page,
                output_dir,
                images_dir,
                pdf_path.name,
                temp_chapter_index,
            )
            temp_chapter_index += 1
            if chapter.sections:
                chapters.append(chapter)
                total_sections += len(chapter.sections)
            else:
                shutil.rmtree(chapter.folder_path, ignore_errors=True)

        self._apply_chapter_numbering(chapters)

        # Generate table of contents if enabled
        toc_readme_path = None
        toc_json_path = None
        if self.config.include_toc:
            toc_readme_path, toc_json_path = await self._generate_toc(chapters, output_dir, book_title)

        doc.close()

        return ConversionResult(
            book_title=book_title,
            chapters_count=len(chapters),
            sections_count=total_sections,
            output_directory=str(output_dir),
            chapters=chapters,
            table_of_contents_path=str(toc_readme_path) if toc_readme_path else None,
            toc_json_path=str(toc_json_path) if toc_json_path else None,
        )

    def _extract_chapters_info(self, doc: fitz.Document) -> list[tuple[str, int, int]]:
        """
        Extract chapter information from PDF outline or create default chapter.

        Returns:
            List of (chapter_title, start_page, end_page) tuples
        """
        if not self.config.use_pdf_outlines:
            # Treat whole document as one chapter
            return [("Full Document", 0, doc.page_count)]

        outline = doc.get_toc(simple=False)  # Get outline with level, title, page
        if not outline:
            # No outline - treat as single chapter
            return [("Full Document", 0, doc.page_count)]

        # Extract level-1 entries as chapters
        chapters_info = []
        level_1_entries = [(i, entry) for i, entry in enumerate(outline) if entry[0] == 1]

        for idx, (_entry_idx, entry) in enumerate(level_1_entries):
            _level, title, page = entry[0], entry[1], entry[2]

            # Find next chapter to determine end page
            if idx + 1 < len(level_1_entries):
                next_entry_idx = level_1_entries[idx + 1][0]
                next_entry = outline[next_entry_idx]
                end_page = next_entry[2] - 1  # End just before next chapter
            else:
                end_page = doc.page_count

            # Convert to 0-based index
            start_page = page - 1 if page > 0 else 0
            chapters_info.append((title, start_page, end_page))

        if not chapters_info:
            # Outline exists but no level-1 entries
            return [("Full Document", 0, doc.page_count)]

        return chapters_info

    async def _process_chapter(
        self,
        doc: fitz.Document,
        chapter_title: str,
        start_page: int,
        end_page: int,
        output_dir: Path,
        images_dir: Path,
        pdf_filename: str,
        temp_index: int,
    ) -> EpubChapter:
        """Process a single chapter from the PDF."""
        # Create chapter folder
        folder_slug = f"chapter-temp-{temp_index:04d}"
        chapter_dir = output_dir / folder_slug
        chapter_dir.mkdir(parents=True, exist_ok=True)

        # Convert chapter pages to markdown
        page_range = list(range(start_page, end_page))

        # Use pymupdf4llm to convert to markdown
        # Note: image_path must be str (API doesn't accept None, even if write_images=False)
        md_text = pymupdf4llm.to_markdown(
            doc,
            pages=page_range,
            page_chunks=False,  # Get one continuous markdown string
            write_images=self.config.preserve_images,
            image_path=str(images_dir),
            image_format="png",
        )

        # Add code language hints if configured
        if self.config.code_language:
            md_text = self._add_code_language_hints(md_text, self.config.code_language)

        # Split markdown into sections by ## headings
        sections = self._split_markdown_by_heading(md_text, chapter_title)

        # Create markdown files for each section
        chapter_sections = []
        section_index = 1
        for sec_title, sec_content in sections:
            section = await self._create_section_file(
                sec_title,
                sec_content,
                chapter_dir,
                images_dir,
                section_index,
            )
            if section:
                chapter_sections.append(section)
                section_index += 1

        return EpubChapter(
            title=chapter_title,
            folder_name=folder_slug,
            folder_path=str(chapter_dir),
            sections=chapter_sections,
            source_file=pdf_filename,
        )

    def _split_markdown_by_heading(self, md_text: str, chapter_title: str) -> list[tuple[str, str]]:
        """
        Split markdown text into sections by ## headings.

        Returns:
            List of (section_title, section_content) tuples
        """
        # Find all ## headings (level 2)
        heading_pattern = r"^##\s+(.+?)$"
        lines = md_text.split("\n")
        sections = []
        current_section_title = None
        current_section_lines = []

        # Handle content before first ## (introduction)
        in_intro = True

        for line in lines:
            match = re.match(heading_pattern, line)
            if match:
                # Found a section heading
                if in_intro:
                    # Save intro section if it has content
                    if current_section_lines:
                        intro_content = "\n".join(current_section_lines).strip()
                        if intro_content:
                            sections.append(("Introduction", intro_content))
                    in_intro = False
                elif current_section_title:
                    # Save previous section
                    section_content = "\n".join(current_section_lines).strip()
                    if section_content:
                        sections.append((current_section_title, section_content))

                # Start new section
                current_section_title = match.group(1).strip()
                current_section_lines = [line]  # Include heading
            else:
                current_section_lines.append(line)

        # Save last section
        if current_section_title:
            section_content = "\n".join(current_section_lines).strip()
            if section_content:
                sections.append((current_section_title, section_content))
        elif current_section_lines:
            # No sections found - treat entire content as one section
            content = "\n".join(current_section_lines).strip()
            if content:
                sections.append((chapter_title, content))

        return sections if sections else [(chapter_title, md_text)]

    async def _create_section_file(
        self,
        section_title: str,
        section_content: str,
        chapter_dir: Path,
        images_dir: Path,
        section_index: int,
    ) -> EpubSection | None:
        """Create a markdown file for a section."""
        if not section_content.strip():
            return None

        # Fix image paths to be relative from chapter folder
        section_content = self._fix_image_paths(section_content, images_dir, chapter_dir)

        filename = f"section-temp-{section_index:04d}.md"
        file_path = chapter_dir / filename

        # Write to file
        file_path.write_text(section_content, encoding="utf-8")

        return EpubSection(
            title=section_title,
            filename=filename,
            file_path=str(file_path),
            word_count=len(section_content.split()),
            character_count=len(section_content),
            slug_hint=self._slugify(section_title, fallback="section"),
        )

    def _fix_image_paths(self, content: str, images_dir: Path, chapter_dir: Path) -> str:
        """Fix image paths in markdown to be relative from chapter folder."""
        if not self.config.preserve_images:
            return content

        # Images are in ../images/ relative to chapter folder
        # PyMuPDF4LLM outputs ![](image.png) format
        # We need to change to ![](../images/image.png)

        # Pattern for markdown images: ![alt text](path)
        def replace_image_path(match):
            alt_text = match.group(1)
            img_path = match.group(2)

            # Check if path is already relative or absolute
            if img_path.startswith(("../", "/")):
                return match.group(0)

            # Make relative to chapter folder
            relative_path = f"../images/{Path(img_path).name}"
            return f"![{alt_text}]({relative_path})"

        content = re.sub(r"!\[(.*?)\]\(([^)]+)\)", replace_image_path, content)

        return content

    def _add_code_language_hints(self, md_text: str, language: str) -> str:
        """Add language hints to code fences."""
        # Find code fences without language and add hint
        # Pattern: ``` at start of line (not followed by language)
        pattern = r"^```\s*$"
        replacement = f"```{language}"
        return re.sub(pattern, replacement, md_text, flags=re.MULTILINE)

    def _extract_book_title(self, doc: fitz.Document) -> str:
        """Extract book title from PDF metadata."""
        metadata = doc.metadata
        if metadata and "title" in metadata and metadata["title"]:
            return metadata["title"]
        return "Untitled PDF"

    def _clean_filename(self, filename: str) -> str:
        """Clean filename to be filesystem-safe."""
        cleaned = re.sub(r'[<>:"/\\|?*]', "", filename)
        cleaned = re.sub(r"[^\w\s\-._()]", "", cleaned)
        cleaned = re.sub(r"\s+", "-", cleaned.strip())
        cleaned = cleaned.lower()
        cleaned = cleaned.strip("-")[:100]
        return cleaned or "unnamed"

    def _slugify(self, text: str | None, fallback: str) -> str:
        if not text:
            return fallback
        slug = self._clean_filename(text)
        return slug or fallback

    def _determine_padding(self, count: int) -> int:
        """Determine how many digits to pad based on total count."""
        if count < 10:
            return 1
        return len(str(count))

    def _format_number(self, value: int, width: int) -> str:
        return str(value).zfill(width) if width > 1 else str(value)

    def _apply_chapter_numbering(self, chapters: list[EpubChapter]) -> None:
        """Rename chapter folders using slugified titles while keeping section numbering stable."""
        if not chapters:
            return

        chapter_padding = self._determine_padding(len(chapters))
        slug_counts: dict[str, int] = defaultdict(int)

        for index, chapter in enumerate(chapters, start=1):
            current_path = Path(chapter.folder_path)
            chapter_label = self._format_number(index, chapter_padding)
            base_slug = self._slugify(chapter.title, fallback="")
            if not base_slug:
                base_slug = f"chapter-{chapter_label}"
            base_slug = base_slug[:80]

            slug_counts[base_slug] += 1
            occurrence = slug_counts[base_slug]
            folder_slug = base_slug if occurrence == 1 else f"{base_slug}-{occurrence}"

            new_path = current_path
            if current_path.name != folder_slug:
                new_path = current_path.with_name(folder_slug)
                if new_path.exists():
                    shutil.rmtree(new_path)
                current_path.rename(new_path)

            chapter.folder_name = folder_slug
            chapter.folder_path = str(new_path)

            for section in chapter.sections:
                section.file_path = str(Path(new_path) / section.filename)

            self._apply_section_numbering(chapter.sections, chapter_label)

    def _apply_section_numbering(self, sections: list[EpubSection], chapter_label: str) -> None:
        """Rename section files inside a chapter to include numeric prefixes."""
        if not sections:
            return

        section_padding = self._determine_padding(len(sections))

        for index, section in enumerate(sections, start=1):
            current_path = Path(section.file_path)
            section_label = self._format_number(index, section_padding)
            slug = self._slugify(section.slug_hint or section.title, fallback="section")
            slug = slug[:80]
            prefix = f"{chapter_label}.{section_label}"
            new_filename = f"{prefix}-{slug}{current_path.suffix}" if slug else f"{prefix}{current_path.suffix}"

            if current_path.name != new_filename:
                new_path = current_path.with_name(new_filename)
                current_path.rename(new_path)
            else:
                new_path = current_path

            section.filename = new_filename
            section.file_path = str(new_path)

    async def _generate_toc(
        self,
        chapters: list[EpubChapter],
        output_dir: Path,
        book_title: str,
    ) -> tuple[Path, Path]:
        """Generate README.md plus toc.json for downstream tooling."""
        toc_path = output_dir / "README.md"
        json_path = output_dir / "toc.json"

        toc_content = [
            f"# {book_title}",
            "",
            "## Table of Contents",
            "",
        ]

        json_entries: list[dict[str, int | str]] = []

        for chapter_index, chapter in enumerate(chapters, start=1):
            toc_content.append(f"### [{chapter.title}]({chapter.folder_name}/)")
            toc_content.append("")

            json_entries.append(
                {
                    "title": chapter.title,
                    "href": f"{chapter.folder_name}/",
                    "level": 1,
                    "type": "chapter",
                    "chapter_index": chapter_index,
                }
            )

            for section_index, section in enumerate(chapter.sections, start=1):
                section_path = f"{chapter.folder_name}/{section.filename}"
                toc_content.append(f"- [{section.title}]({section_path})")
                json_entries.append(
                    {
                        "title": section.title,
                        "href": section_path,
                        "level": 2,
                        "type": "section",
                        "chapter_index": chapter_index,
                        "section_index": section_index,
                    }
                )
            toc_content.append("")

        # Add statistics
        total_sections = sum(len(chapter.sections) for chapter in chapters)
        total_words = sum(section.word_count for chapter in chapters for section in chapter.sections)

        toc_content.extend(
            [
                "---",
                "",
                "## Book Statistics",
                "",
                f"- **Chapters:** {len(chapters)}",
                f"- **Sections:** {total_sections}",
                f"- **Total Word Count:** {total_words}",
            ]
        )

        toc_path.write_text("\n".join(toc_content), encoding="utf-8")

        json_payload = {
            "book_title": book_title,
            "chapters": len(chapters),
            "sections": total_sections,
            "total_word_count": total_words,
            "entries": json_entries,
        }
        json_path.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")

        return toc_path, json_path
