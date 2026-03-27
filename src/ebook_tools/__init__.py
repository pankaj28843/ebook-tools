"""Reusable ebook/PDF conversion utilities."""

from .converter_base import BaseConverter, make_slug
from .epub_converter import EpubConverter, EpubConverterConfig
from .epub_models import Chapter, ConversionResult, EpubInfo, PdfInfo, Section
from .pdf_converter import PdfConverter, PdfConverterConfig
from . import toc_checker

# Backward-compatible aliases
EpubChapter = Chapter
EpubSection = Section

__all__ = [
    "BaseConverter",
    "Chapter",
    "ConversionResult",
    "EpubChapter",
    "EpubConverter",
    "EpubConverterConfig",
    "EpubInfo",
    "EpubSection",
    "PdfConverter",
    "PdfConverterConfig",
    "PdfInfo",
    "Section",
    "make_slug",
    "toc_checker",
]
