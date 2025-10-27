"""
Advanced Metadata Fixer
Inspired by veraPDF's pdfbox-metadata-fixer
Comprehensive metadata repair for PDF/A compliance
"""

import logging
from typing import Dict, Any, Optional
from pikepdf import Pdf, Dictionary, Name, Array
from datetime import datetime

logger = logging.getLogger(__name__)

class AdvancedMetadataFixer:
    """Advanced metadata fixing for PDF/A compliance"""
    
    def __init__(self, pdf: Pdf):
        self.pdf = pdf
        self.fixes_applied = []
        
    def fix_all_metadata(self, title: Optional[str] = None) -> List[str]:
        """Apply all metadata fixes"""
        self.fixes_applied = []
        
        try:
            # Fix document info dictionary
            self._fix_document_info(title)
            
            # Fix XMP metadata
            self._fix_xmp_metadata(title)
            
            # Synchronize XMP and DocInfo
            self._synchronize_metadata()
            
            # Fix PDF/A identification
            self._fix_pdfa_identification()
            
            # Fix modification date
            self._fix_modification_date()
            
            logger.info(f"Applied {len(self.fixes_applied)} metadata fixes")
            
        except Exception as e:
            logger.error(f"Error fixing metadata: {e}")
            
        return self.fixes_applied
    
    def _fix_document_info(self, title: Optional[str] = None):
        """Fix document info dictionary"""
        try:
            # Ensure docinfo exists
            if not self.pdf.docinfo:
                self.pdf.docinfo = self.pdf.make_indirect(Dictionary())
                self.fixes_applied.append("Created document info dictionary")
            
            # Add title if missing
            if '/Title' not in self.pdf.docinfo:
                doc_title = title or "Untitled Document"
                self.pdf.docinfo['/Title'] = doc_title
                self.fixes_applied.append(f"Added document title: {doc_title}")
            
            # Add creation date if missing
            if '/CreationDate' not in self.pdf.docinfo:
                creation_date = datetime.now().strftime("D:%Y%m%d%H%M%S")
                self.pdf.docinfo['/CreationDate'] = creation_date
                self.fixes_applied.append("Added creation date")
            
            # Add producer if missing
            if '/Producer' not in self.pdf.docinfo:
                self.pdf.docinfo['/Producer'] = "Document Accessibility Accelerator"
                self.fixes_applied.append("Added producer")
                
        except Exception as e:
            logger.error(f"Error fixing document info: {e}")
    
    def _fix_xmp_metadata(self, title: Optional[str] = None):
        """Fix XMP metadata stream"""
        try:
            with self.pdf.open_metadata() as meta:
                # Ensure dc:title exists
                if 'dc:title' not in meta:
                    doc_title = title or self.pdf.docinfo.get('/Title', 'Untitled Document')
                    meta['dc:title'] = str(doc_title)
                    self.fixes_applied.append("Added dc:title to XMP metadata")
                
                # Ensure dc:format exists
                if 'dc:format' not in meta:
                    meta['dc:format'] = 'application/pdf'
                    self.fixes_applied.append("Added dc:format to XMP metadata")
                
                # Ensure xmp:CreateDate exists
                if 'xmp:CreateDate' not in meta:
                    create_date = self.pdf.docinfo.get('/CreationDate', datetime.now().strftime("D:%Y%m%d%H%M%S"))
                    meta['xmp:CreateDate'] = str(create_date)
                    self.fixes_applied.append("Added xmp:CreateDate")
                
                # Ensure xmp:CreatorTool exists
                if 'xmp:CreatorTool' not in meta:
                    meta['xmp:CreatorTool'] = 'Document Accessibility Accelerator'
                    self.fixes_applied.append("Added xmp:CreatorTool")
                    
        except Exception as e:
            logger.error(f"Error fixing XMP metadata: {e}")
    
    def _synchronize_metadata(self):
        """Synchronize XMP and DocInfo metadata"""
        try:
            with self.pdf.open_metadata() as meta:
                # Sync title
                if '/Title' in self.pdf.docinfo and 'dc:title' in meta:
                    docinfo_title = str(self.pdf.docinfo['/Title'])
                    xmp_title = str(meta.get('dc:title', ''))
                    
                    if docinfo_title != xmp_title:
                        meta['dc:title'] = docinfo_title
                        self.fixes_applied.append("Synchronized title between XMP and DocInfo")
                
                # Sync creator
                if '/Creator' in self.pdf.docinfo:
                    meta['dc:creator'] = str(self.pdf.docinfo['/Creator'])
                    self.fixes_applied.append("Synchronized creator")
                    
        except Exception as e:
            logger.error(f"Error synchronizing metadata: {e}")
    
    def _fix_pdfa_identification(self):
        """Add PDF/A identification to XMP metadata"""
        try:
            with self.pdf.open_metadata() as meta:
                # Add PDF/A-1b identification if not present
                if 'pdfaid:part' not in meta:
                    meta['pdfaid:part'] = '1'
                    meta['pdfaid:conformance'] = 'B'
                    self.fixes_applied.append("Added PDF/A-1b identification")
                    
        except Exception as e:
            logger.error(f"Error fixing PDF/A identification: {e}")
    
    def _fix_modification_date(self):
        """Update modification date"""
        try:
            mod_date = datetime.now().strftime("D:%Y%m%d%H%M%S")
            self.pdf.docinfo['/ModDate'] = mod_date
            
            with self.pdf.open_metadata() as meta:
                meta['xmp:ModifyDate'] = mod_date
                
            self.fixes_applied.append("Updated modification date")
            
        except Exception as e:
            logger.error(f"Error fixing modification date: {e}")
