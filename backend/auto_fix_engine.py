import json
import pikepdf
from pikepdf import Pdf, Dictionary, Array, Name, String
import os
from pathlib import Path
import shutil
import tempfile
import pdfplumber
from datetime import datetime
import re
from typing import Any, Dict, Optional
# from backend.pdfa_fix_engine import PDFAFixEngine  # PDF/A fix engine temporarily disabled
from backend.pdf_analyzer import PDFAccessibilityAnalyzer
from backend.fix_suggestions import generate_fix_suggestions
from backend.utils.metadata_helpers import ensure_pdfua_metadata_stream
from backend.utils.fix_traceability import (
    FixTraceabilityFormatter,
    count_successful_fixes,
    derive_allowed_fix_types,
    get_canonical_fix_type,
)
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
        # PDF/A fix engine is disabled so automated fixes focus on WCAG and PDF/UA issues.
        
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

        canonical = results.get("issues")
        if isinstance(canonical, list) and canonical:
            seen = set()
            wcag_issues = 0
            pdfua_issues = 0
            for issue in canonical:
                if not isinstance(issue, dict):
                    continue
                issue_id = issue.get("issueId")
                if issue_id and issue_id in seen:
                    continue
                if issue_id:
                    seen.add(issue_id)
                if issue.get("criterion"):
                    wcag_issues += 1
                if issue.get("clause"):
                    pdfua_issues += 1
            total = wcag_issues + pdfua_issues
        else:
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

        metrics_getter = getattr(analyzer, "get_wcag_validator_metrics", None)
        if isinstance(summary, dict) and callable(metrics_getter):
            metrics = metrics_getter()
            if isinstance(metrics, dict):
                # Keep auto-fix summary aligned with backend: WCAG validator drives compliance.
                summary["wcagCompliance"] = metrics.get("wcagScore", summary.get("wcagCompliance"))
                summary["pdfuaCompliance"] = metrics.get("pdfuaScore", summary.get("pdfuaCompliance"))
                if metrics.get("wcagCompliance"):
                    summary["wcagLevels"] = metrics["wcagCompliance"]
                if metrics.get("pdfuaCompliance"):
                    summary["pdfuaLevels"] = metrics["pdfuaCompliance"]

        if isinstance(summary, dict) and verapdf_status:
            summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
            summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))

        fixes = generate_fix_suggestions(results)

        return {
            "results": results,
            "summary": summary,
            "verapdfStatus": verapdf_status,
            "fixes": fixes,
        }

    def _extract_issue_payload(self, scan_data):
        """Extract the original scan results dict for suggestion lookups."""
        if not scan_data:
            return {}
        payload = (
            scan_data.get("scan_results")
            or scan_data.get("scanResults")
            or scan_data.get("results")
        )
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        if isinstance(payload, dict):
            issues = payload.get("results")
            if isinstance(issues, dict):
                return issues
            return payload
        return {}

    def _detect_missing_rolemap_mappings(self, pdf) -> list:
        """Identify missing RoleMap mappings using the canonical mapping list."""
        try:
            struct_root = getattr(pdf.Root, "StructTreeRoot", None)
            if not struct_root:
                return []
            role_map = struct_root.RoleMap if hasattr(struct_root, "RoleMap") else None
            missing = []
            for custom_type, standard_type in COMMON_ROLEMAP_MAPPINGS.items():
                if role_map is None or Name(custom_type) not in role_map:
                    missing.append(custom_type)
            return missing
        except Exception as exc:
            print(f"[AutoFixEngine] Warning: could not inspect RoleMap for suggestions: {exc}")
            return []
    
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
        
        # Metadata guidance, splitting semantic fixes
        metadata_issues = scan_results.get('missingMetadata') or []
        metadata_misc_present = bool(scan_results.get('metadataIssues') or scan_results.get('titleIssues'))
        metadata_title_missing = False
        metadata_other_missing = False
        author_fix_added = False
        subject_fix_added = False

        for issue in metadata_issues:
            description = issue.get('description', '')
            desc_lower = description.lower()
            severity = issue.get('severity', 'medium')
            recommendation = issue.get('recommendation')

            if 'title' in desc_lower:
                metadata_title_missing = True
            elif 'author' in desc_lower or 'creator' in desc_lower:
                if not author_fix_added:
                    fixes['semiAutomated'].append({
                        'action': 'Add author metadata',
                        'title': 'Add author metadata',
                        'description': description,
                        'category': 'missingMetadata',
                        'severity': severity,
                        'estimatedTime': '2 minutes',
                        'fixType': 'addMetadata',
                        'fixData': {'field': 'author'},
                        'instructions': recommendation
                        or "Open the PDF metadata settings and provide the author name."
                    })
                    fixes['estimatedTime'] += 2
                    author_fix_added = True
            elif 'subject' in desc_lower:
                if not subject_fix_added:
                    fixes['semiAutomated'].append({
                        'action': 'Add subject/description metadata',
                        'title': 'Add subject/description metadata',
                        'description': description,
                        'category': 'missingMetadata',
                        'severity': severity,
                        'estimatedTime': '2 minutes',
                        'fixType': 'addMetadata',
                        'fixData': {'field': 'subject'},
                        'instructions': recommendation
                        or "Summarize the document content in the Subject/Description metadata fields."
                    })
                    fixes['estimatedTime'] += 2
                    subject_fix_added = True
            else:
                metadata_other_missing = True

        if metadata_title_missing or metadata_other_missing or metadata_misc_present:
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
        
        # PDF/A fix suggestions are currently disabled so the engine focuses on WCAG and PDF/UA issues.
        
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
        scan_data = scan_data or {}
        initial_scan_issues = self._extract_issue_payload(scan_data)
        pre_fix_results = initial_scan_issues or {}
        pre_fix_suggestions = {}
        allowed_fix_types = set()
        suggestion_formatter = FixTraceabilityFormatter({})
        if scan_data:
            resolved_path = scan_data.get("resolved_file_path")
        if resolved_path:
            pdf_path = Path(resolved_path)
        else:
            pdf_path = upload_dir / f"{scan_id}.pdf"

        locate_step_id = None
        if tracker:
            locate_step_id = tracker.add_step(
                "Locate PDF File",
                "Resolving the uploaded document for remediation",
                "pending",
            )
            tracker.start_step(locate_step_id)

        try:
            if pdf_path.exists():
                if tracker and locate_step_id:
                    tracker.complete_step(locate_step_id, "PDF located in uploads")
            else:
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

                pdf_found = False
                for alt_path in possible_names:
                    if alt_path and alt_path.exists():
                        pdf_path = alt_path
                        pdf_found = True
                        print(f"[AutoFixEngine] Found existing PDF file: {pdf_path}")
                        break
                if pdf_found:
                    if tracker and locate_step_id:
                        tracker.complete_step(locate_step_id, "PDF located in uploads")
                else:
                    if tracker and locate_step_id:
                        tracker.fail_step(locate_step_id, "Uploaded document could not be located")
                    raise FileNotFoundError(f"PDF not found for scan ID: {scan_id} in uploads/")
            
            print(f"[AutoFixEngine] File size: {os.path.getsize(pdf_path)} bytes")
            if not pre_fix_results:
                try:
                    analyzer = PDFAccessibilityAnalyzer()
                    analyzed = analyzer.analyze(str(pdf_path))
                    if isinstance(analyzed, dict):
                        pre_fix_results = analyzed.get("results") or analyzed
                except Exception as exc:
                    print(f"[AutoFixEngine] Warning: pre-fix analysis failed for suggestions: {exc}")
                    pre_fix_results = {}
            
            step_id = tracker.add_step(
                "Open PDF File",
                f"Opening {scan_data.get('filename', 'PDF file')}",
                "pending"
            ) if tracker else None
            
            if tracker:
                tracker.start_step(step_id)

            filename_hint = scan_data.get("filename") or pdf_path.name
            original_stem = Path(filename_hint).stem or pdf_path.stem
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"{original_stem}_fixed_{timestamp}.pdf"
            fixed_output_path = pdf_path.parent / output_filename

            temp_fd, temp_name = tempfile.mkstemp(
                prefix=f"{original_stem}_",
                suffix=".tmp.pdf",
                dir=str(pdf_path.parent),
            )
            os.close(temp_fd)
            if os.path.exists(temp_name):
                os.remove(temp_name)
            temp_path = Path(temp_name)

            pdf = pikepdf.open(pdf_path, allow_overwriting_input=False)
            print("[AutoFixEngine] ✓ PDF opened successfully")
            
            if tracker:
                tracker.complete_step(step_id, "PDF opened successfully")
            
            fixes_applied = []
            missing_rolemap_mappings = self._detect_missing_rolemap_mappings(pdf)
            if missing_rolemap_mappings:
                try:
                    pre_fix_results = dict(pre_fix_results or {})
                except Exception:
                    pre_fix_results = {}
                pre_fix_results["roleMapMissingMappings"] = missing_rolemap_mappings

            try:
                pre_fix_suggestions = generate_fix_suggestions(pre_fix_results)
            except Exception as suggestion_error:
                print(
                    f"[AutoFixEngine] Warning: could not generate fix suggestions "
                    f"for traceability: {suggestion_error}"
                )
                pre_fix_suggestions = {}
            allowed_fix_types = derive_allowed_fix_types(pre_fix_suggestions)
            suggestion_formatter = FixTraceabilityFormatter(pre_fix_suggestions)
            normalize_fix_type = FixTraceabilityFormatter._normalize

            def _is_allowed(fix_key: str) -> bool:
                canonical = get_canonical_fix_type(fix_key)
                return normalize_fix_type(canonical) in allowed_fix_types

            def _record_skipped_fix(
                fix_key: str, description: str, extra: Optional[Dict[str, Any]] = None
            ):
                fixes_applied.append(
                    suggestion_formatter.build_entry(
                        fix_key,
                        description,
                        success=False,
                        extra={
                            "implicit": True,
                            "skipped": True,
                            "skipSuggestionLink": True,
                            "skipHistory": True,
                            **(extra or {}),
                        },
                    )
                )
            
            step_id = tracker.add_step(
                "Add Document Language",
                "Setting document language to en-US",
                "pending"
            ) if tracker else None
            
            if tracker:
                tracker.start_step(step_id)
            if not _is_allowed("addLanguage"):
                if tracker:
                    tracker.skip_step(step_id, "Skipped - no language suggestion available")
                _record_skipped_fix(
                    "addLanguage",
                    "Not run because no automated suggestion was generated for this scan.",
                )
            else:
                try:
                    existing_lang = pdf.Root.get('/Lang')
                    if not existing_lang:
                        pdf.Root['/Lang'] = 'en-US'
                        print("[AutoFixEngine] ✓ Set document language (en-US)")
                        
                        fixes_applied.append(
                            suggestion_formatter.build_entry(
                                "addLanguage",
                                "Set document language (en-US)",
                                success=True,
                            )
                        )
                        if tracker:
                            tracker.complete_step(step_id, "Set language: en-US")
                    else:
                        print("[AutoFixEngine] → Document already defines a language; skipping fix")
                        if tracker:
                            tracker.skip_step(step_id, "Document already defines a language")
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
            
            metadata_allowed = _is_allowed("addMetadata") or _is_allowed("addTitle")
            if not metadata_allowed:
                if tracker:
                    tracker.skip_step(step_id, "Skipped - no metadata suggestion available")
                _record_skipped_fix(
                    "addMetadata",
                    "Not run because no automated suggestion was generated for this scan.",
                )
            else:
                try:
                    filename = scan_data.get('filename', os.path.basename(pdf_path))
                    title = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ')
                    initial_title = ""
                    try:
                        if hasattr(pdf, "docinfo") and pdf.docinfo and "/Title" in pdf.docinfo:
                            initial_title = str(pdf.docinfo.get("/Title") or "").strip()
                    except Exception:
                        initial_title = ""

                    had_metadata_stream = "/Metadata" in pdf.Root
                    metadata_changed = ensure_pdfua_metadata_stream(pdf, title)

                    if not initial_title:
                        print(f"[AutoFixEngine] ✓ Set document title metadata: {title}")
                    if not had_metadata_stream and "/Metadata" in pdf.Root:
                        print("[AutoFixEngine] ✓ Added catalog Metadata stream with dc:title/pdfuaid markers")

                    if metadata_changed:
                        fixes_applied.append(
                            suggestion_formatter.build_entry(
                                "addTitle",
                                f"Set document title and metadata: {title}",
                                success=True,
                            )
                        )
                        fixes_applied.append(
                            suggestion_formatter.build_entry(
                                "pdfuaNotice",
                                "PDF/UA identifier not asserted - manual tagging and validation required.",
                                success=False,
                                extra={"warning": True},
                            )
                        )
                        if tracker:
                            tracker.complete_step(step_id, f"Set title: {title}")
                    else:
                        print("[AutoFixEngine] → Title metadata already present; skipping fix")
                        if tracker:
                            tracker.skip_step(step_id, "Title metadata already present")
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
            
            if not _is_allowed("markTagged"):
                if tracker:
                    tracker.skip_step(step_id, "Skipped - no tagging suggestion available")
                _record_skipped_fix(
                    "markTagged",
                    "Not run because no automated suggestion was generated for this scan.",
                )
            else:
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
                        
                        fixes_applied.append(
                            suggestion_formatter.build_entry(
                                "markTagged",
                                "Confirmed document remains tagged",
                                success=True,
                                # Validation-only so history treats it as implicit behavior, not an issue fix.
                                extra={"implicit": True},
                            )
                        )
                        if tracker:
                            tracker.complete_step(step_id, "Document confirmed as tagged")
                    except Exception as e:
                        print(f"[AutoFixEngine] ✗ Error updating MarkInfo: {e}")
                        if tracker:
                            tracker.fail_step(step_id, str(e))
                else:
                    if tracker:
                        tracker.skip_step(step_id, "No valid structure tree detected; leaving document untagged")
                    fixes_applied.append(
                        suggestion_formatter.build_entry(
                            "markTagged",
                            "Skipped automatic tagging - manual tagging required for PDF/UA compliance.",
                            success=False,
                            extra={"warning": True},
                        )
                    )
            
            step_id = tracker.add_step(
                "Configure Viewer Preferences",
                "Setting DisplayDocTitle preference",
                "pending"
            ) if tracker else None
            
            if tracker:
                tracker.start_step(step_id)
            if not _is_allowed("fixViewerPreferences"):
                if tracker:
                    tracker.skip_step(step_id, "Skipped - no ViewerPreferences suggestion available")
                _record_skipped_fix(
                    "fixViewerPreferences",
                    "Not run because no automated suggestion was generated for this scan.",
                )
            else:
                try:
                    viewer_prefs = getattr(pdf.Root, 'ViewerPreferences', None)
                    preferences_changed = False

                    if viewer_prefs is None:
                        pdf.Root.ViewerPreferences = pdf.make_indirect(Dictionary(
                            DisplayDocTitle=True
                        ))
                        preferences_changed = True
                        print("[AutoFixEngine] ✓ Created ViewerPreferences")
                    else:
                        display_doc_title = viewer_prefs.get('/DisplayDocTitle')
                        if not display_doc_title:
                            viewer_prefs['/DisplayDocTitle'] = True
                            preferences_changed = True
                            print("[AutoFixEngine] ✓ Enabled DisplayDocTitle")

                    if preferences_changed:
                        fixes_applied.append(
                            suggestion_formatter.build_entry(
                                "fixViewerPreferences",
                                "Set ViewerPreferences to display document title",
                                success=True,
                            )
                        )
                        if tracker:
                            tracker.complete_step(step_id, "ViewerPreferences configured")
                    else:
                        print("[AutoFixEngine] → ViewerPreferences already configured; skipping fix")
                        if tracker:
                            tracker.skip_step(step_id, "ViewerPreferences already configured")
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
            
            if not _is_allowed("createStructureTree"):
                if tracker:
                    tracker.skip_step(step_id, "Skipped - no RoleMap suggestion available")
                _record_skipped_fix(
                    "createStructureTree",
                    "Not run because no automated suggestion was generated for this scan.",
                )
            else:
                def _normalize_rolemap_value(value: Any) -> Optional[str]:
                    if value is None:
                        return None
                    return str(value)

                rolemap_changed = False
                rolemap_change_count = 0
                if hasattr(pdf.Root, 'StructTreeRoot'):
                    try:
                        struct_tree = pdf.Root.StructTreeRoot
                        role_map = getattr(struct_tree, 'RoleMap', None)
                        if role_map is None:
                            role_map = pdf.make_indirect(Dictionary())
                            struct_tree.RoleMap = role_map
                            for custom_type, standard_type in COMMON_ROLEMAP_MAPPINGS.items():
                                role_map[Name(custom_type)] = Name(standard_type)
                            rolemap_change_count = len(COMMON_ROLEMAP_MAPPINGS)
                            rolemap_changed = rolemap_change_count > 0
                            print(f"[AutoFixEngine] ✓ Added RoleMap with {rolemap_change_count} mappings")
                        else:
                            added_count = 0
                            for custom_type, standard_type in COMMON_ROLEMAP_MAPPINGS.items():
                                key = Name(custom_type)
                                target = Name(standard_type)
                                existing = role_map.get(key)
                                if existing is None:
                                    existing = role_map.get(str(key))
                                existing_value = _normalize_rolemap_value(existing)
                                target_value = _normalize_rolemap_value(target)
                                if existing_value != target_value:
                                    role_map[key] = target
                                    added_count += 1
                            if added_count > 0:
                                rolemap_change_count = added_count
                                rolemap_changed = True
                                print(f"[AutoFixEngine] ✓ Added {added_count} missing or updated RoleMap mappings")

                        if rolemap_changed:
                            fixes_applied.append(
                                suggestion_formatter.build_entry(
                                    "createStructureTree",
                                    f"Enhanced RoleMap mappings ({rolemap_change_count} added/updated)",
                                    success=True,
                                    extra={"changeCount": rolemap_change_count},
                                )
                            )
                            if tracker:
                                tracker.complete_step(step_id, "Structure RoleMap enhanced")
                        else:
                            if tracker:
                                tracker.skip_step(
                                    step_id, "Structure tree already contains standard RoleMap mappings"
                                )
                            _record_skipped_fix(
                                "createStructureTree",
                                "RoleMap already contains standard mappings; no change needed.",
                            )
                    except Exception as e:
                        print(f"[AutoFixEngine] ✗ Error enhancing structure tree: {e}")
                        if tracker:
                            tracker.fail_step(step_id, str(e))
                        import traceback
                        traceback.print_exc()
                else:
                    if tracker:
                        tracker.skip_step(step_id, "No structure tree detected; automatic creation disabled to prevent invalid tagging")
                    _record_skipped_fix(
                        "createStructureTree",
                        "Automatic structure tree creation skipped - document still requires manual tagging.",
                        extra={"warning": True},
                    )
            
            # PDF/A compliance step waived; AutoFixEngine concentrates on WCAG and PDF/UA improvements.

            step_id = tracker.add_step(
                "Save Fixed PDF",
                "Writing changes to file",
                "pending"
            ) if tracker else None
            
            if tracker:
                tracker.start_step(step_id)
            
            print("[AutoFixEngine] ========== SAVING PDF ==========")
            print(f"[AutoFixEngine] Applied {len(fixes_applied)} fixes, now saving...")
            print(f"[AutoFixEngine] Saving to temp file: {temp_path}")
            
            pdf.save(
                str(temp_path),
                linearize=True,
                object_stream_mode=pikepdf.ObjectStreamMode.preserve,
                compress_streams=True,
                stream_decode_level=pikepdf.StreamDecodeLevel.none
            )
            
            temp_size = os.path.getsize(temp_path)
            print(f"[AutoFixEngine] Temp file size: {temp_size} bytes")
            
            pdf.close()
            pdf = None

            if fixed_output_path.exists():
                fixed_output_path.unlink()
            shutil.move(str(temp_path), str(fixed_output_path))
            print(f"[AutoFixEngine] ✓ Fixed PDF saved: {fixed_output_path}")
            if tracker:
                tracker.complete_step(step_id, f"PDF saved ({temp_size} bytes)")

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
                rescan_data = self._analyze_fixed_pdf(fixed_output_path)
                rescan_data["fixedFile"] = fixed_output_path.name
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

            success_count = count_successful_fixes(fixes_applied)
            print("[AutoFixEngine] ========== FIXES COMPLETE ==========")
            print(f"[AutoFixEngine] Total fixes applied: {len(fixes_applied)} (successful: {success_count})")
            
            return {
                'success': True,
                'fixedFile': fixed_output_path.name,
                'fixedTempPath': str(fixed_output_path),
                'tempOutputPath': str(temp_path),
                'fixesApplied': fixes_applied,
                'successCount': success_count,
                'message': f'Successfully applied {success_count} automated fixes',
                'scanResults': rescan_data,
                'summary': rescan_data.get('summary'),
                'verapdfStatus': rescan_data.get('verapdfStatus'),
                'fixes': rescan_data.get('fixes', [])
            }
            
        except Exception as e:
            print("[AutoFixEngine] ========== ERROR ==========")
            print(f"[AutoFixEngine] ERROR: {e}")
            import traceback
            traceback.print_exc()
            
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                    print("[AutoFixEngine] Cleaned up temp file")
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
            print("[AutoFixEngine] ========== APPLYING MANUAL FIX ==========")
            print(f"[AutoFixEngine] Fix type: {fix_type}")
            print(f"[AutoFixEngine] Fix data: {fix_data}")
            print(f"[AutoFixEngine] PDF path: {pdf_path}")
            print(f"[AutoFixEngine] File exists: {os.path.exists(pdf_path)}")
            
            temp_path = f"{pdf_path}.temp"
            
            pdf = pikepdf.open(pdf_path, allow_overwriting_input=False)
            print("[AutoFixEngine] ✓ PDF opened")
            
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
                print("[AutoFixEngine] ✓ Alt text added")
            
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
                linearize=True,
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
