"""
WCAG 2.1 and PDF/UA-1 Validation Algorithms
Based on veraPDF-wcag-algs: https://github.com/veraPDF/veraPDF-wcag-algs

This module implements validation algorithms for WCAG 2.1 and PDF/UA-1 compliance
without requiring external dependencies like veraPDF CLI.
"""

import pikepdf
from typing import Dict, List, Any, Tuple, Optional, Callable
import logging
from collections import defaultdict
import re

logger = logging.getLogger(__name__)


def _resolve_pdf_object(value):
    """Return the underlying direct object if value is an indirect reference."""
    if value is None:
        return None
    try:
        return value.get_object()
    except AttributeError:
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


def _element_has_alt_text(element: Any) -> bool:
    """Determine if a structure element exposes alt text."""
    if not isinstance(element, pikepdf.Dictionary):
        return False

    for attr in ('/Alt', '/ActualText'):
        value = element.get(attr)
        if value and str(value).strip():
            return True
    return False


def _extract_structure_refs(entry: Any) -> Tuple[List[int], List[Any]]:
    """Collect MCIDs and object references within a structure element's /K tree."""
    mcids: List[int] = []
    obj_refs: List[Any] = []

    def _walk(value: Any):
        value = _resolve_pdf_object(value)
        if value is None:
            return

        if isinstance(value, int):
            mcids.append(int(value))
            return

        if isinstance(value, pikepdf.Dictionary):
            value_type = str(value.get('/Type', ''))
            if value_type == '/MCR' and '/MCID' in value:
                try:
                    mcids.append(int(value.MCID))
                except Exception:
                    pass
            elif value_type == '/OBJR' and '/Obj' in value:
                obj_refs.append(value.Obj)

            if '/K' in value:
                _walk(value.K)
            return

        if isinstance(value, (list, pikepdf.Array)):
            for item in value:
                _walk(item)

    _walk(entry)
    return mcids, obj_refs


def _iter_structure_children(entry: Any) -> List[Any]:
    """Yield child structure elements contained within /K."""
    entry = _resolve_pdf_object(entry)
    if entry is None:
        return []

    if isinstance(entry, (list, pikepdf.Array)):
        return list(entry)

    if isinstance(entry, pikepdf.Dictionary):
        # Only dictionaries with structure semantics should be traversed as children.
        if '/S' in entry or '/K' in entry:
            return [entry]

    return []


def _build_figure_alt_lookup(pdf) -> Dict[str, Any]:
    """Construct lookup data for Figure elements that expose alt text."""
    lookup = {
        'xobject_keys': set(),
        'page_mcids': defaultdict(set),
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
            for child in element:
                _walk(child, current_page)

    try:
        _walk(struct_tree_root)
    except Exception as exc:
        logger.debug(f"[WCAGValidator] Failed to traverse structure tree for alt lookup: {exc}")

    return lookup


def has_figure_alt_text(xobject: Any, lookup: Optional[Dict[str, Any]]) -> bool:
    """Return True if the XObject is linked to a Figure element with alt text."""
    if not lookup or xobject is None:
        return False

    object_key = _object_key(xobject)
    if not object_key:
        return False

    return object_key in lookup['xobject_keys']


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
        self._page_lookup = None
        self._role_map_cache = None
        self._role_map_cache_initialized = False
    
    def _get_role_map(self):
        """Return the PDF RoleMap dictionary, caching when possible."""
        if self._role_map_cache_initialized:
            return self._role_map_cache

        self._role_map_cache_initialized = True
        role_map = None

        try:
            if self.pdf and '/StructTreeRoot' in self.pdf.Root:
                struct_tree_root = self.pdf.Root.StructTreeRoot
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
        if self.pdf:
            try:
                for page_num, page in enumerate(self.pdf.pages, 1):
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
        if not self.pdf or '/StructTreeRoot' not in self.pdf.Root:
            return

        struct_tree_root = self.pdf.Root.StructTreeRoot
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
                for child in node:
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
                for entry in payload:
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
            self._validate_alternative_text()
            self._validate_table_structure()
            self._validate_heading_hierarchy()
            self._validate_list_structure()
            self._validate_contrast_ratios()
            self._validate_form_fields()
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
                }
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
            # Rule 7.1-1: Check for PDF/UA Identification Schema
            if '/Metadata' not in self.pdf.Root:
                self._add_pdfua_issue(
                    'Document lacks metadata stream',
                    'ISO 14289-1:7.1',
                    'high',
                    'Add a metadata stream to the document catalog with PDF/UA Identification Schema'
                )
                self.pdfua_compliance = False
            
            # Rule 7.1-2: Check if document is tagged
            if '/MarkInfo' not in self.pdf.Root:
                self._add_pdfua_issue(
                    'Document not marked as tagged',
                    'ISO 14289-1:7.1',
                    'high',
                    'Add MarkInfo dictionary to document catalog with Marked=true'
                )
                self.pdfua_compliance = False
                return
            
            mark_info = self.pdf.Root.MarkInfo
            if not mark_info.get('/Marked', False):
                self._add_pdfua_issue(
                    'Document MarkInfo.Marked is false',
                    'ISO 14289-1:7.1',
                    'high',
                    'Set MarkInfo.Marked to true in document catalog'
                )
                self.pdfua_compliance = False
            
            # Rule 7.1-3: Check Suspects entry
            if mark_info.get('/Suspects', False):
                self._add_pdfua_issue(
                    'Document has Suspects entry set to true',
                    'ISO 14289-1:7.1',
                    'high',
                    'Set Suspects entry to false or remove it'
                )
                self.pdfua_compliance = False
            
            # Rule 7.1-4: Check ViewerPreferences DisplayDocTitle
            if '/ViewerPreferences' not in self.pdf.Root:
                self._add_pdfua_issue(
                    'Document lacks ViewerPreferences dictionary',
                    'ISO 14289-1:7.1',
                    'medium',
                    'Add ViewerPreferences dictionary with DisplayDocTitle=true'
                )
            else:
                viewer_prefs = self.pdf.Root.ViewerPreferences
                if not viewer_prefs.get('/DisplayDocTitle', False):
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
            if '/Lang' not in self.pdf.Root:
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
                lang = str(self.pdf.Root.Lang)
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
            has_dc_title = False
            if '/Metadata' in self.pdf.Root:
                try:
                    with self.pdf.open_metadata() as meta:
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
                if hasattr(self.pdf, 'docinfo') and self.pdf.docinfo is not None:
                    if '/Title' in self.pdf.docinfo:
                        title = str(self.pdf.docinfo['/Title'])
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
            if '/StructTreeRoot' not in self.pdf.Root:
                self._add_pdfua_issue(
                    'Document lacks structure tree',
                    'ISO 14289-1:7.1',
                    'high',
                    'Add a structure tree root to the document catalog'
                )
                self.pdfua_compliance = False
                return
            
            struct_tree_root = self.pdf.Root.StructTreeRoot
            
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
                            f'Use a standard structure type from PDF/UA-1 specification'
                        )
                
                # Recursively check children
                if '/K' in elements:
                    self._validate_structure_elements(elements.K, depth + 1, role_map=role_map)
                    
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating structure element: {str(e)}")
    
    def _validate_reading_order(self):
        """Validate WCAG 1.3.2 (Meaningful Sequence) - Level A."""
        try:
            if '/StructTreeRoot' not in self.pdf.Root:
                return  # Already reported in structure tree validation
            
            # Check if structure tree defines reading order
            struct_tree_root = self.pdf.Root.StructTreeRoot
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
    
    def _validate_alternative_text(self):
        """Validate WCAG 1.1.1 (Non-text Content) - Level A."""
        try:
            # Check for images without alt text
            for page_num, page in enumerate(self.pdf.pages, 1):
                if '/Resources' in page and '/XObject' in page.Resources:
                    xobjects = page.Resources.XObject
                    for name, xobject in xobjects.items():
                        if xobject.get('/Subtype') == '/Image':
                            # Check if image has alt text in structure tree
                            if not self._has_alt_text(xobject):
                                self._add_wcag_issue(
                                    f'Image on page {page_num} lacks alternative text',
                                    '1.1.1',
                                    'A',
                                    'high',
                                    'Add Alt text to the Figure structure element',
                                    page=page_num,
                                    context=str(name)
                                )
                                self.wcag_compliance['A'] = False
                                
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating alternative text: {str(e)}")
    
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
        if self.pdf is None:
            return None

        if self._figure_alt_lookup is None:
            try:
                self._figure_alt_lookup = _build_figure_alt_lookup(self.pdf)
            except Exception as exc:
                logger.debug(f"[WCAGValidator] Could not build Figure alt lookup: {exc}")
                self._figure_alt_lookup = None

        return self._figure_alt_lookup
    
    def _validate_table_structure(self):
        """
        Validate WCAG 1.3.1 / PDF/UA §7.5 table structure semantics.
        Ensures tables expose header cells and associate data cells with headers.
        """
        try:
            if '/StructTreeRoot' not in self.pdf.Root:
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
            if '/StructTreeRoot' not in self.pdf.Root:
                return found
            element = self.pdf.Root.StructTreeRoot
        
        try:
            if isinstance(element, pikepdf.Dictionary):
                if '/S' in element and str(element.S) == struct_type:
                    found.append(element)
                if '/K' in element:
                    self._find_structure_elements(struct_type, element.K, found)
            elif isinstance(element, list):
                for item in element:
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
                for child in node:
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
                for child in node:
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
        data_cells = table_model['data_cells']
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
                for item in value:
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
            if '/AcroForm' not in self.pdf.Root:
                return  # No forms to validate
            
            acro_form = self.pdf.Root.AcroForm
            if '/Fields' in acro_form:
                fields = acro_form.Fields
                for field in fields:
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
    
    def _validate_annotations(self):
        """Validate PDF/UA-1 annotation requirements."""
        try:
            for page_num, page in enumerate(self.pdf.pages, 1):
                if '/Annots' in page:
                    for annot in page.Annots:
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
            
            for custom_type, mapped_type in role_map.items():
                custom_type_str = str(custom_type)
                mapped_type_str = str(mapped_type)
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
        issue = {
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
        issue = {
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
        total_checks = 15  # Total number of WCAG checks performed
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
