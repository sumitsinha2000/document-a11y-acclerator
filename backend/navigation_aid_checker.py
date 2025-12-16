"""
Navigation aid checker for PDF documents.

This module inspects simple PDF metadata/structure to decide whether a document
exposes at least one navigation aid (outline/bookmarks, internal /GoTo links on
early pages, or page labels). It purposely avoids OCR or layout analysis so it
remains fast on large PDFs.
"""

import logging
import os
from typing import Any, Dict, Iterable, Optional, Set

import pikepdf
from pikepdf import Name, String

logger = logging.getLogger(__name__)

DEFAULT_NAVIGATION_PAGE_THRESHOLD = 2
NAVIGATION_PAGE_THRESHOLD_ENV = "NAVIGATION_AID_PAGE_THRESHOLD"


def _parse_positive_int(value: Any) -> Optional[int]:
    """Return value as positive int if possible; otherwise None."""
    if value is None:
        return None

    try:
        number = int(value)
    except (TypeError, ValueError):
        return None

    return number if number > 0 else None


def get_navigation_page_threshold(override: Optional[int] = None) -> int:
    """Resolve effective navigation-page threshold.

    Order of precedence:
    1. Explicit override argument (if valid positive int)
    2. NAVIGATION_AID_PAGE_THRESHOLD env var
    3. DEFAULT_NAVIGATION_PAGE_THRESHOLD fallback
    """

    override_value = _parse_positive_int(override)
    if override_value is not None:
        return override_value

    env_value = _parse_positive_int(os.getenv(NAVIGATION_PAGE_THRESHOLD_ENV))
    if env_value is not None:
        return env_value

    return DEFAULT_NAVIGATION_PAGE_THRESHOLD


def _resolve_pdf_object(value: Any) -> Any:
    """Dereference indirect objects safely; return the original if not possible."""
    if value is None:
        return None

    try:
        get_obj = getattr(value, "get_object", None)
        if callable(get_obj):
            return get_obj()
    except Exception:
        return value

    return value


def _iter_array_items(value: Any) -> Iterable[Any]:
    """Yield items from a pikepdf.Array or list."""
    if isinstance(value, list):
        return value
    if isinstance(value, pikepdf.Array):
        return value
    return ()


def _object_key(obj: Any) -> Optional[str]:
    """Stable key for comparing pikepdf objects (based on object number)."""
    obj = getattr(obj, "obj", obj)
    obj = _resolve_pdf_object(obj)

    for attr in ("objgen", "reference"):
        ref = getattr(obj, attr, None)
        if ref:
            try:
                return f"{int(ref[0])}:{int(ref[1])}"
            except Exception:
                continue
    return None


def _build_page_lookup(pdf: pikepdf.Pdf) -> Dict[str, int]:
    """Map page object references to 1-based page numbers."""
    lookup: Dict[str, int] = {}
    try:
        for idx, page in enumerate(pdf.pages, 1):
            key = _object_key(page)
            if key:
                lookup[key] = idx
    except Exception as exc:
        logger.debug("[NavigationAidChecker] Failed to build page lookup: %s", exc)
    return lookup


def _extract_named_destinations(pdf: pikepdf.Pdf) -> Dict[str, Any]:
    """Read the /Names -> /Dests name tree so /GoTo destinations can resolve."""
    named_map: Dict[str, Any] = {}
    names_root = pdf.Root.get("/Names")
    if not names_root:
        return named_map

    dests_root = names_root.get("/Dests")

    def _walk(node: Any) -> None:
        node = _resolve_pdf_object(node)
        if node is None:
            return

        names_array = node.get("/Names")
        if isinstance(names_array, (list, pikepdf.Array)):
            entries = list(_iter_array_items(names_array))
            for idx in range(0, len(entries), 2):
                name = entries[idx]
                target = entries[idx + 1] if idx + 1 < len(entries) else None
                if name and target is not None:
                    named_map[str(name)] = target

        kids = node.get("/Kids")
        if isinstance(kids, (list, pikepdf.Array)):
            for kid in _iter_array_items(kids):
                _walk(kid)

    _walk(dests_root)
    return named_map


def _resolve_destination_page(
    pdf: pikepdf.Pdf,
    dest: Any,
    page_lookup: Dict[str, int],
    named_destinations: Dict[str, Any],
    visited_names: Optional[Set[str]] = None,
) -> Optional[int]:
    """Resolve a /Dest or /D value to a 1-based page number."""
    dest = _resolve_pdf_object(dest)
    if dest is None:
        return None

    if isinstance(dest, (list, pikepdf.Array)):
        entries = list(_iter_array_items(dest))
        if not entries:
            return None
        return page_lookup.get(_object_key(entries[0]))

    normalized = None
    if isinstance(dest, (str, bytes, Name, String)):
        normalized = str(dest)

    if normalized:
        visited = set(visited_names or set())
        if normalized in visited:
            return None
        visited.add(normalized)
        alias = named_destinations.get(normalized)
        if alias is not None:
            return _resolve_destination_page(
                pdf, alias, page_lookup, named_destinations, visited
            )

    if isinstance(dest, pikepdf.Dictionary):
        for key in ("/D", "/Dest"):
            target = dest.get(key)
            if target is None:
                continue
            resolved = _resolve_destination_page(
                pdf, target, page_lookup, named_destinations, visited_names
            )
            if resolved is not None:
                return resolved

    return None


def _outline_entry_has_dest(
    pdf: pikepdf.Pdf,
    entry: Any,
    page_lookup: Dict[str, int],
    named_destinations: Dict[str, Any],
    visited: Set[int],
) -> bool:
    """Depth-first search of the outline tree for any actionable destination."""
    entry = _resolve_pdf_object(entry)
    if entry is None or id(entry) in visited:
        return False
    visited.add(id(entry))

    if not isinstance(entry, pikepdf.Dictionary):
        return False

    dest = entry.get("/Dest")
    if dest is None:
        action = entry.get("/A")
        if isinstance(action, pikepdf.Dictionary) and str(action.get("/S")) == "/GoTo":
            dest = action.get("/D") or action.get("/Dest")

    if dest is not None and _resolve_destination_page(
        pdf, dest, page_lookup, named_destinations
    ):
        return True

    first_child = entry.get("/First")
    if first_child and _outline_entry_has_dest(
        pdf, first_child, page_lookup, named_destinations, visited
    ):
        return True

    next_sibling = entry.get("/Next")
    if next_sibling and _outline_entry_has_dest(
        pdf, next_sibling, page_lookup, named_destinations, visited
    ):
        return True

    return False


def has_outline_navigation(
    pdf: pikepdf.Pdf, page_lookup: Dict[str, int], named_destinations: Dict[str, Any]
) -> bool:
    """Detect a bookmark/outline tree with at least one valid destination."""
    try:
        outlines_root = pdf.Root.get("/Outlines")
        if not outlines_root:
            return False
        first_entry = outlines_root.get("/First")
        if not first_entry:
            return False
        return _outline_entry_has_dest(
            pdf, first_entry, page_lookup, named_destinations, set()
        )
    except Exception as exc:
        logger.debug("[NavigationAidChecker] Outline detection skipped: %s", exc)
        return False


def has_internal_toc_links(
    pdf: pikepdf.Pdf,
    page_lookup: Dict[str, int],
    named_destinations: Dict[str, Any],
    max_pages_to_scan: int = 4,
) -> bool:
    """
    Look for /GoTo link annotations on early pages.

    Many PDFs place a Table of Contents near the start; scanning the first few
    pages keeps the check fast even for long documents.
    """
    try:
        max_page = min(max_pages_to_scan, len(pdf.pages))
        for idx in range(max_page):
            page = pdf.pages[idx]
            annots = getattr(page, "Annots", None)
            if not annots:
                continue

            for annot in annots:
                annot_obj = _resolve_pdf_object(annot)
                if not isinstance(annot_obj, pikepdf.Dictionary):
                    continue

                dest = None
                action = annot_obj.get("/A")
                if isinstance(action, pikepdf.Dictionary) and str(action.get("/S")) == "/GoTo":
                    dest = action.get("/D") or action.get("/Dest")
                if dest is None and "/Dest" in annot_obj:
                    dest = annot_obj.get("/Dest")

                if dest is not None and _resolve_destination_page(
                    pdf, dest, page_lookup, named_destinations
                ):
                    return True
    except Exception as exc:
        logger.debug("[NavigationAidChecker] TOC link detection skipped: %s", exc)
        return False

    return False


def has_page_labels(pdf: pikepdf.Pdf) -> bool:
    """Detect a /PageLabels dictionary in the catalog."""
    try:
        labels = pdf.Root.get("/PageLabels")
        if not labels:
            return False

        labels = _resolve_pdf_object(labels)
        if not isinstance(labels, pikepdf.Dictionary):
            return False

        nums = labels.get("/Nums")
        if isinstance(nums, (list, pikepdf.Array)) and len(nums) >= 2:
            return True

        kids = labels.get("/Kids")
        if isinstance(kids, (list, pikepdf.Array)) and len(kids) > 0:
            return True
    except Exception as exc:
        logger.debug("[NavigationAidChecker] Page label detection skipped: %s", exc)
        return False

    return False


def check_navigation_aids(
    pdf_path: str,
    length_threshold: Optional[int] = None,
    max_toc_pages: int = 4,
) -> Dict[str, Any]:
    """Check navigation aids and return a structured result."""
    effective_threshold = get_navigation_page_threshold(length_threshold)

    with pikepdf.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        page_lookup = _build_page_lookup(pdf)
        named_destinations = _extract_named_destinations(pdf)

        outline_found = has_outline_navigation(pdf, page_lookup, named_destinations)
        toc_links_found = has_internal_toc_links(
            pdf, page_lookup, named_destinations, max_pages_to_scan=max_toc_pages
        )
        page_labels_found = has_page_labels(pdf)

        has_navigation = outline_found or toc_links_found or page_labels_found
        passed = has_navigation or page_count < effective_threshold

        return {
            "page_count": page_count,
            "threshold": effective_threshold,
            "navigation_aids": {
                "outline": outline_found,
                "table_of_contents_links": toc_links_found,
                "page_labels": page_labels_found,
            },
            "status": "PASS" if passed else "FAIL",
            "reason": (
                "Navigation aid present."
                if has_navigation
                else "Below page threshold."
                if page_count < effective_threshold
                else "Long document without navigation aids."
            ),
        }


__all__ = ["check_navigation_aids", "get_navigation_page_threshold"]
