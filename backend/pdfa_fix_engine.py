"""
PDF/A Fix Engine
Implements semi-automated fixes for PDF/A compliance issues
Based on veraPDF library approach and ISO 19005 standards
Enhanced with proper XMP metadata and ICC profile handling
"""

import logging
from typing import Dict, List, Any, Optional
from pikepdf import Pdf, Name, Dictionary, Array, Stream
import os
from pathlib import Path
import shutil
import base64

from pdf_structure_standards import (
    STANDARD_STRUCTURE_TYPES,
    COMMON_ROLEMAP_MAPPINGS,
    get_standard_mapping,
    is_standard_type,
    validate_structure_tree
)

logger = logging.getLogger(__name__)

# This is a minimal sRGB IEC61966-2.1 profile for PDF/A compliance
SRGB_ICC_PROFILE_BASE64 = """
AAACCGFwcGwCEAAAbW50clJHQiBYWVogB9kAAgAZAAsAGgALYWNzcEFQUEwAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAPbWAAEAAAAA0y1hcHBsAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAALY3BydAAAASwAAAAjZGVzYwAAAVAAAABiZHNj
bQAAAbQAAAGMd3RwdAAAA0AAAAAUclhZWgAAA1QAAAAUZ1hZWgAAA2gAAAAUYlhZWgAAA3wAAAAU
clRSQwAAA5AAAAgMYWFyZwAAC5wAAAAgdmNndAAAC7wAAAAwbmRpbgAAC+wAAAA+Y2hhZAAADCwA
AAAsbW1vZAAADFgAAAAoYlRSQwAAA5AAAAgMZ1RSQwAAA5AAAAgMYWFiZwAAC5wAAAAgYWFnZwAA
C5wAAAAgZGVzYwAAAAAAAAAIRGlzcGxheQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAG1sdWMAAAAAAAAmAAAADGhySFIAAAAUAAAB2GtvS1IAAAAMAAAB7G5iTk8AAAASAAAB+GlkAAAAAAASAAACCmh1SFUAAAAUAAACHGNzQ1oAAAAWAAACMGRhREsAAAAcAAACRm5sTkwAAAAWAAACYmZpRkkAAAAQAAACeGl0SVQAAAAUAAACiGVzRVMAAAASAAACnHJvUk8AAAASAAACnGZyQ0EAAAAWAAACrmFyAAAAAAAUAAACxHVrVUEAAAAcAAAC2GhlSUwAAAAWAAAC9HpoVFcAAAAKAAADCnZpVk4AAAAOAAADFHNrU0sAAAAWAAADInpoQ04AAAAKAAADCnJ1UlUAAAAkAAADOGVuR0IAAAAUAAADXGZyRlIAAAAWAAADcG1zAAAAAAASAAADhmhpSU4AAAASAAADmHRoVEgAAAAMAAADqmNhRVMAAAAYAAADtnBsUEwAAAASAAADzm5sTkwAAAAWAAACYmVzWEwAAAASAAACnGRlREUAAAAQAAAD4GNzQ1oAAAAWAAACMGVuVVMAAAASAAAD8HB0QlIAAAAYAAAEAnBsUEwAAAASAAADzgBMAEMARAAgAHUAIABiAG8AagBpzuy37AAgAEwAQwBEAEYAYQByAGcAZQAtAEwAQwBEAEwAQwBEACAAVwBhAHIAbgBhAFMAegDtAG4AZQBzACAATABDAEQAQgBhAHIAZQB2AG4A/QAgAEwAQwBEAEwAQwBEAC0AZgBhAHIAdgBlAHMAawDmAHIAbQBLAGwAZQB1AHIAZQBuAC0ATABDAEQAVgDkAHIAaQAtAEwAQwBEAEwAQwBEACAAYQAgAGMAbwBsAG8AcgAgAEwAQwBEACAAYQAgAGMAbwBsAG8AcgBMAEMARAAgAGMAbwBsAG8AcgBBAEMATAAgAGMAbwB1AGwAZQB1AHIgDwBMAEMARAAgBkUGRAZIBkYGKQQaBD4EOwRMBD4EQAQ+BDIEOAQ5ACAATABDAEQgDwBMAEMARAAgBeYF0QXiBdUF4AXZX2mCcgBMAEMARABMAEMARAAgAE0A4AB1AEYAYQByAGUAYgBuAP0AIABMAEMARAQmBDIENQRCBD0EPgQ5ACAEFgQaAC0ENAQ4BEEEPwQ7BDUEOQBDAG8AbABvAHUAcgAgAEwAQwBEAEwAQwBEACAAYwBvAHUAbABlAHUAcgBXAGEAcgBuAGEAIABMAEMARAkwCQIJFwlACSgAIABMAEMARABMAEMARAAgDioONQBMAEMARAAgAGUAbgAgAGMAbwBsAG8AcgBGAGEAcgBiAC0ATABDAEQAQwBvAGwAbwByACAATABDAEQATABDAEQAIABDAG8AbABvAHIAaQBkAG8ASwBvAGwAbwByACAATABDAEQDiAOzA8cDwQPJA7wDtwAgA78DuAPMA70DtwAgAEwAQwBEAEYA5AByAGcALQBMAEMARABSAGUAbgBrAGwAaQAgAEwAQwBEAEwAQwBEACAAYQAgAEMAbwByAGUAczCrMOkw/ABMAEMARHRleHQAAAAAQ29weXJpZ2h0IEFwcGxlIEluYy4sIDIwMTUAAFhZWiAAAAAAAADzUgABAAAAARbPWFlaIAAAAAAAAG+iAAA49QAAA5BYWVogAAAAAAAAYpkAALeFAAAY2lhZWiAAAAAAAAAkoAAAD4QAALbPY3VydgAAAAAAAAQAAAAABQAKAA8AFAAZAB4AIwAoAC0AMgA3ADsAQABFAEoATwBUAFkAXgBjAGgAbQByAHcAfACBAIYAiwCQAJUAmgCfAKQAqQCuALIAtwC8AMEAxgDLANAA1QDbAOAA5QDrAPAA9gD7AQEBBwENARMBGQEfASUBKwEyATgBPgFFAUwBUgFZAWABZwFuAXUBfAGDAYsBkgGaAaEBqQGxAbkBwQHJAdEB2QHhAekB8gH6AgMCDAIUAh0CJgIvAjgCQQJLAlQCXQJnAnECegKEAo4CmAKiAqwCtgLBAssC1QLgAusC9QMAAwsDFgMhAy0DOANDA08DWgNmA3IDfgOKA5YDogOuA7oDxwPTA+AD7AP5BAYEEwQgBC0EOwRIBFUEYwRxBH4EjASaBKgEtgTEBNME4QTwBP4FDQUcBSsFOgVJBVgFZwV3BYYFlgWmBbUFxQXVBeUF9gYGBhYGJwY3BkgGWQZqBnsGjAadBq8GwAbRBuMG9QcHBxkHKwc9B08HYQd0B4YHmQesB78H0gflB/gICwgfCDIIRghaCG4IggiWCKoIvgjSCOcI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
"""

class PDFAFixEngine:
    """
    PDF/A fix engine for semi-automated compliance fixes
    Handles font embedding, color spaces, metadata, and other PDF/A requirements
    Enhanced with proper XMP and ICC profile support
    """
    
    def __init__(self):
        self.supported_fixes = [
            'addOutputIntent',
            'fixColorSpaces',
            'addPDFAIdentifier',
            'fixAnnotationAppearances',
            'removeEncryption',
            'fixMetadataConsistency',
            'fixStructureTypes',
            'downgradePDFVersion',
            'fixRoleMapCircular',  # New fix for circular RoleMap references
            'addMissingRoleMappings'  # New fix to add all common mappings
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
            
            try:
                result = self._downgrade_pdf_version(pdf)
                if result['success']:
                    fixes_applied.append(result)
                    success_count += 1
                    print(f"[PDFAFixEngine] ✓ Downgraded PDF version")
            except Exception as e:
                print(f"[PDFAFixEngine] ✗ Error downgrading PDF version: {e}")
            
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
                compress_streams=True
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
        """
        Add OutputIntent with embedded sRGB ICC profile
        Now embeds actual ICC profile data instead of just reference
        """
        try:
            if '/OutputIntents' in pdf.Root and len(pdf.Root.OutputIntents) > 0:
                return {
                    'success': False,
                    'message': 'OutputIntent already exists'
                }
            
            # Decode the ICC profile from base64
            try:
                icc_data = base64.b64decode(SRGB_ICC_PROFILE_BASE64)
            except Exception as e:
                print(f"[PDFAFixEngine] Warning: Could not decode ICC profile: {e}")
                # Fall back to reference-only OutputIntent
                output_intent = pdf.make_indirect(Dictionary(
                    Type=Name('/OutputIntent'),
                    S=Name('/GTS_PDFA1'),
                    OutputConditionIdentifier='sRGB IEC61966-2.1',
                    RegistryName='http://www.color.org',
                    Info='sRGB IEC61966-2.1'
                ))
                pdf.Root.OutputIntents = Array([output_intent])
                return {
                    'success': True,
                    'type': 'addOutputIntent',
                    'description': 'Added OutputIntent with sRGB reference (ICC profile embedding failed)'
                }
            
            # Create ICC profile stream
            icc_stream = Stream(pdf, icc_data)
            icc_stream.stream_dict = Dictionary(
                N=3,  # Number of color components (RGB)
                Alternate=Name('/DeviceRGB')
            )
            icc_stream_indirect = pdf.make_indirect(icc_stream)
            
            # Create OutputIntent with embedded ICC profile
            output_intent = pdf.make_indirect(Dictionary(
                Type=Name('/OutputIntent'),
                S=Name('/GTS_PDFA1'),
                OutputConditionIdentifier='sRGB IEC61966-2.1',
                RegistryName='http://www.color.org',
                Info='sRGB IEC61966-2.1',
                DestOutputProfile=icc_stream_indirect
            ))
            
            pdf.Root.OutputIntents = Array([output_intent])
            
            return {
                'success': True,
                'type': 'addOutputIntent',
                'description': 'Added OutputIntent with embedded sRGB ICC profile'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Failed to add OutputIntent: {str(e)}'
            }
    
    def _add_pdfa_identifier(self, pdf: Pdf) -> Dict[str, Any]:
        """
        Add PDF/A identifier to XMP metadata with proper namespace declarations
        Enhanced to include proper XMP namespace declarations
        """
        try:
            with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
                # Check if PDF/A identifier already exists
                existing_part = meta.get('{http://www.aiim.org/pdfa/ns/id/}part')
                if existing_part:
                    return {
                        'success': False,
                        'message': 'PDF/A identifier already exists'
                    }
                
                # Add PDF/A-1B identifier with proper namespace
                meta['{http://www.aiim.org/pdfa/ns/id/}part'] = '1'
                meta['{http://www.aiim.org/pdfa/ns/id/}conformance'] = 'B'
                
                # Also set using the shorthand if available
                try:
                    meta['pdfaid:part'] = '1'
                    meta['pdfaid:conformance'] = 'B'
                except:
                    pass
                
                return {
                    'success': True,
                    'type': 'addPDFAIdentifier',
                    'description': 'Added PDF/A-1B identifier to XMP metadata with proper namespaces'
                }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Failed to add PDF/A identifier: {str(e)}'
            }
    
    def _downgrade_pdf_version(self, pdf: Pdf) -> Dict[str, Any]:
        """
        New method to downgrade PDF version from 1.7 to 1.4 for PDF/A-1 compliance
        """
        try:
            current_version = str(pdf.pdf_version) if hasattr(pdf, 'pdf_version') else 'unknown'
            
            # PDF/A-1 requires PDF version 1.4
            if hasattr(pdf, 'pdf_version'):
                if pdf.pdf_version == '1.4':
                    return {
                        'success': False,
                        'message': 'PDF version is already 1.4'
                    }
                
                # Set PDF version to 1.4
                pdf.pdf_version = '1.4'
                
                # Also update the catalog version if present
                if hasattr(pdf.Root, 'Version'):
                    pdf.Root.Version = Name('/1.4')
                
                return {
                    'success': True,
                    'type': 'downgradePDFVersion',
                    'description': f'Downgraded PDF version from {current_version} to 1.4 for PDF/A-1 compliance'
                }
            
            return {
                'success': False,
                'message': 'Could not determine PDF version'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Failed to downgrade PDF version: {str(e)}'
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
        """
        Ensure DocInfo and XMP metadata are consistent
        Enhanced to handle more metadata fields and proper XMP namespaces
        """
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
            
            # Sync with XMP metadata using proper namespaces
            with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
                # Dublin Core namespace for title
                if not meta.get('{http://purl.org/dc/elements/1.1/}title'):
                    meta['{http://purl.org/dc/elements/1.1/}title'] = title
                
                # Also try shorthand
                try:
                    if not meta.get('dc:title'):
                        meta['dc:title'] = title
                except:
                    pass
                
                # Sync other common fields
                if hasattr(pdf, 'docinfo') and pdf.docinfo:
                    if '/Author' in pdf.docinfo:
                        author = str(pdf.docinfo.Author)
                        try:
                            meta['{http://purl.org/dc/elements/1.1/}creator'] = author
                            meta['dc:creator'] = author
                        except:
                            pass
                    
                    if '/Subject' in pdf.docinfo:
                        subject = str(pdf.docinfo.Subject)
                        try:
                            meta['{http://purl.org/dc/elements/1.1/}description'] = subject
                            meta['dc:description'] = subject
                        except:
                            pass
                    
                    if '/Keywords' in pdf.docinfo:
                        keywords = str(pdf.docinfo.Keywords)
                        try:
                            meta['{http://ns.adobe.com/pdf/1.3/}Keywords'] = keywords
                            meta['pdf:Keywords'] = keywords
                        except:
                            pass
            
            return {
                'success': True,
                'type': 'fixMetadataConsistency',
                'description': 'Synchronized DocInfo and XMP metadata with proper namespaces'
            }
            
        except Exception as e:
            return {
                'success': False,
                'message': f'Failed to fix metadata consistency: {str(e)}'
            }
    
    def _fix_structure_types(self, pdf: Pdf) -> Dict[str, Any]:
        """
        Fix non-standard structure types by adding proper RoleMap mappings
        ENHANCED with comprehensive mappings from veraPDF corpus analysis
        """
        try:
            # Ensure structure tree exists
            if not hasattr(pdf.Root, 'StructTreeRoot'):
                return {
                    'success': False,
                    'message': 'No structure tree found'
                }
            
            struct_tree = pdf.Root.StructTreeRoot
            
            # Validate structure tree
            validation = validate_structure_tree(struct_tree)
            if not validation['valid']:
                print(f"[PDFAFixEngine] Structure tree validation issues: {validation['issues']}")
            
            # Ensure RoleMap exists
            if not hasattr(struct_tree, 'RoleMap'):
                struct_tree.RoleMap = pdf.make_indirect(Dictionary())
                print("[PDFAFixEngine] Created new RoleMap dictionary")
            
            role_map = struct_tree.RoleMap
            
            mappings_added = []
            
            for custom_type, standard_type in COMMON_ROLEMAP_MAPPINGS.items():
                custom_name = Name(custom_type)
                standard_name = Name(standard_type)
                
                # Only add if not already mapped
                if custom_name not in role_map:
                    role_map[custom_name] = standard_name
                    mappings_added.append(f'{custom_type} -> {standard_type}')
            
            circular_fixed = self._fix_circular_rolemaps(pdf, role_map)
            if circular_fixed:
                mappings_added.append('Fixed circular RoleMap references')
            
            if len(mappings_added) > 0:
                print(f"[PDFAFixEngine] Added {len(mappings_added)} RoleMap mappings")
                return {
                    'success': True,
                    'type': 'fixStructureTypes',
                    'description': f'Added {len(mappings_added)} RoleMap mappings including: {", ".join(mappings_added[:5])}'
                }
            
            return {
                'success': False,
                'message': 'No structure type mappings needed'
            }
            
        except Exception as e:
            print(f"[PDFAFixEngine] Error in _fix_structure_types: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': f'Failed to fix structure types: {str(e)}'
            }
    
    def _fix_circular_rolemaps(self, pdf: Pdf, role_map: Dictionary) -> bool:
        """
        NEW METHOD: Detect and fix circular RoleMap references
        Based on veraPDF validation rules
        """
        try:
            fixed = False
            visited = set()
            
            for key in list(role_map.keys()):
                if key in visited:
                    continue
                
                # Trace the mapping chain
                chain = [key]
                current = role_map.get(key)
                
                while current and current in role_map:
                    if current in chain:
                        # Circular reference detected!
                        print(f"[PDFAFixEngine] Circular RoleMap detected: {' -> '.join(str(c) for c in chain)} -> {current}")
                        
                        # Break the circle by mapping to a standard type
                        standard_mapping = get_standard_mapping(str(key))
                        role_map[key] = Name(standard_mapping)
                        fixed = True
                        break
                    
                    chain.append(current)
                    current = role_map.get(current)
                    
                    # Safety limit
                    if len(chain) > 10:
                        print(f"[PDFAFixEngine] RoleMap chain too long, breaking: {chain}")
                        standard_mapping = get_standard_mapping(str(key))
                        role_map[key] = Name(standard_mapping)
                        fixed = True
                        break
                
                visited.update(chain)
            
            return fixed
            
        except Exception as e:
            print(f"[PDFAFixEngine] Error fixing circular RoleMaps: {e}")
            return False

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
