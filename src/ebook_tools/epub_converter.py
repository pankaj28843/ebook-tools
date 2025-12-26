"""
EPUB to Structured Markdown Converter

This module provides functionality to convert EPUB programming books into structured Markdown files.
Each section becomes a numbered Markdown file in the root output directory using chapter/section slugs.

The conversion preserves the original book's logical structure including:
- Headings (h1, h2, h3, etc.)
- Paragraphs and text formatting
- Lists (ordered and unordered)
- Code blocks and inline code
- Links and images
- Tables and other structural elements

Typical usage:
    converter = EpubConverter()
    result = await converter.convert_epub_to_markdown("book.epub", "output_dir")
    print(f"Converted {result.chapters_count} chapters with {result.sections_count} sections")
"""

from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
import unicodedata
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from bs4 import BeautifulSoup, Tag
from ebooklib import epub
import markdownify
from pydantic import BaseModel, Field

from . import toc_checker
from .epub_models import ConversionResult, EpubChapter, EpubSection


def _normalize_path_value(path: str | None) -> str | None:
    """Return a normalized manifest path (unix separators, stripped prefixes)."""

    if not path:
        return None
    normalized = path.replace("\\", "/").lstrip("./")
    return normalized or None


def _normalize_fragment_value(fragment: str | None) -> str | None:
    """Strip leading # and whitespace from fragment identifiers."""

    if fragment is None:
        return None
    normalized = str(fragment).strip().lstrip("#").strip()
    return normalized or None


def _fragment_from_href_value(href: str | None) -> str | None:
    """Extract a normalized fragment identifier from an href string."""

    if not href:
        return None
    _, _, fragment = href.partition("#")
    return _normalize_fragment_value(fragment)


def _path_from_href_value(href: str | None) -> str | None:
    """Extract a normalized path (without fragment) from an href string."""

    if not href:
        return None
    path, _, _ = href.partition("#")
    return _normalize_path_value(path)


class EpubConverterConfig(BaseModel):
    """Configuration for EPUB conversion process."""

    heading_style: str = Field(default="ATX", description="Heading style for markdown (ATX uses # syntax)")
    code_language: str | None = Field(default=None, description="Default language for code blocks")
    strip_unwanted_tags: bool = Field(default=True, description="Remove script, style and other unwanted tags")
    preserve_images: bool = Field(default=True, description="Extract and preserve images from EPUB")
    max_section_depth: int = Field(default=6, description="Maximum heading depth to consider for sections")
    clean_filenames: bool = Field(default=True, description="Clean filenames to be filesystem-safe")
            soup,
            chapter_title_tag,
            section_headings[0],
            chapter_dir,
            temp_index,
        )
        if intro_section:
            sections.append(intro_section)
            temp_index += 1

        for i, section_heading in enumerate(section_headings):
            next_heading = section_headings[i + 1] if i + 1 < len(section_headings) else None
            section = await self._process_section(
                section_heading,
                next_heading,
                chapter_dir,
                temp_index,
            )
            if section:
                sections.append(section)
                temp_index += 1

        return sections

    async def _process_introduction(
        self,
        soup: BeautifulSoup,
        chapter_title_tag: Tag | None,
        first_section: Tag,
        chapter_dir: Path,
        temp_index: int,
    ) -> EpubSection | None:
        """Process introductory content before the first section."""
        intro_parts = self._collect_intro_parts(
            self._intro_candidates(soup, chapter_title_tag),
            first_section,
        )
        if not intro_parts:
            return None

        intro_html = "".join(str(part) for part in intro_parts).strip()
        if not intro_html:
            return None

        return await self._create_section_from_html(
            intro_html,
            "Introduction",
            "introduction",
            chapter_dir,
            temp_index,
        )

    def _intro_candidates(self, soup: BeautifulSoup, chapter_title_tag: Tag | None):
        """Yield nodes that may form the introduction block."""
        if chapter_title_tag:
            return chapter_title_tag.next_siblings
        if soup.body:
            return soup.body.children
        return soup.children

    def _collect_intro_parts(self, candidates, first_section: Tag):
        """Collect nodes preceding the first section heading."""
        parts = []
        for element in candidates:
            if element == first_section:
                break
            if getattr(element, "name", None):
                parts.append(element)
        return parts

    async def _process_section(
        self,
        section_heading: Tag,
        next_heading: Tag | None,
        chapter_dir: Path,
        temp_index: int,
    ) -> EpubSection | None:
        """Process a single section defined by h2 headings."""
        section_title = section_heading.get_text().strip()
        section_parts = [section_heading]  # Include the heading itself

        # Collect all content until the next heading or end
        current = section_heading.next_sibling
        while current:
            if current == next_heading:
                break
            if hasattr(current, "name"):
                # Stop if we encounter another h1 or h2 (shouldn't happen with next_heading logic)
                if current.name and current.name.lower() in ["h1", "h2"]:  # type: ignore[union-attr]
                    break
                section_parts.append(current)  # type: ignore[arg-type]
            current = current.next_sibling

        # Convert to HTML and then to Markdown
        section_html = "".join(str(part) for part in section_parts)
        return await self._create_section_from_html(
            section_html,
            section_title,
            section_title,
            chapter_dir,
            temp_index,
            source_fragment=self._extract_fragment_id(section_heading),
        )

    def _extract_fragment_id(self, element: Tag | None) -> str | None:
        """Return the normalized fragment identifier for a heading element."""

        if element is None:
            return None
        fragment = element.get("id") or element.get("name")
        if isinstance(fragment, list):  # Defensive: BeautifulSoup can return lists for dup attributes
            fragment = fragment[0] if fragment else None
        return self._normalize_fragment(fragment)

    def _normalize_fragment(self, fragment: str | None) -> str | None:
        """Normalize raw fragment identifiers by stripping prefixes and whitespace."""

        return _normalize_fragment_value(fragment)

    async def _create_section_from_html(
        self,
        html_content: str,
        section_title: str,
        slug_hint: str,
        chapter_dir: Path,
        temp_index: int,
        *,
        source_fragment: str | None = None,
    ) -> EpubSection | None:
        """Create a section from HTML content."""
        if not html_content.strip():
            return None

        # Fix image paths if we extracted images
        html_content = self._fix_image_paths(html_content)

        # Convert to Markdown
        markdown_content = markdownify.markdownify(
            html_content,
            heading_style=self.config.heading_style,
            code_language=self.config.code_language or "",  # markdownify requires str, not None
        )

        if not markdown_content.strip():
            return None

        # Save to file using temporary numbered prefix
        md_filename = f"section-temp-{temp_index:04d}.md"
        md_path = chapter_dir / md_filename

        md_path.write_text(markdown_content, encoding="utf-8")

        return EpubSection(
            title=section_title,
            filename=md_filename,
            file_path=str(md_path),
            word_count=len(markdown_content.split()),
            character_count=len(markdown_content),
            slug_hint=self._slugify(slug_hint, fallback="section"),
            source_fragment=self._normalize_fragment(source_fragment),
        )

    async def _create_section_from_content(
        self,
        soup: BeautifulSoup,
        section_title: str,
        slug_hint: str,
        chapter_dir: Path,
        temp_index: int,
    ) -> EpubSection | None:
        """Create a section from BeautifulSoup content."""
        # Remove the chapter title tag to avoid duplication
        chapter_title_tag = soup.find(["h1", "h2", "h3"])
        if chapter_title_tag:
            chapter_title_tag.decompose()

        # Get remaining content
        content = soup.get_text().strip() if soup.body else ""
        if not content:
            return None

        html_content = str(soup)
        return await self._create_section_from_html(
            html_content,
            section_title,
            slug_hint,
            chapter_dir,
            temp_index,
            source_fragment=None,
        )

    def _extract_chapter_title(self, soup: BeautifulSoup) -> tuple[str, Tag | None]:
        """Extract chapter title from soup content."""
        # Look for h1 first, then h2, then h3
        for tag_name in ["h1", "h2", "h3"]:
            tag = soup.find(tag_name)
            if tag:
                title = tag.get_text().strip()
                if title:
                    return title, tag

        # Fallback: use title tag or first heading
        title_tag = soup.find("title")
        if title_tag:
            return title_tag.get_text().strip(), None

        # Last resort: generic name
        return "Chapter", None

    def _extract_book_title(self, book: epub.EpubBook) -> str:
        """Extract book title from EPUB metadata."""
        title = book.get_metadata("DC", "title")
        if title and title[0]:
            return title[0][0]
        return "Unknown Book"

    def _load_nav_entries(self, book: epub.EpubBook) -> list[toc_checker.TocEntry]:
        """Extract navigation table entries from the EPUB if available."""

        nav_source: Any | None = None
        nav_accessor = getattr(book, "get_toc", None)
        if callable(nav_accessor):
            try:
                nav_source = nav_accessor()
            except Exception:
                nav_source = None

        if nav_source is None and hasattr(book, "toc"):
            nav_source = book.toc

        if not nav_source:
            return []

        try:
            return toc_checker.extract_nav_entries(nav_source)
        except Exception:
            return []

    def _clean_filename(self, filename: str) -> str:
        """Clean filename to be filesystem-safe."""
        cleaned = re.sub(r'[<>:"/\\|?*]', "", filename)
        cleaned = re.sub(r"[^\w\s\-._()]", "", cleaned)
        cleaned = re.sub(r"\s+", "-", cleaned.strip())
        cleaned = cleaned.lower()
        cleaned = cleaned.strip("-")[:100]
        return cleaned or ""

    def _slugify(self, text: str | None, fallback: str) -> str:
        """Generate a deterministic slug, falling back when empty."""
        if not text:
            return fallback
        slug = self._clean_filename(text)
        return slug or fallback

    def _determine_padding(self, count: int) -> int:
        """Return number of digits to pad based on total count."""
        if count < 10:
            return 1
        return len(str(count))

    def _format_number(self, value: int, width: int) -> str:
        """Format numeric index with conditional zero padding."""
        return str(value).zfill(width) if width > 1 else str(value)

    def _apply_nav_titles(
        self,
        chapters: list[EpubChapter],
        nav_entries: Sequence[toc_checker.TocEntry] | None,
    ) -> None:
        """Use navMap entries to enrich chapter titles when possible."""

        if not nav_entries or not chapters:
            return

        chapters_by_source: dict[str, list[EpubChapter]] = defaultdict(list)
        for chapter in chapters:
            source_key = _normalize_path_value(chapter.source_file)
            if source_key:
                chapters_by_source[source_key].append(chapter)

        claimed_ids: set[int] = set()

        for entry in nav_entries:
            if entry.level and entry.level > 1:
                continue
            if not entry.title:
                continue

            normalized_title = entry.title.strip()
            if not normalized_title:
                continue

            matched_chapter: EpubChapter | None = None
            href_path = _path_from_href_value(entry.href)
            if href_path:
                for candidate in chapters_by_source.get(href_path, []):
                    if id(candidate) not in claimed_ids:
                        matched_chapter = candidate
                        break

            if matched_chapter is None:
                entry_key = toc_checker.normalize_title(normalized_title)
                if entry_key:
                    for candidate in chapters:
                        if id(candidate) in claimed_ids:
                            continue
                        if toc_checker.normalize_title(candidate.title) == entry_key:
                            matched_chapter = candidate
                            break

            if matched_chapter is None:
                continue

            matched_chapter.title = normalized_title
            claimed_ids.add(id(matched_chapter))

    def _flatten_sections(self, chapters: list[EpubChapter], output_dir: Path) -> None:
        """Move every section into the root output dir using global numbering."""

        total_sections = sum(len(chapter.sections) for chapter in chapters)
        if total_sections == 0:
            for chapter in chapters:
                shutil.rmtree(chapter.working_dir, ignore_errors=True)
            return

        padding = self._determine_padding(total_sections)
        global_index = 1

        for chapter in chapters:
            first_index_for_chapter = global_index
            chapter_slug = self._slugify(chapter.title, fallback="")
            if not chapter_slug:
                chapter_slug = f"chapter-{self._format_number(first_index_for_chapter, padding)}"
            chapter.slug = chapter_slug[:80] or "chapter"

            for section in chapter.sections:
                current_path = Path(section.file_path)
                section_slug = self._slugify(section.slug_hint or section.title, fallback="section")
                section_slug = section_slug[:80] or "section"

                prefix = self._format_number(global_index, padding)
                suffix = current_path.suffix or ".md"
                base_name = f"{chapter.slug}-{section_slug}".strip("-") or chapter.slug
                new_filename = f"{prefix}-{base_name}{suffix}"
                new_path = output_dir / new_filename
                if new_path.exists():
                    new_path.unlink()

                current_path.rename(new_path)
                section.filename = new_filename
                section.file_path = str(new_path)

                global_index += 1

            shutil.rmtree(chapter.working_dir, ignore_errors=True)

    def _prepare_epub_for_conversion(self, epub_path: Path) -> tuple[Path, Path | None]:
        """Ensure EPUB has all manifest files available; return normalized path."""
        with ZipFile(epub_path) as z:
            names = z.namelist()
            names_set, lower_map, ascii_map = self._build_name_maps(names)

            container_path = self._find_container_path(names)
            if not container_path:
                return epub_path, None

            opf_info = self._load_opf_manifest(z, container_path, names_set, lower_map, ascii_map)
            if not opf_info:
                return epub_path, None
            opf_root, opf_dir = opf_info

            alias_map = self._collect_manifest_aliases(
                opf_root,
                opf_dir,
                names_set,
                lower_map,
                ascii_map,
            )

        if not alias_map:
            return epub_path, None

        temp_file = self._write_epub_with_aliases(epub_path, alias_map)
        return temp_file, temp_file

    def _build_name_maps(self, names: list[str]) -> tuple[set[str], dict[str, str], dict[str, str]]:
        names_set = set(names)
        lower_map = {name.lower(): name for name in names}
        ascii_map = {self._ascii_path(name).lower(): name for name in names}
        return names_set, lower_map, ascii_map

    def _find_container_path(self, names: list[str]) -> str | None:
        for name in names:
            if name.lower().endswith("container.xml"):
                return name
        return None

    def _load_opf_manifest(
        self,
        z: ZipFile,
        container_path: str,
        names_set: set[str],
        lower_map: dict[str, str],
        ascii_map: dict[str, str],
    ) -> tuple[ET.Element, Path] | None:
        container_root = ET.fromstring(z.read(container_path))
        ns = {"ct": "urn:oasis:names:tc:opendocument:xmlns:container"}
        rootfile = container_root.find("ct:rootfiles/ct:rootfile", ns)
        if rootfile is None:
            return None
        opf_path = rootfile.get("full-path")
        resolved_opf_path = self._resolve_zip_path(opf_path, names_set, lower_map, ascii_map)
        if not resolved_opf_path:
            return None
        opf_data = z.read(resolved_opf_path)
        opf_root = ET.fromstring(opf_data)
        opf_dir = Path(resolved_opf_path).parent
        return opf_root, opf_dir

    def _collect_manifest_aliases(
        self,
        opf_root: ET.Element,
        opf_dir: Path,
        names_set: set[str],
        lower_map: dict[str, str],
        ascii_map: dict[str, str],
    ) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        opf_ns = opf_root.tag[1:].split("}")[0] if "}" in opf_root.tag else ""
        manifest_tag = f".//{{{opf_ns}}}manifest" if opf_ns else ".//manifest"
        manifest = opf_root.find(manifest_tag)
        if manifest is None:
            return {}

        item_tag = f"{{{opf_ns}}}item" if opf_ns else "item"
        for item in manifest.findall(item_tag):
            href = item.get("href")
            if not href:
                continue
            target = (opf_dir / href).as_posix()
            if target in names_set:
                continue
            alias = self._find_alias(target, lower_map, ascii_map)
            if alias:
                alias_map[target] = alias
        return alias_map

    def _write_epub_with_aliases(self, epub_path: Path, alias_map: dict[str, str]) -> Path:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp:
            temp_file = Path(tmp.name)

        with ZipFile(epub_path) as src, ZipFile(temp_file, "w", compression=ZIP_DEFLATED) as dst:
            for info in src.infolist():
                data = src.read(info.filename)
                new_info = ZipInfo(info.filename)
                new_info.date_time = info.date_time
                new_info.compress_type = info.compress_type or ZIP_DEFLATED
                new_info.external_attr = info.external_attr
                new_info.create_system = info.create_system
                new_info.flag_bits = info.flag_bits
                dst.writestr(new_info, data)

            for alias, original in alias_map.items():
                orig_info = src.getinfo(original)
                new_info = ZipInfo(alias)
                new_info.date_time = orig_info.date_time
                new_info.compress_type = orig_info.compress_type or ZIP_DEFLATED
                new_info.external_attr = orig_info.external_attr
                new_info.create_system = orig_info.create_system
                dst.writestr(new_info, src.read(original))

        return temp_file

    def _find_alias(
        self,
        target: str,
        lower_map: dict[str, str],
        ascii_map: dict[str, str],
    ) -> str | None:
        lower_target = target.lower()
        if lower_target in lower_map:
            return lower_map[lower_target]
        if lower_target.endswith(".xhtml"):
            html_target = lower_target[:-6] + ".html"
            if html_target in lower_map:
                return lower_map[html_target]
        ascii_target = self._ascii_path(target).lower()
        return ascii_map.get(ascii_target)

    def _resolve_zip_path(
        self,
        target: str | None,
        names_set: set[str],
        lower_map: dict[str, str],
        ascii_map: dict[str, str],
    ) -> str | None:
        if not target:
            return None
        if target in names_set:
            return target
        lower_target = target.lower()
        if lower_target in lower_map:
            return lower_map[lower_target]
        ascii_target = self._ascii_path(target).lower()
        return ascii_map.get(ascii_target)

    def _ascii_path(self, path: str) -> str:
        segments = path.split("/")
        safe_segments = []
        for segment in segments:
            normalized = unicodedata.normalize("NFKD", segment)
            ascii_part = "".join(ch for ch in normalized if ord(ch) < 128)
            safe_segments.append(ascii_part or "_")
        return "/".join(safe_segments)

    def _fix_image_paths(self, html_content: str) -> str:
        """Fix image paths in HTML content to point to extracted images."""
        if not self._images_extracted:
            return html_content

        soup = BeautifulSoup(html_content, "html.parser")
        for img in soup.find_all("img"):
            src = img.get("src")
            # BeautifulSoup can return list for attributes; ensure it's a string
            if isinstance(src, list):
                src = src[0] if src else None
            if src and isinstance(src, str) and src in self._images_extracted:
                img["src"] = self._images_extracted[src]

        return str(soup)

    def _extract_images(self, book: epub.EpubBook, output_dir: Path) -> None:
        """Extract images from EPUB to images directory."""
        from ebooklib import ITEM_IMAGE

        images_dir = output_dir / "images"
        images_dir.mkdir(exist_ok=True)

        for item in book.get_items_of_type(ITEM_IMAGE):
            # Get image content
            image_content = item.get_content()

            # Determine filename
            original_name = item.get_name()
            filename = Path(original_name).name

            # Save image
            image_path = images_dir / filename
            image_path.write_bytes(image_content)

            # Map original path to new relative path
            self._images_extracted[original_name] = f"images/{filename}"

