from pathlib import Path

from bs4 import BeautifulSoup
import pytest

from ebook_tools.epub_converter import EpubConverter


@pytest.mark.asyncio
async def test_collect_structured_sections_and_process_section(tmp_path):
    conv = EpubConverter()

    # Build HTML with an h1 title, intro paragraph, and two h2 sections
    html = """
    <html><body>
    <h1>Chapter Title</h1>
    <p>Intro paragraph here.</p>
    <h2 id="s1">Section One</h2>
    <p>First section text.</p>
    <h2 id="s2">Section Two</h2>
    <p>Second section text.</p>
    </body></html>
    """

    soup = BeautifulSoup(html, "html.parser")

    chapter_dir = tmp_path / "chapter-temp-0001"
    chapter_dir.mkdir()

    # collect structured sections via the internal helper
    sections = await conv._collect_sections(
        soup=soup,
        chapter_title="Chapter Title",
        chapter_title_tag=soup.find("h1"),
        chapter_dir=chapter_dir,
    )

    assert isinstance(sections, list)
    assert len(sections) >= 2

    # validate section files were written and contain converted markdown
    for sec in sections:
        p = Path(sec.file_path)
        assert p.exists()
        txt = p.read_text(encoding="utf-8")
        assert len(txt) > 0
