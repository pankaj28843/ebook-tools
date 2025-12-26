"""
PDF to Flattened Markdown Converter

Transforms PDF technical books into numbered Markdown files placed directly in the
output directory. Assets remain under a shared `images/` folder while **chapter** files
receive deterministic prefixes (`NN-chapter-slug.md`).

The conversion leverages PyMuPDF (fitz) for text extraction and pymupdf4llm for
Markdown conversion. It preserves:
- Headings detected by font analysis (mapped to #/## levels)
- Lists, code blocks, tables, inline formatting
- Image references (rewritten to `images/<asset>`)

Typical usage:
    converter = PdfConverter()
    result = await converter.convert_pdf_to_markdown("book.pdf", "output_dir")
    print(f"Converted {result.chapters_count} chapters with {result.sections_count} sections")
"""

from pathlib import Path
import re
import shutil

try:
    import fitz  # PyMuPDF
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError("PyMuPDF is required for PDF conversion. Install with: uv add pymupdf") from exc

try:
    import pymupdf4llm
except ImportError as exc:  # pragma: no cover - import guard
    raise ImportError(
        "pymupdf4llm is required for PDF to Markdown conversion. Install with: uv add pymupdf4llm"
    ) from exc

from pydantic import BaseModel, Field

from .epub_models import ConversionResult, EpubChapter, EpubSection


class PdfConverterConfig(BaseModel):
    """Configuration for PDF conversion process."""

    preserve_images: bool = Field(default=True, description="Extract and preserve images from PDF")
    clean_filenames: bool = Field(default=True, description="Clean filenames to be filesystem-safe")
    use_pdf_outlines: bool = Field(default=True, description="Use PDF bookmarks/outlines to detect chapters")
    max_section_depth: int = Field(default=2, description="Maximum heading depth (2 = split at h2)")
    code_language: str | None = Field(default=None, description="Default language for code blocks")
    heading_style: str = Field(default="ATX", description="Heading style for markdown (ATX uses # syntax)")


class PdfConverter:
    """Convert PDF files to flattened Markdown outputs."""

    def __init__(self, config: PdfConverterConfig | None = None) -> None:
        self.config = config or PdfConverterConfig()

    async def convert_pdf_to_markdown(
        self,
        pdf_path: str | Path,
        output_dir: str | Path,
        book_title: str | None = None,
    ) -> ConversionResult:
        pdf_path = Path(pdf_path)
        output_dir = Path(output_dir)

        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found: {pdf_path}")

        output_dir.mkdir(parents=True, exist_ok=True)

        doc = fitz.open(str(pdf_path))
        try:
            book_title = book_title or self._extract_book_title(doc)
            if self.config.preserve_images:
                (output_dir / "images").mkdir(exist_ok=True)

            chapters_info = self._extract_chapters_info(doc)
            chapters: list[EpubChapter] = []
            temp_chapter_index = 1

            for chapter_title, start_page, end_page in chapters_info:
                chapter = await self._process_chapter(
                    doc=doc,
                    chapter_title=chapter_title,
                    start_page=start_page,
                    end_page=end_page,
                    output_dir=output_dir,
                    pdf_filename=pdf_path.name,
                    temp_index=temp_chapter_index,
                )
                temp_chapter_index += 1
                if chapter.sections:
                    chapters.append(chapter)
                else:
                    shutil.rmtree(chapter.working_dir, ignore_errors=True)

            self._flatten_sections(chapters, output_dir)
            sections_count = sum(len(chapter.sections) for chapter in chapters)
        finally:
            doc.close()

        return ConversionResult(
            book_title=book_title,
            chapters_count=len(chapters),
            sections_count=sections_count,
            output_directory=str(output_dir),
            chapters=chapters,
            table_of_contents_path=None,
            toc_json_path=None,
        )

    def _extract_chapters_info(self, doc: fitz.Document) -> list[tuple[str, int, int]]:
        """Return chapter tuples `(title, start_page, end_page)` using outlines when available."""

        if not self.config.use_pdf_outlines:
            return [("Full Document", 0, doc.page_count)]

        outline = doc.get_toc(simple=False)
        if not outline:
            return [("Full Document", 0, doc.page_count)]

        def _entry_level(entry: list) -> int | None:
            try:
                return int(entry[0])
            except (IndexError, TypeError, ValueError):
                return None

        def _entry_title(entry: list, fallback_index: int) -> str:
            if len(entry) > 1 and isinstance(entry[1], str):
                title = entry[1].strip()
                if title:
                    return title
            return f"Chapter {fallback_index}"

        def _entry_start_page(entry: list) -> int:
            if len(entry) > 2:
                try:
                    return max(int(entry[2]) - 1, 0)
                except (TypeError, ValueError):
                    return 0
            return 0

        level_1_entries = [entry for entry in outline if _entry_level(entry) == 1]
        if not level_1_entries:
            return [("Full Document", 0, doc.page_count)]

        chapters_info: list[tuple[str, int, int]] = []
        for idx, entry in enumerate(level_1_entries):
            title = _entry_title(entry, idx + 1)
            start_page = _entry_start_page(entry)

            if idx + 1 < len(level_1_entries):
                next_start = _entry_start_page(level_1_entries[idx + 1])
                end_page = max(next_start, start_page)
            else:
                end_page = doc.page_count

            chapters_info.append((title, start_page, end_page))

        return chapters_info or [("Full Document", 0, doc.page_count)]

    async def _process_chapter(
        self,
        doc: fitz.Document,
        chapter_title: str,
        start_page: int,
        end_page: int,
        output_dir: Path,
        pdf_filename: str,
        temp_index: int,
    ) -> EpubChapter:
        """Convert a single chapter slice into temporary section files."""

        chapter_dir = output_dir / f"chapter-temp-{temp_index:04d}"
        chapter_dir.mkdir(parents=True, exist_ok=True)

        page_range = list(range(start_page, end_page))
        markdown_text = pymupdf4llm.to_markdown(
            doc,
            pages=page_range,
            page_chunks=False,
            write_images=self.config.preserve_images,
            image_path=str(output_dir / "images"),
            image_format="png",
        )

        if self.config.code_language:
            markdown_text = self._add_code_language_hints(markdown_text, self.config.code_language)

        sections = self._split_markdown_by_heading(markdown_text, chapter_title)

        chapter_sections: list[EpubSection] = []
        section_index = 1
        for section_title, section_content in sections:
            section = await self._create_section_file(
                section_title=section_title,
                section_content=section_content,
                chapter_dir=chapter_dir,
                section_index=section_index,
            )
            if section:
                chapter_sections.append(section)
                section_index += 1

        return EpubChapter(
            title=chapter_title,
            slug=self._slugify(chapter_title, fallback="chapter"),
            working_dir=str(chapter_dir),
            sections=chapter_sections,
            source_file=pdf_filename,
        )

    def _split_markdown_by_heading(self, md_text: str, chapter_title: str) -> list[tuple[str, str]]:
        """Split markdown into sections using `##` headings (with intro fallback)."""

        heading_pattern = r"^##\s+(.+?)$"
        lines = md_text.split("\n")
        sections: list[tuple[str, str]] = []
        current_section_title: str | None = None
        current_section_lines: list[str] = []
        in_intro = True

        for line in lines:
            match = re.match(heading_pattern, line)
            if match:
                if in_intro and current_section_lines:
                    intro_content = "\n".join(current_section_lines).strip()
                    if intro_content:
                        sections.append(("Introduction", intro_content))
                elif current_section_title and current_section_lines:
                    section_content = "\n".join(current_section_lines).strip()
                    if section_content:
                        sections.append((current_section_title, section_content))

                current_section_title = match.group(1).strip()
                current_section_lines = [line]
                in_intro = False
            else:
                current_section_lines.append(line)

        if current_section_title and current_section_lines:
            section_content = "\n".join(current_section_lines).strip()
            if section_content:
                sections.append((current_section_title, section_content))
        elif current_section_lines:
            content = "\n".join(current_section_lines).strip()
            if content:
                sections.append((chapter_title, content))

        return sections or [(chapter_title, md_text)]

    async def _create_section_file(
        self,
        section_title: str,
        section_content: str,
        chapter_dir: Path,
        section_index: int,
    ) -> EpubSection | None:
        """Write a temporary markdown file for a section."""

        if not section_content.strip():
            return None

        section_content = self._fix_image_paths(section_content)

        filename = f"section-temp-{section_index:04d}.md"
        file_path = chapter_dir / filename
        file_path.write_text(section_content, encoding="utf-8")

        return EpubSection(
            title=section_title,
            filename=filename,
            file_path=str(file_path),
            word_count=len(section_content.split()),
            character_count=len(section_content),
            slug_hint=self._slugify(section_title, fallback="section"),
            source_fragment=None,
        )

    def _fix_image_paths(self, content: str) -> str:
        """Normalize image references to point at the root `images/` folder."""

        if not self.config.preserve_images:
            return content

        def replace_image_path(match: re.Match[str]) -> str:
            alt_text = match.group(1)
            img_path = match.group(2)
            if img_path.startswith(("../", "/", "images/")):
                return match.group(0)
            normalized = f"images/{Path(img_path).name}"
            return f"![{alt_text}]({normalized})"

        return re.sub(r"!\[(.*?)\]\(([^)]+)\)", replace_image_path, content)

    def _add_code_language_hints(self, md_text: str, language: str) -> str:
        pattern = r"^```\s*$"
        replacement = f"```{language}"
        return re.sub(pattern, replacement, md_text, flags=re.MULTILINE)

    def _extract_book_title(self, doc: fitz.Document) -> str:
        metadata = doc.metadata or {}
        title = metadata.get("title")
        return title or "Untitled PDF"

    def _clean_filename(self, filename: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*]', "", filename)
        cleaned = re.sub(r"[^\w\s\-._()]", "", cleaned)
        cleaned = re.sub(r"\s+", "-", cleaned.strip())
        cleaned = cleaned.lower().strip("-")[:100]
        return cleaned or "unnamed"

    def _slugify(self, text: str | None, fallback: str) -> str:
        if not text:
            return fallback
        slug = self._clean_filename(text)
        return slug or fallback

    def _determine_padding(self, count: int) -> int:
        if count < 10:
            return 1
        return len(str(count))

    def _format_number(self, value: int, width: int) -> str:
        return str(value).zfill(width) if width > 1 else str(value)

    def _flatten_sections(self, chapters: list[EpubChapter], output_dir: Path) -> None:
        if not chapters:
            return

        padding = self._determine_padding(len(chapters))

        for index, chapter in enumerate(chapters, start=1):
            chapter_slug = self._slugify(chapter.title, fallback=f"chapter-{self._format_number(index, padding)}")
            chapter.slug = chapter_slug[:80] or "chapter"

            final_filename = f"{self._format_number(index, padding)}-{chapter.slug}.md"
            final_path = output_dir / final_filename
            if final_path.exists():
                final_path.unlink()

            content_parts: list[str] = []
            chapter_title = chapter.title.strip()
            if chapter_title:
                content_parts.append(f"# {chapter_title}")

            for section in chapter.sections:
                section_path = Path(section.file_path)
                section_text = ""
                if section_path.exists():
                    section_text = section_path.read_text(encoding="utf-8").strip()
                if section_text:
                    content_parts.append(section_text)

                section.filename = final_filename
                section.file_path = str(final_path)

            combined = "\n\n".join(part for part in (part.strip() for part in content_parts) if part)
            if not combined:
                combined = f"# {chapter.title or 'Chapter'}"

            final_path.write_text(combined.rstrip() + "\n", encoding="utf-8")

            chapter.output_filename = final_filename
            chapter.output_path = str(final_path)

            shutil.rmtree(chapter.working_dir, ignore_errors=True)
