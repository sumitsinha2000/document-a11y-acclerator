"""
PDF/A Fix Engine
Implements semi-automated fixes for PDF/A compliance issues
Based on veraPDF library approach and ISO 19005 standards
"""

import logging
from typing import Dict, List, Any, Optional
from pikepdf import Pdf, Name, Dictionary, Array, Stream
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class PDFAFixEngine:
    """
    PDF/A fix engine for semi-automated compliance fixes
    Handles font embedding, color spaces, metadata, and other PDF/A requirements
    """
    
    def __init__(self):
        self.supported_fixes = [
            'addOutputIntent',
            'fixColorSpaces',
            'addPDFAIdentifier',
            'fixAnnotationAppearances',
            'removeEncryption',
            'fixMetadataConsistency'
        ]
    
    def apply_pdfa_fixes(self, pdf_path: str, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Apply semi-automated PDF/A fixes based on detected issues
        
        Args:
            pdf_path: Path to the PDF file
            issues: List of PDF/A issues to fix
            
        Returns:
            Dictionary with fix results
        """
        try:
            logger.info(f"Applying PDF/A fixes to: {pdf_path}")
            pdf = Pdf.open(pdf_path)
            
            fixes_applied = []
            success_count = 0
            warnings = []
            
            for issue in issues:
                severity = issue.get('severity', 'error')
                message = issue.get('message', '')
                
                # Fix 1: Add OutputIntent for color spaces
                if 'outputintent' in message.lower() or 'color space' in message.lower():
                    result = self._add_output_intent(pdf)
                    if result['success']:
                        fixes_applied.append(result)
                        success_count += 1
                    else:
                        warnings.append(result['message'])
                
                # Fix 2: Add PDF/A identifier
                if 'pdf/a identification' in message.lower() or 'pdfaid:part' in message.lower():
                    result = self._add_pdfa_identifier(pdf)
                    if result['success']:
                        fixes_applied.append(result)
                        success_count += 1
                
                # Fix 3: Fix annotation appearances
                if 'annotation' in message.lower() and 'appearance' in message.lower():
                    result = self._fix_annotation_appearances(pdf)
                    if result['success']:
                        fixes_applied.append(result)
                        success_count += 1
                    else:
                        warnings.append(result['message'])
                
                # Fix 4: Fix metadata consistency
                if 'metadata' in message.lower() and ('docinfo' in message.lower() or 'xmp' in message.lower()):
                    result = self._fix_metadata_consistency(pdf)
                    if result['success']:
                        fixes_applied.append(result)
                        success_count += 1
                
                # Fix 5: Font embedding (warning only - requires source fonts)
                if 'font' in message.lower() and 'embed' in message.lower():
                    warnings.append({
                        'type': 'fontEmbedding',
                        'message': 'Font embedding requires source font files. Please re-create PDF with embedded fonts.',
                        'severity': 'critical'
                    })
                
                # Fix 6: Transparency (warning only - requires flattening)
                if 'transparency' in message.lower():
                    warnings.append({
                        'type': 'transparency',
                        'message': 'Transparency removal requires flattening. Use PDF editor to flatten transparency.',
                        'severity': 'error'
                    })
                
                # Fix 7: Encryption (can be removed)
                if 'encrypt' in message.lower():
                    warnings.append({
                        'type': 'encryption',
                        'message': 'Document is encrypted. Save without encryption for PDF/A compliance.',
                        'severity': 'critical'
                    })
            
            # Save fixed PDF
            fixed_filename = f"{os.path.splitext(os.path.basename(pdf_path))[0]}_pdfa_fixed.pdf"
            fixed_path = os.path.join(os.path.dirname(pdf_path), fixed_filename)
            
            pdf.save(fixed_path)
            pdf.close()
            
            logger.info(f"Applied {success_count} PDF/A fixes")
            
            return {
                'success': True,
                'fixedFile': fixed_filename,
                'fixesApplied': fixes_applied,
                'warnings': warnings,
                'successCount': success_count,
                'message': f'Applied {success_count} PDF/A fixes with {len(warnings)} warnings'
            }
            
        except Exception as e:
            logger.error(f"Error applying PDF/A fixes: {e}")
            return {
                'success': False,
                'error': str(e),
                'fixesApplied': [],
                'successCount': 0
            }
    
    def _add_output_intent(self, pdf: Pdf) -> Dict[str, Any]:
        """Add OutputIntent with sRGB ICC profile"""
        try:
            if '/OutputIntents' in pdf.Root and len(pdf.Root.OutputIntents) > 0:
                return {
                    'success': False,
                    'message': 'OutputIntent already exists'
                }
            
            # Create OutputIntent with sRGB profile reference
            # Note: In production, you would embed an actual ICC profile
            output_intent = pdf.make_indirect(Dictionary(
                Type=Name('/OutputIntent'),
                S=Name('/GTS_PDFA1'),
                OutputConditionIdentifier='sRGB IEC61966-2.1',
                RegistryName='http://www.color.org',
                Info='sRGB IEC61966-2.1'
            ))
            
            # Note: For full PDF/A compliance, you need to embed the actual ICC profile
            # This would require: DestOutputProfile = <ICC profile stream>
            
            pdf.Root.OutputIntents = Array([output_intent])
            
            logger.info("Added OutputIntent (note: ICC profile embedding required for full compliance)")
            
            return {
                'success': True,
                'type': 'addOutputIntent',
                'description': 'Added OutputIntent with sRGB reference',
                'note': 'Full compliance requires ICC profile embedding'
            }
            
        except Exception as e:
            logger.error(f"Error adding OutputIntent: {e}")
            return {
                'success': False,
                'message': f'Failed to add OutputIntent: {str(e)}'
            }
    
    def _add_pdfa_identifier(self, pdf: Pdf) -> Dict[str, Any]:
        """Add PDF/A identifier to XMP metadata"""
        try:
            with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
                if not meta.get('pdfaid:part'):
                    meta['pdfaid:part'] = '1'
                    meta['pdfaid:conformance'] = 'B'
                    
                    logger.info("Added PDF/A-1B identifier to XMP metadata")
                    
                    return {
                        'success': True,
                        'type': 'addPDFAIdentifier',
                        'description': 'Added PDF/A-1B identifier to XMP metadata'
                    }
            
            return {
                'success': False,
                'message': 'PDF/A identifier already exists'
            }
            
        except Exception as e:
            logger.error(f"Error adding PDF/A identifier: {e}")
            return {
                'success': False,
                'message': f'Failed to add PDF/A identifier: {str(e)}'
            }
    
    def _fix_annotation_appearances(self, pdf: Pdf) -> Dict[str, Any]:
        """Add appearance streams to annotations"""
        try:
            fixed_count = 0
            
            for page_num, page in enumerate(pdf.pages, 1):
                if '/Annots' not in page:
                    continue
                
                annots = page.Annots
                for annot in annots:
                    if '/AP' not in annot:
                        # Create a minimal appearance stream
                        # Note: In production, you would create proper appearance based on annotation type
                        appearance = pdf.make_indirect(Dictionary(
                            N=pdf.make_indirect(Stream(pdf, b''))
                        ))
                        annot.AP = appearance
                        fixed_count += 1
            
            if fixed_count > 0:
                logger.info(f"Added appearance streams to {fixed_count} annotations")
                return {
                    'success': True,
                    'type': 'fixAnnotationAppearances',
                    'description': f'Added appearance streams to {fixed_count} annotations',
                    'note': 'Minimal appearances added - manual review recommended'
                }
            
            return {
                'success': False,
                'message': 'No annotations without appearances found'
            }
            
        except Exception as e:
            logger.error(f"Error fixing annotation appearances: {e}")
            return {
                'success': False,
                'message': f'Failed to fix annotation appearances: {str(e)}'
            }
    
    def _fix_metadata_consistency(self, pdf: Pdf) -> Dict[str, Any]:
        """Ensure DocInfo and XMP metadata are consistent"""
        try:
            # Get title from docinfo or filename
            title = None
            if hasattr(pdf, 'docinfo') and '/Title' in pdf.docinfo:
                title = str(pdf.docinfo.Title)
            
            if not title:
                filename = os.path.basename(pdf.filename) if hasattr(pdf, 'filename') else 'Untitled'
                title = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ')
            
            # Sync with XMP metadata
            with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=True) as meta:
                if not meta.get('dc:title'):
                    meta['dc:title'] = title
                
                # Sync other common fields
                if hasattr(pdf, 'docinfo'):
                    if '/Author' in pdf.docinfo and not meta.get('dc:creator'):
                        meta['dc:creator'] = str(pdf.docinfo.Author)
                    
                    if '/Subject' in pdf.docinfo and not meta.get('dc:description'):
                        meta['dc:description'] = str(pdf.docinfo.Subject)
                    
                    if '/Keywords' in pdf.docinfo and not meta.get('pdf:Keywords'):
                        meta['pdf:Keywords'] = str(pdf.docinfo.Keywords)
            
            logger.info("Synchronized DocInfo and XMP metadata")
            
            return {
                'success': True,
                'type': 'fixMetadataConsistency',
                'description': 'Synchronized DocInfo and XMP metadata'
            }
            
        except Exception as e:
            logger.error(f"Error fixing metadata consistency: {e}")
            return {
                'success': False,
                'message': f'Failed to fix metadata consistency: {str(e)}'
            }


def apply_pdfa_fixes(pdf_path: str, issues: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Apply PDF/A fixes to a PDF file
    
    Args:
        pdf_path: Path to the PDF file
        issues: List of PDF/A issues to fix
        
    Returns:
        Dictionary with fix results
    """
    engine = PDFAFixEngine()
    return engine.apply_pdfa_fixes(pdf_path, issues)
