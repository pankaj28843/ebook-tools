"""Utilities for comparing EPUB navMap entries to generated Markdown tables of contents."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
from typing import Any


__all__ = [
    "OrderMismatch",
    "TocComparisonResult",
    "TocEntry",
    "compare_toc_entries",
    "extract_nav_entries",
    "load_json_toc",
    "load_markdown_toc",
    "load_nav_entries",
    "normalize_title",
    "parse_json_toc",
    "parse_markdown_toc",
]


@dataclass(slots=True)
class TocEntry:
    """Normalized representation of a TOC entry."""

    title: str
    href: str | None
    level: int
    source: str

    def normalized_title(self) -> str:
        """Return the canonical representation used for diffing."""
        return normalize_title(self.title)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass(slots=True)
class OrderMismatch:
    """Represents a pair of entries that share a position but differ."""

    nav_entry: TocEntry
    reference_entry: TocEntry

    def as_dict(self) -> dict[str, Any]:
        return {
            "nav_entry": self.nav_entry.as_dict(),
            "reference_entry": self.reference_entry.as_dict(),
        }


@dataclass(slots=True)
class TocComparisonResult:
    """Holds the outcome of comparing navMap entries with another reference."""

    nav_entries: list[TocEntry]
    reference_entries: list[TocEntry]
    missing_in_reference: list[TocEntry]
    missing_in_navmap: list[TocEntry]
    order_mismatches: list[OrderMismatch]

    @property
    def is_match(self) -> bool:
        return not (self.missing_in_reference or self.missing_in_navmap or self.order_mismatches)

    def as_dict(self) -> dict[str, Any]:
        return {
            "nav_entries": [entry.as_dict() for entry in self.nav_entries],
            "reference_entries": [entry.as_dict() for entry in self.reference_entries],
            "missing_in_reference": [entry.as_dict() for entry in self.missing_in_reference],
            "missing_in_navmap": [entry.as_dict() for entry in self.missing_in_navmap],
            "order_mismatches": [mismatch.as_dict() for mismatch in self.order_mismatches],
            "is_match": self.is_match,
        }


def extract_nav_entries(nav_map: Sequence[Any], max_depth: int | None = None) -> list[TocEntry]:
    """Flatten `ebooklib` navMap objects into TocEntry rows."""

    entries: list[TocEntry] = []
    _walk_nav_map(nav_map, level=1, max_depth=max_depth, acc=entries)
    return entries


def _walk_nav_map(items: Sequence[Any] | Any, *, level: int, max_depth: int | None, acc: list[TocEntry]) -> None:
    if max_depth is not None and level > max_depth:
        return

    if _handle_nav_sequence(items, level=level, max_depth=max_depth, acc=acc):
        return

    if items is None:
        return

    _append_nav_entry(items, level=level, acc=acc)


def _handle_nav_sequence(
    items: Sequence[Any] | Any,
    *,
    level: int,
    max_depth: int | None,
    acc: list[TocEntry],
) -> bool:
    if not isinstance(items, (list, tuple)):
        return False

    if len(items) == 2 and _looks_like_nav_node(items[0]) and isinstance(items[1], (list, tuple)):
        _walk_nav_map(items[0], level=level, max_depth=max_depth, acc=acc)
        _walk_nav_map(items[1], level=level + 1, max_depth=max_depth, acc=acc)
        return True

    for item in items:
        _walk_nav_map(item, level=level, max_depth=max_depth, acc=acc)
    return True


def _append_nav_entry(item: Any, *, level: int, acc: list[TocEntry]) -> None:
    title = _extract_nav_title(item)
    if not title:
        return
    href = _extract_nav_href(item)
    acc.append(TocEntry(title=title, href=href, level=level, source="navmap"))


def _extract_nav_title(item: Any) -> str:
    raw_title = getattr(item, "title", None) or getattr(item, "label", None) or str(item)
    if isinstance(raw_title, (list, tuple)):
        raw_title = " ".join(str(part) for part in raw_title)
    return str(raw_title).strip()


def _extract_nav_href(item: Any) -> str | None:
    raw_href = getattr(item, "href", None) or getattr(item, "file_name", None)
    if isinstance(raw_href, (list, tuple)):
        raw_href = raw_href[0] if raw_href else None
    return str(raw_href) if raw_href else None


def load_nav_entries(epub_path: str | Path, max_depth: int | None = None) -> list[TocEntry]:
    """Read the EPUB and return navMap entries."""

    from ebooklib import epub  # Imported lazily to keep optional dependency local

    path = Path(epub_path).expanduser().resolve()
    book = epub.read_epub(str(path))
    nav_map: Any | None = None
    nav_accessor = getattr(book, "get_toc", None)
    if callable(nav_accessor):
        nav_map = nav_accessor()
    elif hasattr(book, "toc"):
        nav_map = book.toc
    if nav_map is None:
        raise AttributeError("The provided EPUB book does not expose a TOC")
    return extract_nav_entries(nav_map, max_depth=max_depth)


_MARKDOWN_HEADING = re.compile(r"^(?P<hashes>#+)\s+\[(?P<title>.+?)\]\((?P<link>[^)]+)\)")
_MARKDOWN_LINK = re.compile(r"^(?P<indent>\s*)[-*+]\s+\[(?P<title>.+?)\]\((?P<link>[^)]+)\)")


def parse_markdown_toc(markdown_text: str, max_depth: int | None = None) -> list[TocEntry]:
    """Parse README.md TOC into TocEntry rows."""

    entries: list[TocEntry] = []

    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        heading_match = _MARKDOWN_HEADING.match(line)
        if heading_match:
            hashes = heading_match.group("hashes")
            level = max(1, len(hashes) - 2)
            if max_depth is not None and level > max_depth:
                continue
            entries.append(
                TocEntry(
                    title=heading_match.group("title").strip(),
                    href=heading_match.group("link").strip(),
                    level=level,
                    source="markdown",
                )
            )
            continue

        link_match = _MARKDOWN_LINK.match(line)
        if link_match:
            indent = len(link_match.group("indent"))
            level = 2 + indent // 2
            if max_depth is not None and level > max_depth:
                continue
            entries.append(
                TocEntry(
                    title=link_match.group("title").strip(),
                    href=link_match.group("link").strip(),
                    level=level,
                    source="markdown",
                )
            )

    return entries


def load_markdown_toc(readme_path: str | Path, max_depth: int | None = None) -> list[TocEntry]:
    """Load and parse a README TOC file."""

    path = Path(readme_path).expanduser().resolve()
    contents = path.read_text(encoding="utf-8")
    return parse_markdown_toc(contents, max_depth=max_depth)


def parse_json_toc(payload: dict[str, Any], max_depth: int | None = None) -> list[TocEntry]:
    """Normalize toc.json payloads emitted by converters."""

    entries: list[TocEntry] = []
    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list):
        return entries

    for entry in raw_entries:
        if not isinstance(entry, dict):
            continue

        if entry.get("derived_only") is True:
            continue

        title = str(entry.get("title", "")).strip()
        if not title:
            continue

        level = _determine_json_level(entry)
        if max_depth is not None and level > max_depth:
            continue

        entries.append(
            TocEntry(
                title=title,
                href=_sanitize_json_href(entry),
                level=level,
                source="json",
            )
        )

    return entries


def load_json_toc(toc_path: str | Path, max_depth: int | None = None) -> list[TocEntry]:
    """Load entries from converter-emitted toc.json files."""

    path = Path(toc_path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return []
    return parse_json_toc(payload, max_depth=max_depth)


def _determine_json_level(entry: dict[str, Any]) -> int:
    level = entry.get("level")
    if isinstance(level, str):
        stripped = level.strip()
        if stripped.isdigit():
            return max(1, int(stripped))
        try:
            return max(1, int(float(stripped)))
        except ValueError:
            pass
    if isinstance(level, (int, float)):
        return max(1, int(level))

    entry_type = str(entry.get("type", "")).strip().lower()
    if entry_type == "chapter":
        return 1
    if entry_type:
        return 2

    depth = entry.get("depth")
    if isinstance(depth, (int, float)):
        return max(1, int(depth))

    return 2


def _sanitize_json_href(entry: dict[str, Any]) -> str | None:
    href = entry.get("href")
    if isinstance(href, str):
        stripped = href.strip()
        return stripped or None
    return None


def compare_toc_entries(nav_entries: Iterable[TocEntry], reference_entries: Iterable[TocEntry]) -> TocComparisonResult:
    """Compare navMap-derived entries with entries from another source."""

    nav_list = list(nav_entries)
    ref_list = list(reference_entries)
    if not nav_list and not ref_list:
        return TocComparisonResult(nav_list, ref_list, [], [], [])

    matcher = SequenceMatcher(
        None,
        [entry.normalized_title() for entry in nav_list],
        [entry.normalized_title() for entry in ref_list],
        autojunk=False,
    )

    missing_in_reference: list[TocEntry] = []
    missing_in_navmap: list[TocEntry] = []
    order_mismatches: list[OrderMismatch] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        match tag:
            case "equal":
                continue
            case "delete":
                missing_in_reference.extend(nav_list[i1:i2])
            case "insert":
                missing_in_navmap.extend(ref_list[j1:j2])
            case "replace":
                _handle_replace_opcode(
                    nav_slice=nav_list[i1:i2],
                    toc_slice=ref_list[j1:j2],
                    missing_in_reference=missing_in_reference,
                    missing_in_navmap=missing_in_navmap,
                    order_mismatches=order_mismatches,
                )
            case _:
                continue

    return TocComparisonResult(
        nav_entries=nav_list,
        reference_entries=ref_list,
        missing_in_reference=missing_in_reference,
        missing_in_navmap=missing_in_navmap,
        order_mismatches=order_mismatches,
    )


def _handle_replace_opcode(
    *,
    nav_slice: Sequence[TocEntry],
    toc_slice: Sequence[TocEntry],
    missing_in_reference: list[TocEntry],
    missing_in_navmap: list[TocEntry],
    order_mismatches: list[OrderMismatch],
) -> None:
    """Handle a single SequenceMatcher ``replace`` opcode."""

    for nav_entry, toc_entry in zip(nav_slice, toc_slice, strict=False):
        order_mismatches.append(OrderMismatch(nav_entry=nav_entry, reference_entry=toc_entry))

    slices_delta = len(nav_slice) - len(toc_slice)
    if slices_delta > 0:
        missing_in_reference.extend(nav_slice[len(toc_slice) :])
    elif slices_delta < 0:
        missing_in_navmap.extend(toc_slice[len(nav_slice) :])


def _looks_like_nav_node(value: Any) -> bool:
    return hasattr(value, "title") or hasattr(value, "label")


_NUMBER_PREFIX = re.compile(r"^[\d\s.\-:]+")


def normalize_title(title: str) -> str:
    """Normalize titles for diffing by stripping numbering and whitespace."""

    clean = re.sub(r"\s+", " ", title).strip()
    clean = _NUMBER_PREFIX.sub("", clean).strip()
    return clean.casefold()
