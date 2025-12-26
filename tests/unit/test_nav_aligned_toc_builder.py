from ebook_tools.epub_converter import _NavAlignedTocBuilder
from ebook_tools.epub_models import EpubChapter, EpubSection
from ebook_tools.toc_checker import TocEntry


def make_chapter(title, folder_name, source_file, section_title, section_fragment=None):
    section = EpubSection(
        title=section_title,
        filename="section-temp-0001.md",
        file_path=f"/tmp/{folder_name}/section-temp-0001.md",
        word_count=10,
        character_count=50,
        slug_hint=section_title.lower().replace(" ", "-"),
        source_fragment=section_fragment,
    )
    return EpubChapter(
        title=title,
        folder_name=folder_name,
        folder_path=f"/tmp/{folder_name}",
        sections=[section],
        source_file=source_file,
    )


def test_build_aligns_by_href_and_fragment_and_appends_derived():
    # Create two chapters; chap1 has a section with fragment 'sec-a'
    chap1 = make_chapter("Intro 1", "ch1", "OEBPS/ch1.xhtml", "Section A", section_fragment="sec-a")
    chap2 = make_chapter("Second Chapter", "ch2", "OEBPS/ch2.xhtml", "Section B")

    # Nav entries reference chap1 by href and its section by fragment
    nav_entries = [
        TocEntry(title="Intro 1", href="OEBPS/ch1.xhtml", level=1, source="navmap"),
        TocEntry(title="Section A", href="OEBPS/ch1.xhtml#sec-a", level=2, source="navmap"),
    ]

    builder = _NavAlignedTocBuilder([chap1, chap2], nav_entries)
    entries = builder.build()

    # First two entries should correspond to chap1 and its section
    assert len(entries) >= 2
    first = entries[0]
    assert first["type"] == "chapter"
    assert first["href"] == f"{chap1.folder_name}/"
    assert first["chapter_index"] == 1

    second = entries[1]
    assert second["type"] == "section"
    assert second["href"] == f"{chap1.folder_name}/{chap1.sections[0].filename}"
    assert second["chapter_index"] == 1
    assert second["section_index"] == 1

    # Derived entries should include chap2 and its section
    derived = [e for e in entries if e.get("derived_only")]
    assert any(e["href"] == f"{chap2.folder_name}/" for e in derived)


def test_match_by_normalized_title_when_href_missing():
    chap = make_chapter("Getting Started 1.0", "gs", "OEBPS/gs.xhtml", "Start Here")
    # Nav entry has no href but title matches after normalization (numbers removed)
    nav_entries = [TocEntry(title="Getting Started 1.0", href=None, level=1, source="navmap")]

    builder = _NavAlignedTocBuilder([chap], nav_entries)
    entries = builder.build()

    # Expect at least the chapter entry; derived entries for sections may also be produced
    assert any(e["type"] == "chapter" and e["href"] == f"{chap.folder_name}/" for e in entries)
    # Also ensure there is at least one derived entry (chapter or section) to cover fallback behavior
    assert any(e.get("derived_only") for e in entries)


def test_section_match_by_title_when_fragment_absent():
    chap = make_chapter("Chap X", "cpx", "OEBPS/cpx.xhtml", "Deep Section")
    # Nav entry provides section title only; should match section by normalized title
    nav_entries = [
        TocEntry(title="Chap X", href=None, level=1, source="navmap"),
        TocEntry(title="Deep Section", href=None, level=2, source="navmap"),
    ]
    builder = _NavAlignedTocBuilder([chap], nav_entries)
    entries = builder.build()

    # Should produce a chapter and a section entry
    types = [e["type"] for e in entries]
    assert "chapter" in types
    assert "section" in types
