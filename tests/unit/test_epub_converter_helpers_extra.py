from pathlib import Path

from ebook_tools.epub_converter import EpubConverter
from ebook_tools.epub_models import EpubChapter, EpubSection


def make_section(title, filename="section-temp-0001.md", file_path=None, slug_hint="s"):
    fp = str(file_path) if file_path else f"/tmp/{filename}"
    return EpubSection(
        title=title,
        filename=filename,
        file_path=fp,
        word_count=5,
        character_count=20,
        slug_hint=slug_hint,
        source_fragment=None,
    )


def make_chapter(title, working_dir, sections):
    return EpubChapter(
        title=title,
        slug="temp",
        working_dir=str(working_dir),
        sections=sections,
        source_file=f"{title}.xhtml",
    )


def test_ascii_path_normalizes_nonascii():
    conv = EpubConverter()
    path = "Ångström/naïve-ファイル.html"
    ascii = conv._ascii_path(path)
    # all characters should be ASCII-only (ord < 128)
    assert all(ord(ch) < 128 for ch in ascii.replace("/", ""))


def test_fix_image_paths_rewrites(tmp_path):
    conv = EpubConverter()
    # map original path to extracted path
    conv._images_extracted = {"images/orig.png": "images/extracted.png"}
    html = '<p><img src="images/orig.png" alt="x"/></p>'
    out = conv._fix_image_paths(html)
    assert "images/extracted.png" in out


def test_determine_padding_and_format_number():
    conv = EpubConverter()
    assert conv._determine_padding(1) == 1
    assert conv._determine_padding(9) == 1
    assert conv._determine_padding(10) == 2
    assert conv._determine_padding(123) == 3

    assert conv._format_number(3, 1) == "3"
    assert conv._format_number(3, 2) == "03"
    assert conv._format_number(12, 3) == "012"


def test_flatten_sections_moves_files_and_cleans_temp(tmp_path):
    conv = EpubConverter()

    chapter_dir = tmp_path / "chapter-temp-0001"
    chapter_dir.mkdir()
    section_path = chapter_dir / "section-temp-0001.md"
    section_path.write_text("# Intro\n", encoding="utf-8")

    section = make_section("A Section", filename="section-temp-0001.md", file_path=section_path, slug_hint="A Section")
    chapter = make_chapter("My Chapter", working_dir=chapter_dir, sections=[section])

    conv._flatten_sections([chapter], tmp_path)

    assert not chapter_dir.exists()
    flattened = Path(chapter.sections[0].file_path)
    assert flattened.parent == tmp_path
    assert flattened.name.startswith("1-my-chapter-a-section")
    assert chapter.slug == "my-chapter"
