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


def make_chapter(title, working_dir="/tmp/chapter", sections=None, source_file="chap.xhtml"):
    return EpubChapter(
        title=title,
        slug="temp",
        working_dir=working_dir,
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


def test_apply_nav_titles_prefers_href_matches():
    conv = EpubConverter()
    chapter = make_chapter("Placeholder", working_dir="/tmp/chapter", source_file="chapter1.xhtml")

    nav_entries = [
        toc_checker.TocEntry(title="Nav Chapter", href="chapter1.xhtml", level=1, source="nav"),
        toc_checker.TocEntry(title="Sibling", href="other.xhtml", level=1, source="nav"),
    ]

    conv._apply_nav_titles([chapter], nav_entries)

    assert chapter.title == "Nav Chapter"


def test_apply_nav_titles_normalizes_titles_when_no_href_match():
    conv = EpubConverter()
    chapter = make_chapter("Intro chapter", working_dir="/tmp/chapter", source_file="missing.xhtml")

    nav_entries = [
        toc_checker.TocEntry(title="Intro Chapter", href=None, level=1, source="nav"),
    ]

    conv._apply_nav_titles([chapter], nav_entries)

    assert chapter.title == "Intro Chapter"
