from pathlib import Path
import zipfile

from ebook_tools.epub_converter import EpubConverter
from ebook_tools.epub_models import EpubChapter, EpubSection


def test_build_name_maps_and_resolve_and_find_alias(tmp_path):
    conv = EpubConverter()
    names = ["OEBPS/CH1.xhtml", "OEBPS/images/Pic.png", "META-INF/container.xml"]
    names_set, lower_map, ascii_map = conv._build_name_maps(names)

    assert "OEBPS/CH1.xhtml" in names_set
    assert lower_map.get("oebps/ch1.xhtml") == "OEBPS/CH1.xhtml"

    # ascii path conversion
    ascii = conv._ascii_path("Caf\u00e9/na\u00efve.xhtml")
    assert "Cafe" in ascii or "naive" in ascii

    # resolve by different-cased target
    resolved = conv._resolve_zip_path("OEBPS/ch1.xhtml", names_set, lower_map, ascii_map)
    assert resolved == "OEBPS/CH1.xhtml"

    # find alias using .xhtml -> .html fallback path
    lower_map_case = {k: v for k, v in lower_map.items()}
    # pretend there is a .html in lower_map
    lower_map_case["oebps/ch1.html"] = "OEBPS/CH1.html"
    alias = conv._find_alias("OEBPS/ch1.xhtml", lower_map_case, ascii_map)
    assert alias in ("OEBPS/CH1.html", "OEBPS/CH1.xhtml")


def test_load_opf_manifest_reads_opf(tmp_path):
    # create minimal EPUB-like zip with container.xml and content.opf
    epub_file = tmp_path / "test.epub"
    container_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        "<rootfiles>"
        '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles>"
        "</container>"
    )
    opf_content = """<?xml version='1.0' encoding='utf-8'?>
    <package>
      <manifest>
        <item id="doc" href="ch1.xhtml" media-type="application/xhtml+xml"/>
      </manifest>
    </package>
    """

    with zipfile.ZipFile(epub_file, "w") as z:
        z.writestr("META-INF/container.xml", container_xml)
        z.writestr("OEBPS/content.opf", opf_content)

    conv = EpubConverter()
    with zipfile.ZipFile(epub_file) as z:
        names = z.namelist()
        names_set, lower_map, ascii_map = conv._build_name_maps(names)
        # load_opf_manifest should parse and return opf root and dir
        result = conv._load_opf_manifest(z, "META-INF/container.xml", names_set, lower_map, ascii_map)
        assert result is not None
        opf_root, opf_dir = result
        assert opf_dir == Path("OEBPS")


def _container_xml_str() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        "<rootfiles>"
        '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles>"
        "</container>"
    )


def _opf_manifest_with_href(href: str) -> str:
    return f"""<?xml version='1.0' encoding='utf-8'?>
<package>
    <manifest>
        <item id="doc" href="{href}" media-type="application/xhtml+xml"/>
    </manifest>
</package>
"""


def test_prepare_epub_for_conversion_creates_alias(tmp_path):
    epub_file = tmp_path / "alias.epub"
    with zipfile.ZipFile(epub_file, "w") as z:
        z.writestr("META-INF/container.xml", _container_xml_str())
        z.writestr("OEBPS/content.opf", _opf_manifest_with_href("ch1.xhtml"))
        z.writestr("OEBPS/Ch1.xhtml", "<html></html>")

    conv = EpubConverter()
    normalized, temp = conv._prepare_epub_for_conversion(epub_file)
    assert temp is not None
    assert normalized != epub_file
    assert temp.exists()
    with zipfile.ZipFile(temp) as z:
        names = z.namelist()
        assert "OEBPS/ch1.xhtml" in names


def test_prepare_epub_for_conversion_no_alias(tmp_path):
    epub_file = tmp_path / "no-alias.epub"
    with zipfile.ZipFile(epub_file, "w") as z:
        z.writestr("META-INF/container.xml", _container_xml_str())
        z.writestr("OEBPS/content.opf", _opf_manifest_with_href("Ch1.xhtml"))
        z.writestr("OEBPS/Ch1.xhtml", "<html></html>")

    conv = EpubConverter()
    normalized, temp = conv._prepare_epub_for_conversion(epub_file)
    assert temp is None
    assert normalized == epub_file


def test_fix_image_paths_and_extract_images(tmp_path):
    conv = EpubConverter()

    # fix_image_paths with no mapping returns unchanged
    html = '<p><img src="img1.png"/></p>'
    assert "img1.png" in conv._fix_image_paths(html)

    # set mapping and ensure replacement
    conv._images_extracted = {"img1.png": "images/img1.png"}
    fixed = conv._fix_image_paths(html)
    assert "images/img1.png" in fixed

    # test _extract_images with a fake book object
    class FakeItem:
        def __init__(self, name, content):
            self._name = name
            self._content = content

        def get_content(self):
            return self._content

        def get_name(self):
            return self._name

    class FakeBook:
        def __init__(self, items):
            self._items = items

        def get_items_of_type(self, *_args, **_kwargs):
            return self._items

    fake = FakeBook([FakeItem("images/pic.png", b"PNGDATA")])
    out = tmp_path / "out"
    out.mkdir()
    conv = EpubConverter()
    conv._extract_images(fake, out)
    img_path = out / "images" / "pic.png"
    assert img_path.exists()
    assert conv._images_extracted.get("images/pic.png") == "images/pic.png"


def test_apply_chapter_and_section_numbering(tmp_path):
    # prepare chapter dir and a section file
    chapter_dir = tmp_path / "chapter-temp-0001"
    chapter_dir.mkdir()
    section_file = chapter_dir / "section-temp-0001.md"
    section_file.write_text("hello world")

    section = EpubSection(
        title="First Section",
        filename="section-temp-0001.md",
        file_path=str(section_file),
        word_count=2,
        character_count=11,
        slug_hint="first-section",
        source_fragment=None,
    )

    chapter = EpubChapter(
        title="My Chapter",
        folder_name=chapter_dir.name,
        folder_path=str(chapter_dir),
        sections=[section],
        source_file="OEBPS/ch1.xhtml",
    )

    conv = EpubConverter()
    conv._apply_chapter_numbering([chapter])

    # After numbering, folder should be renamed and section files renamed accordingly
    new_folder = tmp_path / "my-chapter"
    assert new_folder.exists()
    # Section should have been renamed to include prefix
    files = list(new_folder.iterdir())
    assert any("1.1-" in f.name for f in files)


def test_apply_chapter_numbering_removes_existing_slug(tmp_path):
    conv = EpubConverter()
    stale_dir = tmp_path / "getting-started"
    stale_dir.mkdir()
    (stale_dir / "old.md").write_text("old", encoding="utf-8")

    chapter_dir = tmp_path / "chapter-temp-0001"
    chapter_dir.mkdir()
    section_path = chapter_dir / "section-temp-0001.md"
    section_path.write_text("intro", encoding="utf-8")

    section = EpubSection(
        title="Introduction",
        filename=section_path.name,
        file_path=str(section_path),
        word_count=10,
        character_count=45,
        slug_hint="intro",
        source_fragment=None,
    )

    chapter = EpubChapter(
        title="Getting Started",
        folder_name=chapter_dir.name,
        folder_path=str(chapter_dir),
        sections=[section],
        source_file="ch01.xhtml",
    )

    conv._apply_chapter_numbering([chapter])

    assert Path(chapter.folder_path).name == "getting-started"
    assert not (stale_dir / "old.md").exists()
