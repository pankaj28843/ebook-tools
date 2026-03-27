"""Shared base class for EPUB and PDF converters.

Centralizes output emission logic (flat vs structured), slugification,
file numbering, and section file management.
"""

import shutil
from pathlib import Path

from slugify import slugify

from .epub_models import Chapter, Section


def make_slug(text: str | None, *, fallback: str = "untitled", max_length: int = 80) -> str:
    """Create a filesystem-safe slug from arbitrary text.

    Uses python-slugify for proper Unicode transliteration.
    """
    if not text or not text.strip():
        return fallback
    result = slugify(text, max_length=max_length, word_boundary=True, save_order=True)
    return result or fallback


class BaseConverter:
    """Mixin providing shared output-emission helpers for EPUB and PDF converters."""

    def _determine_padding(self, count: int) -> int:
        if count < 10:
            return 1
        return len(str(count))

    def _format_number(self, value: int, width: int) -> str:
        return str(value).zfill(width) if width > 1 else str(value)

    def _emit_output_files(self, chapters: list[Chapter], output_dir: Path, max_output_depth: int) -> None:
        if max_output_depth <= 1:
            self._flatten_sections(chapters, output_dir)
        else:
            self._write_structured_sections(chapters, output_dir)

    def _write_structured_sections(self, chapters: list[Chapter], output_dir: Path) -> None:
        if not chapters:
            return

        padding = self._determine_padding(len(chapters))

        for index, chapter in enumerate(chapters, start=1):
            existing_sections = [s for s in chapter.sections if Path(s.file_path).exists()]
            if len(existing_sections) <= 1:
                self._write_chapter_flat_file(chapter, output_dir, index, padding)
                continue

            chapter_slug = make_slug(
                chapter.title,
                fallback=f"chapter-{self._format_number(index, padding)}",
            )
            chapter.slug = chapter_slug

            chapter_dir_name = f"{self._format_number(index, padding)}-{chapter.slug}"
            final_dir = output_dir / chapter_dir_name
            if final_dir.exists():
                shutil.rmtree(final_dir)
            final_dir.mkdir(parents=True, exist_ok=True)

            section_padding = self._determine_padding(len(existing_sections))
            for section_index, section in enumerate(existing_sections, start=1):
                self._move_section_file(
                    section=section,
                    destination_dir=final_dir,
                    section_index=section_index,
                    padding=section_padding,
                )

            chapter.output_filename = None
            chapter.output_path = str(final_dir)

            shutil.rmtree(chapter.working_dir, ignore_errors=True)

    def _move_section_file(
        self,
        *,
        section: Section,
        destination_dir: Path,
        section_index: int,
        padding: int,
    ) -> None:
        source_path = Path(section.file_path)
        if not source_path.exists():
            return

        slug = make_slug(section.slug_hint, fallback="section")
        final_name = f"{self._format_number(section_index, padding)}-{slug}.md"
        final_path = destination_dir / final_name
        if final_path.exists():
            final_path.unlink()

        source_path.replace(final_path)

        section.filename = final_name
        section.file_path = str(final_path)

    def _write_chapter_flat_file(
        self,
        chapter: Chapter,
        output_dir: Path,
        index: int,
        padding: int,
    ) -> None:
        chapter_slug = make_slug(
            chapter.title,
            fallback=f"chapter-{self._format_number(index, padding)}",
        )
        chapter.slug = chapter_slug

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

    def _flatten_sections(self, chapters: list[Chapter], output_dir: Path) -> None:
        if not chapters:
            return

        padding = self._determine_padding(len(chapters))

        for index, chapter in enumerate(chapters, start=1):
            self._write_chapter_flat_file(chapter, output_dir, index, padding)
