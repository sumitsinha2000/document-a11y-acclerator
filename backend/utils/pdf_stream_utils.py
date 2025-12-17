from __future__ import annotations

import re
from typing import Any, Iterator, List, Optional, Set

try:  # pragma: no cover - defensive import since pypdf may not be available
    from pypdf.generic import IndirectObject
except Exception:  # pragma: no cover - defensive import guard
    IndirectObject = None

from backend.utils.language_detection import normalize_lang_value
from backend.wcag_validator import _resolve_pdf_object


LANG_OVERRIDE_PATTERN = re.compile(r"/Lang\s*\(([^()]+)\)\s*>>\s*BDC")


def _as_bytes(data: Any) -> Optional[bytes]:
    if data is None:
        return None
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    if hasattr(data, "tobytes"):
        try:
            return data.tobytes()
        except Exception:
            return None
    try:
        return bytes(data)
    except Exception:
        return None


def _iter_stream_objects(value: Any) -> Iterator[Any]:
    stack: List[Any] = [value]
    seen: Set[int] = set()

    while stack:
        entry = stack.pop()
        entry = _resolve_pdf_object(entry)
        if entry is None:
            continue

        try:
            entry_id = id(entry)
        except Exception:
            entry_id = None
        if entry_id is not None:
            if entry_id in seen:
                continue
            seen.add(entry_id)

        if isinstance(entry, (list, tuple)):
            stack.extend(entry)
            continue

        if IndirectObject is not None and isinstance(entry, IndirectObject):
            try:
                entry = entry.get_object()
            except Exception:
                continue

        yield entry


def iter_content_stream_data(page: Any) -> Iterator[bytes]:
    """
    Yield decoded content stream bytes for a page.

    This walker intentionally avoids pypdf's ContentStream parser so tests can
    fall back to raw text inspection when parser support is limited.
    """
    getter = getattr(page, "get", None)
    contents = None
    if callable(getter):
        try:
            contents = getter("/Contents")
        except Exception:
            contents = None

    for entry in _iter_stream_objects(contents):
        get_data = getattr(entry, "get_data", None)
        if callable(get_data):
            try:
                raw = get_data()
            except Exception:
                continue
            decoded = _as_bytes(raw)
            if decoded:
                yield decoded
            continue

        decoded = _as_bytes(entry)
        if decoded:
            yield decoded


def detect_raw_marked_content_languages(page: Any) -> Set[str]:
    """Return language values extracted from raw BDC dictionaries on a page."""
    languages: Set[str] = set()
    for data in iter_content_stream_data(page):
        if not data:
            continue
        try:
            text = data.decode("latin-1", errors="ignore")
        except Exception:
            continue
        for match in LANG_OVERRIDE_PATTERN.finditer(text):
            normalized = normalize_lang_value(match.group(1))
            if normalized:
                languages.add(normalized)
    return languages


__all__ = ["detect_raw_marked_content_languages", "iter_content_stream_data"]
