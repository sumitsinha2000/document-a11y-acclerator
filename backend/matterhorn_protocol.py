"""
Matterhorn Protocol Implementation for PDF/UA Validation
Based on PDF Association's Matterhorn Protocol 1.02
Inspired by iText's PDF/UA validation approach
"""

from typing import Any, Dict, List
import pikepdf
import logging

logger = logging.getLogger(__name__)


class MatterhornProtocol:
    """
    Implements the Matterhorn Protocol for PDF/UA validation.
    The Matterhorn Protocol defines 31 checkpoints organized into 7 categories.
    
    Inspired by iText's PdfUAConformanceException and validation approach.
    """
    
    def __init__(self):
        self.checkpoints = self._initialize_checkpoints()
    
    def _initialize_checkpoints(self) -> Dict[str, Dict[str, Any]]:
        """Initialize all Matterhorn Protocol checkpoints"""
        return {
            # 01: Document-level requirements
            "01-001": {
                "category": "Document",
                "description": "Document does not contain a Metadata stream",
                "severity": "HIGH",
                "wcag": "4.1.2"
            },
            "01-002": {
                "category": "Document",
                "description": "XMP metadata stream does not contain dc:title",
                "severity": "HIGH",
                "wcag": "2.4.2"
            },
            "01-003": {
                "category": "Document",
                "description": "Document title is not set",
                "severity": "MEDIUM",
                "wcag": "2.4.2"
            },
            "01-004": {
                "category": "Document",
                "description": "Document language is not set",
                "severity": "HIGH",
                "wcag": "3.1.1"
            },
            "01-005": {
                "category": "Document",
                "description": "ViewerPreferences dictionary does not contain DisplayDocTitle key",
                "severity": "MEDIUM",
                "wcag": "2.4.2"
            },
            "01-006": {
                "category": "Document",
                "description": "Suspects entry in MarkInfo dictionary is set to true",
                "severity": "HIGH",
                "wcag": "4.1.2"
            },
            
            # 02: Page-level requirements
            "02-001": {
                "category": "Page",
                "description": "Page does not contain Tabs entry",
                "severity": "MEDIUM",
                "wcag": "1.3.2"
            },
            "02-002": {
                "category": "Page",
                "description": "Tabs entry in page dictionary is not set to S",
                "severity": "MEDIUM",
                "wcag": "1.3.2"
            },
            
            # 06: Structure tree requirements
            "06-001": {
                "category": "Structure",
                "description": "Structure tree root does not contain any children",
                "severity": "HIGH",
                "wcag": "1.3.1"
            },
            "06-002": {
                "category": "Structure",
                "description": "Structure element is not mapped to standard structure type",
                "severity": "HIGH",
                "wcag": "1.3.1"
            },
            "06-003": {
                "category": "Structure",
                "description": "Structure element does not have proper parent-child relationship",
                "severity": "HIGH",
                "wcag": "1.3.1"
            },
            
            # 07: Tagged content requirements
            "07-001": {
                "category": "Content",
                "description": "Real content is not tagged",
                "severity": "HIGH",
                "wcag": "1.3.1"
            },
            "07-002": {
                "category": "Content",
                "description": "Artifact is tagged as real content",
                "severity": "HIGH",
                "wcag": "1.3.1"
            },
            "07-003": {
                "category": "Content",
                "description": "Content marked as Artifact is not properly tagged",
                "severity": "MEDIUM",
                "wcag": "1.3.1"
            },
            
            # 09: Graphics requirements
            "09-001": {
                "category": "Graphics",
                "description": "Figure does not have alternative text",
                "severity": "HIGH",
                "wcag": "1.1.1"
            },
            "09-002": {
                "category": "Graphics",
                "description": "Figure alternative text is empty",
                "severity": "HIGH",
                "wcag": "1.1.1"
            },
            "09-003": {
                "category": "Graphics",
                "description": "Formula does not have alternative text",
                "severity": "HIGH",
                "wcag": "1.1.1"
            },
            
            # 13: Graphics state requirements
            "13-001": {
                "category": "Graphics State",
                "description": "Graphics state parameter BM has value other than Normal or Compatible",
                "severity": "MEDIUM",
                "wcag": "1.4.3"
            },
            
            # 14: Font requirements
            "14-001": {
                "category": "Font",
                "description": "Font is not embedded",
                "severity": "HIGH",
                "wcag": "1.4.5"
            },
            "14-002": {
                "category": "Font",
                "description": "Font does not contain ToUnicode CMap",
                "severity": "HIGH",
                "wcag": "1.4.5"
            },
            "14-003": {
                "category": "Font",
                "description": "Glyph is not mapped to Unicode",
                "severity": "HIGH",
                "wcag": "1.4.5"
            },
            
            # 28: Annotation requirements
            "28-001": {
                "category": "Annotation",
                "description": "Annotation does not have Contents or Alt entry",
                "severity": "HIGH",
                "wcag": "1.1.1"
            },
            "28-002": {
                "category": "Annotation",
                "description": "Annotation is not nested inside structure tree",
                "severity": "HIGH",
                "wcag": "1.3.1"
            },
            "28-003": {
                "category": "Annotation",
                "description": "Widget annotation does not have TU entry",
                "severity": "MEDIUM",
                "wcag": "4.1.2"
            },
            
            # 31: Optional content requirements
            "31-001": {
                "category": "Optional Content",
                "description": "Optional content configuration dictionary does not have Name entry",
                "severity": "MEDIUM",
                "wcag": "1.3.1"
            },
            "31-002": {
                "category": "Optional Content",
                "description": "Optional content group does not have Name entry",
                "severity": "MEDIUM",
                "wcag": "1.3.1"
            }
        }
    
    def validate(self, pdf: pikepdf.Pdf) -> List[Dict[str, Any]]:
        """
        Validate PDF against Matterhorn Protocol checkpoints
        
        Args:
            pdf: pikepdf.Pdf object
            
        Returns:
            List of validation issues with checkpoint references
        """
        issues = []
        
        try:
            # Document-level checks
            issues.extend(self._check_document_level(pdf))
            
            # Page-level checks
            issues.extend(self._check_page_level(pdf))
            
            # Structure tree checks
            issues.extend(self._check_structure_tree(pdf))
            
            # Content checks
            issues.extend(self._check_tagged_content(pdf))
            
            # Font checks
            issues.extend(self._check_fonts(pdf))
            
            # Annotation checks
            issues.extend(self._check_annotations(pdf))
            
        except Exception as e:
            logger.error(f"Error during Matterhorn Protocol validation: {e}")
        
        return issues
    
    def _check_document_level(self, pdf: pikepdf.Pdf) -> List[Dict[str, Any]]:
        """Check document-level requirements (01-xxx)"""
        issues = []
        
        # 01-001: Metadata stream
        if '/Metadata' not in pdf.Root:
            issues.append(self._create_issue("01-001", "Document level"))
        
        # 01-002 & 01-003: Document title
        try:
            with pdf.open_metadata() as meta:
                if 'dc:title' not in meta:
                    issues.append(self._create_issue("01-002", "XMP metadata"))
        except Exception as e:
            logger.debug(f"Unable to read XMP metadata: {e}")
        
        if not pdf.docinfo or '/Title' not in pdf.docinfo:
            issues.append(self._create_issue("01-003", "Document info"))
        
        # 01-004: Document language
        if '/Lang' not in pdf.Root:
            issues.append(self._create_issue("01-004", "Document level"))
        
        # 01-005: ViewerPreferences
        if '/ViewerPreferences' not in pdf.Root:
            issues.append(self._create_issue("01-005", "Document level"))
        elif '/DisplayDocTitle' not in pdf.Root.ViewerPreferences:
            issues.append(self._create_issue("01-005", "ViewerPreferences"))
        
        # 01-006: Suspects entry
        if '/MarkInfo' in pdf.Root and '/Suspects' in pdf.Root.MarkInfo:
            if pdf.Root.MarkInfo.Suspects:
                issues.append(self._create_issue("01-006", "MarkInfo"))
        
        return issues
    
    def _check_page_level(self, pdf: pikepdf.Pdf) -> List[Dict[str, Any]]:
        """Check page-level requirements (02-xxx)"""
        issues = []
        
        for page_num, page in enumerate(pdf.pages, 1):
            # 02-001 & 02-002: Tabs entry
            if '/Tabs' not in page:
                issues.append(self._create_issue("02-001", f"Page {page_num}"))
            elif page.Tabs != '/S':
                issues.append(self._create_issue("02-002", f"Page {page_num}"))
        
        return issues
    
    def _check_structure_tree(self, pdf: pikepdf.Pdf) -> List[Dict[str, Any]]:
        """Check structure tree requirements (06-xxx)"""
        issues = []
        
        if '/StructTreeRoot' not in pdf.Root:
            issues.append(self._create_issue("06-001", "Document level"))
            return issues
        
        struct_tree_root = pdf.Root.StructTreeRoot
        
        # 06-001: Structure tree has children
        if '/K' not in struct_tree_root:
            issues.append(self._create_issue("06-001", "Structure tree root"))
        
        return issues
    
    def _check_tagged_content(self, pdf: pikepdf.Pdf) -> List[Dict[str, Any]]:
        """Check tagged content requirements (07-xxx)"""
        issues = []
        
        # Check if document is tagged
        if '/MarkInfo' not in pdf.Root or '/Marked' not in pdf.Root.MarkInfo:
            issues.append(self._create_issue("07-001", "Document level"))
        elif not pdf.Root.MarkInfo.Marked:
            issues.append(self._create_issue("07-001", "MarkInfo"))

        struct_artifacts = self._find_structure_artifacts(pdf)
        if struct_artifacts:
            location = "; ".join(struct_artifacts[:3])
            remaining = len(struct_artifacts) - 3
            if remaining > 0:
                location = f"{location} (+{remaining} more)"
            issues.append(self._create_issue("07-002", location or "Structure tree"))

        nested_pages = self._find_artifacts_inside_tagged_scopes(pdf)
        if nested_pages:
            page_list = ", ".join(str(page) for page in nested_pages)
            issues.append(self._create_issue("07-003", f"Pages {page_list}"))
        
        return issues
    
    def _check_fonts(self, pdf: pikepdf.Pdf) -> List[Dict[str, Any]]:
        """Check font requirements (14-xxx)"""
        issues = []
        
        for page_num, page in enumerate(pdf.pages, 1):
            if '/Resources' in page and '/Font' in page.Resources:
                for font_name, font_obj in page.Resources.Font.items():
                    font_dict = font_obj
                    
                    # 14-001: Font embedding
                    if '/FontDescriptor' in font_dict:
                        font_desc = font_dict.FontDescriptor
                        if '/FontFile' not in font_desc and '/FontFile2' not in font_desc and '/FontFile3' not in font_desc:
                            issues.append(self._create_issue("14-001", f"Page {page_num}, Font {font_name}"))
                    
                    # 14-002: ToUnicode CMap
                    if '/ToUnicode' not in font_dict:
                        issues.append(self._create_issue("14-002", f"Page {page_num}, Font {font_name}"))
        
        return issues
    
    def _check_annotations(self, pdf: pikepdf.Pdf) -> List[Dict[str, Any]]:
        """Check annotation requirements (28-xxx)"""
        issues = []
        
        for page_num, page in enumerate(pdf.pages, 1):
            if '/Annots' in page:
                for annot_num, annot in enumerate(page.Annots, 1):
                    # 28-001: Annotation alternative text
                    if '/Contents' not in annot and '/Alt' not in annot:
                        issues.append(self._create_issue("28-001", f"Page {page_num}, Annotation {annot_num}"))
                    
                    # 28-003: Widget annotation TU entry
                    if '/Subtype' in annot and annot.Subtype == '/Widget':
                        if '/TU' not in annot:
                            issues.append(self._create_issue("28-003", f"Page {page_num}, Widget {annot_num}"))
        
        return issues
    
    def _create_issue(self, checkpoint: str, location: str) -> Dict[str, Any]:
        """Create an issue dictionary with checkpoint information"""
        checkpoint_info = self.checkpoints.get(checkpoint, {})
        return {
            "checkpoint": checkpoint,
            "category": checkpoint_info.get("category", "Unknown"),
            "description": checkpoint_info.get("description", "Unknown issue"),
            "severity": checkpoint_info.get("severity", "MEDIUM"),
            "wcag": checkpoint_info.get("wcag", ""),
            "location": location,
            "message": f"[{checkpoint}] {checkpoint_info.get('description', 'Unknown issue')} at {location}"
        }
    
    def get_checkpoint_info(self, checkpoint: str) -> Dict[str, Any]:
        """Get information about a specific checkpoint"""
        return self.checkpoints.get(checkpoint, {})
    
    def get_checkpoints_by_category(self, category: str) -> List[str]:
        """Get all checkpoints for a specific category"""
        return [
            cp for cp, info in self.checkpoints.items()
            if info.get("category") == category
        ]

    # ------------------------------------------------------------------ Helpers
    def _resolve_pdf_object(self, value: Any) -> Any:
        """Return the underlying object for indirect pikepdf references."""
        if value is None:
            return None
        try:
            if hasattr(value, "get_object"):
                return value.get_object()
        except Exception:
            return value
        return value

    def _iter_structure_children(self, value: Any) -> List[Any]:
        """Return a list of children for a /K entry."""
        resolved = self._resolve_pdf_object(value)
        if resolved is None:
            return []
        if isinstance(resolved, pikepdf.Array):
            return [self._resolve_pdf_object(item) for item in resolved]
        if isinstance(resolved, list):
            return [self._resolve_pdf_object(item) for item in resolved]
        return [resolved]

    def _find_structure_artifacts(self, pdf: pikepdf.Pdf) -> List[str]:
        """Return structure tree paths where /Artifact elements appear."""
        if '/StructTreeRoot' not in pdf.Root:
            return []

        artifacts: List[str] = []

        def _walk(element: Any, path: List[str]) -> None:
            element = self._resolve_pdf_object(element)
            if element is None:
                return
            if isinstance(element, pikepdf.Dictionary):
                struct_type = str(element.get("/S") or "").lstrip("/")
                type_label = struct_type or str(element.get("/Type") or "").lstrip("/")
                node_label = type_label or "StructElem"
                current_path = path + [node_label]
                if struct_type == "Artifact":
                    artifacts.append(">".join(current_path))
                kids = element.get("/K")
                if kids is not None:
                    for child in self._iter_structure_children(kids):
                        _walk(child, current_path)
            elif isinstance(element, (list, pikepdf.Array)):
                for idx, child in enumerate(element):
                    _walk(child, path + [f"Idx{idx}"])

        try:
            struct_root = pdf.Root.StructTreeRoot
            _walk(struct_root, ["StructTreeRoot"])
        except Exception as exc:
            logger.debug(f"[Matterhorn] Unable to walk structure tree: {exc}")

        return artifacts

    def _find_artifacts_inside_tagged_scopes(self, pdf: pikepdf.Pdf) -> List[int]:
        """
        Return page numbers where /Artifact content is nested inside tagged scopes.
        veraPDF UA1:7.3-2 is based on marked-content scope nesting, not MCIDs.
        """
        violating_pages: List[int] = []

        def _extract_tag_name(operator_name: str, operands: Any, operator: Any) -> str:
            tag_value = ""
            if operator_name == "BDC":
                try:
                    if operands:
                        tag_value = str(operands[0])
                except Exception:
                    tag_value = ""
            elif operator_name == "BMC":
                try:
                    if operands:
                        tag_value = str(operands[0])
                except Exception:
                    tag_value = ""
                if not tag_value:
                    try:
                        operator_tag = str(operator).strip()
                        if operator_tag.startswith("/"):
                            tag_value = operator_tag
                    except Exception:
                        tag_value = ""
            return tag_value.lstrip("/")

        def _normalize_operator_name(operator: Any) -> str:
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
                try:
                    name = str(operator)
                except Exception:
                    name = ""
            if name.startswith("/"):
                name = name[1:]
            return name

        for page_index, page in enumerate(pdf.pages, start=1):
            tag_stack: List[str] = []
            try:
                operations = pikepdf.parse_content_stream(page)
                operations = list(operations)
            except Exception as exc:
                logger.debug(f"[Matterhorn] Unable to parse content stream on page {page_index}: {exc}")
                continue

            page_violation = False
            for operands, operator in operations:
                operator_name = _normalize_operator_name(operator)
                if operator_name in ("BDC", "BMC"):
                    tag_name = _extract_tag_name(operator_name, operands, operator)
                    normalized_tag = tag_name.lstrip("/") if tag_name else ""
                    tag_stack.append(normalized_tag)
                    if normalized_tag == "Artifact" and any(scope != "Artifact" for scope in tag_stack[:-1]):
                        page_violation = True
                elif operator_name == "EMC":
                    if tag_stack:
                        tag_stack.pop()

            if page_violation:
                violating_pages.append(page_index)

        return violating_pages
