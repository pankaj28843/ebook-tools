from ebook_tools import toc_checker
from ebook_tools.epub_converter import EpubConverter
from ebook_tools.epub_models import EpubChapter, EpubSection


def make_section(title, filename="s.md", file_path="/tmp/s.md", slug_hint="s"):
    return EpubSection(
        title=title,
        filename=filename,
        file_path=file_path,
        word_count=10,
        character_count=100,
        slug_hint=slug_hint,
        source_fragment=None,
    )


def make_chapter(title, folder_name="chap", folder_path="/tmp/chap", sections=None, source_file="chap.xhtml"):
    return EpubChapter(
        title=title,
        folder_name=folder_name,
        folder_path=folder_path,
        sections=sections or [make_section("Intro")],
        source_file=source_file,
    )


def test_clean_filename_and_slugify_roundtrip():
    conv = EpubConverter()
    dirty = "This / Is: A? Test<>File *Name | With Weird -- chars"
    cleaned = conv._clean_filename(dirty)
    # cleaned should be lower, no slashes, and hyphen separated
    assert "/" not in cleaned
    assert cleaned == cleaned.lower()

    # slugify falls back when given None
    assert conv._slugify(None, fallback="fallback") == "fallback"
    assert conv._slugify("  My Title  ", fallback="x") != ""


def test_build_linear_json_entries_basic(tmp_path):
    conv = EpubConverter()
    c1 = make_chapter("Chapter One", folder_name="ch1", folder_path=str(tmp_path / "ch1"))
    c2 = make_chapter("Chapter Two", folder_name="ch2", folder_path=str(tmp_path / "ch2"))
    chapters = [c1, c2]

    entries = conv._build_json_entries(chapters, nav_entries=None)
    # Expect chapter entries + section entries
    assert any(e.get("type") == "chapter" for e in entries)
    assert any(e.get("type") == "section" for e in entries)
    # chapter count equals created chapters
    assert sum(1 for e in entries if e.get("type") == "chapter") == 2


def test_nav_aligned_toc_builder_matches_by_title_and_fragment(tmp_path):
    conv = EpubConverter()

    # Create chapters/sections with explicit fragments and titles
    sec1 = make_section("Getting Started", filename="s1.md", file_path=str(tmp_path / "s1.md"), slug_hint="start")
    sec1.source_fragment = "intro"
    ch = EpubChapter(
        title="Intro Chapter",
        folder_name="chint",
        folder_path=str(tmp_path / "chint"),
        sections=[sec1],
        source_file="chapter1.xhtml",
    )

    # Create nav entries that reference the fragment and the title
    nav_entries = [
        toc_checker.TocEntry(title="Intro Chapter", href="chapter1.xhtml", level=1, source="navmap"),
        toc_checker.TocEntry(title="Getting Started", href="chapter1.xhtml#intro", level=2, source="navmap"),
    ]

    json_entries = conv._build_json_entries([ch], nav_entries=nav_entries)
    # Ensure the nav-driven entries include our chapter and section
    titles = [e.get("title") for e in json_entries]
    assert "Intro Chapter" in titles
    assert "Getting Started" in titles
