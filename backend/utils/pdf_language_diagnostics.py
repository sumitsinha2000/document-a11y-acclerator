from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import pdfplumber
from pypdf import PdfReader

try:
    from pypdf.generic import (
        ContentStream,
        IndirectObject,
        TextStringObject,
        ByteStringObject,
    )
except Exception:  # pragma: no cover - defensive import guard
    ContentStream = None
    IndirectObject = None
    TextStringObject = None
    ByteStringObject = None

try:
    import pikepdf

    PIKEPDF_AVAILABLE = True
except Exception:  # pragma: no cover - defensive import guard
    pikepdf = None
    PIKEPDF_AVAILABLE = False

from backend.utils.language_detection import (
    collect_script_hints,
    detect_script_hint,
    is_valid_lang_tag,
    normalize_lang_value,
)
from backend.utils.pdf_stream_utils import detect_raw_marked_content_languages
from backend.wcag_validator import (
    _build_properties_lookup as _build_pike_properties_lookup,
    _normalize_operator_name,
    _resolve_pdf_object,
)


@dataclass
class PageLanguageDiagnostics:
    page: int
    has_marked_content_lang: bool = False
    script_hints: Set[str] = field(default_factory=set)
    extracted_text: Optional[str] = None


@dataclass
class LanguageDiagnostics:
    document_language: Optional[str]
    is_tagged: bool
    has_struct_tree: bool
    pages: List[PageLanguageDiagnostics]

    @property
    def has_marked_content_language(self) -> bool:
        return any(page.has_marked_content_lang for page in self.pages)


def _dict_get_by_name(d: Any, name: str) -> Any:
    """
    Get a key by name robustly across:
      - plain dict
      - pypdf DictionaryObject (NameObject keys)
      - pikepdf.Dictionary (Name keys)
    """
    if d is None:
        return None

    # Fast path: mapping-like objects with .get (dict, pikepdf.Dictionary, many pypdf dict-likes)
    try:
        val = d.get(name)
        if val is not None:
            return val
    except Exception:
        pass

    # Second try: if caller passed "Lang" instead of "/Lang" (or vice versa), normalize variants
    variants = {name}
    if name.startswith("/"):
        variants.add(name.lstrip("/"))
    else:
        variants.add(f"/{name}")

    # Iterate items and compare by string value
    try:
        for k, v in d.items():
            try:
                k_str = str(k)
            except Exception:
                continue
            if k_str in variants:
                return v
    except Exception:
        pass

    return None


def _build_pypdf_properties_lookup(page: Any) -> Dict[str, Any]:
    """Return mapping of property resource names to dictionaries (pypdf)."""
    properties: Dict[str, Any] = {}
    resources = page.get("/Resources") if hasattr(page, "get") else None
    if IndirectObject is not None and isinstance(resources, IndirectObject):
        resources = resources.get_object()

    if isinstance(resources, dict) or hasattr(resources, "items"):
        props_dict = _dict_get_by_name(resources, "/Properties") or _dict_get_by_name(
            resources, "Properties"
        )
        if IndirectObject is not None and isinstance(props_dict, IndirectObject):
            props_dict = props_dict.get_object()
        if isinstance(props_dict, dict) or hasattr(props_dict, "items"):
            try:
                items = props_dict.items()
            except Exception:
                items = []
            for key, value in items:
                key_str = str(key)
                properties[key_str] = value
                properties[key_str.lstrip("/")] = value
    return properties


def _extract_lang_from_bdc_operands(
    operands: Any, properties_lookup: Dict[str, Any]
) -> Optional[str]:
    """Pull /Lang value from BDC operands or referenced Properties dictionary."""
    try:
        op_list = list(operands) if isinstance(operands, (list, tuple)) else [operands]
    except Exception:
        op_list = [operands]

    # BDC operands are typically: [tag, properties] where properties may be an inline dict or a name
    if len(op_list) < 2:
        return None

    properties_entry = op_list[1]
    resolved = _resolve_pdf_object(properties_entry)

    lookup_candidates: List[Any] = [resolved]
    if resolved is not None:
        try:
            lookup_candidates.append(properties_lookup.get(str(resolved)))
            lookup_candidates.append(properties_lookup.get(str(resolved).lstrip("/")))
        except Exception:
            pass

    for candidate in lookup_candidates:
        candidate = _resolve_pdf_object(candidate)
        if isinstance(candidate, dict) or hasattr(candidate, "items"):
            lang_value = _dict_get_by_name(candidate, "/Lang") or _dict_get_by_name(
                candidate, "Lang"
            )
            normalized = normalize_lang_value(lang_value)
            if normalized:
                return normalized
    return None


def _extract_text_from_operands(operands: Any) -> Optional[str]:
    """Return normalized text from a Tj/TJ operand list."""
    if operands is None:
        return None

    samples: List[str] = []

    def _normalize(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if TextStringObject is not None and isinstance(value, TextStringObject):
            try:
                return str(value)
            except Exception:
                return None
        if ByteStringObject is not None and isinstance(value, ByteStringObject):
            for encoding in ("utf-16-be", "utf-8"):
                try:
                    decoded = bytes(value).decode(encoding, errors="ignore")
                    if decoded:
                        return decoded
                except Exception:
                    continue
        if hasattr(value, "decode"):
            for encoding in ("utf-16-be", "utf-8"):
                try:
                    decoded = value.decode(encoding, errors="ignore")
                    if decoded:
                        return decoded
                except Exception:
                    continue
        return None

    def _append(value: Any) -> None:
        snippet = _normalize(value)
        if snippet:
            cleaned = " ".join(snippet.split())
            if cleaned:
                samples.append(cleaned)

    try:
        op_list = list(operands) if isinstance(operands, (list, tuple)) else [operands]
    except Exception:
        op_list = [operands]

    for operand in op_list:
        if isinstance(operand, (list, tuple)):
            for entry in operand:
                _append(entry)
        else:
            _append(operand)

    if not samples:
        return None

    combined = " ".join(samples).strip()
    return combined or None


def _iter_page_operations(page: Any, pdf_reader: PdfReader) -> List[Any]:
    """Safely return content stream operations for a page (pypdf)."""
    if ContentStream is None:
        return []
    try:
        contents = page.get_contents()
        if contents is None:
            return []
        stream = ContentStream(contents, pdf_reader)
        return list(getattr(stream, "operations", []))
    except Exception:
        return []


def _scan_marked_content_with_pikepdf(
    pdf_path: str,
    pages: List[PageLanguageDiagnostics],
    doc_lang: Optional[str],
    is_tagged: bool,
    has_struct_tree: bool,
) -> Tuple[Optional[str], bool, bool]:
    """
    Use pikepdf to verify BDC spans and refine document tagging metadata.
    This is a best-effort supplement for diagnostics; failures are swallowed.
    """
    if not PIKEPDF_AVAILABLE or not pikepdf:
        return doc_lang, is_tagged, has_struct_tree

    pdf_doc = None
    try:
        pdf_doc = pikepdf.open(pdf_path)
        root = getattr(pdf_doc, "Root", None)

        if root and doc_lang is None:
            candidate = normalize_lang_value(_dict_get_by_name(root, "/Lang"))
            if candidate and is_valid_lang_tag(candidate):
                doc_lang = candidate

        mark_info = _dict_get_by_name(root, "/MarkInfo") if root else None
        if mark_info:
            try:
                is_tagged = bool(_dict_get_by_name(mark_info, "/Marked"))
            except Exception:
                pass

        struct_tree = _dict_get_by_name(root, "/StructTreeRoot") if root else None
        has_struct_tree = has_struct_tree or bool(struct_tree)

        for index, page in enumerate(pdf_doc.pages, start=1):
            if index - 1 >= len(pages):
                break
            page_diag = pages[index - 1]
            if page_diag.has_marked_content_lang:
                continue  # already detected via pypdf

            props_lookup = _build_pike_properties_lookup(page)
            try:
                operations = pikepdf.parse_content_stream(page)
            except Exception:
                operations = []

            for operands, operator in operations:
                op_name = _normalize_operator_name(operator)
                if op_name != "BDC":
                    continue
                lang_value = _extract_lang_from_bdc_operands(operands, props_lookup)
                if lang_value:
                    page_diag.has_marked_content_lang = True
                    break
    except Exception:
        pass
    finally:
        if pdf_doc is not None:
            try:
                pdf_doc.close()
            except Exception:
                pass

    return doc_lang, is_tagged, has_struct_tree


def collect_language_diagnostics(pdf_path: str) -> LanguageDiagnostics:
    """Lightweight, test-friendly diagnostics for language markers inside PDFs."""
    reader = PdfReader(pdf_path)
    catalog = reader.trailer.get("/Root", {}) if hasattr(reader, "trailer") else {}
    if IndirectObject is not None and isinstance(catalog, IndirectObject):
        catalog = catalog.get_object()

    doc_lang = (
        normalize_lang_value(_dict_get_by_name(catalog, "/Lang")) if catalog else None
    )
    if doc_lang and not is_valid_lang_tag(doc_lang):
        doc_lang = None

    mark_info = _dict_get_by_name(catalog, "/MarkInfo") if catalog else None
    if IndirectObject is not None and isinstance(mark_info, IndirectObject):
        mark_info = mark_info.get_object()

    is_tagged = bool(_dict_get_by_name(mark_info, "/Marked")) if mark_info else False
    has_struct_tree = (
        bool(_dict_get_by_name(catalog, "/StructTreeRoot")) if catalog else False
    )

    try:
        plumber_pdf = pdfplumber.open(pdf_path)
    except Exception:
        plumber_pdf = None

    pages: List[PageLanguageDiagnostics] = []
    try:
        for page_number, page in enumerate(reader.pages, start=1):
            page_diag = PageLanguageDiagnostics(page=page_number)
            properties_lookup = _build_pypdf_properties_lookup(page)
            text_segments: List[str] = []

            try:
                plumber_page = (
                    plumber_pdf.pages[page_number - 1]
                    if plumber_pdf and page_number - 1 < len(plumber_pdf.pages)
                    else None
                )
            except Exception:
                plumber_page = None

            for operands, operator in _iter_page_operations(page, reader):
                op_name = _normalize_operator_name(operator)

                if op_name == "BDC":
                    lang_value = _extract_lang_from_bdc_operands(
                        operands, properties_lookup
                    )
                    if lang_value:
                        page_diag.has_marked_content_lang = True

                elif op_name in ("Tj", "TJ"):
                    text = _extract_text_from_operands(operands)
                    if not text:
                        continue
                    text_segments.append(text)
                    script_hint = detect_script_hint(text)
                    if script_hint:
                        page_diag.script_hints.add(script_hint)

            if text_segments:
                page_diag.extracted_text = " ".join(text_segments)[:500]

            if not page_diag.has_marked_content_lang:
                raw_langs = detect_raw_marked_content_languages(page)
                if raw_langs:
                    page_diag.has_marked_content_lang = True

            def _apply_script_text(raw_text: str) -> None:
                if not raw_text:
                    return
                hints = collect_script_hints(raw_text)
                if hints:
                    page_diag.script_hints.update(hints)
                if page_diag.extracted_text is None:
                    page_diag.extracted_text = raw_text[:500]

            # Fallback extraction if no scripts found from operations
            if not page_diag.script_hints:
                try:
                    fallback_text = page.extract_text() or ""
                except Exception:
                    fallback_text = ""
                if fallback_text:
                    _apply_script_text(fallback_text)

            if not page_diag.script_hints and plumber_page is not None:
                try:
                    plumber_text = plumber_page.extract_text() or ""
                except Exception:
                    plumber_text = ""
                if plumber_text:
                    _apply_script_text(plumber_text)

            pages.append(page_diag)
    finally:
        if plumber_pdf is not None:
            try:
                plumber_pdf.close()
            except Exception:
                pass

    # Best-effort cross-check using pikepdf (more accurate for some PDFs)
    doc_lang, is_tagged, has_struct_tree = _scan_marked_content_with_pikepdf(
        pdf_path, pages, doc_lang, is_tagged, has_struct_tree
    )

    return LanguageDiagnostics(
        document_language=doc_lang,
        is_tagged=is_tagged,
        has_struct_tree=has_struct_tree,
        pages=pages,
    )


__all__ = [
    "collect_language_diagnostics",
    "LanguageDiagnostics",
    "PageLanguageDiagnostics",
]
