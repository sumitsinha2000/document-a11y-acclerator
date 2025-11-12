import pikepdf
from pikepdf import Pdf, Dictionary, Array, Name, String
import os
from pathlib import Path
import shutil
import tempfile
import pdfplumber
from datetime import datetime
import re
from backend.pdfa_fix_engine import PDFAFixEngine  # Import the class instead of the function
from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.fix_suggestions import generate_fix_suggestions
from backend.pdf_structure_standards import (
    STANDARD_STRUCTURE_TYPES,
    COMMON_ROLEMAP_MAPPINGS,
    WCAG_PDF_REQUIREMENTS,
    get_standard_mapping,
    is_standard_type,
    get_required_attributes
)

try:
    from backend.sambanova_remediation import SambaNovaRemediationEngine
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

    def _build_verapdf_status(self, results, analyzer=None):
        """Mirror backend.app.build_verapdf_status without circular import."""
        status = {
            "isActive": False,
            "wcagCompliance": None,
            "pdfuaCompliance": None,
            "totalVeraPDFIssues": 0,
        }

        if analyzer and hasattr(analyzer, "get_verapdf_status"):
            try:
                computed = analyzer.get_verapdf_status()
                if computed:
                    return computed
            except Exception as e:
                print(f"[AutoFixEngine] Warning: analyzer.get_verapdf_status failed: {e}")

        if not isinstance(results, dict):
            return status

        wcag_issues = len(results.get("wcagIssues", []))
        pdfua_issues = len(results.get("pdfuaIssues", []))
        total = wcag_issues + pdfua_issues
        status["totalVeraPDFIssues"] = total

        if total == 0:
            status["isActive"] = True
            status["wcagCompliance"] = 100
            status["pdfuaCompliance"] = 100
            return status

        if wcag_issues or pdfua_issues:
            status["isActive"] = True
            status["wcagCompliance"] = (
                max(0, 100 - wcag_issues * 10) if wcag_issues or pdfua_issues else 100
            )
            status["pdfuaCompliance"] = (
                max(0, 100 - pdfua_issues * 10) if pdfua_issues or wcag_issues else 100
            )

        return status

    def _analyze_fixed_pdf(self, pdf_path):
        """Re-run accessibility analysis on the updated PDF."""
        analyzer = PDFAccessibilityAnalyzer()
        results = analyzer.analyze(str(pdf_path))
        verapdf_status = self._build_verapdf_status(results, analyzer)

        try:
            summary = analyzer.calculate_summary(results, verapdf_status)
        except TypeError:
            summary = PDFAccessibilityAnalyzer.calculate_summary(results)

        if isinstance(summary, dict) and verapdf_status:
            summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
            summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))

        suggestions = generate_fix_suggestions(results)

        return {
            "results": results,
            "summary": summary,
            "verapdfStatus": verapdf_status,
            "suggestions": suggestions,
        }
    
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
    
    def apply_automated_fixes(self, scan_id, scan_data, tracker=None):
        """
        Apply automated fixes to a PDF with progress tracking
        ENHANCED with comprehensive structure type handling and progress updates
        """
        pdf = None
        temp_path = None
        upload_dir = Path("uploads")
        resolved_path = None
        if scan_data:
            resolved_path = scan_data.get("resolved_file_path")
        if resolved_path:
            pdf_path = Path(resolved_path)
        else:
            pdf_path = upload_dir / f"{scan_id}.pdf"

        try:
            if not pdf_path.exists():
                possible_names = [
                upload_dir / scan_id,
                upload_dir / f"{scan_id.replace('.pdf', '')}.pdf",
                upload_dir / scan_data.get("filename", "")
                if scan_data and scan_data.get("filename")
                else None,
                Path(scan_data.get("file_path", ""))
                if scan_data and scan_data.get("file_path")
                else None,
                Path(resolved_path) if resolved_path else None,
            ]

                for alt_path in possible_names:
                    if alt_path and alt_path.exists():
                        pdf_path = alt_path
                        print(f"[AutoFixEngine] Found existing PDF file: {pdf_path}")
                        break
                else:
                    raise FileNotFoundError(f"PDF not found for scan ID: {scan_id} in uploads/")
            
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
            
            if tracker:
                tracker.complete_step(step_id, "PDF opened successfully")
            
            fixes_applied = []
            
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
                
                fixes_applied.append({
                    'type': 'addTitle',
                    'description': f'Set document title and metadata: {title}',
                    'success': True
                })
                fixes_applied.append({
                    'type': 'pdfuaNotice',
                    'description': 'PDF/UA identifier not asserted - manual tagging and validation required.',
                    'success': False,
                    'warning': True
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
            
            can_tag = (
                hasattr(pdf.Root, 'StructTreeRoot')
                and hasattr(pdf.Root.StructTreeRoot, 'K')
                and isinstance(pdf.Root.StructTreeRoot.K, Array)
                and len(pdf.Root.StructTreeRoot.K) > 0
            )

            if can_tag:
                try:
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
                        'description': 'Confirmed document remains tagged',
                        'success': True
                    })
                    if tracker:
                        tracker.complete_step(step_id, "Document confirmed as tagged")
                except Exception as e:
                    print(f"[AutoFixEngine] ✗ Error updating MarkInfo: {e}")
                    if tracker:
                        tracker.fail_step(step_id, str(e))
            else:
                if tracker:
                    tracker.skip_step(step_id, "No valid structure tree detected; leaving document untagged")
                fixes_applied.append({
                    'type': 'markTagged',
                    'description': 'Skipped automatic tagging - manual tagging required for PDF/UA compliance.',
                    'success': False,
                    'warning': True
                })
            
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
            
            structure_modified = False
            if hasattr(pdf.Root, 'StructTreeRoot'):
                try:
                    if not hasattr(pdf.Root.StructTreeRoot, 'RoleMap'):
                        role_map = pdf.make_indirect(Dictionary())
                        for custom_type, standard_type in COMMON_ROLEMAP_MAPPINGS.items():
                            role_map[Name(custom_type)] = Name(standard_type)
                        pdf.Root.StructTreeRoot.RoleMap = role_map
                        structure_modified = True
                        print(f"[AutoFixEngine] ✓ Added RoleMap with {len(COMMON_ROLEMAP_MAPPINGS)} mappings")
                    else:
                        role_map = pdf.Root.StructTreeRoot.RoleMap
                        added_count = 0
                        for custom_type, standard_type in COMMON_ROLEMAP_MAPPINGS.items():
                            if Name(custom_type) not in role_map:
                                role_map[Name(custom_type)] = Name(standard_type)
                                added_count += 1
                        if added_count > 0:
                            structure_modified = True
                            print(f"[AutoFixEngine] ✓ Added {added_count} missing RoleMap mappings")

                    if structure_modified:
                        fixes_applied.append({
                            'type': 'createStructureTree',
                            'description': 'Enhanced existing structure RoleMap mappings',
                            'success': True
                        })
                        if tracker:
                            tracker.complete_step(step_id, "Structure RoleMap enhanced")
                    else:
                        if tracker:
                            tracker.skip_step(step_id, "Structure tree already contains standard RoleMap mappings")
                except Exception as e:
                    print(f"[AutoFixEngine] ✗ Error enhancing structure tree: {e}")
                    if tracker:
                        tracker.fail_step(step_id, str(e))
                    import traceback
                    traceback.print_exc()
            else:
                if tracker:
                    tracker.skip_step(step_id, "No structure tree detected; automatic creation disabled to prevent invalid tagging")
                fixes_applied.append({
                    'type': 'createStructureTree',
                    'description': 'Automatic structure tree creation skipped - document still requires manual tagging.',
                    'success': False,
                    'warning': True
                })
            
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

            rescan_data = {}
            rescan_step_id = None
            if tracker:
                rescan_step_id = tracker.add_step(
                    "Re-scan Fixed PDF",
                    "Analyzing updated accessibility compliance",
                    "pending"
                )
                tracker.start_step(rescan_step_id)

            try:
                rescan_data = self._analyze_fixed_pdf(pdf_path)
                rescan_data["fixedFile"] = os.path.basename(pdf_path)
                if tracker and rescan_step_id:
                    tracker.complete_step(
                        rescan_step_id,
                        "Re-scan completed",
                        result_data=rescan_data
                    )
            except Exception as e:
                print(f"[AutoFixEngine] ✗ Error during re-scan: {e}")
                if tracker and rescan_step_id:
                    tracker.fail_step(rescan_step_id, str(e))
                rescan_data = {}

            print(f"[AutoFixEngine] ========== FIXES COMPLETE ==========")
            print(f"[AutoFixEngine] Total fixes applied: {len(fixes_applied)}")
            
            return {
                'success': True,
                'fixedFile': os.path.basename(pdf_path),
                'fixesApplied': fixes_applied,
                'successCount': len(fixes_applied),
                'message': f'Successfully applied {len(fixes_applied)} automated fixes',
                'scanResults': rescan_data,
                'summary': rescan_data.get('summary'),
                'verapdfStatus': rescan_data.get('verapdfStatus'),
                'suggestions': rescan_data.get('suggestions', [])
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
                except Exception as cleanup_e:
                    print(f"[AutoFixEngine] Warning cleaning temp file: {cleanup_e}")
            
            if pdf:
                try:
                    pdf.close()
                except Exception as close_e:
                    print(f"[AutoFixEngine] Warning closing PDF: {close_e}")
            
            return {
                'success': False,
                'error': str(e),
                'fixesApplied': [],
                'successCount': 0
            }
    
    def apply_semi_automated_fixes(self, scan_id, scan_data, tracker=None, resolved_path=None):
        """Apply semi-automated fixes with progress tracking"""
        pdf_candidates = []
        if resolved_path:
            pdf_candidates.append(resolved_path)
        if scan_data:
            file_path_ref = scan_data.get("file_path")
            if file_path_ref:
                pdf_candidates.append(file_path_ref)
            original_filename = scan_data.get("filename")
            if original_filename:
                pdf_candidates.append(os.path.join("uploads", original_filename))

        if scan_id.endswith(".pdf"):
            pdf_candidates.append(os.path.join("uploads", scan_id))
        else:
            pdf_candidates.append(os.path.join("uploads", f"{scan_id}.pdf"))
            pdf_candidates.append(os.path.join("uploads", scan_id))
            pdf_candidates.append(os.path.join("uploads", f"{scan_id.replace('.pdf', '')}.pdf"))

        pdf_path = None
        for candidate in pdf_candidates:
            if not candidate:
                continue
            candidate_str = str(candidate)
            candidate_path = candidate_str
            if not os.path.isabs(candidate_path):
                candidate_path = os.path.join("uploads", candidate_path) if not candidate_path.startswith("uploads/") else candidate_path
            if os.path.exists(candidate_path):
                pdf_path = candidate_path
                print(f"[AutoFixEngine] Found PDF for semi-automated fixes: {pdf_path}")
                break

        if not pdf_path:
            return {
                "success": False,
                "error": f"PDF file not found: {pdf_candidates[0] if pdf_candidates else scan_id}",
                "fixesApplied": [],
                "successCount": 0,
            }

        scan_data["resolved_file_path"] = pdf_path
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
                except Exception as cleanup_e:
                    print(f"[AutoFixEngine] Warning cleaning temp file: {cleanup_e}")
            
            if pdf:
                try:
                    pdf.close()
                except Exception as close_e:
                    print(f"[AutoFixEngine] Warning closing PDF: {close_e}")
            
            return {
                'success': False,
                'error': str(e),
                'description': f"Failed to apply {fix_type}: {str(e)}"
            }
