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
import shutil

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
            'fixMetadataConsistency',
            'fixStructureTypes'
        ]
    
    def apply_pdfa_fixes(self, pdf_path: str, scan_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply semi-automated PDF/A fixes based on detected issues
        COMPLETELY REWRITTEN to handle actual scan results and fix structural issues
        """
        pdf = None
        temp_path = None
        try:
            print(f"[PDFAFixEngine] ========== STARTING PDF/A FIXES ==========")
            print(f"[PDFAFixEngine] Applying PDF/A fixes to: {pdf_path}")
            print(f"[PDFAFixEngine] File exists: {os.path.exists(pdf_path)}")
            print(f"[PDFAFixEngine] File size: {os.path.getsize(pdf_path)} bytes")
            
            pdfa_issues = []
            if isinstance(scan_results, dict):
                pdfa_issues = scan_results.get('pdfaIssues', [])
                print(f"[PDFAFixEngine] Found {len(pdfa_issues)} PDF/A issues to fix")
            else:
                print(f"[PDFAFixEngine] WARNING: scan_results is not a dict, it's {type(scan_results)}")
                return {
                    'success': False,
                    'error': 'Invalid scan results format',
                    'fixesApplied': [],
                    'successCount': 0
                }
            
            if len(pdfa_issues) == 0:
                print(f"[PDFAFixEngine] No PDF/A issues found, applying basic fixes anyway")
            
            temp_path = f"{pdf_path}.temp"
            
            pdf = Pdf.open(pdf_path)
            print(f"[PDFAFixEngine] ✓ PDF opened successfully")
            
            fixes_applied = []
            success_count = 0
            warnings = []
            
            try:
                if '/OutputIntents' not in pdf.Root or len(pdf.Root.OutputIntents) == 0:
                    result = self._add_output_intent(pdf)
                    if result['success']:
                        fixes_applied.append(result)
                        success_count += 1
                        print(f"[PDFAFixEngine] ✓ Added OutputIntent")
                else:
                    print(f"[PDFAFixEngine] OutputIntent already exists")
            except Exception as e:
                print(f"[PDFAFixEngine] ✗ Error adding OutputIntent: {e}")
            
            try:
                result = self._add_pdfa_identifier(pdf)
                if result['success']:
                    fixes_applied.append(result)
                    success_count += 1
                    print(f"[PDFAFixEngine] ✓ Added PDF/A identifier")
            except Exception as e:
                print(f"[PDFAFixEngine] ✗ Error adding PDF/A identifier: {e}")
            
            try:
                result = self._fix_metadata_consistency(pdf)
                if result['success']:
                    fixes_applied.append(result)
                    success_count += 1
                    print(f"[PDFAFixEngine] ✓ Fixed metadata consistency")
            except Exception as e:
                print(f"[PDFAFixEngine] ✗ Error fixing metadata: {e}")
            
            try:
                result = self._fix_structure_types(pdf)
                if result['success']:
                    fixes_applied.append(result)
                    success_count += 1
                    print(f"[PDFAFixEngine] ✓ Fixed structure types")
            except Exception as e:
                print(f"[PDFAFixEngine] ✗ Error fixing structure types: {e}")
            
            for issue in pdfa_issues:
                if isinstance(issue, str):
                    issue = {'message': issue, 'severity': 'error'}
                
                severity = issue.get('severity', 'error')
                message = issue.get('message', '')
                
                if 'annotation' in message.lower() and 'appearance' in message.lower():
                    result = self._fix_annotation_appearances(pdf)
                    if result['success']:
                        fixes_applied.append(result)
                        success_count += 1
                        print(f"[PDFAFixEngine] ✓ Fixed annotation appearances")
                    else:
                        warnings.append(result['message'])
                
                if 'font' in message.lower() and 'embed' in message.lower():
                    warnings.append({
                        'type': 'fontEmbedding',
                        'message': 'Font embedding requires source font files. Please re-create PDF with embedded fonts.',
                        'severity': 'critical'
                    })
                    print(f"[PDFAFixEngine] ⚠ Font embedding requires manual intervention")
                
                if 'transparency' in message.lower():
                    warnings.append({
                        'type': 'transparency',
                        'message': 'Transparency removal requires flattening. Use PDF editor to flatten transparency.',
                        'severity': 'error'
                    })
                    print(f"[PDFAFixEngine] ⚠ Transparency requires manual intervention")
                
                if 'encrypt' in message.lower():
                    warnings.append({
                        'type': 'encryption',
                        'message': 'Document is encrypted. Save without encryption for PDF/A compliance.',
                        'severity': 'critical'
                    })
                    print(f"[PDFAFixEngine] ⚠ Encryption requires manual intervention")
            
            print(f"[PDFAFixEngine] ========== SAVING PDF/A FIXES ==========")
            print(f"[PDFAFixEngine] Applied {success_count} fixes, now saving...")
            print(f"[PDFAFixEngine] Saving to temp file: {temp_path}")
            
            pdf.save(
                temp_path,
                linearize=False,
                object_stream_mode=Pdf.ObjectStreamMode.preserve,
                compress_streams=True,
                stream_decode_level=Pdf.StreamDecodeLevel.none
            )
            
            print(f"[PDFAFixEngine] ✓ PDF saved to temp file")
            print(f"[PDFAFixEngine] Temp file size: {os.path.getsize(temp_path)} bytes")
            
            # Close PDF
            pdf.close()
            pdf = None
            
            print(f"[PDFAFixEngine] Replacing original file with fixed version...")
            shutil.move(temp_path, pdf_path)
            print(f"[PDFAFixEngine] ✓ Original file replaced")
            print(f"[PDFAFixEngine] Final file size: {os.path.getsize(pdf_path)} bytes")
            
            print(f"[PDFAFixEngine] ========== PDF/A FIXES COMPLETE ==========")
            print(f"[PDFAFixEngine] Total fixes applied: {success_count}")
            
            return {
                'success': True,
                'fixedFile': os.path.basename(pdf_path),
                'fixesApplied': fixes_applied,
                'warnings': warnings,
                'successCount': success_count,
                'message': f'Applied {success_count} PDF/A fixes with {len(warnings)} warnings'
            }
            
        except Exception as e:
            print(f"[PDFAFixEngine] ========== ERROR ==========")
            print(f"[PDFAFixEngine] Error applying PDF/A fixes: {e}")
            import traceback
            traceback.print_exc()
            
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    print(f"[PDFAFixEngine] Cleaned up temp file")
                except:
                    pass
            
            if pdf:
                try:
                    pdf.close()
                except:
                    pass
            
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
            
            return {
                'success': True,
                'type': 'addOutputIntent',
                'description': 'Added OutputIntent with sRGB reference (ICC profile embedding recommended for full compliance)'
            }
            
        except Exception as e:
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
                return {
                    'success': True,
                    'type': 'fixAnnotationAppearances',
                    'description': f'Added appearance streams to {fixed_count} annotations (minimal appearances - manual review recommended)'
                }
            
            return {
                'success': False,
                'message': 'No annotations without appearances found'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Failed to fix annotation appearances: {str(e)}'
            }
    
    def _fix_metadata_consistency(self, pdf: Pdf) -> Dict[str, Any]:
        """Ensure DocInfo and XMP metadata are consistent"""
        try:
            # Get title from docinfo or filename
            title = None
            if hasattr(pdf, 'docinfo') and pdf.docinfo and '/Title' in pdf.docinfo:
                title = str(pdf.docinfo.Title)
            
            if not title:
                filename = os.path.basename(pdf.filename) if hasattr(pdf, 'filename') and pdf.filename else 'Untitled'
                title = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ')
            
            # Ensure docinfo exists
            if not hasattr(pdf, 'docinfo') or pdf.docinfo is None:
                pdf.docinfo = pdf.make_indirect(Dictionary())
            
            # Set title in docinfo
            if '/Title' not in pdf.docinfo:
                pdf.docinfo['/Title'] = title
            
            # Sync with XMP metadata
            with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
                if not meta.get('dc:title'):
                    meta['dc:title'] = title
                
                # Sync other common fields
                if hasattr(pdf, 'docinfo') and pdf.docinfo:
                    if '/Author' in pdf.docinfo and not meta.get('dc:creator'):
                        meta['dc:creator'] = str(pdf.docinfo.Author)
                    
                    if '/Subject' in pdf.docinfo and not meta.get('dc:description'):
                        meta['dc:description'] = str(pdf.docinfo.Subject)
                    
                    if '/Keywords' in pdf.docinfo and not meta.get('pdf:Keywords'):
                        meta['pdf:Keywords'] = str(pdf.docinfo.Keywords)
            
            return {
                'success': True,
                'type': 'fixMetadataConsistency',
                'description': 'Synchronized DocInfo and XMP metadata'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Failed to fix metadata consistency: {str(e)}'
            }
    
    def _fix_structure_types(self, pdf: Pdf) -> Dict[str, Any]:
        """
        Fix non-standard structure types by adding proper RoleMap mappings
        This addresses issues like "Non-standard structure type /Annotation"
        """
        try:
            # Ensure structure tree exists
            if not hasattr(pdf.Root, 'StructTreeRoot'):
                return {
                    'success': False,
                    'message': 'No structure tree found'
                }
            
            struct_tree = pdf.Root.StructTreeRoot
            
            # Ensure RoleMap exists
            if not hasattr(struct_tree, 'RoleMap'):
                struct_tree.RoleMap = pdf.make_indirect(Dictionary())
            
            role_map = struct_tree.RoleMap
            
            # Add standard mappings for common non-standard types
            mappings_added = []
            
            # Map Annotation to Span (inline element)
            if Name('/Annotation') not in role_map:
                role_map[Name('/Annotation')] = Name('/Span')
                mappings_added.append('Annotation -> Span')
            
            # Map Artifact to NonStruct
            if Name('/Artifact') not in role_map:
                role_map[Name('/Artifact')] = Name('/NonStruct')
                mappings_added.append('Artifact -> NonStruct')
            
            # Map Chart to Figure
            if Name('/Chart') not in role_map:
                role_map[Name('/Chart')] = Name('/Figure')
                mappings_added.append('Chart -> Figure')
            
            # Map common heading variants
            if Name('/Heading') not in role_map:
                role_map[Name('/Heading')] = Name('/H')
                mappings_added.append('Heading -> H')
            
            if Name('/Subheading') not in role_map:
                role_map[Name('/Subheading')] = Name('/H')
                mappings_added.append('Subheading -> H')
            
            if len(mappings_added) > 0:
                return {
                    'success': True,
                    'type': 'fixStructureTypes',
                    'description': f'Added RoleMap mappings: {", ".join(mappings_added)}'
                }
            
            return {
                'success': False,
                'message': 'No structure type mappings needed'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Failed to fix structure types: {str(e)}'
            }


def apply_pdfa_fixes(pdf_path: str, scan_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply PDF/A fixes to a PDF file
    
    Args:
        pdf_path: Path to the PDF file
        scan_results: Scan results dictionary containing pdfaIssues
        
    Returns:
        Dictionary with fix results
    """
    engine = PDFAFixEngine()
    return engine.apply_pdfa_fixes(pdf_path, scan_results)
