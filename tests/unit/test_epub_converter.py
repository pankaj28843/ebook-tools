from unittest.mock import MagicMock, patch

import pytest

from ebook_tools.epub_converter import EpubConverter


@pytest.fixture
def converter():
    return EpubConverter()


@pytest.mark.unit
class TestEpubConverter:
    @pytest.mark.asyncio
    async def test_convert_epub_file_not_found(self, converter, tmp_path):
        with pytest.raises(FileNotFoundError):
            await converter.convert_epub_to_markdown("nonexistent.epub", tmp_path)

    @pytest.mark.asyncio
    async def test_convert_epub_happy_path(self, converter, tmp_path):
        epub_path = tmp_path / "test.epub"
        epub_path.touch()
        output_dir = tmp_path / "output"

        # Mock ebooklib.epub.read_epub
        with patch("ebooklib.epub.read_epub") as mock_read_epub:
            mock_book = MagicMock()
            mock_read_epub.return_value = mock_book

            # Mock metadata
            mock_book.get_metadata.return_value = [("Test Book", {})]

            # Mock items (chapters)
            mock_item = MagicMock()
            mock_item.get_content.return_value = b"<html><body><h1>Chapter 1</h1><p>Content</p></body></html>"
            mock_item.get_name.return_value = "chapter1.html"
            mock_book.get_items_of_type.return_value = [mock_item]

            # Mock ZipFile for _prepare_epub_for_conversion
            with patch("ebook_tools.epub_converter.ZipFile") as mock_zip:
                mock_zip_instance = mock_zip.return_value.__enter__.return_value
                mock_zip_instance.namelist.return_value = ["META-INF/container.xml", "content.opf"]

                def mock_read(filename):
                    if "container.xml" in filename:
                        return b'<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
                    if "content.opf" in filename:
                        return b'<package xmlns="http://www.idpf.org/2007/opf" version="3.0"><manifest><item id="item1" href="chapter1.html" media-type="application/xhtml+xml"/></manifest></package>'
                    return b""

                mock_zip_instance.read.side_effect = mock_read

                result = await converter.convert_epub_to_markdown(epub_path, output_dir)

                assert result.book_title == "Test Book"
                assert result.chapters_count == 1
                assert result.sections_count == 1
                chapter_file = output_dir / "1-chapter-1.md"
                assert chapter_file.exists()
                contents = chapter_file.read_text(encoding="utf-8")
                assert "# Chapter 1" in contents

    @pytest.mark.asyncio
    async def test_process_chapter_with_sections(self, converter, tmp_path):
        # Test processing a chapter with h2 headings
        html_content = """
        <html>
            <body>
                <h1>Chapter Title</h1>
                <p>Intro text</p>
                <h2>Section 1</h2>
                <p>Section 1 content</p>
                <h2>Section 2</h2>
                <p>Section 2 content</p>
            </body>
        </html>
        """

        mock_item = MagicMock()
        mock_item.get_content.return_value = html_content.encode("utf-8")
        mock_item.get_name.return_value = "chapter.html"

        chapter = await converter._process_chapter(mock_item, tmp_path, 1)

        assert chapter.title == "Chapter Title"
        assert len(chapter.sections) == 3  # Intro + 2 sections
        assert chapter.sections[0].title == "Introduction"
        assert chapter.sections[1].title == "Section 1"
        assert chapter.sections[2].title == "Section 2"

    @pytest.mark.asyncio
    async def test_process_chapter_no_sections(self, converter, tmp_path):
        # Test processing a chapter without h2 headings (full chapter)
        html_content = """
        <html>
            <body>
                <h1>Chapter Title</h1>
                <p>Just some content</p>
            </body>
        </html>
        """

        mock_item = MagicMock()
        mock_item.get_content.return_value = html_content.encode("utf-8")
        mock_item.get_name.return_value = "chapter.html"

        chapter = await converter._process_chapter(mock_item, tmp_path, 1)

        assert chapter.title == "Chapter Title"
        assert len(chapter.sections) == 1
        assert chapter.sections[0].title == "Chapter Title"

    def test_strip_unwanted_tags(self, converter):
        from bs4 import BeautifulSoup

        html = "<html><body><script>alert(1)</script><p>Content</p><style>body{}</style></body></html>"
        soup = BeautifulSoup(html, "html.parser")

        converter._strip_unwanted_tags(soup)

        assert not soup.find("script")
        assert not soup.find("style")
        assert soup.find("p")

    def test_prepare_epub_no_aliases_needed(self, converter, tmp_path):
        epub_path = tmp_path / "test.epub"
        epub_path.touch()

        with patch("ebook_tools.epub_converter.ZipFile") as mock_zip:
            mock_zip_instance = mock_zip.return_value.__enter__.return_value
            mock_zip_instance.namelist.return_value = ["META-INF/container.xml", "content.opf"]

            # Mock container.xml reading
            mock_zip_instance.read.side_effect = (
                lambda x: b'<container><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>'
                if "container.xml" in x
                else b""
            )

            # Mock opf reading to return no manifest or simple manifest
            # If we don't mock opf content properly, _load_opf_manifest might fail or return None
            # But here we just want to test that if no aliases are found, it returns original path

            # We need to mock _load_opf_manifest or make it return something valid
            # Let's mock the internal methods to simplify
            with patch.object(converter, "_load_opf_manifest", return_value=None):
                normalized, temp = converter._prepare_epub_for_conversion(epub_path)
                assert normalized == epub_path
                assert temp is None
