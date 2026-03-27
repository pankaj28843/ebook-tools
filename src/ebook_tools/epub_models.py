"""
Models for EPUB and PDF to Markdown conversion.

This module defines the data structures used throughout the EPUB and PDF conversion processes.
"""

from pydantic import BaseModel, Field


class Section(BaseModel):
    """Represents a section within a chapter."""

    title: str = Field(description="The section title")
    filename: str = Field(description="The markdown filename for this section")
    file_path: str = Field(description="Absolute path to the generated markdown file")
    word_count: int = Field(description="Number of words in the section")
    character_count: int = Field(description="Number of characters in the section")
    slug_hint: str | None = Field(default=None, description="Preferred slug for deterministic numbering")
    source_fragment: str | None = Field(
        default=None,
        description="Original heading fragment identifier used for nav-map alignment",
    )
    level: int = Field(default=2, description="Heading depth used when building nested output trees")


class Chapter(BaseModel):
    """Represents a chapter from a book."""

    title: str = Field(description="The chapter title")
    slug: str = Field(description="Slug used when deriving file names")
    working_dir: str = Field(description="Temporary directory used while constructing sections")
    output_filename: str | None = Field(default=None, description="Final markdown filename for this chapter")
    output_path: str | None = Field(
        default=None,
        description="Absolute path to the chapter markdown file or directory root when structured output is enabled",
    )
    sections: list[Section] = Field(description="List of sections in this chapter")
    source_file: str = Field(description="Original source file name")


class ConversionResult(BaseModel):
    """Results from converting a book to structured Markdown."""

    book_title: str = Field(description="The title of the book")
    chapters_count: int = Field(description="Number of chapters converted")
    sections_count: int = Field(description="Total number of sections across all chapters")
    output_directory: str = Field(description="Path to the output directory")
    chapters: list[Chapter] = Field(description="List of converted chapters")


class EpubInfo(BaseModel):
    """Information about an EPUB file without full conversion."""

    title: str = Field(description="The book title")
    author: str | None = Field(default=None, description="The book author")
    language: str | None = Field(default=None, description="The book language")
    identifier: str | None = Field(default=None, description="The book identifier (ISBN, etc.)")
    publisher: str | None = Field(default=None, description="The book publisher")
    description: str | None = Field(default=None, description="The book description")
    chapters_count: int = Field(description="Number of chapters in the book")
    has_images: bool = Field(description="Whether the book contains images")
    file_size_mb: float = Field(description="File size in megabytes")


class PdfInfo(BaseModel):
    """Information about a PDF file without full conversion."""

    title: str = Field(description="The PDF title")
    author: str | None = Field(default=None, description="The PDF author")
    subject: str | None = Field(default=None, description="The PDF subject")
    creator: str | None = Field(default=None, description="The PDF creator application")
    producer: str | None = Field(default=None, description="The PDF producer")
    keywords: str | None = Field(default=None, description="The PDF keywords")
    pages_count: int = Field(description="Number of pages in the PDF")
    has_outline: bool = Field(description="Whether the PDF has a table of contents (outline/bookmarks)")
    has_images: bool = Field(description="Whether the PDF contains images")
    file_size_mb: float = Field(description="File size in megabytes")


# Backward-compatible aliases
EpubChapter = Chapter
EpubSection = Section
