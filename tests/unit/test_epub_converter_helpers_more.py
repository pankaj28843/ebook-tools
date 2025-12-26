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


def test_flatten_sections_assigns_numbered_filenames(tmp_path):
    chapter_dir = tmp_path / "chapter-temp-0001"
    chapter_dir.mkdir()
    first_file = chapter_dir / "section-temp-0001.md"
    second_file = chapter_dir / "section-temp-0002.md"
    first_file.write_text("first", encoding="utf-8")
    second_file.write_text("second", encoding="utf-8")

    sections = [
        EpubSection(
            title="First Section",
            filename=first_file.name,
            file_path=str(first_file),
            word_count=1,
            character_count=5,
            slug_hint="first-section",
            source_fragment=None,
        ),
        EpubSection(
            title="Second Section",
            filename=second_file.name,
            file_path=str(second_file),
            word_count=1,
            character_count=6,
            slug_hint="second-section",
            source_fragment=None,
        ),
    ]

    chapter = EpubChapter(
        title="My Chapter",
        slug="temp",
        working_dir=str(chapter_dir),
        sections=sections,
        source_file="OEBPS/ch1.xhtml",
    )

    conv = EpubConverter()
    conv._flatten_sections([chapter], tmp_path)

    generated = sorted(tmp_path.glob("*.md"))
    assert len(generated) == 1
    assert generated[0].name == "1-my-chapter.md"
    content = generated[0].read_text(encoding="utf-8")
    assert "first" in content
    assert "second" in content


def test_flatten_sections_overwrites_existing_conflicts(tmp_path):
    conv = EpubConverter()
    existing = tmp_path / "1-getting-started.md"
    existing.write_text("old", encoding="utf-8")

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
        slug="temp",
        working_dir=str(chapter_dir),
        sections=[section],
        source_file="ch01.xhtml",
    )

    conv._flatten_sections([chapter], tmp_path)

    new_file = tmp_path / "1-getting-started.md"
    assert new_file.exists()
    new_content = new_file.read_text(encoding="utf-8")
    assert "# Getting Started" in new_content
    assert "intro" in new_content
