from pathlib import Path

from ebooklib import epub
import pytest

from ebook_tools.epub_converter import EpubConverter


def _build_test_epub(epub_path: Path) -> None:
    book = epub.EpubBook()
    book.set_title("Minimal")
    book.set_language("en")

    chapter = epub.EpubHtml(title="Chapter One", file_name="ch1.xhtml", lang="en")
    chapter_content = """<html><body><h1>Chapter</h1><h2 id='sect1'>Section</h2><p>content</p></body></html>"""
    chapter.content = chapter_content
    book.add_item(chapter)
    book.toc = [chapter]
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(epub_path), book)


@pytest.mark.asyncio
async def test_convert_epub_to_markdown_minimal(tmp_path: Path):
    epub_file = tmp_path / "minimal.epub"
    _build_test_epub(epub_file)

    output_dir = tmp_path / "out"
    converter = EpubConverter()
    result = await converter.convert_epub_to_markdown(epub_file, output_dir)

    assert result.chapters_count >= 1
    assert result.sections_count >= 1

    # Collect all markdown content from output
    all_md_content = ""
    for entry in sorted(output_dir.iterdir()):
        if entry.suffix == ".md":
            all_md_content += entry.read_text(encoding="utf-8")
        elif entry.is_dir() and entry.name != "images":
            for md_file in sorted(entry.glob("*.md")):
                all_md_content += md_file.read_text(encoding="utf-8")

    assert all_md_content, "expected markdown output"
    # The chapter or section content should be present somewhere
    assert "Chapter" in all_md_content or "Section" in all_md_content or "content" in all_md_content
