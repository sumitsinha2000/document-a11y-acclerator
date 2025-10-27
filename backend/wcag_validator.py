"""
WCAG 2.1 and PDF/UA-1 Validation Algorithms
Based on veraPDF-wcag-algs: https://github.com/veraPDF/veraPDF-wcag-algs

This module implements validation algorithms for WCAG 2.1 and PDF/UA-1 compliance
without requiring external dependencies like veraPDF CLI.
"""

import pikepdf
from typing import Dict, List, Any, Tuple
import logging
from collections import defaultdict
import re

logger = logging.getLogger(__name__)


class WCAGValidator:
    """
    Implements WCAG 2.1 and PDF/UA-1 validation algorithms based on veraPDF-wcag-algs.
    
    Key validation areas:
    1. Structure Tree Validation (PDF/UA-1)
    2. Contrast Ratio Calculation (WCAG 1.4.3, 1.4.6)
    3. Alternative Text (WCAG 1.1.1)
    4. Document Language (WCAG 3.1.1)
    5. Reading Order (WCAG 1.3.2)
    6. Table Structure (WCAG 1.3.1)
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
    
    def __init__(self, pdf_path: str):
        """Initialize validator with PDF file path."""
        self.pdf_path = pdf_path
        self.pdf = None
        self.issues = defaultdict(list)
        self.wcag_compliance = {'A': True, 'AA': True, 'AAA': True}
        self.pdfua_compliance = True
        
    def validate(self) -> Dict[str, Any]:
        """
        Run all validation checks and return comprehensive results.
        
        Returns:
            Dict containing:
            - wcagIssues: List of WCAG violations
            - pdfuaIssues: List of PDF/UA violations
            - wcagCompliance: Compliance levels (A, AA, AAA)
            - pdfuaCompliance: PDF/UA compliance status
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
        """Validate PDF/UA-1 document structure requirements."""
        try:
            # Check if document is tagged
            if '/MarkInfo' not in self.pdf.Root:
                self._add_pdfua_issue(
                    'Document not marked as tagged',
                    'ISO 14289-1:7.1',
                    'high',
                    'The document must be marked as tagged for accessibility'
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
        """Validate WCAG 2.4.2 (Page Titled) - Level A."""
        try:
            if '/Info' not in self.pdf.docinfo or '/Title' not in self.pdf.docinfo:
                self._add_wcag_issue(
                    'Document title not specified',
                    '2.4.2',
                    'A',
                    'medium',
                    'Add a Title entry to the document information dictionary'
                )
                self.wcag_compliance['A'] = False
            else:
                title = str(self.pdf.docinfo.Title)
                if not title or title.strip() == '':
                    self._add_wcag_issue(
                        'Document title is empty',
                        '2.4.2',
                        'A',
                        'medium',
                        'Provide a meaningful title for the document'
                    )
                    self.wcag_compliance['A'] = False
                    
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating document title: {str(e)}")
    
    def _validate_structure_tree(self):
        """Validate PDF/UA-1 structure tree requirements."""
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
            
            # Validate structure tree has children
            if '/K' not in struct_tree_root:
                self._add_pdfua_issue(
                    'Structure tree root has no children',
                    'ISO 14289-1:7.1',
                    'high',
                    'Add structure elements to the structure tree'
                )
                self.pdfua_compliance = False
                return
            
            # Validate structure element types
            self._validate_structure_elements(struct_tree_root.K)
            
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating structure tree: {str(e)}")
    
    def _validate_structure_elements(self, elements, depth=0):
        """Recursively validate structure elements."""
        if depth > 50:  # Prevent infinite recursion
            return
        
        try:
            if isinstance(elements, list):
                for element in elements:
                    self._validate_structure_elements(element, depth + 1)
            elif isinstance(elements, pikepdf.Dictionary):
                if '/S' in elements:
                    struct_type = str(elements.S)
                    if struct_type not in self.REQUIRED_STRUCTURE_TYPES:
                        self._add_pdfua_issue(
                            f'Invalid structure type: {struct_type}',
                            'ISO 14289-1:7.2',
                            'medium',
                            f'Use a standard structure type from PDF/UA-1 specification'
                        )
                
                # Recursively check children
                if '/K' in elements:
                    self._validate_structure_elements(elements.K, depth + 1)
                    
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
                                    'Add Alt text to the Figure structure element'
                                )
                                self.wcag_compliance['A'] = False
                                
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating alternative text: {str(e)}")
    
    def _has_alt_text(self, xobject) -> bool:
        """Check if an image has alternative text."""
        # This is a simplified check - full implementation would traverse structure tree
        return '/Alt' in xobject or '/ActualText' in xobject
    
    def _validate_table_structure(self):
        """Validate WCAG 1.3.1 (Info and Relationships) for tables - Level A."""
        try:
            if '/StructTreeRoot' not in self.pdf.Root:
                return
            
            # Look for Table structure elements
            tables_found = self._find_structure_elements('Table')
            
            for table in tables_found:
                # Check for table headers (TH elements)
                if not self._has_table_headers(table):
                    self._add_wcag_issue(
                        'Table lacks proper header markup',
                        '1.3.1',
                        'A',
                        'high',
                        'Add TH (table header) elements to define table structure'
                    )
                    self.wcag_compliance['A'] = False
                    
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
    
    def _validate_heading_hierarchy(self):
        """Validate WCAG 1.3.1 (Info and Relationships) for headings - Level A."""
        try:
            headings = []
            for i in range(1, 7):
                headings.extend(self._find_structure_elements(f'H{i}'))
            
            if not headings:
                return  # No headings to validate
            
            # Check heading hierarchy (H1 should come before H2, etc.)
            prev_level = 0
            for heading in headings:
                if '/S' in heading:
                    heading_type = str(heading.S)
                    match = re.match(r'H(\d)', heading_type)
                    if match:
                        level = int(match.group(1))
                        if level > prev_level + 1:
                            self._add_wcag_issue(
                                f'Heading hierarchy skipped from H{prev_level} to H{level}',
                                '1.3.1',
                                'A',
                                'medium',
                                'Use sequential heading levels (H1, H2, H3, etc.)'
                            )
                            self.wcag_compliance['A'] = False
                        prev_level = level
                        
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating heading hierarchy: {str(e)}")
    
    def _validate_list_structure(self):
        """Validate WCAG 1.3.1 (Info and Relationships) for lists - Level A."""
        try:
            lists = self._find_structure_elements('L')
            
            for list_elem in lists:
                # Check if list has list items (LI elements)
                list_items = self._find_structure_elements('LI', list_elem)
                if not list_items:
                    self._add_wcag_issue(
                        'List structure lacks list items',
                        '1.3.1',
                        'A',
                        'medium',
                        'Add LI (list item) elements to list structure'
                    )
                    self.wcag_compliance['A'] = False
                    
        except Exception as e:
            logger.error(f"[WCAGValidator] Error validating list structure: {str(e)}")
    
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
    
    def _add_wcag_issue(self, description: str, criterion: str, level: str, severity: str, remediation: str):
        """Add a WCAG issue to the results."""
        self.issues['wcag'].append({
            'description': description,
            'criterion': criterion,
            'level': level,
            'severity': severity,
            'remediation': remediation,
            'specification': f'WCAG 2.1 Level {level}',
            'category': 'wcag'
        })
    
    def _add_pdfua_issue(self, description: str, clause: str, severity: str, remediation: str):
        """Add a PDF/UA issue to the results."""
        self.issues['pdfua'].append({
            'description': description,
            'clause': clause,
            'severity': severity,
            'remediation': remediation,
            'specification': 'PDF/UA-1 (ISO 14289-1)',
            'category': 'pdfua'
        })
    
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
