"""
PDF/A Validator
Based on veraPDF library approach and ISO 19005 standards
Validates PDF/A-1, PDF/A-2, and PDF/A-3 conformance
"""

import logging
from typing import Dict, List, Any
from pikepdf import Pdf, Name, Dictionary, Array
import re

logger = logging.getLogger(__name__)


class PDFAValidator:
    """
    PDF/A validator implementing ISO 19005 standards
    Inspired by veraPDF library architecture
    """
    
    def __init__(self, pdf: Pdf):
        self.pdf = pdf
        self.issues = []
        
    def validate(self) -> Dict[str, Any]:
        """
        Validate PDF/A conformance
        Returns validation results with issues categorized by severity
        """
        logger.info("Starting PDF/A validation")
        
        results = {
            'isValid': True,
            'conformanceLevel': self._detect_conformance_level(),
            'issues': [],
            'summary': {
                'critical': 0,
                'error': 0,
                'warning': 0
            }
        }
        
        # Run all validation checks
        self._validate_file_structure()
        self._validate_graphics()
        self._validate_fonts()
        self._validate_transparency()
        self._validate_annotations()
        self._validate_actions()
        self._validate_metadata()
        self._validate_output_intents()
        self._validate_encryption()
        
        # Categorize issues
        for issue in self.issues:
            severity = issue.get('severity', 'error')
            results['summary'][severity] = results['summary'].get(severity, 0) + 1
            if severity in ['critical', 'error']:
                results['isValid'] = False
        
        results['issues'] = self.issues
        
        logger.info(f"PDF/A validation complete. Valid: {results['isValid']}, Issues: {len(self.issues)}")
        return results
    
    def _detect_conformance_level(self) -> str:
        """Detect claimed PDF/A conformance level from XMP metadata"""
        try:
            with self.pdf.open_metadata() as meta:
                # Check for PDF/A identifier in XMP
                if 'pdfaid:part' in meta:
                    part = meta.get('pdfaid:part', '')
                    conformance = meta.get('pdfaid:conformance', '')
                    return f"PDF/A-{part}{conformance}"
        except Exception as e:
            logger.debug(f"Could not detect PDF/A conformance level: {e}")
        
        return "None"
    
    def _validate_file_structure(self):
        """Validate PDF file structure requirements"""
        version = self.pdf.pdf_version
        if not isinstance(version, tuple):
            # If version is a string like "1.7", convert to tuple
            try:
                if isinstance(version, str):
                    parts = version.split('.')
                    version = (int(parts[0]), int(parts[1]))
                else:
                    version = (1, 4)  # Default to 1.4 if can't parse
            except:
                version = (1, 4)
        
        if version > (1, 4):  # PDF/A-1 requires PDF 1.4
            self.issues.append({
                'category': 'pdfaIssues',
                'severity': 'error',
                'message': f'PDF version {version[0]}.{version[1]} exceeds PDF/A-1 limit (1.4)',
                'clause': 'ISO 19005-1:2005, 6.1.2',
                'remediation': 'Convert document to PDF 1.4 or use PDF/A-2/3'
            })
        
        # Check for linearization (optional but recommended)
        if not self.pdf.is_linearized:
            self.issues.append({
                'category': 'pdfaIssues',
                'severity': 'warning',
                'message': 'Document is not linearized (fast web view)',
                'remediation': 'Linearize PDF for better web performance'
            })
        
    def _validate_graphics(self):
        """Validate graphics and color requirements"""
        root = self.pdf.Root
        
        # Check for OutputIntents (required for PDF/A)
        if '/OutputIntents' not in root:
            self.issues.append({
                'category': 'pdfaIssues',
                'severity': 'error',
                'message': 'Document lacks OutputIntents (required for PDF/A)',
                'clause': 'ISO 19005-1:2005, 6.2.2',
                'remediation': 'Add ICC color profile as OutputIntent'
            })
        
        # Check pages for color space issues
        for page_num, page in enumerate(self.pdf.pages, 1):
            if '/Resources' in page:
                resources = page.Resources
                
                # Check ColorSpace
                if '/ColorSpace' in resources:
                    colorspaces = resources.ColorSpace
                    for cs_name, cs_def in colorspaces.items():
                        if isinstance(cs_def, Name):
                            # DeviceRGB, DeviceCMYK, DeviceGray are allowed with OutputIntent
                            if str(cs_name) in ['/DeviceRGB', '/DeviceCMYK', '/DeviceGray']:
                                if '/OutputIntents' not in root:
                                    self.issues.append({
                                        'category': 'pdfaIssues',
                                        'severity': 'error',
                                        'message': f'Page {page_num} uses {cs_name} without OutputIntent',
                                        'clause': 'ISO 19005-1:2005, 6.2.2',
                                        'remediation': 'Add OutputIntent or use calibrated color space'
                                    })
    
    def _validate_fonts(self):
        """Validate font embedding requirements"""
        for page_num, page in enumerate(self.pdf.pages, 1):
            if '/Resources' not in page:
                continue
            
            resources = page.Resources
            if '/Font' not in resources:
                continue
            
            fonts = resources.Font
            for font_name, font_obj in fonts.items():
                # Check if font is embedded
                is_embedded = False
                
                if '/FontDescriptor' in font_obj:
                    font_desc = font_obj.FontDescriptor
                    # Check for embedded font stream
                    if any(key in font_desc for key in ['/FontFile', '/FontFile2', '/FontFile3']):
                        is_embedded = True
                
                if not is_embedded:
                    self.issues.append({
                        'category': 'pdfaIssues',
                        'severity': 'critical',
                        'message': f'Font {font_name} on page {page_num} is not embedded',
                        'clause': 'ISO 19005-1:2005, 6.3.5',
                        'remediation': 'Embed all fonts used in the document'
                    })
                
                # Check for symbolic fonts without ToUnicode
                if is_embedded and '/ToUnicode' not in font_obj:
                    if '/Encoding' in font_obj:
                        encoding = font_obj.Encoding
                        if isinstance(encoding, Name) and 'Symbol' in str(encoding):
                            self.issues.append({
                                'category': 'pdfaIssues',
                                'severity': 'error',
                                'message': f'Symbolic font {font_name} lacks ToUnicode mapping',
                                'clause': 'ISO 19005-1:2005, 6.3.6',
                                'remediation': 'Add ToUnicode CMap for text extraction'
                            })
    
    def _validate_transparency(self):
        """Validate transparency usage (not allowed in PDF/A-1)"""
        for page_num, page in enumerate(self.pdf.pages, 1):
            # Check for transparency group
            if '/Group' in page:
                group = page.Group
                if '/S' in group and group.S == Name('/Transparency'):
                    self.issues.append({
                        'category': 'pdfaIssues',
                        'severity': 'error',
                        'message': f'Page {page_num} uses transparency (not allowed in PDF/A-1)',
                        'clause': 'ISO 19005-1:2005, 6.4',
                        'remediation': 'Flatten transparency or use PDF/A-2/3'
                    })
            
            # Check for blend modes in resources
            if '/Resources' in page and '/ExtGState' in page.Resources:
                ext_gstates = page.Resources.ExtGState
                for gs_name, gs_obj in ext_gstates.items():
                    if '/BM' in gs_obj:
                        blend_mode = gs_obj.BM
                        if blend_mode != Name('/Normal') and blend_mode != Name('/Compatible'):
                            self.issues.append({
                                'category': 'pdfaIssues',
                                'severity': 'error',
                                'message': f'Page {page_num} uses blend mode {blend_mode}',
                                'clause': 'ISO 19005-1:2005, 6.4',
                                'remediation': 'Use only Normal/Compatible blend modes'
                            })
    
    def _validate_annotations(self):
        """Validate annotation requirements"""
        for page_num, page in enumerate(self.pdf.pages, 1):
            if '/Annots' not in page:
                continue
            
            annots = page.Annots
            for annot in annots:
                # Check annotation appearance
                if '/AP' not in annot:
                    self.issues.append({
                        'category': 'pdfaIssues',
                        'severity': 'error',
                        'message': f'Annotation on page {page_num} lacks appearance stream',
                        'clause': 'ISO 19005-1:2005, 6.5.3',
                        'remediation': 'Add appearance stream to annotation'
                    })
                
                # Check for forbidden annotation types
                if '/Subtype' in annot:
                    subtype = annot.Subtype
                    forbidden_types = ['/Movie', '/Sound', '/FileAttachment']
                    if subtype in [Name(t) for t in forbidden_types]:
                        self.issues.append({
                            'category': 'pdfaIssues',
                            'severity': 'error',
                            'message': f'Forbidden annotation type {subtype} on page {page_num}',
                            'clause': 'ISO 19005-1:2005, 6.5.3',
                            'remediation': 'Remove or replace forbidden annotation types'
                        })
    
    def _validate_actions(self):
        """Validate action restrictions"""
        root = self.pdf.Root
        
        # Check for forbidden actions in catalog
        if '/OpenAction' in root:
            action = root.OpenAction
            if isinstance(action, Dictionary) and '/S' in action:
                action_type = action.S
                forbidden_actions = ['/Launch', '/Sound', '/Movie', '/ResetForm', 
                                   '/ImportData', '/JavaScript']
                if action_type in [Name(a) for a in forbidden_actions]:
                    self.issues.append({
                        'category': 'pdfaIssues',
                        'severity': 'error',
                        'message': f'Forbidden action type {action_type} in OpenAction',
                        'clause': 'ISO 19005-1:2005, 6.6.1',
                        'remediation': 'Remove or replace forbidden action types'
                    })
    
    def _validate_metadata(self):
        """Validate XMP metadata requirements"""
        root = self.pdf.Root
        
        # Check for Metadata stream
        if '/Metadata' not in root:
            self.issues.append({
                'category': 'pdfaIssues',
                'severity': 'critical',
                'message': 'Document lacks XMP metadata stream',
                'clause': 'ISO 19005-1:2005, 6.7.3',
                'remediation': 'Add XMP metadata stream to document catalog'
            })
            return
        
        # Validate XMP metadata content
        try:
            with self.pdf.open_metadata() as meta:
                # Check for required PDF/A identification
                if 'pdfaid:part' not in meta:
                    self.issues.append({
                        'category': 'pdfaIssues',
                        'severity': 'critical',
                        'message': 'XMP metadata lacks PDF/A identification (pdfaid:part)',
                        'clause': 'ISO 19005-1:2005, 6.7.11',
                        'remediation': 'Add pdfaid:part and pdfaid:conformance to XMP'
                    })
                
                if 'pdfaid:conformance' not in meta:
                    self.issues.append({
                        'category': 'pdfaIssues',
                        'severity': 'critical',
                        'message': 'XMP metadata lacks PDF/A conformance level',
                        'clause': 'ISO 19005-1:2005, 6.7.11',
                        'remediation': 'Add pdfaid:conformance (A or B) to XMP'
                    })
                
                # Check for dc:title
                if 'dc:title' not in meta:
                    self.issues.append({
                        'category': 'pdfaIssues',
                        'severity': 'warning',
                        'message': 'XMP metadata lacks dc:title',
                        'remediation': 'Add document title to XMP metadata'
                    })
        
        except Exception as e:
            self.issues.append({
                'category': 'pdfaIssues',
                'severity': 'error',
                'message': f'Error reading XMP metadata: {str(e)}',
                'remediation': 'Fix or recreate XMP metadata stream'
            })
    
    def _validate_output_intents(self):
        """Validate OutputIntent requirements"""
        root = self.pdf.Root
        
        if '/OutputIntents' not in root:
            return  # Already reported in _validate_graphics
        
        output_intents = root.OutputIntents
        if not output_intents or len(output_intents) == 0:
            self.issues.append({
                'category': 'pdfaIssues',
                'severity': 'error',
                'message': 'OutputIntents array is empty',
                'clause': 'ISO 19005-1:2005, 6.2.2',
                'remediation': 'Add at least one OutputIntent with ICC profile'
            })
            return
        
        # Check first OutputIntent
        output_intent = output_intents[0]
        
        # Check for required keys
        if '/S' not in output_intent:
            self.issues.append({
                'category': 'pdfaIssues',
                'severity': 'error',
                'message': 'OutputIntent lacks /S (subtype) entry',
                'clause': 'ISO 19005-1:2005, 6.2.2',
                'remediation': 'Add /S entry to OutputIntent'
            })
        
        if '/DestOutputProfile' not in output_intent:
            self.issues.append({
                'category': 'pdfaIssues',
                'severity': 'error',
                'message': 'OutputIntent lacks ICC color profile',
                'clause': 'ISO 19005-1:2005, 6.2.2',
                'remediation': 'Embed ICC color profile in OutputIntent'
            })
        
        if '/OutputConditionIdentifier' not in output_intent:
            self.issues.append({
                'category': 'pdfaIssues',
                'severity': 'error',
                'message': 'OutputIntent lacks OutputConditionIdentifier',
                'clause': 'ISO 19005-1:2005, 6.2.2',
                'remediation': 'Add OutputConditionIdentifier to OutputIntent'
            })
    
    def _validate_encryption(self):
        """Validate encryption restrictions"""
        if self.pdf.is_encrypted:
            self.issues.append({
                'category': 'pdfaIssues',
                'severity': 'critical',
                'message': 'Document is encrypted (not allowed in PDF/A)',
                'clause': 'ISO 19005-1:2005, 6.1.3',
                'remediation': 'Remove encryption from document'
            })


def validate_pdfa(pdf: Pdf) -> Dict[str, Any]:
    """
    Validate PDF/A conformance
    
    Args:
        pdf: pikepdf Pdf object
        
    Returns:
        Dictionary with validation results
    """
    validator = PDFAValidator(pdf)
    return validator.validate()
