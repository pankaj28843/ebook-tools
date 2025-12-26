import json

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


def make_chapter(title, folder_name, folder_path, sections):
    return EpubChapter(
        title=title,
        folder_name=folder_name,
        folder_path=str(folder_path),
        sections=sections,
        source_file=f"{folder_name}.xhtml",
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


def test_apply_chapter_and_section_numbering_and_generate_toc(tmp_path):
    conv = EpubConverter()

    # create temp chapter dir and a section file
    chap_dir = tmp_path / "chapter-temp-0001"
    chap_dir.mkdir()
    sect_path = chap_dir / "section-temp-0001.md"
    sect_path.write_text("# Hello\n\nContent")

    section = make_section("A Section", filename="section-temp-0001.md", file_path=sect_path, slug_hint="A Section")
    chapter = make_chapter("My Chapter", folder_name="chapter-temp-0001", folder_path=chap_dir, sections=[section])

    # Apply numbering (will rename files/folders)
    conv._apply_chapter_numbering([chapter])

    # After numbering, chapter folder_name should use the chapter title slug
    assert chapter.folder_name == "my-chapter"
    assert chapter.sections[0].filename.startswith("1.")

    # generate toc files
    toc_path, json_path = conv._generate_toc([chapter], tmp_path, "Book Title", nav_entries=None)
    assert toc_path.exists()
    assert json_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload.get("book_title") == "Book Title"
    assert payload.get("chapters") == 1
