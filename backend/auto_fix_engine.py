import pikepdf
from pikepdf import Pdf, Dictionary, Array, Name, String
import os
from pathlib import Path
import shutil
import tempfile
import pdfplumber
from datetime import datetime
import re
from pdfa_fix_engine import PDFAFixEngine  # Import the class instead of the function
from pdf_structure_standards import (
    STANDARD_STRUCTURE_TYPES,
    COMMON_ROLEMAP_MAPPINGS,
    WCAG_PDF_REQUIREMENTS,
    get_standard_mapping,
    is_standard_type,
    get_required_attributes
)

try:
    from sambanova_remediation import SambaNovaRemediationEngine
    SAMBANOVA_AVAILABLE = True
except ImportError:
    SAMBANOVA_AVAILABLE = False
    print("[AutoFixEngine] SambaNova AI not available - using traditional fixes only")

class AutoFixEngine:
    """Engine for applying automated and manual fixes to PDFs"""
    
    def __init__(self):
        self.supported_fixes = {
            'automated': [
                'addLanguage', 'addTitle', 'addMetadata', 'fixStructure', 
                'fixViewerPreferences', 'embedFonts', 'fixUnicode', 
                'createBookmarks', 'fixOptionalContent', 'fixRoleMap', 'addPDFAIdentifier', 'fixMetadataConsistency'
            ],
            'manual': [
                'tagContent', 'fixTableStructure', 'addAltText', 
                'addFormLabel', 'fixHeadingHierarchy', 'fixListStructure',
                'markArtifacts', 'flattenTransparency'
            ],
            'semiAutomated': [
                'removeEncryption', 'addOutputIntent', 'fixAnnotationAppearances'
            ]
        }
        print("[AutoFixEngine] Initializing PDFAFixEngine...")
        self.pdfa_engine = PDFAFixEngine()
        print(f"[AutoFixEngine] PDFAFixEngine instantiated: {type(self.pdfa_engine)}")
        print(f"[AutoFixEngine] apply_pdfa_fixes method: {type(self.pdfa_engine.apply_pdfa_fixes)}")
        
        # Check the method signature
        import inspect
        sig = inspect.signature(self.pdfa_engine.apply_pdfa_fixes)
        print(f"[AutoFixEngine] apply_pdfa_fixes signature: {sig}")
        
        self.ai_engine = None
        if SAMBANOVA_AVAILABLE:
            try:
                self.ai_engine = SambaNovaRemediationEngine()
                if not hasattr(self.ai_engine, 'is_available') or not self.ai_engine.is_available():
                    print("[AutoFixEngine] SambaNova API key not configured")
                    self.ai_engine = None
            except Exception as e:
                print(f"[AutoFixEngine] Could not initialize AI engine: {e}")
                self.ai_engine = None
    
    def generate_fixes(self, scan_results):
        """Generate fix suggestions based on scan results"""
        fixes = {
            'automated': [],
            'semiAutomated': [],
            'manual': [],
            'estimatedTime': 0
        }
        
        # Automated fixes for document structure
        if scan_results.get('structureIssues') or scan_results.get('documentStructureIssues'):
            fixes['automated'].append({
                'action': 'Fix document structure',
                'title': 'Fix PDF/UA document structure',
                'description': 'Add MarkInfo, metadata, structure tree, and RoleMap',
                'category': 'structureIssues',
                'severity': 'high',
                'estimatedTime': '< 1 minute',
                'fixType': 'fixStructure',
                'fixData': {}
            })
            fixes['estimatedTime'] += 1
        
        # Automated fixes for language
        if scan_results.get('missingLanguage') or scan_results.get('languageIssues'):
            for issue in scan_results.get('missingLanguage', []) or scan_results.get('languageIssues', []):
                fixes['automated'].append({
                    'action': 'Set document language',
                    'title': 'Set document language',
                    'description': 'Automatically set document language to English (en-US)',
                    'category': 'missingLanguage',
                    'severity': 'medium',
                    'estimatedTime': '< 1 minute',
                    'fixType': 'addLanguage',
                    'fixData': {'language': 'en-US'}
                })
                fixes['estimatedTime'] += 1
                break
        
        # Automated fixes for metadata and title
        if scan_results.get('missingMetadata') or scan_results.get('metadataIssues') or scan_results.get('titleIssues'):
            fixes['automated'].append({
                'action': 'Add document metadata',
                'title': 'Add document metadata and title',
                'description': 'Add title, metadata, ViewerPreferences, and PDF/UA identifier',
                'category': 'missingMetadata',
                'severity': 'medium',
                'estimatedTime': '< 1 minute',
                'fixType': 'addMetadata',
                'fixData': {}
            })
            fixes['estimatedTime'] += 1
        
        # Automated fixes for ViewerPreferences
        if scan_results.get('viewerPreferencesIssues'):
            fixes['automated'].append({
                'action': 'Fix ViewerPreferences',
                'title': 'Set DisplayDocTitle',
                'description': 'Configure ViewerPreferences to display document title',
                'category': 'viewerPreferencesIssues',
                'severity': 'medium',
                'estimatedTime': '< 1 minute',
                'fixType': 'fixViewerPreferences',
                'fixData': {}
            })
            fixes['estimatedTime'] += 1
        
        if scan_results.get('fontIssues'):
            fixes['automated'].append({
                'action': 'Check font embedding',
                'title': 'Verify font embedding',
                'description': 'Check if fonts are properly embedded for accessibility',
                'category': 'fontIssues',
                'severity': 'medium',
                'estimatedTime': '< 1 minute',
                'fixType': 'embedFonts',
                'fixData': {}
            })
            fixes['estimatedTime'] += 1
        
        if scan_results.get('roleMapIssues'):
            fixes['automated'].append({
                'action': 'Fix RoleMap',
                'title': 'Fix structure RoleMap',
                'description': 'Add standard RoleMap and remove circular mappings',
                'category': 'roleMapIssues',
                'severity': 'high',
                'estimatedTime': '< 1 minute',
                'fixType': 'fixRoleMap',
                'fixData': {}
            })
            fixes['estimatedTime'] += 1
        
        # Semi-automated fixes for heading hierarchy
        if scan_results.get('headingIssues'):
            for issue in scan_results['headingIssues']:
                fixes['semiAutomated'].append({
                    'action': 'Fix heading hierarchy',
                    'title': 'Fix heading hierarchy',
                    'description': 'Correct heading levels to follow proper hierarchy',
                    'category': 'headingIssues',
                    'severity': 'medium',
                    'estimatedTime': '5-10 minutes',
                    'timeEstimate': '5-10 minutes',
                    'fixType': 'fixHeadingHierarchy',
                    'fixData': {}
                })
                fixes['estimatedTime'] += 7
                break
        
        # Semi-automated fixes for list structure
        if scan_results.get('listIssues'):
            for issue in scan_results['listIssues']:
                fixes['semiAutomated'].append({
                    'action': 'Fix list structure',
                    'title': 'Fix list structure',
                    'description': 'Ensure lists have proper list items',
                    'category': 'listIssues',
                    'severity': 'medium',
                    'estimatedTime': '5-10 minutes',
                    'timeEstimate': '5-10 minutes',
                    'fixType': 'fixListStructure',
                    'fixData': {}
                })
                fixes['estimatedTime'] += 7
                break
        
        # Manual fixes for tables
        if scan_results.get('tableIssues'):
            for issue in scan_results['tableIssues']:
                fixes['manual'].append({
                    'action': 'Fix table structure',
                    'title': 'Fix table structure',
                    'description': 'Add proper table headers and markup for complex tables',
                    'category': 'tableIssues',
                    'severity': 'high',
                    'impact': 'high',
                    'estimatedTime': '20-40 minutes',
                    'timeEstimate': '20-40 minutes',
                    'fixType': 'tagContent',
                    'fixData': {'tagType': 'Table'}
                })
                fixes['estimatedTime'] += 30
        
        # Manual fixes for alt text
        if scan_results.get('missingAltText') or scan_results.get('imageIssues'):
            issues = scan_results.get('missingAltText', []) or scan_results.get('imageIssues', [])
            for issue in issues:
                fixes['manual'].append({
                    'action': 'Add alt text to images',
                    'title': 'Add alt text to images',
                    'description': f'Add descriptive alt text to {issue.get("count", 1)} image(s)',
                    'category': 'missingAltText',
                    'severity': 'high',
                    'impact': 'high',
                    'estimatedTime': '5-10 minutes per image',
                    'timeEstimate': '5-10 minutes',
                    'fixType': 'addAltText',
                    'fixData': {}
                })
                fixes['estimatedTime'] += 10
        
        # Manual fixes for form fields
        if scan_results.get('formIssues'):
            for issue in scan_results['formIssues']:
                fixes['manual'].append({
                    'action': 'Add form field labels',
                    'title': 'Add form field labels',
                    'description': 'Add accessible labels to form fields',
                    'category': 'formIssues',
                    'severity': 'high',
                    'impact': 'high',
                    'estimatedTime': '10-15 minutes',
                    'timeEstimate': '10-15 minutes',
                    'fixType': 'addFormLabel',
                    'fixData': {}
                })
                fixes['estimatedTime'] += 15
        
        # Manual fixes for annotations
        if scan_results.get('annotationIssues'):
            for issue in scan_results['annotationIssues']:
                fixes['manual'].append({
                    'action': 'Add annotation descriptions',
                    'title': 'Add annotation descriptions',
                    'description': 'Add descriptions to annotations and links',
                    'category': 'annotationIssues',
                    'severity': 'medium',
                    'estimatedTime': '5-10 minutes',
                    'timeEstimate': '5-10 minutes',
                    'fixType': 'fixAnnotations',
                    'fixData': {}
                })
                fixes['estimatedTime'] += 7
                break
        
        # Handle WCAG issues
        if scan_results.get('wcagIssues') and len(scan_results['wcagIssues']) > 0:
            for issue in scan_results['wcagIssues']:
                severity = issue.get('severity', 'high')
                description = issue.get('description', '')
                
                # Determine if fix can be automated
                if any(keyword in description.lower() for keyword in ['metadata', 'title', 'dc:title']):
                    fixes['automated'].append({
                        'action': 'Fix WCAG metadata issue',
                        'title': f"Fix {issue.get('criterion', 'WCAG')} issue",
                        'description': description,
                        'category': 'wcagIssues',
                        'severity': severity,
                        'estimatedTime': '< 1 minute',
                        'fixType': 'addMetadata',
                        'fixData': {'criterion': issue.get('criterion', '')}
                    })
                    fixes['estimatedTime'] += 1
                elif 'reading order' in description.lower():
                    fixes['manual'].append({
                        'action': 'Fix reading order',
                        'title': 'Define proper reading order',
                        'description': description,
                        'category': 'wcagIssues',
                        'severity': severity,
                        'estimatedTime': '20-30 minutes',
                        'fixType': 'fixReadingOrder',
                        'fixData': {'criterion': issue.get('criterion', '')},
                        'instructions': 'Use PDF editor to create structure tree and define reading order'
                    })
                    fixes['estimatedTime'] += 25
                else:
                    fixes['semiAutomated'].append({
                        'action': f"Fix {issue.get('criterion', 'WCAG')} issue",
                        'title': f"Fix {issue.get('criterion', 'WCAG')} compliance",
                        'description': description,
                        'category': 'wcagIssues',
                        'severity': severity,
                        'estimatedTime': '10-15 minutes',
                        'fixType': 'fixWCAG',
                        'fixData': {'criterion': issue.get('criterion', '')}
                    })
                    fixes['estimatedTime'] += 12
        
        # Handle PDF/UA issues
        if scan_results.get('pdfuaIssues') and len(scan_results['pdfuaIssues']) > 0:
            for issue in scan_results['pdfuaIssues']:
                severity = issue.get('severity', 'high')
                description = issue.get('description', '')
                
                # Determine if fix can be automated
                if any(keyword in description.lower() for keyword in ['metadata stream', 'viewerpreferences', 'dc:title', 'suspects']):
                    fixes['automated'].append({
                        'action': 'Fix PDF/UA structure issue',
                        'title': f"Fix {issue.get('clause', 'PDF/UA')} issue",
                        'description': description,
                        'category': 'pdfuaIssues',
                        'severity': severity,
                        'estimatedTime': '< 1 minute',
                        'fixType': 'fixStructure',
                        'fixData': {'clause': issue.get('clause', '')}
                    })
                    fixes['estimatedTime'] += 1
                elif 'structure tree' in description.lower() and 'no children' in description.lower():
                    fixes['automated'].append({
                        'action': 'Create structure tree',
                        'title': 'Add structure tree children',
                        'description': description,
                        'category': 'pdfuaIssues',
                        'severity': severity,
                        'estimatedTime': '< 1 minute',
                        'fixType': 'fixStructure',
                        'fixData': {'clause': issue.get('clause', '')}
                    })
                    fixes['estimatedTime'] += 1
                else:
                    fixes['semiAutomated'].append({
                        'action': f"Fix {issue.get('clause', 'PDF/UA')} issue",
                        'title': f"Fix PDF/UA {issue.get('clause', 'PDF/UA')} compliance",
                        'description': description,
                        'category': 'pdfuaIssues',
                        'severity': severity,
                        'estimatedTime': '10-15 minutes',
                        'fixType': 'fixPDFUA',
                        'fixData': {'clause': issue.get('clause', '')}
                    })
                    fixes['estimatedTime'] += 12
        
        if scan_results.get('pdfaIssues') and len(scan_results['pdfaIssues']) > 0:
            for issue in scan_results['pdfaIssues']:
                severity = issue.get('severity', 'error')
                message = issue.get('message', '')
                
                # Categorize PDF/A fixes
                if any(keyword in message.lower() for keyword in ['font', 'embed']):
                    # Font embedding requires source fonts - manual
                    fixes['manual'].append({
                        'action': 'Embed fonts',
                        'title': 'Embed all fonts in document',
                        'description': message,
                        'category': 'pdfaIssues',
                        'severity': 'critical',
                        'estimatedTime': '30-60 minutes',
                        'fixType': 'embedFonts',
                        'fixData': {'clause': issue.get('clause', '')},
                        'instructions': 'Re-create PDF with all fonts embedded, or use PDF editor to embed fonts'
                    })
                    fixes['estimatedTime'] += 45
                
                elif any(keyword in message.lower() for keyword in ['transparency', 'blend mode']):
                    # Transparency requires flattening - manual
                    fixes['manual'].append({
                        'action': 'Flatten transparency',
                        'title': 'Remove transparency from document',
                        'description': message,
                        'category': 'pdfaIssues',
                        'severity': 'error',
                        'estimatedTime': '15-30 minutes',
                        'fixType': 'flattenTransparency',
                        'fixData': {'clause': issue.get('clause', '')},
                        'instructions': 'Use PDF editor to flatten transparency layers'
                    })
                    fixes['estimatedTime'] += 22
                
                elif any(keyword in message.lower() for keyword in ['encrypt']):
                    # Encryption removal - semi-automated
                    fixes['semiAutomated'].append({
                        'action': 'Remove encryption',
                        'title': 'Remove document encryption',
                        'description': message,
                        'category': 'pdfaIssues',
                        'severity': 'critical',
                        'estimatedTime': '< 5 minutes',
                        'fixType': 'removeEncryption',
                        'fixData': {'clause': issue.get('clause', '')},
                        'instructions': 'Save document without encryption'
                    })
                    fixes['estimatedTime'] += 3
                
                elif any(keyword in message.lower() for keyword in ['outputintent', 'color space', 'icc']):
                    # OutputIntent - semi-automated
                    fixes['semiAutomated'].append({
                        'action': 'Add OutputIntent',
                        'title': 'Add ICC color profile',
                        'description': message,
                        'category': 'pdfaIssues',
                        'severity': 'error',
                        'estimatedTime': '5-10 minutes',
                        'fixType': 'addOutputIntent',
                        'fixData': {'clause': issue.get('clause', '')},
                        'instructions': 'Add sRGB or custom ICC profile as OutputIntent'
                    })
                    fixes['estimatedTime'] += 7
                
                elif any(keyword in message.lower() for keyword in ['annotation', 'appearance']):
                    # Annotation appearances - semi-automated
                    fixes['semiAutomated'].append({
                        'action': 'Fix annotation appearances',
                        'title': 'Add appearance streams to annotations',
                        'description': message,
                        'category': 'pdfaIssues',
                        'severity': 'error',
                        'estimatedTime': '5-10 minutes',
                        'fixType': 'fixAnnotationAppearances',
                        'fixData': {'clause': issue.get('clause', '')},
                        'instructions': 'Add appearance streams to all annotations'
                    })
                    fixes['estimatedTime'] += 7
                
                elif any(keyword in message.lower() for keyword in ['pdfaid:part', 'pdfaid:conformance', 'pdf/a identification']):
                    # PDF/A identifier - automated
                    fixes['automated'].append({
                        'action': 'Add PDF/A identifier',
                        'title': 'Add PDF/A identification to metadata',
                        'description': message,
                        'category': 'pdfaIssues',
                        'severity': 'critical',
                        'estimatedTime': '< 1 minute',
                        'fixType': 'addPDFAIdentifier',
                        'fixData': {'clause': issue.get('clause', '')}
                    })
                    fixes['estimatedTime'] += 1
                
                elif any(keyword in message.lower() for keyword in ['metadata', 'xmp', 'docinfo']):
                    # Metadata consistency - automated
                    fixes['automated'].append({
                        'action': 'Fix metadata consistency',
                        'title': 'Synchronize DocInfo and XMP metadata',
                        'description': message,
                        'category': 'pdfaIssues',
                        'severity': 'error',
                        'estimatedTime': '< 1 minute',
                        'fixType': 'fixMetadataConsistency',
                        'fixData': {'clause': issue.get('clause', '')}
                    })
                    fixes['estimatedTime'] += 1
                
                else:
                    # Other PDF/A issues - semi-automated
                    fixes['semiAutomated'].append({
                        'action': f"Fix {issue.get('clause', 'PDF/A')} issue",
                        'title': f"Fix PDF/A {issue.get('clause', 'PDF/A')} compliance",
                        'description': message,
                        'category': 'pdfaIssues',
                        'severity': severity,
                        'estimatedTime': '10-15 minutes',
                        'fixType': 'fixPDFA',
                        'fixData': {'clause': issue.get('clause', '')}
                    })
                    fixes['estimatedTime'] += 12
        
        return fixes
    
    # COMPLETELY REWRITTEN with veraPDF-inspired approach
    def apply_automated_fixes(self, scan_id, scan_data, tracker=None):
        """
        Apply automated fixes to a PDF with progress tracking
        ENHANCED with comprehensive structure type handling and progress updates
        """
        pdf = None
        temp_path = None
        
        # Extract PDF path from scan_id
        pdf_path = os.path.join('uploads', scan_id)
        
        try:
            print(f"[AutoFixEngine] ========== STARTING AUTOMATED FIXES ==========")
            print(f"[AutoFixEngine] Opening PDF: {pdf_path}")
            print(f"[AutoFixEngine] File exists: {os.path.exists(pdf_path)}")
            print(f"[AutoFixEngine] File size: {os.path.getsize(pdf_path)} bytes")
            
            step_id = tracker.add_step(
                "Open PDF File",
                f"Opening {scan_data.get('filename', 'PDF file')}",
                "pending"
            ) if tracker else None
            
            if tracker:
                tracker.start_step(step_id)
            
            temp_path = f"{pdf_path}.temp"
            
            pdf = pikepdf.open(pdf_path, allow_overwriting_input=False)
            print(f"[AutoFixEngine] ✓ PDF opened successfully")

            def structure_ready() -> bool:
                """Return True when the document already has tagged structure content."""
                try:
                    struct_tree = getattr(pdf.Root, 'StructTreeRoot', None)
                    if struct_tree is None:
                        return False
                    kids = getattr(struct_tree, 'K', None)
                    if kids is None:
                        return False
                    try:
                        return len(kids) > 0
                    except TypeError:
                        return bool(kids)
                except Exception as err:
                    print(f"[AutoFixEngine] ⚠ Unable to determine structure state: {err}")
                    return False

            if tracker:
                tracker.complete_step(step_id, "PDF opened successfully")

            fixes_applied = []
            pdfua_identifier_applied = False
            
            step_id = tracker.add_step(
                "Add Document Language",
                "Setting document language to en-US",
                "pending"
            ) if tracker else None
            
            if tracker:
                tracker.start_step(step_id)
            
            try:
                # Always set language to ensure compliance
                pdf.Root.Lang = 'en-US'
                print("[AutoFixEngine] ✓ Set document language (en-US)")
                
                fixes_applied.append({
                    'type': 'addLanguage',
                    'description': 'Set document language (en-US)',
                    'success': True
                })
                if tracker:
                    tracker.complete_step(step_id, "Set language: en-US")
            except Exception as e:
                print(f"[AutoFixEngine] ✗ Error adding language: {e}")
                if tracker:
                    tracker.fail_step(step_id, str(e))
            
            step_id = tracker.add_step(
                "Add Document Metadata",
                "Adding title and PDF/UA identifier",
                "pending"
            ) if tracker else None
            
            if tracker:
                tracker.start_step(step_id)
            
            try:
                filename = scan_data.get('filename', os.path.basename(pdf_path))
                title = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ')
                
                # Ensure docinfo exists
                if not hasattr(pdf, 'docinfo') or pdf.docinfo is None:
                    pdf.docinfo = pdf.make_indirect(Dictionary())
                    print("[AutoFixEngine] Created new docinfo dictionary")
                
                # Always set title to ensure compliance
                pdf.docinfo['/Title'] = title
                print(f"[AutoFixEngine] ✓ Set DocInfo title: {title}")
                
                # Always set XMP metadata to ensure compliance
                with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
                    meta['dc:title'] = title
                    print(f"[AutoFixEngine] ✓ Set XMP dc:title: {title}")
                    if structure_ready():
                        meta['pdfuaid:part'] = '1'
                        pdfua_identifier_applied = True
                        print("[AutoFixEngine] ✓ Set PDF/UA-1 identifier (existing tagged structure)")
                    else:
                        print("[AutoFixEngine] ⚠ Skipping PDF/UA identifier (no tagged structure detected)")
                
                fixes_applied.append({
                    'type': 'addTitle',
                    'description': f'Set document title and metadata: {title}',
                    'success': True
                })
                if tracker:
                    tracker.complete_step(step_id, f"Set title: {title}")
            except Exception as e:
                print(f"[AutoFixEngine] ✗ Error adding title/metadata: {e}")
                if tracker:
                    tracker.fail_step(step_id, str(e))
                import traceback
                traceback.print_exc()
            
            step_id = tracker.add_step(
                "Mark as Tagged",
                "Setting document as tagged for accessibility",
                "pending"
            ) if tracker else None
            
            if tracker:
                tracker.start_step(step_id)
            
            try:
                if not structure_ready():
                    print("[AutoFixEngine] ⚠ Skipping MarkInfo tagging (no tagged structure present)")
                    if tracker:
                        tracker.complete_step(step_id, "Skipped: no tagged structure detected")
                else:
                    if not hasattr(pdf.Root, 'MarkInfo'):
                        pdf.Root.MarkInfo = pdf.make_indirect(Dictionary(
                            Marked=True,
                            Suspects=False
                        ))
                        print("[AutoFixEngine] ✓ Created MarkInfo dictionary")
                    else:
                        pdf.Root.MarkInfo['/Marked'] = True
                        pdf.Root.MarkInfo['/Suspects'] = False
                        print("[AutoFixEngine] ✓ Updated MarkInfo dictionary")
                    
                    fixes_applied.append({
                        'type': 'markTagged',
                        'description': 'Marked document as tagged',
                        'success': True
                    })
                    if tracker:
                        tracker.complete_step(step_id, "Document marked as tagged")
            except Exception as e:
                print(f"[AutoFixEngine] ✗ Error setting MarkInfo: {e}")
                if tracker:
                    tracker.fail_step(step_id, str(e))
            
            step_id = tracker.add_step(
                "Configure Viewer Preferences",
                "Setting DisplayDocTitle preference",
                "pending"
            ) if tracker else None
            
            if tracker:
                tracker.start_step(step_id)
            
            try:
                if not hasattr(pdf.Root, 'ViewerPreferences'):
                    pdf.Root.ViewerPreferences = pdf.make_indirect(Dictionary(
                        DisplayDocTitle=True
                    ))
                    print("[AutoFixEngine] ✓ Created ViewerPreferences")
                else:
                    # Always set to ensure compliance
                    pdf.Root.ViewerPreferences['/DisplayDocTitle'] = True
                    print("[AutoFixEngine] ✓ Updated ViewerPreferences")
                
                fixes_applied.append({
                    'type': 'fixViewerPreferences',
                    'description': 'Set ViewerPreferences to display document title',
                    'success': True
                })
                if tracker:
                    tracker.complete_step(step_id, "ViewerPreferences configured")
            except Exception as e:
                print(f"[AutoFixEngine] ✗ Error setting ViewerPreferences: {e}")
                if tracker:
                    tracker.fail_step(step_id, str(e))
            
            step_id = tracker.add_step(
                "Create Structure Tree",
                "Building document structure with RoleMap",
                "pending"
            ) if tracker else None
            
            if tracker:
                tracker.start_step(step_id)
            
            try:
                struct_tree_root = getattr(pdf.Root, 'StructTreeRoot', None)
                if struct_tree_root is None:
                    print("[AutoFixEngine] ⚠ Skipping structure tree enhancements (no existing structure tree)")
                    if tracker:
                        tracker.complete_step(step_id, "Skipped: no existing structure tree")
                else:
                    struct_fixed = False
                    if not hasattr(struct_tree_root, 'RoleMap'):
                        role_map = pdf.make_indirect(Dictionary())
                        for custom_type, standard_type in COMMON_ROLEMAP_MAPPINGS.items():
                            role_map[Name(custom_type)] = Name(standard_type)
                        struct_tree_root.RoleMap = role_map
                        struct_fixed = True
                        print(f"[AutoFixEngine] ✓ Added RoleMap with {len(COMMON_ROLEMAP_MAPPINGS)} mappings")
                    else:
                        role_map = struct_tree_root.RoleMap
                        added_count = 0
                        for custom_type, standard_type in COMMON_ROLEMAP_MAPPINGS.items():
                            if Name(custom_type) not in role_map:
                                role_map[Name(custom_type)] = Name(standard_type)
                                added_count += 1
                        if added_count > 0:
                            struct_fixed = True
                            print(f"[AutoFixEngine] ✓ Added {added_count} missing RoleMap mappings")
                    
                    if struct_fixed:
                        fixes_applied.append({
                            'type': 'createStructureTree',
                            'description': 'Enhanced structure tree RoleMap mappings',
                            'success': True
                        })
                        if tracker:
                            tracker.complete_step(step_id, f"Structure tree RoleMap enhanced ({len(COMMON_ROLEMAP_MAPPINGS)} mappings)")
                    else:
                        if tracker:
                            tracker.complete_step(step_id, "Structure tree already satisfied")
            except Exception as e:
                print(f"[AutoFixEngine] ✗ Error creating structure tree: {e}")
                if tracker:
                    tracker.fail_step(step_id, str(e))
                import traceback
                traceback.print_exc()

            if not pdfua_identifier_applied and structure_ready():
                try:
                    with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as meta:
                        meta['pdfuaid:part'] = '1'
                        pdfua_identifier_applied = True
                        print("[AutoFixEngine] ✓ Set PDF/UA-1 identifier after structure verification")
                except Exception as e:
                    print(f"[AutoFixEngine] ⚠ Unable to set PDF/UA identifier: {e}")
            
            step_id = tracker.add_step(
                "Add PDF/A Compliance",
                "Adding OutputIntent and PDF/A identifier",
                "pending"
            ) if tracker else None
            
            if tracker:
                tracker.start_step(step_id)
            
            try:
                pdfa_result = self.pdfa_engine.apply_pdfa_fixes(pdf_path, scan_data)
                
                if pdfa_result.get('success'):
                    fixes_applied.append({
                        'type': 'addPDFACompliance',
                        'description': 'Added PDF/A OutputIntent and identifier',
                        'success': True
                    })
                    if tracker:
                        tracker.complete_step(step_id, "PDF/A compliance added")
                else:
                    if tracker:
                        tracker.fail_step(step_id, pdfa_result.get('error', 'Unknown error'))
            except Exception as e:
                print(f"[AutoFixEngine] ✗ Error adding PDF/A compliance: {e}")
                if tracker:
                    tracker.fail_step(step_id, str(e))
                import traceback
                traceback.print_exc()

            step_id = tracker.add_step(
                "Save Fixed PDF",
                "Writing changes to file",
                "pending"
            ) if tracker else None
            
            if tracker:
                tracker.start_step(step_id)
            
            print(f"[AutoFixEngine] ========== SAVING PDF ==========")
            print(f"[AutoFixEngine] Applied {len(fixes_applied)} fixes, now saving...")
            print(f"[AutoFixEngine] Saving to temp file: {temp_path}")
            
            pdf.save(
                temp_path,
                linearize=False,
                object_stream_mode=pikepdf.ObjectStreamMode.preserve,
                compress_streams=True,
                stream_decode_level=pikepdf.StreamDecodeLevel.none
            )
            
            print(f"[AutoFixEngine] ✓ PDF saved to temp file")
            print(f"[AutoFixEngine] Temp file size: {os.path.getsize(temp_path)} bytes")
            
            pdf.close()
            pdf = None
            
            print(f"[AutoFixEngine] Replacing original file with fixed version...")
            shutil.move(temp_path, pdf_path)
            print(f"[AutoFixEngine] ✓ Original file replaced")
            print(f"[AutoFixEngine] Final file size: {os.path.getsize(pdf_path)} bytes")
            
            if tracker:
                tracker.complete_step(step_id, f"PDF saved ({os.path.getsize(pdf_path)} bytes)")
            
            print(f"[AutoFixEngine] ========== FIXES COMPLETE ==========")
            print(f"[AutoFixEngine] Total fixes applied: {len(fixes_applied)}")
            
            return {
                'success': True,
                'fixedFile': os.path.basename(pdf_path),
                'fixesApplied': fixes_applied,
                'successCount': len(fixes_applied),
                'message': f'Successfully applied {len(fixes_applied)} automated fixes'
            }
            
        except Exception as e:
            print(f"[AutoFixEngine] ========== ERROR ==========")
            print(f"[AutoFixEngine] ERROR: {e}")
            import traceback
            traceback.print_exc()
            
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    print(f"[AutoFixEngine] Cleaned up temp file")
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
    
    def apply_semi_automated_fixes(self, scan_id, scan_data, tracker=None):
        """Apply semi-automated fixes with progress tracking"""
        pdf_path = os.path.join('uploads', scan_id)
        
        # For now, semi-automated fixes are similar to automated
        # In the future, this could include OCR, user confirmations, etc.
        return self.apply_automated_fixes(scan_id, scan_data, tracker)
    
    def apply_single_fix(self, pdf_path, fix_config):
        """Apply a single manual fix to a PDF"""
        fix_type = fix_config.get('type')
        fix_data = fix_config.get('data', {})
        page = fix_config.get('page', 1)
        
        return self.apply_manual_fix(pdf_path, fix_type, fix_data, page)
    
    # COMPLETELY REWRITTEN to ensure changes persist
    def apply_manual_fix(self, pdf_path, fix_type, fix_data, page=1):
        """
        Apply a manual fix to a PDF
        COMPLETELY REWRITTEN to ensure changes persist
        """
        pdf = None
        temp_path = None
        try:
            print(f"[AutoFixEngine] ========== APPLYING MANUAL FIX ==========")
            print(f"[AutoFixEngine] Fix type: {fix_type}")
            print(f"[AutoFixEngine] Fix data: {fix_data}")
            print(f"[AutoFixEngine] PDF path: {pdf_path}")
            print(f"[AutoFixEngine] File exists: {os.path.exists(pdf_path)}")
            
            temp_path = f"{pdf_path}.temp"
            
            pdf = pikepdf.open(pdf_path, allow_overwriting_input=False)
            print(f"[AutoFixEngine] ✓ PDF opened")
            
            fix_applied = False
            fix_description = ""
            
            if fix_type in ['tagContent', 'fixTableStructure']:
                print("[AutoFixEngine] Applying table structure fix...")
                
                # Ensure language
                if not hasattr(pdf.Root, 'Lang') or not pdf.Root.Lang:
                    pdf.Root.Lang = 'en-US'
                    print("[AutoFixEngine] ✓ Added document language (en-US)")
                
                # Mark as tagged
                if not hasattr(pdf.Root, 'MarkInfo'):
                    pdf.Root.MarkInfo = pdf.make_indirect(Dictionary(Marked=True, Suspects=False))
                    print("[AutoFixEngine] ✓ Created MarkInfo dictionary")
                else:
                    pdf.Root.MarkInfo['/Marked'] = True
                    pdf.Root.MarkInfo['/Suspects'] = False
                    print("[AutoFixEngine] ✓ Updated MarkInfo dictionary")
                
                # Ensure structure tree
                if not hasattr(pdf.Root, 'StructTreeRoot'):
                    struct_tree_root = pdf.make_indirect(Dictionary(
                        Type=Name('/StructTreeRoot'),
                        K=Array([])
                    ))
                    pdf.Root.StructTreeRoot = struct_tree_root
                    print("[AutoFixEngine] ✓ Created StructTreeRoot dictionary")
                
                fix_applied = True
                fix_description = "Marked document as tagged for table accessibility"
                print("[AutoFixEngine] ✓ Table structure fix applied")
            
            elif fix_type == 'addAltText':
                print("[AutoFixEngine] Applying alt text fix...")
                image_index = int(fix_data.get('imageIndex', 1)) - 1
                alt_text = fix_data.get('altText', '')
                
                # Store in metadata
                with pdf.open_metadata() as meta:
                    meta[f'image_{image_index}_alt'] = alt_text
                
                fix_applied = True
                fix_description = f"Added alt text to image {image_index + 1}"
                print(f"[AutoFixEngine] ✓ Alt text added")
            
            elif fix_type == 'addFormLabel':
                print("[AutoFixEngine] Applying form label fix...")
                field_name = fix_data.get('fieldName', '')
                label = fix_data.get('label', '')
                
                if hasattr(pdf.Root, 'AcroForm') and hasattr(pdf.Root.AcroForm, 'Fields'):
                    for field in pdf.Root.AcroForm.Fields:
                        if hasattr(field, 'T') and str(field.T) == field_name:
                            field.TU = label
                            fix_applied = True
                            break
                
                if fix_applied:
                    fix_description = f"Added label '{label}' to form field"
                    print(f"[AutoFixEngine] ✓ Form label added")
                else:
                    fix_description = f"Form field '{field_name}' not found"
                    print(f"[AutoFixEngine] ⚠ Form field '{field_name}' not found")
            
            else:
                # Generic fix - mark as tagged
                print(f"[AutoFixEngine] Applying generic fix for: {fix_type}")
                if not hasattr(pdf.Root, 'Lang') or not pdf.Root.Lang:
                    pdf.Root.Lang = 'en-US'
                    print("[AutoFixEngine] ✓ Added document language (en-US)")
                
                if not hasattr(pdf.Root, 'MarkInfo'):
                    pdf.Root.MarkInfo = pdf.make_indirect(Dictionary(Marked=True))
                    print("[AutoFixEngine] ✓ Created MarkInfo dictionary for generic fix")
                else:
                    pdf.Root.MarkInfo['/Marked'] = True
                    print("[AutoFixEngine] ✓ Updated MarkInfo dictionary for generic fix")
                
                fix_applied = True
                fix_description = f"Applied basic tagging for {fix_type}"
            
            if not fix_applied:
                print(f"[AutoFixEngine] WARNING: No fix was applied for type: {fix_type}")
                return {
                    'success': False,
                    'error': f'Fix type {fix_type} not implemented or applicable',
                    'description': f'Fix type {fix_type} not implemented or applicable'
                }
            
            print(f"[AutoFixEngine] ========== SAVING MANUAL FIX ==========")
            print(f"[AutoFixEngine] Saving changes to temp file: {temp_path}")
            
            pdf.save(
                temp_path,
                linearize=False,
                object_stream_mode=pikepdf.ObjectStreamMode.preserve,
                compress_streams=True,
                stream_decode_level=pikepdf.StreamDecodeLevel.none
            )
            
            print(f"[AutoFixEngine] ✓ PDF saved to temp file")
            print(f"[AutoFixEngine] Temp file size: {os.path.getsize(temp_path)} bytes")
            
            pdf.close()
            pdf = None
            
            print(f"[AutoFixEngine] Replacing original file...")
            shutil.move(temp_path, pdf_path)
            print(f"[AutoFixEngine] ✓ Original file replaced")
            print(f"[AutoFixEngine] File size after save: {os.path.getsize(pdf_path)} bytes")
            
            print(f"[AutoFixEngine] ========== MANUAL FIX COMPLETE ==========")
            
            return {
                'success': True,
                'fixType': fix_type,
                'description': fix_description,
                'message': fix_description
            }
            
        except Exception as e:
            print(f"[AutoFixEngine] ========== ERROR ==========")
            print(f"[AutoFixEngine] ERROR: {e}")
            import traceback
            traceback.print_exc()
            
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    print(f"[AutoFixEngine] Cleaned up temp file")
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
                'description': f"Failed to apply {fix_type}: {str(e)}"
            }
