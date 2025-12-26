from ebook_tools.epub_converter import EpubConverter
from ebook_tools.epub_models import EpubChapter, EpubSection
from ebook_tools.toc_checker import TocEntry


def _make_chapter(idx: int, title: str, folder_prefix: str = "chapter-temp"):
    folder_name = f"{folder_prefix}-{idx:04d}"
    section = EpubSection(
        title="Sec",
        filename="section-temp-0001.md",
        file_path=f"/tmp/{folder_name}/section-temp-0001.md",
        word_count=5,
        character_count=20,
        slug_hint="sec",
        source_fragment=None,
    )
    return EpubChapter(
        title=title,
        folder_name=folder_name,
        folder_path=f"/tmp/{folder_name}",
        sections=[section],
        source_file=f"OEBPS/ch{idx}.xhtml",
    )


def test_generate_toc_linear_and_json(tmp_path):
    conv = EpubConverter()
    chapters = [_make_chapter(1, "Alpha"), _make_chapter(2, "Beta")]

    # generate toc files
    toc_path, json_path = conv._generate_toc(chapters, tmp_path, "My Book", nav_entries=None)

    assert toc_path.exists()
    assert json_path.exists()

    payload = json_path.read_text(encoding="utf-8")
    assert "My Book" in toc_path.read_text(encoding="utf-8")
    assert '"chapters": 2' in payload


def test_build_json_entries_prefers_nav_alignment():
    # create chapters and a nav that references the second chapter first
    chap1 = _make_chapter(1, "One")
    chap2 = _make_chapter(2, "Two")

    nav_entries = [
        TocEntry(title="Two", href="OEBPS/ch2.xhtml", level=1, source="navmap"),
        TocEntry(title="Section", href="OEBPS/ch2.xhtml#sec-1", level=2, source="navmap"),
    ]

    conv = EpubConverter()
    entries = conv._build_json_entries([chap1, chap2], nav_entries)

    # First entry should correspond to chap2 because nav aligns to it
    assert entries[0]["href"].startswith(chap2.folder_name)
