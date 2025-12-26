from bs4 import BeautifulSoup
import pytest

from ebook_tools.epub_converter import EpubConverter


@pytest.mark.asyncio
async def test_collect_sections_without_h2(tmp_path):
    converter = EpubConverter()
    html = """<html><body><h1>Chapter Title</h1><p>single paragraph</p></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    chapter_dir = tmp_path / "chapter-temp-0001"
    chapter_dir.mkdir()

    sections = await converter._collect_sections(soup, "Chapter Title", soup.find("h1"), chapter_dir)
    assert len(sections) == 1
    section = sections[0]
    assert section.slug_hint == "full-chapter"
    assert section.title == "Chapter Title"


@pytest.mark.asyncio
async def test_introduction_includes_nodes_before_first_h2(tmp_path):
    converter = EpubConverter()
    html = """<html><body><h1>Chapter</h1><p>intro text</p><h2 id='s1'>Sec 1</h2><p>content</p></body></html>"""
    soup = BeautifulSoup(html, "html.parser")
    chapter_dir = tmp_path / "chapter-temp-0002"
    chapter_dir.mkdir()
    section_headings = soup.find_all("h2")

    sections = await converter._collect_structured_sections(
        soup,
        soup.find("h1"),
        section_headings,
        chapter_dir,
    )

    intro = next((s for s in sections if s.title == "Introduction"), None)
    assert intro is not None
    assert "intro text" in intro.filename or intro.word_count > 0
