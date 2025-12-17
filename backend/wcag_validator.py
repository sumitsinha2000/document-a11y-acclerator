"""
WCAG 2.1 and PDF/UA-1 Validation Algorithms
Based on veraPDF-wcag-algs: https://github.com/veraPDF/veraPDF-wcag-algs

This module implements validation algorithms for WCAG 2.1 and PDF/UA-1 compliance
without requiring external dependencies like veraPDF CLI.
"""

import pikepdf
from pikepdf import Name, String
from typing import Dict, List, Any, Tuple, Optional, Callable, Set, Mapping, Iterable, cast
import logging
from collections import defaultdict
import re
import pdfplumber
from pdfplumber.utils.geometry import get_bbox_overlap

from backend.navigation_aid_checker import (
    check_navigation_aids,
    get_navigation_page_threshold,
)

logger = logging.getLogger(__name__)
GENERIC_LINK_TEXTS = {"click here", "here", "link"}


def _resolve_pdf_object(value: Any) -> Any:
    """Return the underlying direct object if value is an indirect reference.
    If the value is already a direct object or cannot be dereferenced, return it unchanged.
    """
    if value is None:
        return None

    try:
        get_obj = getattr(value, "get_object", None)
        if callable(get_obj):
            return get_obj()
    except Exception:
        # Direct object or non-dereferenceable; just return as-is
        return value

    return value


def _object_key(obj: Any) -> Optional[str]:
    """Produce a stable key for comparing pikepdf objects when possible."""
    if obj is None:
        return None

    resolved = getattr(obj, 'obj', obj)
    resolved = _resolve_pdf_object(resolved)

    for attr in ('objgen', 'reference'):
        ref = getattr(resolved, attr, None)
        if ref:
            try:
                return f"{int(ref[0])}:{int(ref[1])}"
            except Exception:
                continue

    return None


def _iter_array_items(value: Any) -> Iterable[Any]:
    """Best-effort iterable wrapper for pikepdf.Array/list values."""
    if isinstance(value, list):
        return value
    if isinstance(value, pikepdf.Array):
        return cast(Iterable[Any], value)
    return ()


def _array_to_list(value: Any) -> List[Any]:
    """Convert pikepdf.Array/list to a Python list for safer iteration."""
    if isinstance(value, list):
        return value
    if isinstance(value, pikepdf.Array):
        return list(cast(Iterable[Any], value))
    return []

def _element_has_alt_text(element: Any) -> bool:
    """Determine if a structure element (or its immediate children) expose alt text."""
    element = _resolve_pdf_object(element)
    if not isinstance(element, pikepdf.Dictionary):
        return False

    def _dict_has_alt(d: pikepdf.Dictionary) -> bool:
        for attr in ("/Alt", "/ActualText"):
            value = d.get(attr)
            if value and str(value).strip():
                return True
        return False

    # 1) Direct alt on this element (covers the AU Figure with Alt)
    if _dict_has_alt(element):
        return True

    # 2) Some tools put alt on an immediate child of the element's /K
    children = element.get("/K")
    if not children:
        return False

    for child in _iter_structure_children(children):
        child = _resolve_pdf_object(child)
        if isinstance(child, pikepdf.Dictionary) and _dict_has_alt(child):
            return True

    return False


def _extract_structure_refs(entry: Any) -> Tuple[List[int], List[Any]]:
    """Collect MCIDs and object references within a structure element's /K tree.

    Returns lists of MCIDs and OBJR references discovered anywhere under the /K subtree.
    """
    mcids: Set[int] = set()
    obj_refs: Set[Any] = set()

    def _walk(value: Any) -> None:
        value = _resolve_pdf_object(value)
        if value is None:
            return

        # Direct integer MCID (rare but easy)
        if isinstance(value, int):
            mcids.add(int(value))
            return

        if isinstance(value, pikepdf.Dictionary):
            # MCID inside a dictionary (with or without explicit /Type)
            if "/MCID" in value:
                try:
                    mcids.add(int(value.get("/MCID")))
                except Exception:
                    pass

            # Type-based handling for older /MCR /OBJR patterns
            type_obj = value.get("/Type")
            value_type = str(type_obj) if type_obj is not None else ""

            if value_type == "/MCR" and "/MCID" in value:
                try:
                    mcids.add(int(value.MCID))
                except Exception:
                    pass

            if value_type == "/OBJR" and "/Obj" in value:
                try:
                    obj_refs.add(value.Obj)
                except Exception:
                    pass

            # Recurse into nested /K if present
            nested = value.get("/K")
            if nested is not None:
                _walk(nested)

            return

        if isinstance(value, (list, pikepdf.Array)):
            for item in _iter_array_items(value):
                _walk(item)

    _walk(entry)
    return list(mcids), list(obj_refs)


def _iter_structure_children(entry: Any) -> List[Any]:
    """Yield child structure elements contained within /K."""
    entry = _resolve_pdf_object(entry)
    if entry is None:
        return []

    if isinstance(entry, (list, pikepdf.Array)):
        return list(_iter_array_items(entry))

    if isinstance(entry, pikepdf.Dictionary):
        # Only dictionaries with structure semantics should be traversed as children.
        if '/S' in entry or '/K' in entry:
            return [entry]

    return []


def _normalize_operator_name(operator: Any) -> str:
    """Return a comparable operator name for content stream instructions.

    Be defensive: some pikepdf objects raise when arbitrary attributes are
    accessed, so we always guard getattr/str() with try/except and fall
    back to an empty string on failure.
    """
    # First try attribute-style names (e.g. Operator.name) without assuming
    # the object is a dictionary/stream.
    try:
        raw_name = getattr(operator, "name", None)
    except Exception:
        raw_name = None

    if raw_name is not None:
        try:
            name = str(raw_name)
        except Exception:
            name = ""
    else:
        # Fall back to the string representation of the operator itself
        try:
            name = str(operator)
        except Exception:
            return ""

    if name.startswith("/"):
        name = name[1:]
    return name

def _build_page_reference_lookup(pdf: pikepdf.Pdf) -> Dict[str, Any]:
    """Map page object references to page objects for quick resolution."""
    lookup: Dict[str, Any] = {}
    try:
        for page in pdf.pages:
            key = _object_key(page)
            if key:
                lookup[key] = page
    except Exception:
        return lookup
    return lookup


def _build_properties_lookup(page: Any) -> Dict[str, Any]:
    """Return mapping of property resource names to dictionaries."""
    properties: Dict[str, Any] = {}
    resources = getattr(page, "Resources", None)
    if resources and "/Properties" in resources:
        try:
            props_dict = resources.Properties
            if isinstance(props_dict, pikepdf.Dictionary):
                for key, value in props_dict.items():
                    key_str = str(key)
                    properties[key_str] = value
                    properties[key_str.lstrip("/")] = value
        except Exception:
            return properties
    return properties


def _extract_mcid_from_properties(properties_entry: Any, properties_lookup: Mapping[str, Any]) -> Optional[int]:
    """Extract MCID from an inline property dict or a named property resource."""
    try:
        resolved = _resolve_pdf_object(properties_entry)
        if isinstance(resolved, Name):
            resolved = properties_lookup.get(str(resolved)) or properties_lookup.get(str(resolved).lstrip("/"))
        elif isinstance(resolved, str):
            resolved = properties_lookup.get(resolved) or properties_lookup.get(resolved.lstrip("/"))

        resolved = _resolve_pdf_object(resolved)
        if isinstance(resolved, pikepdf.Dictionary) and "/MCID" in resolved:
            try:
                return int(resolved.MCID)
            except Exception:
                try:
                    return int(str(resolved.get("/MCID")))
                except Exception:
                    return None
    except Exception:
        return None
    return None


def _extract_mcid_from_bdc_operands(operands: Any, properties_lookup: Mapping[str, Any]) -> Optional[int]:
    """Pull MCID value from BDC operands when present."""
    try:
        op_list = list(operands) if isinstance(operands, (list, tuple, pikepdf.Array)) else []
    except Exception:
        op_list = []

    if len(op_list) < 2:
        return None

    properties_entry = op_list[1]
    return _extract_mcid_from_properties(properties_entry, properties_lookup)


def _resolve_xobject_from_do(page: Any, operands: Any) -> Any:
    """Resolve the XObject referenced by a Do operator on the given page."""
    resources = getattr(page, "Resources", None)
    if resources is None or "/XObject" not in resources:
        return None

    xobjects = resources.XObject
    try:
        op_list = list(operands) if isinstance(operands, (list, tuple, pikepdf.Array)) else [operands]
    except Exception:
        op_list = [operands]

    name_obj = op_list[0] if op_list else None

    candidates: List[Any] = []
    if name_obj is not None:
        candidates.append(name_obj)
        try:
            name_str = str(name_obj)
            candidates.append(name_str)
            candidates.append(name_str.lstrip("/"))
            try:
                candidates.append(Name(name_str))
            except Exception:
                pass
            try:
                candidates.append(Name(name_str.lstrip("/")))
            except Exception:
                pass
        except Exception:
            pass

    for candidate in candidates:
        try:
            if candidate in xobjects:
                return xobjects[candidate]
        except Exception:
            try:
                value = xobjects.get(candidate)
            except Exception:
                value = None
            if value is not None:
                return value

    return None

def _collect_drawn_image_xobject_keys(container: Any) -> Set[str]:
    """
    Return the set of /Image XObject object keys that are actually drawn
    via Do operators inside the content stream of ``container``.
    """
    drawn: Set[str] = set()

    if container is None or not hasattr(pikepdf, "parse_content_stream"):
        return drawn

    try:
        operations = pikepdf.parse_content_stream(container)
    except Exception:
        return drawn

    for operands, operator in operations:
        op_name = _normalize_operator_name(operator)
        if op_name != "Do":
            continue

        xobject = _resolve_xobject_from_do(container, operands)
        if xobject is None:
            continue

        try:
            subtype = xobject.get("/Subtype")
            subtype_str = str(subtype) if subtype is not None else ""
        except Exception:
            subtype_str = ""

        if subtype_str == "/Image":
            key = _object_key(xobject)
            if key:
                drawn.add(key)
        elif subtype_str == "/Form":
            nested = _collect_drawn_image_xobject_keys(xobject)
            if nested:
                drawn.update(nested)

    return drawn



def _map_page_mcids_to_xobject_keys(page: Any) -> Dict[int, Set[str]]:
    """Return mapping of MCID -> XObject keys for a single page.

    This walks the page content stream AND any nested Form XObjects,
    tracking MCID scopes across BDC/BMC/EMC and associating image
    XObjects drawn inside those scopes.
    """
    mapping: Dict[int, Set[str]] = defaultdict(set)
    if page is None or not hasattr(pikepdf, "parse_content_stream"):
        return mapping

    mcid_stack: List[Optional[int]] = []

    def _active_mcid() -> Optional[int]:
        for value in reversed(mcid_stack):
            if value is not None:
                return value
        return None

    def _merge_properties(
        parent_props: Optional[Mapping[str, Any]],
        local_props: Mapping[str, Any],
    ) -> Dict[str, Any]:
        if parent_props:
            merged: Dict[str, Any] = dict(parent_props)
            merged.update(local_props)
            return merged
        return dict(local_props)

    def _walk_container(
        container: Any,
        inherited_properties: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Walk a page or Form XObject content stream.

        - Tracks MCID scopes using mcid_stack.
        - Recurses into nested /Form XObjects.
        - Associates active MCIDs to /Image XObjects.
        """
        # Build properties lookup for this container and merge with inherited
        local_props = _build_properties_lookup(container)
        properties_lookup = _merge_properties(inherited_properties, local_props)

        try:
            operations = pikepdf.parse_content_stream(container)
        except Exception:
            return

        try:
            for operands, operator in operations:
                op_name = _normalize_operator_name(operator)

                if op_name in ("BDC", "BMC"):
                    mcid_value = (
                        _extract_mcid_from_bdc_operands(operands, properties_lookup)
                        if op_name == "BDC"
                        else None
                    )
                    mcid_stack.append(mcid_value)

                elif op_name == "EMC":
                    if mcid_stack:
                        mcid_stack.pop()

                elif op_name == "Do":
                    # Resolve the XObject in the context of this container
                    xobject = _resolve_xobject_from_do(container, operands)
                    if xobject is None:
                        continue

                    # Best-effort /Subtype lookup
                    try:
                        subtype = xobject.get("/Subtype")
                        subtype_str = str(subtype) if subtype is not None else ""
                    except Exception:
                        subtype_str = ""

                    # Always recurse into Form XObjects – they may contain
                    # their own BDC/MCID + image drawing inside.
                    if subtype_str == "/Form":
                        _walk_container(xobject, properties_lookup)

                    # If there is an active MCID and this is an image, record mapping.
                    active = _active_mcid()
                    if active is not None and subtype_str == "/Image":
                        xobj_key = _object_key(xobject)
                        if xobj_key:
                            mapping.setdefault(active, set()).add(xobj_key)

        except Exception:
            return

    # Kick off traversal from the page; nested Form XObjects are handled
    _walk_container(page)
    return mapping


def _build_figure_alt_lookup(pdf) -> Dict[str, Any]:
    """Construct lookup data for Figure elements that expose alt text."""
    lookup = {
        'xobject_keys': set(),
        'page_mcids': defaultdict(set),
        'mcid_xobject_keys': set(),
        'page_alt_counts': defaultdict(int),
    }

    if pdf is None:
        return lookup

    try:
        struct_tree_root = pdf.Root.get('/StructTreeRoot')
    except Exception:
        struct_tree_root = None

    if not struct_tree_root:
        return lookup

    def _walk(element: Any, current_page: Any = None):
        element = _resolve_pdf_object(element)
        if element is None:
            return

        next_page = current_page
        if isinstance(element, pikepdf.Dictionary):
            if '/Pg' in element:
                next_page = element.get('/Pg')

            struct_type = element.get('/S')
            if struct_type and str(struct_type) == '/Figure' and _element_has_alt_text(element):
                page_key = _object_key(next_page) if next_page is not None else None
                mcids, obj_refs = _extract_structure_refs(element.get('/K'))

                if page_key is not None:
                    lookup['page_alt_counts'][page_key] += 1
                    for mcid in mcids:
                        lookup['page_mcids'][page_key].add(mcid)

                for obj_ref in obj_refs:
                    ref_key = _object_key(obj_ref)
                    if ref_key:
                        lookup['xobject_keys'].add(ref_key)

            children = element.get('/K')
            for child in _iter_structure_children(children):
                _walk(child, next_page)

        elif isinstance(element, (list, pikepdf.Array)):
            for child in _iter_array_items(element):
                _walk(child, current_page)

    try:
        _walk(struct_tree_root)
    except Exception:
        return lookup

    try:
        page_lookup = _build_page_reference_lookup(pdf)
        for page_key, mcids in lookup['page_mcids'].items():
            page = page_lookup.get(page_key)
            if page is None:
                continue

            mcid_map = _map_page_mcids_to_xobject_keys(page)
            for mcid in mcids:
                xobject_keys = mcid_map.get(mcid)
                if xobject_keys:
                    lookup['mcid_xobject_keys'].update(xobject_keys)
    except Exception:
        return lookup

    return lookup


def has_figure_alt_text(xobject: Any, lookup: Optional[Dict[str, Any]]) -> bool:
    """Return True if the XObject is linked to a Figure element with alt text."""
    if not lookup or xobject is None:
        return False

    object_key = _object_key(xobject)
    if not object_key:
        return False

    if object_key in lookup.get('xobject_keys', set()):
        return True

    mcid_keys = lookup.get('mcid_xobject_keys', set())
    return object_key in mcid_keys


def build_figure_alt_lookup(pdf) -> Dict[str, Any]:
    """Public helper to build Figure alt mappings for other modules."""
    return _build_figure_alt_lookup(pdf)


class WCAGValidator:
    """
    Implements WCAG 2.1 and PDF/UA-1 validation algorithms based on veraPDF validation profiles.
    
    Based on:
    - veraPDF-wcag-algs: https://github.com/veraPDF/veraPDF-wcag-algs
    - veraPDF-validation: https://github.com/veraPDF/veraPDF-validation
    - veraPDF-validation-profiles: https://github.com/veraPDF/veraPDF-validation-profiles
    
    Key validation areas:
    1. PDF/UA Identification Schema (ISO 14289-1:7.1)
    2. Document Structure and Tagging (ISO 14289-1:7.1)
    3. Structure Tree Validation (ISO 14289-1:7.2-7.8)
    4. Alternative Text (WCAG 1.1.1, ISO 14289-1:7.18)
    5. Document Language (WCAG 3.1.1, ISO 14289-1:7.2)
    6. Document Title (WCAG 2.4.2, ISO 14289-1:7.1)
    7. Reading Order (WCAG 1.3.2, ISO 14289-1:7.2)
    8. Table Structure (WCAG 1.3.1, ISO 14289-1:7.5)
    9. Heading Hierarchy (WCAG 1.3.1, ISO 14289-1:7.4)
    10. Form Fields (WCAG 3.3.2, ISO 14289-1:7.18)
    """
    
    # WCAG 2.1 Contrast Ratios
    CONTRAST_NORMAL_AA = 4.5  # Normal text, Level AA
    CONTRAST_LARGE_AA = 3.0   # Large text (18pt+), Level AA
    CONTRAST_NORMAL_AAA = 7.0  # Normal text, Level AAA
    CONTRAST_LARGE_AAA = 4.5   # Large text, Level AAA
    
    # PDF/UA-1 Required Structure Elements
    REQUIRED_STRUCTURE_TYPES = {
        'Document', 'Part', 'Art', 'Sect', 'Div', 'BlockQuote', 'Caption',
        'TOC', 'TOCI', 'Index', 'NonStruct', 'Private', 'P', 'H', 'H1', 'H2',
        'H3', 'H4', 'H5', 'H6', 'L', 'LI', 'Lbl', 'LBody', 'Table', 'TR',
        'TH', 'TD', 'THead', 'TBody', 'TFoot', 'Span', 'Quote', 'Note',
        'Reference', 'BibEntry', 'Code', 'Link', 'Annot', 'Ruby', 'RB', 'RT',
        'RP', 'Warichu', 'WT', 'WP', 'Figure', 'Formula', 'Form'
    }

    def _normalize_structure_type(self, struct_type: Any) -> str:
        """Normalize structure types by stripping leading slashes."""
        if struct_type is None:
            return ""
        return str(struct_type).lstrip('/')
    
    def __init__(self, pdf_path: str):
        """Initialize validator with PDF file path."""
        self.pdf_path = pdf_path
        self.pdf = None
        self.issues = defaultdict(list)
        self.wcag_compliance = {'A': True, 'AA': True, 'AAA': True}
        self.pdfua_compliance = True
        self._figure_alt_lookup = None
        self._named_destinations: Optional[Dict[str, Any]] = None
        self._page_lookup = None
        self._role_map_cache = None
        self._role_map_cache_initialized = False
        self._page_drawn_image_cache: Dict[str, Set[str]] = {}
        self.navigation_aid_result: Optional[Dict[str, Any]] = None
        self.navigation_page_threshold = get_navigation_page_threshold()
    
    def _get_role_map(self):
        """Return the PDF RoleMap dictionary, caching when possible."""
        if self._role_map_cache_initialized:
            return self._role_map_cache

        self._role_map_cache_initialized = True
        role_map = None

        try:
            pdf = self.pdf
            if pdf and '/StructTreeRoot' in pdf.Root:
                struct_tree_root = pdf.Root.StructTreeRoot
                if '/RoleMap' in struct_tree_root:
                    role_map = struct_tree_root.RoleMap
        except Exception as exc:
            logger.debug(f"[WCAGValidator] Could not read RoleMap: {exc}")

        self._role_map_cache = role_map
        return role_map

    def _resolve_role_mapped_type(self, struct_type: Any) -> str:
        """Return the effective structure type after applying RoleMap mappings."""
        normalized = self._normalize_structure_type(struct_type)
        if not normalized:
            return ""

        role_map = self._get_role_map()
        if not role_map:
            return normalized

        visited = set()
        current = normalized
        while True:
            if current in self.REQUIRED_STRUCTURE_TYPES:
                return current
            if current in visited:
                return current
            visited.add(current)

            mapped = self._find_role_map_value(current, role_map)
            if not mapped:
                return current

            mapped_norm = self._normalize_structure_type(mapped)
            if not mapped_norm:
                return current
            current = mapped_norm

    def _get_page_lookup(self) -> Dict[str, int]:
        """Return mapping from page object references to 1-based page numbers."""
        if self._page_lookup is not None:
            return self._page_lookup

        lookup: Dict[str, int] = {}
        pdf = self.pdf
        if pdf is not None:
            try:
                for page_num, page in enumerate(pdf.pages, 1):
                    key = _object_key(page)
                    if key:
                        lookup[key] = page_num
            except Exception as exc:
                logger.debug(f"[WCAGValidator] Failed to build page lookup: {exc}")

        self._page_lookup = lookup
        return lookup

    def _resolve_page_number(self, page_ref: Any) -> Optional[int]:
        """Resolve a page reference to its 1-based page number."""
        if page_ref is None or self.pdf is None:
            return None

        lookup = self._get_page_lookup()
        page_key = _object_key(page_ref)
        if page_key and page_key in lookup:
            return lookup[page_key]

        try:
            if isinstance(page_ref, int):
                return int(page_ref)
        except Exception:
            return None

        return None

    def _determine_page_number(self, page_ref: Any, element: Optional[Any] = None) -> Optional[int]:
        """Determine the best page number for an element, falling back to descendants."""
        page_num = self._resolve_page_number(page_ref)
        if page_num is not None:
            return page_num

        if element is not None:
            return self._find_descendant_page_number(element, set())

        return None

    def _find_descendant_page_number(self, element: Any, visited: set) -> Optional[int]:
        """Search descendants for a usable /Pg reference."""
        element = _resolve_pdf_object(element)
        if not isinstance(element, pikepdf.Dictionary):
            return None

        element_id = id(element)
        if element_id in visited:
            return None
        visited.add(element_id)

        if '/Pg' in element:
            page_num = self._resolve_page_number(element.get('/Pg'))
            if page_num is not None:
                return page_num

        for child in self._get_child_structure_elements(element):
            page_num = self._find_descendant_page_number(child, visited)
            if page_num is not None:
                return page_num

        return None

    def _traverse_structure(self, visitor: Callable[[pikepdf.Dictionary, Any], None]):
        """Traverse the structure tree depth-first and invoke visitor for structure elements."""
        pdf = self.pdf
        if pdf is None or '/StructTreeRoot' not in pdf.Root:
            return

        struct_tree_root = pdf.Root.StructTreeRoot
        if '/K' not in struct_tree_root:
            return

        def _walk(node: Any, current_page: Any):
            node = _resolve_pdf_object(node)
            if node is None:
                return

            if isinstance(node, pikepdf.Dictionary):
                next_page = current_page
                if '/Pg' in node:
                    next_page = node.get('/Pg')

                if '/S' in node:
                    try:
                        visitor(node, next_page)
                    except Exception as exc:
                        logger.debug(f"[WCAGValidator] Structure visitor error: {exc}")

                if '/K' in node:
                    _walk(node.K, next_page)
                return

            if isinstance(node, (list, pikepdf.Array)):
                for child in _iter_array_items(node):
                    _walk(child, current_page)

        try:
            _walk(struct_tree_root.K, None)
        except Exception as exc:
            logger.debug(f"[WCAGValidator] Failed to traverse structure tree: {exc}")

    def _collect_headings_in_order(self) -> List[Dict[str, Any]]:
        """Collect heading elements in reading order with level, text, and page info."""
        headings: List[Dict[str, Any]] = []

        def _visitor(element: pikepdf.Dictionary, page_ref: Any):
            resolved_type = self._resolve_role_mapped_type(element.get('/S'))
            level = self._get_heading_level(element, resolved_type)
            if level is None:
                return

            headings.append({
                'level': level,
                'page': self._determine_page_number(page_ref, element),
                'title': self._extract_element_label(element),
                'struct_type': resolved_type or self._normalize_structure_type(element.get('/S'))
            })

        self._traverse_structure(_visitor)
        return headings

    def _get_heading_level(self, element: Any, resolved_type: Optional[str]) -> Optional[int]:
        """Return heading level (1-6) when available."""
        if not resolved_type:
            return None

        if resolved_type.startswith('H') and len(resolved_type) == 2 and resolved_type[1].isdigit():
            try:
                level = int(resolved_type[1])
                if 1 <= level <= 6:
                    return level
            except Exception:
                return None

        if resolved_type == 'H':
            for key in ('/Level', '/level', '/Lvl'):
                raw_level = element.get(key) if isinstance(element, pikepdf.Dictionary) else None
                if raw_level is None:
                    continue
                try:
                    level = int(str(raw_level))
                except Exception:
                    continue
                if 1 <= level <= 6:
                    return level

        return None

    def _clean_text_snippet(self, value: Any, limit: int = 80) -> Optional[str]:
        """Normalize a value to a short text snippet for reporting."""
        if value is None:
            return None

        try:
            snippet = re.sub(r'\s+', ' ', str(value)).strip()
        except Exception:
            return None

        if not snippet:
            return None
        if len(snippet) > limit:
            snippet = snippet[:limit - 1].rstrip() + '…'
        return snippet

    def _extract_element_label(self, element: Any) -> Optional[str]:
        """Extract a human-readable label from a structure element."""
        if not isinstance(element, pikepdf.Dictionary):
            return None

        for key in ('/ActualText', '/Alt', '/T'):
            snippet = self._clean_text_snippet(element.get(key))
            if snippet:
                return snippet
        return None

    def _get_child_structure_elements(self, element: Any) -> List[pikepdf.Dictionary]:
        """Return direct child structure elements under an element's /K entry."""
        children: List[pikepdf.Dictionary] = []
        if not isinstance(element, pikepdf.Dictionary):
            return children
        if '/K' not in element:
            return children

        def _collect(payload: Any):
            payload = _resolve_pdf_object(payload)
            if payload is None:
                return

            if isinstance(payload, pikepdf.Dictionary):
                if '/S' in payload:
                    children.append(payload)
                elif '/K' in payload:
                    _collect(payload.K)
                return

            if isinstance(payload, (list, pikepdf.Array)):
                for entry in _iter_array_items(payload):
                    _collect(entry)

        try:
            _collect(element.K)
        except Exception as exc:
            logger.debug(f"[WCAGValidator] Failed collecting child elements: {exc}")

        return children
        
    def validate(self) -> Dict[str, Any]:
        """
        Run all validation checks and return comprehensive results.
        
        Returns:
            Dict containing:
            - wcagIssues: List of WCAG violations
            - pdfuaIssues: List of PDF/UA violations
            - wcagCompliance: Compliance levels (A, AA, AAA)
            - pdfuaCompliance: PDF/UA compliance status
            - wcagScore: WCAG compliance score (0-100)
            - pdfuaScore: PDF/UA compliance score (0-100)
            - summary: Overall compliance summary
        """
        try:
            self.pdf = pikepdf.open(self.pdf_path)
            logger.info(f"[WCAGValidator] Starting validation for {self.pdf_path}")
            
            # Run all validation checks
            self._validate_document_structure()
            self._validate_document_language()
            self._validate_document_title()
            self._validate_structure_tree()
            self._validate_reading_order()
            self._validate_sensory_characteristics()
            self._validate_bypass_blocks()
            self._validate_multiple_ways()
            self._validate_alternative_text()
            self._validate_table_structure()
            self._validate_heading_hierarchy()
            self._validate_list_structure()
            self._validate_contrast_ratios()
            self._validate_form_fields()
            self._validate_link_purposes()
            self._validate_annotations()
            
            # Calculate compliance scores
            wcag_score = self._calculate_wcag_score()
            pdfua_score = self._calculate_pdfua_score()
            
            results = {
                'wcagIssues': self.issues['wcag'],
                'pdfuaIssues': self.issues['pdfua'],
                'wcagCompliance': self.wcag_compliance,
                'pdfuaCompliance': self.pdfua_compliance,
                'wcagScore': wcag_score,
                'pdfuaScore': pdfua_score,
                'summary': {
                    'totalIssues': len(self.issues['wcag']) + len(self.issues['pdfua']),
                    'wcagIssues': len(self.issues['wcag']),
                    'pdfuaIssues': len(self.issues['pdfua']),
                    'validated': True
                },
                'navigationAidCheck': self.navigation_aid_result,
            }
            
            logger.info(f"[WCAGValidator] Validation complete: {results['summary']['totalIssues']} issues found")
            return results
            
        except Exception as e:
            logger.error(f"[WCAGValidator] Validation error: {str(e)}")
            return {
                'wcagIssues': [],
                'pdfuaIssues': [],
                'wcagCompliance': {'A': False, 'AA': False, 'AAA': False},
                'pdfuaCompliance': False,
                'wcagScore': 0,
                'pdfuaScore': 0,
                'summary': {'totalIssues': 0, 'validated': False, 'error': str(e)}
            }
        finally:
            if self.pdf:
                self.pdf.close()
    
    def _validate_document_structure(self):
        """
        Validate PDF/UA-1 document structure requirements.
        Based on veraPDF rules: 7.1-1, 7.1-2, 7.1-3
        """
        try:
            pdf = self.pdf
            if pdf is None:
                logger.debug("[WCAGValidator] Skipping document structure validation; PDF not loaded.")
                return

            # Rule 7.1-1: Check for PDF/UA Identification Schema
            if '/Metadata' not in pdf.Root:
                self._add_pdfua_issue(
                    'Document lacks metadata stream',
                    'ISO 14289-1:7.1',
                    'high',
                    'Add a metadata stream to the document catalog with PDF/UA Identification Schema'
                )
                self.pdfua_compliance = False
            else:
                has_pdfua_identifier = False
                duplicate_pdfua_identifier = False
                invalid_pdfua_value = False
                try:
                    # The catalog Metadata stream must carry the PDF/UA identification schema.
                    with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
                        part_value = str(meta.get('pdfuaid:part') or '').strip()
                        if part_value:
                            has_pdfua_identifier = True
                            if part_value != "1":
                                invalid_pdfua_value = True
                except Exception as e:
                    logger.error(f"[WCAGValidator] Error validating PDF/UA identifier: {e}")

                # Detect duplicates by reading raw XMP (pikepdf metadata view will not expose dupes).
                try:
                    metadata_obj = getattr(pdf.Root, "Metadata", None)
                    if metadata_obj:
                        if hasattr(metadata_obj, "get_object"):
                            try:
                                metadata_obj = metadata_obj.get_object()
                            except Exception:
                                pass
                        raw_xmp = metadata_obj.read_bytes()
                        import xml.etree.ElementTree as ET  # Local import to avoid global dependency
                        ns = {"pdfuaid": "http://www.aiim.org/pdfua/ns/id/"}
                        root = ET.fromstring(raw_xmp.decode("utf-8", errors="ignore"))
                        pdfua_parts = root.findall(".//pdfuaid:part", ns)
                        if len(pdfua_parts) > 1:
                            duplicate_pdfua_identifier = True
                        if pdfua_parts and any((elem.text or "").strip() != "1" for elem in pdfua_parts):
                            invalid_pdfua_value = True
                except Exception as e:
                    logger.debug(f"[WCAGValidator] Could not parse XMP for duplicate PDF/UA identifiers: {e}")

                if not has_pdfua_identifier:
                    self._add_pdfua_issue(
                        'Metadata stream missing PDF/UA identification (pdfuaid:part)',
                        'ISO 14289-1:7.1',
                        'high',
                        'Add <pdfuaid:part>1</pdfuaid:part> to the XMP metadata stream and reference it from the catalog /Metadata entry'
                    )
                    self.pdfua_compliance = False
                if duplicate_pdfua_identifier:
                    self._add_pdfua_issue(
                        'Metadata stream contains multiple PDF/UA identification entries',
                        'ISO 14289-1:7.1',
                        'high',
                        'Ensure only a single <pdfuaid:part>1</pdfuaid:part> appears in XMP metadata'
                    )
                    self.pdfua_compliance = False
                if invalid_pdfua_value:
                    self._add_pdfua_issue(
                        'Metadata stream has invalid PDF/UA identification value',
                        'ISO 14289-1:7.1',
                        'high',
                        'Set <pdfuaid:part> to "1" to claim PDF/UA-1 conformance'
                    )
                    self.pdfua_compliance = False
            
            # Rule 7.1-2: Check if document is tagged
            if '/MarkInfo' not in pdf.Root:
                self._add_pdfua_issue(
                    'Document not marked as tagged',
                    'ISO 14289-1:7.1',
                    'high',
                    'Add MarkInfo dictionary to document catalog with Marked=true'
                )
                self.pdfua_compliance = False
                return
            
            mark_info = pdf.Root.MarkInfo
            marked_value = mark_info.get('/Marked')
            if not bool(marked_value):
                self._add_pdfua_issue(
                    'Document MarkInfo.Marked is false',
                    'ISO 14289-1:7.1',
                    'high',
                    'Set MarkInfo.Marked to true in document catalog'
                )
                self.pdfua_compliance = False
            
            # Rule 7.1-3: Check Suspects entry
            suspects_value = mark_info.get('/Suspects')
            if bool(suspects_value):
                self._add_pdfua_issue(
                    'Document has Suspects entry set to true',
                    'ISO 14289-1:7.1',
                    'high',
                    'Set Suspects entry to false or remove it'
                )
                self.pdfua_compliance = False
            
            # Rule 7.1-4: Check ViewerPreferences DisplayDocTitle
            if '/ViewerPreferences' not in pdf.Root:
                self._add_pdfua_issue(
                    'Document lacks ViewerPreferences dictionary',
                    'ISO 14289-1:7.1',
                    'medium',
                    'Add ViewerPreferences dictionary with DisplayDocTitle=true'
                )
            else:
                viewer_prefs = pdf.Root.ViewerPreferences
                display_doc_title = viewer_prefs.get('/DisplayDocTitle')
                if not bool(display_doc_title):
                    self._add_pdfua_issue(
                        'ViewerPreferences.DisplayDocTitle is not set to true',
                        'ISO 14289-1:7.1',
                        'medium',
                        'Set DisplayDocTitle to true in ViewerPreferences dictionary'
                    )
                    
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating document structure: {str(e)}")
    
    def _validate_document_language(self):
        """Validate WCAG 3.1.1 (Language of Page) - Level A."""
        try:
            pdf = self.pdf
            if pdf is None:
                logger.debug("[WCAGValidator] Skipping language validation; PDF not loaded.")
                return

            if '/Lang' not in pdf.Root:
                self._add_wcag_issue(
                    'Document language not specified',
                    '3.1.1',
                    'A',
                    'high',
                    'Set the Lang entry in the document catalog'
                )
                self.wcag_compliance['A'] = False
                self.wcag_compliance['AA'] = False
                self.wcag_compliance['AAA'] = False
            else:
                lang = str(pdf.Root.Lang)
                if not lang or len(lang) < 2:
                    self._add_wcag_issue(
                        'Invalid document language code',
                        '3.1.1',
                        'A',
                        'high',
                        'Use a valid ISO 639 language code (e.g., "en-US")'
                    )
                    self.wcag_compliance['A'] = False
                    
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating document language: {str(e)}")
    
    def _validate_document_title(self):
        """
        Validate WCAG 2.4.2 (Page Titled) - Level A and PDF/UA-1 title requirements.
        Based on veraPDF rules: 7.1-5, 7.1-6
        """
        try:
            pdf = self.pdf
            if pdf is None:
                logger.debug("[WCAGValidator] Skipping document title validation; PDF not loaded.")
                return

            has_dc_title = False
            if '/Metadata' in pdf.Root:
                try:
                    with pdf.open_metadata() as meta:
                        # Check if dc:title exists and is not empty
                        dc_title = meta.get('dc:title', '')
                        if dc_title and str(dc_title).strip():
                            has_dc_title = True
                            logger.info(f"[WCAGValidator] Found dc:title: {dc_title}")
                        else:
                            logger.info("[WCAGValidator] dc:title is missing or empty")
                except Exception as e:
                    logger.error(f"[WCAGValidator] Error reading XMP metadata: {e}")
            
            if not has_dc_title:
                self._add_wcag_issue(
                    'Document metadata lacks dc:title entry',
                    '2.4.2',
                    'A',
                    'high',
                    'Add dc:title entry to document metadata stream'
                )
                self._add_pdfua_issue(
                    'Document metadata lacks dc:title entry',
                    'ISO 14289-1:7.1',
                    'high',
                    'Add dc:title entry to document metadata stream'
                )
                self.wcag_compliance['A'] = False
            
            # Rule 7.1-6: Check ViewerPreferences DisplayDocTitle
            # (Already checked in _validate_document_structure)
            
            has_docinfo_title = False
            try:
                if hasattr(pdf, 'docinfo') and pdf.docinfo is not None:
                    if '/Title' in pdf.docinfo:
                        title = str(pdf.docinfo['/Title'])
                        if title and title.strip():
                            has_docinfo_title = True
                            logger.info(f"[WCAGValidator] Found docinfo title: {title}")
                        else:
                            logger.info("[WCAGValidator] Docinfo title is empty")
                    else:
                        logger.info("[WCAGValidator] Docinfo /Title key not found")
                else:
                    logger.info("[WCAGValidator] Docinfo dictionary not found")
            except Exception as e:
                logger.error(f"[WCAGValidator] Error checking docinfo title: {e}")
            
            if not has_docinfo_title:
                self._add_wcag_issue(
                    'Document title not specified in info dictionary',
                    '2.4.2',
                    'A',
                    'medium',
                    'Add a Title entry to the document information dictionary'
                )
                self.wcag_compliance['A'] = False
                    
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating document title: {str(e)}")
    
    def _validate_structure_tree(self):
        """
        Validate PDF/UA-1 structure tree requirements.
        Based on veraPDF rules: 7.2-1 through 7.2-5
        """
        try:
            pdf = self.pdf
            if pdf is None:
                logger.debug("[WCAGValidator] Skipping structure tree validation; PDF not loaded.")
                return

            if '/StructTreeRoot' not in pdf.Root:
                self._add_pdfua_issue(
                    'Document lacks structure tree',
                    'ISO 14289-1:7.1',
                    'high',
                    'Add a structure tree root to the document catalog'
                )
                self.pdfua_compliance = False
                return
            
            struct_tree_root = pdf.Root.StructTreeRoot
            
            # Rule 7.2-1: Validate structure tree has children
            if '/K' not in struct_tree_root:
                self._add_pdfua_issue(
                    'Structure tree root has no children',
                    'ISO 14289-1:7.1',
                    'high',
                    'Add structure elements to the structure tree'
                )
                self.pdfua_compliance = False
                return
            
            # Rule 7.2-2: Check for RoleMap and validate mappings
            role_map = struct_tree_root.RoleMap if '/RoleMap' in struct_tree_root else None
            if role_map:
                self._validate_role_map(role_map)
            
            # Validate structure element types and hierarchy, passing RoleMap
            self._validate_structure_elements(struct_tree_root.K, role_map=role_map)
            
            # Rule 7.3-1, 7.3-2: Validate artifacts are not inside tagged content
            self._validate_artifacts()
            
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating structure tree: {str(e)}")
    
    def _validate_structure_elements(self, elements, depth=0, role_map=None):
        """Recursively validate structure elements."""
        if depth > 50:  # Prevent infinite recursion
            return
        
        try:
            if isinstance(elements, list):
                for element in elements:
                    self._validate_structure_elements(element, depth + 1, role_map=role_map)
            elif isinstance(elements, pikepdf.Dictionary):
                if '/S' in elements:
                    struct_type_raw = str(elements.S)
                    normalized = self._normalize_structure_type(struct_type_raw)
                    is_standard = normalized in self.REQUIRED_STRUCTURE_TYPES
                    has_mapping = (
                        bool(role_map) and self._maps_to_standard_type(struct_type_raw, role_map, set())
                    )
                    if not is_standard and not has_mapping:
                        self._add_pdfua_issue(
                            f'Invalid structure type: {struct_type_raw}',
                            'ISO 14289-1:7.2',
                            'medium',
                            'Use a standard structure type from PDF/UA-1 specification'
                        )
                
                # Recursively check children
                if '/K' in elements:
                    self._validate_structure_elements(elements.K, depth + 1, role_map=role_map)
                    
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating structure element: {str(e)}")
    
    def _validate_reading_order(self):
        """Validate WCAG 1.3.2 (Meaningful Sequence) - Level A."""
        try:
            pdf = self.pdf
            if pdf is None:
                logger.debug("[WCAGValidator] Skipping reading order validation; PDF not loaded.")
                return

            if '/StructTreeRoot' not in pdf.Root:
                return  # Already reported in structure tree validation
            
            # Check if structure tree defines reading order
            struct_tree_root = pdf.Root.StructTreeRoot
            if '/K' not in struct_tree_root:
                self._add_wcag_issue(
                    'Reading order not defined',
                    '1.3.2',
                    'A',
                    'high',
                    'Define reading order using structure tree'
                )
                self.wcag_compliance['A'] = False
                
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating reading order: {str(e)}")

    def _validate_sensory_characteristics(self):
        """Validate WCAG 1.3.3 (Sensory Characteristics) with simple text heuristics."""
        try:
            color_terms = "(?:red|green|blue|yellow|orange|purple|pink|brown|black|white|gray|grey|silver|gold)"
            direction_terms = "(?:above|below|left|right|top|bottom|upper|lower|next to|on the left|on the right|in the corner)"
            shape_terms = "(?:circle|square|triangle|diamond|star|arrow|box|icon|symbol|dot|marker|line|bar|bubble)"
            cue_verbs = "(?:see|refer to|look at|click|select|press|choose|use|follow|notice)"

            pattern_flags = re.IGNORECASE | re.DOTALL
            patterns = [
                re.compile(rf"\b{cue_verbs}\b.*?\b{color_terms}\b.*?\b{direction_terms}\b", pattern_flags),
                re.compile(rf"\b{cue_verbs}\b.*?\b{shape_terms}\b.*?\b{direction_terms}\b", pattern_flags),
                re.compile(rf"\b{shape_terms}\b.*?\b{direction_terms}\b", pattern_flags),
                re.compile(rf"\b{direction_terms}\b.*?\b{shape_terms}\b", pattern_flags),
                re.compile(rf"\b{color_terms}\b.*?\b{direction_terms}\b", pattern_flags),
                re.compile(r"\bcolor[-\s]?coded\b", pattern_flags),
                re.compile(rf"\b{cue_verbs}\b.*?\b{color_terms}\b", pattern_flags),
            ]

            seen_snippets = set()
            findings = 0
            max_findings = 20

            with pdfplumber.open(self.pdf_path) as document:
                for page_num, page in enumerate(document.pages, 1):
                    try:
                        text = page.extract_text() or ""
                    except Exception:
                        text = ""

                    if not text:
                        try:
                            words = page.extract_words()
                        except Exception:
                            words = []
                        if words:
                            text = " ".join(
                                str(word.get("text") or "").strip()
                                for word in words
                                if word.get("text")
                            )

                    normalized = " ".join(str(text or "").split())
                    if not normalized:
                        continue

                    for pattern in patterns:
                        if findings >= max_findings:
                            break
                        for match in pattern.finditer(normalized):
                            snippet = self._clean_text_snippet(match.group(0), limit=140)
                            if not snippet:
                                continue
                            key = (page_num, snippet.lower())
                            if key in seen_snippets:
                                continue
                            seen_snippets.add(key)

                            self._add_wcag_issue(
                                f"Text on page {page_num} may rely on sensory cues like color, shape, or position.",
                                '1.3.3',
                                'A',
                                'medium',
                                'Provide instructions that do not rely solely on color, shape, or location; include text labels or numbering that work for non-visual users.',
                                page=page_num,
                                context=snippet,
                            )
                            findings += 1
                            if findings >= max_findings:
                                break

                    if findings >= max_findings:
                        break

            if seen_snippets:
                self.wcag_compliance['A'] = False
                self.wcag_compliance['AA'] = False
                self.wcag_compliance['AAA'] = False

        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating sensory characteristics: {str(e)}")

    def _validate_bypass_blocks(self):
        """Validate WCAG 2.4.1 (Bypass Blocks) - Level A."""
        try:
            if self._has_navigation_entry_point():
                return

            self._add_wcag_issue(
                "Document lacks a bypass block or clear entry point.",
                "2.4.1",
                "A",
                "high",
                "Add a clear first-page H1 heading, accessible bookmarks/outlines, or an internal TOC so users can bypass repeated content.",
                page=1,
            )
            self.wcag_compliance["A"] = False
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating bypass blocks: {str(e)}")

    def _validate_multiple_ways(self):
        """Validate WCAG 2.4.5 (Multiple Ways) - Level AA."""
        pdf_path = getattr(self, "pdf_path", None)
        if not pdf_path:
            return

        try:
            result = check_navigation_aids(
                pdf_path,
                length_threshold=self.navigation_page_threshold,
            )
            self.navigation_aid_result = result
        except Exception as exc:
            logger.debug("[WCAGValidator] Navigation aid check skipped: %s", exc)
            return

        if result.get("status") != "FAIL":
            return

        aids = result.get("navigation_aids") or {}
        context = (
            "pages={pages}; outline={outline}; toc_links={toc}; page_labels={labels}"
        ).format(
            pages=result.get("page_count"),
            outline="yes" if aids.get("outline") else "no",
            toc="yes" if aids.get("table_of_contents_links") else "no",
            labels="yes" if aids.get("page_labels") else "no",
        )

        self._add_wcag_issue(
            "Long PDFs (over {threshold} pages) must expose bookmarks, an internal table of contents, or page labels."
            .format(threshold=self.navigation_page_threshold),
            "2.4.5",
            "AA",
            "high",
            "Add at least one navigation aid (outline/bookmarks, TOC links, or page labels) so users have multiple ways to locate content.",
            page=1,
            context=context,
        )
        self.wcag_compliance["AA"] = False

    def _has_navigation_entry_point(self) -> bool:
        """Return True if the document exposes an entry point that satisfies WCAG 2.4.1."""
        return (
            self._has_first_h1_near_first_page()
            or self._has_valid_outline_navigation()
            or self._has_internal_toc_links()
        )

    def _has_first_h1_near_first_page(self) -> bool:
        """Check if a level-1 heading appears early on page 1."""
        headings = self._collect_headings_in_order()
        if not headings:
            return False

        first_h1_index = None
        first_h1 = None
        for index, heading in enumerate(headings):
            if heading.get("level") == 1:
                first_h1 = heading
                first_h1_index = index
                break

        if not first_h1:
            return False

        page = first_h1.get("page")
        if page is None:
            return True

        return page == 1 and (first_h1_index is None or first_h1_index <= 2)

    def _has_valid_outline_navigation(self) -> bool:
        """Check if the document has outlines/bookmarks pointing to a valid destination."""
        pdf = self.pdf
        if pdf is None:
            return False

        try:
            # Safer access: use .get instead of attribute, and handle missing/None
            outlines_root = pdf.Root.get("/Outlines", None)
            if outlines_root is None:
                return False

            # Some files will have /Outlines but not as a proper dictionary.
            # Guard against "pikepdf.Object is not a Dictionary or Stream".
            try:
                # outlines_root may be a pikepdf.Dictionary-like; .get should exist then.
                first_entry = outlines_root.get("/First", None)
            except Exception:
                # If it's not dictionary-like, bail out gracefully.
                return False

            if first_entry is None:
                return False

            # Delegate to the traversal helper
            return self._traverse_outline_entries(first_entry, set())

        except Exception as e:
            # Any weird structure: treat as "no valid outline navigation"
            logger.debug(
                "[WCAGValidator] Skipping outline navigation check due to error: %s", e
            )
            return False
    
    def _traverse_outline_entries(self, entry: Any, visited: Set[int]) -> bool:
        """Walk the outline tree looking for entries with valid destinations."""
        entry = _resolve_pdf_object(entry)
        if entry is None:
            return False

        entry_id = id(entry)
        if entry_id in visited:
            return False
        visited.add(entry_id)

        # If this outline entry isn't dictionary-like, we can't safely access /First or /Next
        if not isinstance(entry, Mapping):
            return False

        # If this entry points to a valid destination, we're done
        try:
            if self._resolve_outline_entry_destination(entry) is not None:
                return True
        except Exception as e:
            # If resolving the destination for this entry fails, just skip this node
            logger.debug(
                "[WCAGValidator] Skipping outline entry due to destination error: %s",
                e,
            )
            return False

        # Traverse children and siblings defensively
        first_child = entry.get("/First")
        if first_child and self._traverse_outline_entries(first_child, visited):
            return True

        next_sibling = entry.get("/Next")
        if next_sibling and self._traverse_outline_entries(next_sibling, visited):
            return True

        return False

    def _resolve_outline_entry_destination(self, entry: Any) -> Optional[int]:
        """Resolve the page number targeted by an outline/bookmark entry."""
        if not isinstance(entry, pikepdf.Dictionary):
            return None

        dest = entry.get("/Dest")
        if dest is None:
            action = entry.get("/A")
            if isinstance(action, pikepdf.Dictionary) and str(action.get("/S")) == "/GoTo":
                dest = action.get("/D") or action.get("/Dest")

        return self._resolve_destination_page(dest)

    def _resolve_destination_page(
        self, dest: Any, visited_names: Optional[Set[str]] = None
    ) -> Optional[int]:
        """Resolve a destination reference to a page number."""
        dest = _resolve_pdf_object(dest)
        if dest is None:
            return None

        if isinstance(dest, (list, pikepdf.Array)):
            entries = _array_to_list(dest)
            if not entries:
                return None
            return self._resolve_page_number(entries[0])

        normalized = None
        if isinstance(dest, (str, bytes, Name, String)):
            normalized = str(dest)

        if normalized:
            visited = set(visited_names or [])
            if normalized in visited:
                return None
            visited.add(normalized)
            named = self._get_named_destinations()
            alias = named.get(normalized)
            if alias is not None:
                return self._resolve_destination_page(alias, visited)

        if isinstance(dest, pikepdf.Dictionary):
            for key in ("/D", "/Dest"):
                target = dest.get(key)
                if target is not None:
                    resolved = self._resolve_destination_page(target, visited_names)
                    if resolved is not None:
                        return resolved

        return None

    def _get_named_destinations(self) -> Dict[str, Any]:
        """Build or return a cache of named destinations from the document catalog."""
        if self._named_destinations is not None:
            return self._named_destinations

        named_map: Dict[str, Any] = {}
        pdf = self.pdf
        if pdf is None or "/Names" not in pdf.Root:
            self._named_destinations = named_map
            return named_map

        names_root = pdf.Root.Names
        dests_root = names_root.get("/Dests")

        def _walk(node: Any):
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
        self._named_destinations = named_map
        return named_map

    def _has_internal_toc_links(self) -> bool:
        """Look for /GoTo annotations on the first two pages that target internal destinations."""
        pdf = self.pdf
        if pdf is None:
            return False

        max_check_page = min(2, len(pdf.pages))
        for page_index in range(1, max_check_page + 1):
            page = pdf.pages[page_index - 1]
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

                if dest is not None and self._resolve_destination_page(dest) is not None:
                    return True

        return False
    
    def _validate_alternative_text(self):
        """Validate WCAG 1.1.1 (Non-text Content) - Level A."""
        try:
            pdf = self.pdf
            if pdf is None:
                logger.debug(
                    "[WCAGValidator] Skipping alternative text validation; PDF not loaded."
                )
                return

            root = pdf.Root
            has_struct_tree = "/StructTreeRoot" in root

            # For tagged documents, build a lookup of Figures with Alt from the structure tree.
            # This represents strict PDF1 behavior (Alt attached to a Figure/role-mapped element).
            lookup = None
            page_mcids_by_key: Dict[str, Set[int]] = {}
            if has_struct_tree:
                lookup = getattr(self, "_figure_alt_lookup", None)
                if lookup is None:
                    lookup = _build_figure_alt_lookup(pdf)
                    self._figure_alt_lookup = lookup
                page_mcids_by_key = lookup.get("page_mcids") or {}

            for page_num, page in enumerate(pdf.pages, 1):
                if "/Resources" not in page or "/XObject" not in page.Resources:
                    continue

                xobjects = page.Resources.XObject

                # UNTAGGED DOCS: always treat rendered images as lacking alt
                if not has_struct_tree:
                    for name, xobject in xobjects.items():
                        resolved = _resolve_pdf_object(xobject)
                        if not hasattr(resolved, "get"):
                            continue

                        subtype = resolved.get("/Subtype")
                        if subtype != "/Image":
                            continue

                        self._add_wcag_issue(
                            f"Image on page {page_num} lacks alternative text",
                            "1.1.1",
                            "A",
                            "high",
                            "Add alternative text for meaningful images, "
                            "or mark them as decorative where appropriate.",
                            page=page_num,
                            context=str(name),
                        )
                    # Nothing more to do on this page for untagged docs
                    continue

                # TAGGED DOCS: strict alt detection first
                image_entries: List[Tuple[Any, Any, bool]] = []  # (name, resolved, strict_has_alt)

                for name, xobject in xobjects.items():
                    resolved = _resolve_pdf_object(xobject)
                    if not hasattr(resolved, "get"):
                        continue

                    try:
                        subtype = resolved.get("/Subtype")
                    except Exception:
                        subtype = None

                    if subtype != "/Image":
                        continue

                    strict_has_alt = self._has_alt_text(resolved)
                    image_entries.append((name, resolved, strict_has_alt))

                if not image_entries:
                    continue

                # Per-page fallback:
                # Some authoring tools (e.g., Word) produce a Figure with Alt in the
                # structure tree but do not expose a clean MCID→image mapping in the
                # content stream. If a page has exactly one Figure-with-Alt and
                # exactly one rendered image that still fails strict mapping, we
                # pragmatically assume that Figure applies to that image and do not
                # flag a 1.1.1 issue for it.
                page_key = _object_key(page)
                page_fig_mcids = list(page_mcids_by_key.get(page_key, set()))

                if len(page_fig_mcids) == 1:
                    missing_indices = [
                        idx
                        for idx, (_name, _resolved, has_alt) in enumerate(image_entries)
                        if not has_alt
                    ]
                    if len(missing_indices) == 1:
                        idx = missing_indices[0]
                        name_miss, resolved_miss, _ = image_entries[idx]
                        image_entries[idx] = (name_miss, resolved_miss, True)

                # Finally, report 1.1.1 issues for any images that still have no alt.
                for name, resolved, has_alt in image_entries:
                    if has_alt:
                        continue

                    self._add_wcag_issue(
                        f"Image on page {page_num} lacks alternative text",
                        "1.1.1",
                        "A",
                        "high",
                        "Add Alt text to the Figure structure element",
                        page=page_num,
                        context=str(name),
                    )

        except Exception:
            logger.debug(
                "[WCAGValidator] Alternative text validation failed", exc_info=True
            )
            return

    def _has_alt_text(self, xobject) -> bool:
        """Check if an image has alt text on the stream or its Figure element."""
        if xobject is None:
            return False

        if '/Alt' in xobject or '/ActualText' in xobject:
            return True

        lookup = self._get_figure_alt_lookup()
        if has_figure_alt_text(xobject, lookup):
            return True

        return False

    def _get_figure_alt_lookup(self) -> Optional[Dict[str, Any]]:
        """Return cached mapping of Figure structure elements with alt text."""
        pdf = self.pdf
        if pdf is None:
            return None

        if self._figure_alt_lookup is None:
            try:
                self._figure_alt_lookup = _build_figure_alt_lookup(pdf)
            except Exception:
                self._figure_alt_lookup = None

        return self._figure_alt_lookup

    def _get_drawn_image_keys_for_page(self, page: Any) -> Set[str]:
        """Return cached set of image XObject keys drawn on the given page."""
        cache_key = _object_key(page)
        if not cache_key:
            return _collect_drawn_image_xobject_keys(page)

        cached = self._page_drawn_image_cache.get(cache_key)
        if cached is not None:
            return cached

        drawn = _collect_drawn_image_xobject_keys(page)
        self._page_drawn_image_cache[cache_key] = drawn
        return drawn

    def _image_has_fallback_alt(self, page: Any, xobject: Any) -> bool:
        """Heuristic alt association when no MCID/OBJR mapping exists."""
        lookup = self._get_figure_alt_lookup()
        if not lookup:
            return False

        page_key = _object_key(page)
        object_key = _object_key(xobject)
        if not page_key or not object_key:
            return False

        page_alt_counts = lookup.get('page_alt_counts', {})
        if getattr(page_alt_counts, 'get', None) is None:
            return False

        if page_alt_counts.get(page_key) != 1:
            return False

        drawn_keys = self._get_drawn_image_keys_for_page(page)
        if len(drawn_keys) != 1:
            return False

        return object_key in drawn_keys
    
    def _validate_table_structure(self):
        """
        Validate WCAG 1.3.1 / PDF/UA §7.5 table structure semantics.
        Ensures tables expose header cells and associate data cells with headers.
        """
        try:
            pdf = self.pdf
            if pdf is None:
                logger.debug("[WCAGValidator] Skipping table validation; PDF not loaded.")
                return

            if '/StructTreeRoot' not in pdf.Root:
                return

            tables_found = self._find_structure_elements('Table')
            for table_index, table_element in enumerate(tables_found, start=1):
                page_num = self._determine_page_number(table_element.get('/Pg'), table_element)
                table_label = self._extract_element_label(table_element)
                table_model = self._build_table_model(table_element, page_num)
                if not table_model:
                    continue
                self._assess_table_model(table_model, table_index, table_label)

        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating table structure: {str(e)}")
    
    def _find_structure_elements(self, struct_type: str, element=None, found=None) -> List:
        """Recursively find structure elements of a specific type."""
        if found is None:
            found = []
        if element is None:
            pdf = self.pdf
            if pdf is None or '/StructTreeRoot' not in pdf.Root:
                return found
            element = pdf.Root.StructTreeRoot
        
        try:
            if isinstance(element, pikepdf.Dictionary):
                if '/S' in element and str(element.S) == struct_type:
                    found.append(element)
                if '/K' in element:
                    self._find_structure_elements(struct_type, element.K, found)
            elif isinstance(element, (list, pikepdf.Array)):
                for item in _iter_array_items(element):
                    self._find_structure_elements(struct_type, item, found)
        except Exception as e:
            logger.error(f"[WCAGValidator] Error finding structure elements: {str(e)}")
        
        return found
    
    def _has_table_headers(self, table_element) -> bool:
        """Check if a table has proper header markup."""
        # Look for TH elements in the table structure
        th_elements = self._find_structure_elements('TH', table_element)
        return len(th_elements) > 0

    def _build_table_model(self, table_element: pikepdf.Dictionary, page_num: Optional[int]) -> Optional[Dict[str, Any]]:
        """
        Build a simple row/column model for a table, capturing TH/TD placement.
        Returns None if the structure could not be interpreted.
        """
        if table_element is None:
            return None

        row_containers = self._collect_table_rows(table_element)
        if not row_containers:
            row_containers = [table_element]

        rows: List[Dict[str, Any]] = []
        headers: List[Dict[str, Any]] = []
        data_cells: List[Dict[str, Any]] = []
        headers_by_id: Dict[str, Dict[str, Any]] = {}
        max_columns = 0

        for row_index, row_element in enumerate(row_containers):
            row_cells = self._collect_row_cells(row_element)
            if not row_cells:
                continue
            row_data = {
                'index': row_index,
                'cells': [],
            }
            column_position = 0
            for cell in row_cells:
                cell_type = self._resolve_role_mapped_type(cell.get('/S'))
                if cell_type not in ('TH', 'TD'):
                    continue
                col_span = self._extract_positive_int(cell, '/ColSpan', 1)
                row_span = self._extract_positive_int(cell, '/RowSpan', 1)
                scope = self._normalize_scope_value(cell.get('/Scope'))
                header_ids = self._extract_header_ids(cell.get('/Headers'))
                cell_id = self._normalize_id_value(cell.get('/ID'))
                cell_info = {
                    'element': cell,
                    'type': cell_type,
                    'row_index': row_index,
                    'col_start': column_position,
                    'col_end': column_position + col_span - 1,
                    'col_span': col_span,
                    'row_span': row_span,
                    'scope': scope,
                    'headers': header_ids,
                    'id': cell_id,
                    'page': page_num,
                }
                if cell_type == 'TH':
                    headers.append(cell_info)
                    if cell_id:
                        headers_by_id[cell_id] = cell_info
                else:
                    data_cells.append(cell_info)

                row_data['cells'].append(cell_info)
                column_position += col_span

            max_columns = max(max_columns, column_position)
            rows.append(row_data)

        if not rows:
            return None

        return {
            'table': table_element,
            'page': page_num,
            'rows': rows,
            'headers': headers,
            'data_cells': data_cells,
            'headers_by_id': headers_by_id,
            'column_count': max_columns,
        }

    def _collect_table_rows(self, table_element: pikepdf.Dictionary) -> List[pikepdf.Dictionary]:
        """Return a list of TR elements in reading order for the table."""
        rows: List[pikepdf.Dictionary] = []

        def _walk(node: Any):
            node = _resolve_pdf_object(node)
            if node is None:
                return
            if isinstance(node, pikepdf.Dictionary):
                struct_type = self._resolve_role_mapped_type(node.get('/S'))
                if struct_type == 'TR':
                    rows.append(node)
                    return
                if '/K' in node:
                    _walk(node.K)
                return
            if isinstance(node, (list, pikepdf.Array)):
                for child in _iter_array_items(node):
                    _walk(child)

        try:
            if '/K' in table_element:
                _walk(table_element.K)
        except Exception as exc:
            logger.debug(f"[WCAGValidator] Failed collecting table rows: {exc}")
        return rows

    def _collect_row_cells(self, row_element: pikepdf.Dictionary) -> List[pikepdf.Dictionary]:
        """Collect TH/TD structure elements under a row container."""
        cells: List[pikepdf.Dictionary] = []

        def _walk(node: Any):
            node = _resolve_pdf_object(node)
            if node is None:
                return
            if isinstance(node, pikepdf.Dictionary):
                struct_type = self._resolve_role_mapped_type(node.get('/S'))
                if struct_type in ('TH', 'TD'):
                    cells.append(node)
                    return
                if '/K' in node:
                    _walk(node.K)
                return
            if isinstance(node, (list, pikepdf.Array)):
                for child in _iter_array_items(node):
                    _walk(child)

        try:
            if isinstance(row_element, pikepdf.Dictionary) and '/K' in row_element:
                _walk(row_element.K)
            else:
                _walk(row_element)
        except Exception as exc:
            logger.debug(f"[WCAGValidator] Failed collecting row cells: {exc}")
        return cells

    def _assess_table_model(self, table_model: Dict[str, Any], table_index: int, table_label: Optional[str]):
        """Evaluate a parsed table model for structural issues."""
        headers = table_model['headers']
        page_num = table_model['page']
        page_text = str(page_num) if page_num is not None else 'unknown'
        table_desc = self._describe_table_reference(table_index, page_text, table_label)

        if not headers:
            self._add_wcag_issue(
                f'{table_desc} has no header cells (TH).',
                '1.3.1',
                'A',
                'high',
                'Add TH elements to define header rows or columns for this table.',
                page=page_num,
                context=table_label or table_desc
            )
            self._add_pdfua_issue(
                f'{table_desc} has no header cells (TH).',
                'ISO 14289-1:7.5',
                'high',
                'Define table headers using TH elements to satisfy PDF/UA table requirements.',
                page=page_num
            )
            self.wcag_compliance['A'] = False
            return

        self._check_header_scopes(table_model, table_desc, table_label)
        self._check_data_cell_associations(table_model, table_desc, table_label)

    def _check_header_scopes(self, table_model: Dict[str, Any], table_desc: str, table_label: Optional[str]):
        """Validate header scopes for obvious placement issues."""
        headers = table_model['headers']
        issues_reported = 0
        max_scope_issues = 10
        page_num = table_model.get('page')

        for header in headers:
            scope = header.get('scope')
            if not scope:
                continue
            if self._is_scope_consistent(scope, header, table_model):
                continue
            if issues_reported >= max_scope_issues:
                break
            issues_reported += 1
            scope_text = scope.lower()
            context = table_label or table_desc
            self._add_wcag_issue(
                f'{table_desc} has a header cell with potentially invalid {scope_text} scope.',
                '1.3.1',
                'A',
                'medium',
                'Review TH scope placement to ensure row/column headers align with the data they describe.',
                page=page_num,
                context=context
            )
            self._add_pdfua_issue(
                f'{table_desc} has a header cell with potentially invalid {scope_text} scope.',
                'ISO 14289-1:7.5',
                'medium',
                'Ensure header cells correctly describe their row or column scope for table accessibility.',
                page=page_num
            )
            self.wcag_compliance['A'] = False

    def _check_data_cell_associations(self, table_model: Dict[str, Any], table_desc: str, table_label: Optional[str]):
        """Ensure each data cell is associated with at least one header."""
        headers_by_id = table_model['headers_by_id']
        headers = table_model['headers']
        data_cells = table_model['data_cells']
        issues_reported = 0
        max_data_issues = 25
        page_num = table_model.get('page')
        context = table_label or table_desc

        for cell in data_cells:
            associated = self._associate_headers_for_cell(cell, table_model, headers_by_id, headers)
            if associated:
                continue
            if issues_reported >= max_data_issues:
                break
            issues_reported += 1
            row_num = cell.get('row_index', 0) + 1
            self._add_wcag_issue(
                f'{table_desc} contains a data cell (row {row_num}) without associated headers.',
                '1.3.1',
                'A',
                'high',
                'Associate each TD with header cells using /Headers or clear TH scopes.',
                page=page_num,
                context=context
            )
            self._add_pdfua_issue(
                f'{table_desc} contains a data cell (row {row_num}) without associated headers.',
                'ISO 14289-1:7.5',
                'high',
                'Associate data cells with header cells per PDF/UA requirements (e.g., /Headers, TH scopes).',
                page=page_num
            )
            self.wcag_compliance['A'] = False

    def _associate_headers_for_cell(
        self,
        cell: Dict[str, Any],
        table_model: Dict[str, Any],
        headers_by_id: Dict[str, Dict[str, Any]],
        headers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Return a list of header cells associated with the given data cell."""
        associated: List[Dict[str, Any]] = []

        for header_id in cell.get('headers', []):
            header = headers_by_id.get(header_id)
            if header and header not in associated:
                associated.append(header)
        if associated:
            return associated

        column_matches = self._headers_sharing_column(cell, headers, scope_filter='Column')
        if column_matches:
            return column_matches

        row_matches = self._headers_sharing_row(cell, headers, scope_filter='Row')
        if row_matches:
            return row_matches

        inferred = self._infer_headers_from_layout(cell, table_model)
        if inferred:
            return inferred

        return associated

    def _headers_sharing_column(
        self,
        cell: Dict[str, Any],
        headers: List[Dict[str, Any]],
        scope_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return headers that overlap the data cell's column range."""
        matches: List[Dict[str, Any]] = []
        for header in headers:
            if scope_filter and header.get('scope') != scope_filter:
                continue
            if self._columns_overlap(cell, header):
                matches.append(header)
        return matches

    def _headers_sharing_row(
        self,
        cell: Dict[str, Any],
        headers: List[Dict[str, Any]],
        scope_filter: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return headers that appear in the same row as the data cell."""
        matches: List[Dict[str, Any]] = []
        for header in headers:
            if scope_filter and header.get('scope') != scope_filter:
                continue
            if header.get('row_index') == cell.get('row_index'):
                matches.append(header)
        return matches

    def _infer_headers_from_layout(self, cell: Dict[str, Any], table_model: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Fallback heuristic: use first row or first column headers if available."""
        headers = table_model['headers']
        if not headers:
            return []

        first_row_index = min((header.get('row_index') for header in headers), default=None)
        inferred: List[Dict[str, Any]] = []

        if first_row_index is not None:
            for header in headers:
                if header.get('row_index') == first_row_index and self._columns_overlap(cell, header):
                    inferred.append(header)
            if inferred:
                return inferred

        for header in headers:
            if header.get('col_start') == 0 and self._columns_overlap(cell, header):
                inferred.append(header)
        return inferred

    def _is_scope_consistent(self, scope: str, header: Dict[str, Any], table_model: Dict[str, Any]) -> bool:
        """Basic validation that TH scope roughly matches its placement."""
        scope = scope.lower()
        row_index = header.get('row_index')
        if scope == 'column':
            for row in table_model['rows']:
                if row['index'] == row_index:
                    continue
                for cell in row['cells']:
                    if cell.get('type') == 'TD' and self._columns_overlap(cell, header):
                        return True
            return False
        if scope == 'row':
            row = next((r for r in table_model['rows'] if r['index'] == row_index), None)
            if not row:
                return False
            has_data_cells = any(c.get('type') == 'TD' for c in row['cells'])
            spans_multiple = sum(c.get('col_span', 1) for c in row['cells']) > header.get('col_span', 1)
            return has_data_cells and spans_multiple
        return True

    def _columns_overlap(self, cell_a: Dict[str, Any], cell_b: Dict[str, Any]) -> bool:
        """Return True if two cells overlap in column space."""
        return not (
            cell_a.get('col_end', -1) < cell_b.get('col_start', 0) or
            cell_b.get('col_end', -1) < cell_a.get('col_start', 0)
        )

    def _describe_table_reference(self, index: int, page_text: str, label: Optional[str]) -> str:
        """Return a readable table reference for issue descriptions."""
        if label:
            return f'Table "{label}" on page {page_text}'
        if index:
            return f'Table {index} on page {page_text}'
        return f'Table on page {page_text}'

    def _normalize_scope_value(self, scope: Any) -> Optional[str]:
        """Normalize TH scope values."""
        if scope is None:
            return None
        text = str(scope).lstrip('/')
        return text if text else None

    def _extract_header_ids(self, headers_entry: Any) -> List[str]:
        """Normalize /Headers entries to a list of IDs."""
        results: List[str] = []

        def _collect(value: Any):
            value = _resolve_pdf_object(value)
            if value is None:
                return
            if isinstance(value, (list, pikepdf.Array)):
                for item in _iter_array_items(value):
                    _collect(item)
                return
            normalized = self._normalize_id_value(value)
            if normalized:
                results.append(normalized)

        _collect(headers_entry)
        return results

    def _normalize_id_value(self, value: Any) -> Optional[str]:
        """Normalize ID/Headers tokens to comparable strings."""
        if value is None:
            return None
        try:
            text = str(value)
        except Exception:
            return None
        text = text.strip()
        if not text:
            return None
        return text.lstrip('/')

    def _extract_positive_int(self, element: pikepdf.Dictionary, key: str, default: int = 1) -> int:
        """Extract a positive integer entry from a structure element."""
        if not isinstance(element, pikepdf.Dictionary):
            return default
        raw_value = element.get(key)
        if raw_value is None:
            return default
        try:
            value = int(str(raw_value))
            return value if value > 0 else default
        except Exception:
            return default
    
    def _validate_heading_hierarchy(self):
        """Validate heading semantics for WCAG 1.3.1 / 2.4.6."""
        try:
            headings = self._collect_headings_in_order()
            if len(headings) < 2:
                return

            previous = headings[0]
            for entry in headings[1:]:
                current_level = entry.get('level')
                prev_level = previous.get('level')
                if current_level is None or prev_level is None:
                    previous = entry
                    continue

                if current_level > prev_level + 1:
                    page_num = entry.get('page')
                    page_text = str(page_num) if page_num is not None else 'unknown'
                    current_label = entry.get('title')
                    previous_label = previous.get('title')
                    label_suffix = ""
                    if current_label:
                        label_suffix += f' ("{current_label}")'
                    if previous_label:
                        label_suffix += f' after "{previous_label}"'

                    self._add_wcag_issue(
                        f'Non-sequential heading level: H{prev_level} followed directly by H{current_level} on page {page_text}{label_suffix}.',
                        '2.4.6',
                        'AA',
                        'medium',
                        'Ensure headings increase by no more than one level at a time (e.g., H2 should follow H1).',
                        page=page_num,
                        context=current_label
                    )
                    self.wcag_compliance['AA'] = False
                    self.wcag_compliance['AAA'] = False

                previous = entry
                        
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating heading hierarchy: {str(e)}")
    
    def _validate_list_structure(self):
        """Validate WCAG 1.3.1 (Info and Relationships) for lists - Level A."""
        try:
            def _visitor(element: pikepdf.Dictionary, page_ref: Any):
                resolved_type = self._resolve_role_mapped_type(element.get('/S'))
                if resolved_type == 'L':
                    self._validate_single_list(element, page_ref)
                elif resolved_type == 'LI':
                    self._validate_list_item(element, page_ref)

            self._traverse_structure(_visitor)
                    
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating list structure: {str(e)}")

    def _validate_single_list(self, list_element: pikepdf.Dictionary, page_ref: Any):
        """Ensure list containers expose LI children."""
        list_children = [
            child for child in self._get_child_structure_elements(list_element)
            if self._resolve_role_mapped_type(child.get('/S')) == 'LI'
        ]
        if list_children:
            return

        page_num = self._determine_page_number(page_ref, list_element)
        page_text = str(page_num) if page_num is not None else 'unknown'

        self._add_wcag_issue(
            f'List on page {page_text} lacks list items (LI).',
            '1.3.1',
            'A',
            'medium',
            'Ensure each list (<L>) element contains one or more list item (<LI>) children.',
            page=page_num
        )
        self.wcag_compliance['A'] = False

    def _validate_list_item(self, list_item: pikepdf.Dictionary, page_ref: Any):
        """Ensure list items contain both labels (Lbl) and bodies (LBody)."""
        children = self._get_child_structure_elements(list_item)
        has_label = any(self._resolve_role_mapped_type(child.get('/S')) == 'Lbl' for child in children)
        has_body = any(self._resolve_role_mapped_type(child.get('/S')) == 'LBody' for child in children)

        if has_label and has_body:
            return

        page_num = self._determine_page_number(page_ref, list_item)
        page_text = str(page_num) if page_num is not None else 'unknown'
        item_label = self._extract_element_label(list_item)
        item_suffix = f' ("{item_label}")' if item_label else ''

        if not has_label:
            self._add_wcag_issue(
                f'List item{item_suffix} is missing a label (Lbl) on page {page_text}.',
                '1.3.1',
                'A',
                'medium',
                'Add an <Lbl> child to each list item to expose the bullet, number, or descriptor.',
                page=page_num,
                context=item_label
            )
            self.wcag_compliance['A'] = False

        if not has_body:
            self._add_wcag_issue(
                f'List item{item_suffix} is missing a body (LBody) on page {page_text}.',
                '1.3.1',
                'A',
                'medium',
                'Include an <LBody> child for each list item to contain the list content.',
                page=page_num,
                context=item_label
            )
            self.wcag_compliance['A'] = False
    
    def _validate_contrast_ratios(self):
        """
        Validate WCAG 1.4.3 (Contrast Minimum) - Level AA and 1.4.6 (Contrast Enhanced) - Level AAA.
        
        Note: This is a simplified implementation. Full contrast validation requires
        rendering the PDF and analyzing pixel colors, which is complex.
        """
        try:
            # This is a placeholder for contrast ratio validation
            # Full implementation would require:
            # 1. Rendering PDF pages
            # 2. Extracting text and background colors
            # 3. Calculating contrast ratios
            # 4. Comparing against WCAG thresholds
            
            # For now, we'll add a note that manual contrast checking is recommended
            logger.info("[WCAGValidator] Contrast ratio validation requires manual review")
            
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating contrast ratios: {str(e)}")
    
    def _validate_form_fields(self):
        """Validate WCAG 1.3.1, 3.3.2 (Labels or Instructions) for form fields - Level A."""
        try:
            pdf = self.pdf
            if pdf is None:
                logger.debug("[WCAGValidator] Skipping form field validation; PDF not loaded.")
                return

            if '/AcroForm' not in pdf.Root:
                return  # No forms to validate
            
            acro_form = pdf.Root.AcroForm
            if '/Fields' in acro_form:
                fields = acro_form.Fields
                for field in _iter_array_items(fields):
                    # Check if field has a label
                    if '/T' not in field:  # T is the field name/label
                        self._add_wcag_issue(
                            'Form field lacks label',
                            '3.3.2',
                            'A',
                            'high',
                            'Add a label (T entry) to the form field'
                        )
                        self.wcag_compliance['A'] = False

        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating form fields: {str(e)}")
    
    def _validate_link_purposes(self):
        """Validate WCAG 2.4.4 (Link Purpose in Context) - Level AA."""
        try:
            with pdfplumber.open(self.pdf_path) as document:
                for page_num, page in enumerate(document.pages, 1):
                    words = page.extract_words()
                    for annot in page.annots:
                        if not self._annotation_is_link(annot):
                            continue
                        print("[DEBUG] Link annot on page", page_num, "->", annot.get("uri"))

                        bbox = self._get_annotation_bbox(annot)
                        if not bbox:
                            continue

                        link_words = self._words_within_bbox(words, self._expand_bbox(bbox, padding=1.5))
                        visible_text = self._join_words(link_words)
                        annotation_label = self._extract_annotation_label(annot)
                        link_label = visible_text if visible_text else annotation_label

                        if not link_label:
                            self._add_link_purpose_issue(
                                page_num,
                                "lacks descriptive text or alternative text",
                                severity="high",
                                context=None,
                            )
                            continue

                        if self._is_generic_link_text(link_label):
                            self._add_link_purpose_issue(
                                page_num,
                                f'uses ambiguous text "{link_label}"',
                                severity="medium",
                                context=link_label,
                            )
        except Exception as exc:
            logger.error(f"[WCAGValidator] Error validating link purposes: {exc}")

    def _validate_annotations(self):
        """Validate PDF/UA-1 annotation requirements."""
        try:
            pdf = self.pdf
            if pdf is None:
                logger.debug("[WCAGValidator] Skipping annotation validation; PDF not loaded.")
                return

            for page_num, page in enumerate(pdf.pages, 1):
                if '/Annots' in page:
                    for annot in _iter_array_items(page.Annots):
                        # Check if annotation has Contents (tooltip/description)
                        if '/Contents' not in annot:
                            self._add_pdfua_issue(
                                f'Annotation on page {page_num} lacks description',
                                'ISO 14289-1:7.18.1',
                                'medium',
                                'Add Contents entry to annotation for accessibility'
                            )
                            
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating annotations: {str(e)}")

    def _annotation_is_link(self, annotation: Dict[str, Any]) -> bool:
        if not isinstance(annotation, dict):
            return False

        data = annotation.get("data")
        if not data or not isinstance(data, Mapping):
            return False

        # Try multiple common key spellings
        subtype_raw = (
            data.get("Subtype")
            or data.get("/Subtype")
            or data.get("subtype")
            or data.get("SUBTYPE")
        )

        normalized = ""
        if subtype_raw is not None:
            try:
                raw = str(subtype_raw).strip()
            except Exception:
                raw = ""

            # Handle variants like /Link, /'Link', Link, 'Link'
            if raw.startswith("/"):
                raw = raw[1:]
            raw = raw.strip("'\"")
            normalized = raw.lower()

        # pdfplumber exposes `uri` only on link-ish annots, so this is a safe fallback
        has_uri = bool(annotation.get("uri"))

        return normalized == "link" or has_uri

    def _get_annotation_bbox(self, annotation: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
        if not isinstance(annotation, dict):
            return None
        coords = []
        for key in ("x0", "top", "x1", "bottom"):
            value = annotation.get(key)
            if value is None:
                return None
            try:
                coords.append(float(value))
            except (TypeError, ValueError):
                return None
        x0, top, x1, bottom = coords
        if x1 <= x0 or bottom <= top:
            return None
        return x0, top, x1, bottom

    def _bbox_from_word(self, word: Dict[str, Any]) -> Optional[Tuple[float, float, float, float]]:
        if not isinstance(word, dict):
            return None
        coords = []
        for key in ("x0", "top", "x1", "bottom"):
            value = word.get(key)
            if value is None:
                return None
            try:
                coords.append(float(value))
            except (TypeError, ValueError):
                return None
        x0, top, x1, bottom = coords
        if x1 <= x0 or bottom <= top:
            return None
        return x0, top, x1, bottom

    def _words_within_bbox(self, words: List[Dict[str, Any]], bbox: Tuple[float, float, float, float]) -> List[Dict[str, Any]]:
        overlapping: List[Dict[str, Any]] = []
        for word in words:
            word_bbox = self._bbox_from_word(word)
            if not word_bbox:
                continue
            if get_bbox_overlap(bbox, word_bbox) is not None:
                overlapping.append(word)
        return overlapping

    def _expand_bbox(
        self,
        bbox: Tuple[float, float, float, float],
        padding: float = 1.0,
    ) -> Tuple[float, float, float, float]:
        x0, top, x1, bottom = bbox
        return (x0 - padding, top - padding, x1 + padding, bottom + padding)

    def _join_words(self, words: List[Dict[str, Any]]) -> Optional[str]:
        if not words:
            return None
        sorted_words = sorted(
            words,
            key=lambda w: (
                float(w.get("doctop") or 0),
                float(w.get("x0") or 0),
            ),
        )
        tokens = [str(word.get("text") or "").strip() for word in sorted_words]
        filtered = [token for token in tokens if token]
        joined = " ".join(filtered).strip()
        return joined or None

    def _extract_annotation_label(self, annotation: Dict[str, Any]) -> Optional[str]:
        if not isinstance(annotation, dict):
            return None

        # Annotation titles may be shown to users (e.g., tooltip), but /Contents entries
        # generally are not exposed to assistive tech or the visual interface.
        title_snippet = self._clean_text_snippet(annotation.get("title"))
        if title_snippet:
            return title_snippet

        data = annotation.get("data")
        if isinstance(data, dict):
            for key in ("/Alt", "Alt", "/ActualText", "ActualText", "/TU", "TU", "/T", "T"):
                snippet = self._clean_text_snippet(data.get(key))
                if snippet:
                    return snippet
        return None

    def _normalize_link_text(self, value: str) -> str:
        cleaned = " ".join(str(value or "").split()).lower()
        cleaned = re.sub(r"[^a-z0-9\s]", "", cleaned)
        return cleaned.strip()

    def _is_generic_link_text(self, value: str) -> bool:
        normalized = self._normalize_link_text(value)
        return normalized in GENERIC_LINK_TEXTS

    def _add_link_purpose_issue(
        self,
        page: int,
        detail: str,
        *,
        severity: str,
        context: Optional[str],
    ):
        description = f"Link annotation on page {page} {detail}."
        self._add_wcag_issue(
            description,
            '2.4.4',
            'AA',
            severity,
            'Provide descriptive link text or Alt/Contents data so the link purpose is clear.',
            page=page,
            context=context,
        )
        self.wcag_compliance['AA'] = False
        self.wcag_compliance['AAA'] = False
    
    def _find_role_map_value(self, struct_type, role_map):
        """Return the mapped value for a structure type from the RoleMap."""
        normalized = self._normalize_structure_type(struct_type)
        if not normalized or not role_map:
            return None
        for key in role_map.keys():
            if self._normalize_structure_type(key) == normalized:
                return role_map[key]
        return None

    def _validate_role_map(self, role_map):
        """
        Validate RoleMap dictionary for proper structure type mappings.
        Based on veraPDF rules: 7.2-2, 7.2-3, 7.2-4
        """
        try:
            visited = set()
            
            for custom_type, _ in role_map.items():
                custom_type_str = str(custom_type)
                normalized_custom = self._normalize_structure_type(custom_type)
                
                # Rule 7.2-2: Check for circular mappings
                if self._has_circular_mapping(custom_type_str, role_map, visited):
                    self._add_pdfua_issue(
                        f'Circular mapping detected for structure type: {custom_type_str}',
                        'ISO 14289-1:7.2',
                        'high',
                        'Remove circular mapping in RoleMap dictionary'
                    )
                    self.pdfua_compliance = False
                
                # Rule 7.2-3: Check that standard types are not remapped
                if normalized_custom in self.REQUIRED_STRUCTURE_TYPES:
                    self._add_pdfua_issue(
                        f'Standard structure type {custom_type_str} is remapped',
                        'ISO 14289-1:7.2',
                        'high',
                        'Do not remap standard structure types'
                    )
                    self.pdfua_compliance = False
                
                # Rule 7.2-4: Check that non-standard types eventually map to standard types
                if not self._maps_to_standard_type(custom_type_str, role_map, set()):
                    self._add_pdfua_issue(
                        f'Non-standard structure type {custom_type_str} does not map to a standard type',
                        'ISO 14289-1:7.2',
                        'medium',
                        f'Map {custom_type_str} to a standard structure type'
                    )
                    
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating role map: {str(e)}")
    
    def _has_circular_mapping(self, struct_type: str, role_map, visited: set) -> bool:
        """Check if a structure type has circular mapping."""
        normalized = self._normalize_structure_type(struct_type)
        if not normalized or not role_map:
            return False
        if normalized in visited:
            return True
        if normalized in self.REQUIRED_STRUCTURE_TYPES:
            return False

        mapped = self._find_role_map_value(struct_type, role_map)
        if mapped is None:
            return False

        visited.add(normalized)
        mapped_norm = self._normalize_structure_type(mapped)
        return self._has_circular_mapping(mapped_norm, role_map, visited)
    
    def _maps_to_standard_type(self, struct_type: str, role_map, visited: set) -> bool:
        """Check if a structure type eventually maps to a standard type."""
        normalized = self._normalize_structure_type(struct_type)
        if not normalized or not role_map:
            return False
        if normalized in visited:
            return False
        if normalized in self.REQUIRED_STRUCTURE_TYPES:
            return True

        mapped = self._find_role_map_value(struct_type, role_map)
        if mapped is None:
            return False

        visited.add(normalized)
        mapped_norm = self._normalize_structure_type(mapped)
        return self._maps_to_standard_type(mapped_norm, role_map, visited)
    
    def _validate_artifacts(self):
        """
        Validate that artifacts are properly marked and not mixed with tagged content.
        Based on veraPDF rules: 7.3-1, 7.3-2, 7.3-3
        """
        try:
            # This requires analyzing page content streams
            # Simplified implementation - full version would parse content streams
            logger.info("[WCAGValidator] Artifact validation requires content stream analysis")
            
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating artifacts: {str(e)}")
    
    def _add_wcag_issue(
        self,
        description: str,
        criterion: str,
        level: str,
        severity: str,
        remediation: str,
        *,
        page: Optional[int] = None,
        pages: Optional[List[int]] = None,
        context: Optional[str] = None,
    ):
        """Add a WCAG issue to the results with optional context."""
        issue: Dict[str, Any] = {
            'description': description,
            'criterion': criterion,
            'level': level,
            'severity': severity,
            'remediation': remediation,
            'specification': f'WCAG 2.1 Level {level}',
            'category': 'wcag'
        }
        if page is not None:
            issue['page'] = page
        if pages:
            issue['pages'] = pages
        if context:
            issue['context'] = context
        self.issues['wcag'].append(issue)

    def _add_pdfua_issue(
        self,
        description: str,
        clause: str,
        severity: str,
        remediation: str,
        *,
        page: Optional[int] = None,
        pages: Optional[List[int]] = None,
    ):
        """Add a PDF/UA issue to the results."""
        issue: Dict[str, Any] = {
            'description': description,
            'clause': clause,
            'severity': severity,
            'remediation': remediation,
            'specification': 'PDF/UA-1 (ISO 14289-1)',
            'category': 'pdfua'
        }
        if page is not None:
            issue['page'] = page
        if pages:
            issue['pages'] = pages
        self.issues['pdfua'].append(issue)
    
    def _calculate_wcag_score(self) -> int:
        """Calculate WCAG compliance score (0-100)."""
        total_checks = 17  # Total number of WCAG checks performed
        failed_checks = len(self.issues['wcag'])
        passed_checks = total_checks - min(failed_checks, total_checks)
        return int((passed_checks / total_checks) * 100)
    
    def _calculate_pdfua_score(self) -> int:
        """Calculate PDF/UA compliance score (0-100)."""
        total_checks = 10  # Total number of PDF/UA checks performed
        failed_checks = len(self.issues['pdfua'])
        passed_checks = total_checks - min(failed_checks, total_checks)
        return int((passed_checks / total_checks) * 100)


def validate_wcag_pdfua(pdf_path: str) -> Dict[str, Any]:
    """
    Convenience function to validate a PDF against WCAG 2.1 and PDF/UA-1 standards.
    
    Args:
        pdf_path: Path to the PDF file to validate
        
    Returns:
        Dictionary containing validation results
    """
    validator = WCAGValidator(pdf_path)
    return validator.validate()
