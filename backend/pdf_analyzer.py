"""
PDF Accessibility Analyzer Module
Real implementation using PyPDF2 and pdfplumber
Enhanced with PDF-Extract-Kit integration
"""

import json
import logging
from typing import Dict, List, Any, Optional
import PyPDF2
import pdfplumber
# from pathlib import Path

try:
    from backend.pdf_extract_kit_processor import get_pdf_extract_kit
    PDF_EXTRACT_KIT_AVAILABLE = True
except ImportError:
    PDF_EXTRACT_KIT_AVAILABLE = False
    print("[Analyzer] PDF-Extract-Kit processor not available")

try:
    from backend.wcag_validator import WCAGValidator
    WCAG_VALIDATOR_AVAILABLE = True
except ImportError:
    WCAG_VALIDATOR_AVAILABLE = False
    print("[Analyzer] WCAG validator not available")

try:
    from backend.pdfa_validator import validate_pdfa
    import pikepdf
    PDFA_VALIDATOR_AVAILABLE = True
except ImportError:
    PDFA_VALIDATOR_AVAILABLE = False
    print("[Analyzer] PDF/A validator not available")


logger = logging.getLogger("pdf-accessibility-analyzer")


class PDFAccessibilityAnalyzer:
    """
    Analyzes PDF documents for accessibility compliance.
    Checks for WCAG 2.1 compliance across multiple dimensions.
    Uses PDF-Extract-Kit when available for enhanced analysis.
    Includes built-in WCAG 2.1 and PDF/UA-1 validation
    """

    def __init__(self):
        self.issues = {
            "missingMetadata": [],
            "untaggedContent": [],
            "missingAltText": [],
            "poorContrast": [],
            "missingLanguage": [],
            "formIssues": [],
            "tableIssues": [],
            "structureIssues": [],
            "readingOrderIssues": [],
            "wcagIssues": [],
            "pdfuaIssues": [],
            "pdfaIssues": [],
        }
        
        self.pdf_extract_kit = None
        if PDF_EXTRACT_KIT_AVAILABLE:
            try:
                self.pdf_extract_kit = get_pdf_extract_kit()
                if self.pdf_extract_kit.is_available():
                    print("[Analyzer] PDF-Extract-Kit integration enabled")
            except Exception as e:
                print(f"[Analyzer] Could not initialize PDF-Extract-Kit: {e}")
        
        self.wcag_validator = None
        if WCAG_VALIDATOR_AVAILABLE:
            try:
                print("[Analyzer] ✓ Built-in WCAG 2.1 and PDF/UA-1 validator enabled")
                self.wcag_validator_available = True
            except Exception as e:
                print(f"[Analyzer] Could not initialize WCAG validator: {e}")
                self.wcag_validator_available = False
        else:
            self.wcag_validator_available = False

    def analyze(self, pdf_path: str) -> Dict[str, Any]:
        """
        Perform comprehensive accessibility analysis on a PDF.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing all identified accessibility issues
        """
        print(f"[Analyzer] Starting analysis of {pdf_path}")
        
        try:
            if self.pdf_extract_kit and self.pdf_extract_kit.is_available():
                print("[Analyzer] Using PDF-Extract-Kit for enhanced analysis")
                self._analyze_with_pdf_extract_kit(pdf_path)
            else:
                print("[Analyzer] Using standard analysis methods")
            
            self._analyze_with_pypdf2(pdf_path)
            self._analyze_with_pdfplumber(pdf_path)
            
            if self.wcag_validator_available:
                print("[Analyzer] Running built-in WCAG 2.1 and PDF/UA-1 validation")
                self._analyze_with_wcag_validator(pdf_path)
            
            if PDFA_VALIDATOR_AVAILABLE:
                print("[Analyzer] Running PDF/A validation")
                self._analyze_with_pdfa_validator(pdf_path)
            
            total_issues = sum(len(v) for v in self.issues.values())
            print(f"[Analyzer] Analysis complete, found {total_issues} issues")
            
        except Exception as e:
            print(f"[Analyzer] Error during analysis: {e}")
            import traceback
            traceback_text = traceback.format_exc()
            print(traceback_text)
            self._use_simulated_analysis(
                context="PDFAccessibilityAnalyzer.analyze",
                error=e,
                traceback_text=traceback_text,
            )
        
        return self.issues

    def _analyze_with_pdf_extract_kit(self, pdf_path: str):
        """Analyze PDF using PDF-Extract-Kit for advanced accessibility checks"""
        try:
            # Get advanced accessibility analysis
            advanced_issues = self.pdf_extract_kit.analyze_accessibility(pdf_path)
            
            # Merge structure issues
            if advanced_issues.get("structure"):
                self.issues["structureIssues"].extend(advanced_issues["structure"])
            
            # Merge table issues (more detailed than pdfplumber)
            if advanced_issues.get("tables"):
                # Clear basic table issues and use advanced ones
                self.issues["tableIssues"] = advanced_issues["tables"]
            
            # Merge image issues (more accurate alt text detection)
            if advanced_issues.get("images"):
                self.issues["missingAltText"] = advanced_issues["images"]
            
            # Merge form issues (better label detection)
            if advanced_issues.get("forms"):
                self.issues["formIssues"] = advanced_issues["forms"]
            
            # Add reading order issues
            if advanced_issues.get("reading_order"):
                self.issues["readingOrderIssues"].extend(advanced_issues["reading_order"])
            
            print(f"[Analyzer] PDF-Extract-Kit found {sum(len(v) for v in advanced_issues.values())} advanced issues")
            
        except Exception as e:
            print(f"[Analyzer] Error in PDF-Extract-Kit analysis: {e}")
            import traceback
            traceback.print_exc()

    def _analyze_with_pypdf2(self, pdf_path: str):
        """Analyze PDF using PyPDF2 for metadata and structure"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                
                # Check metadata
                metadata = pdf_reader.metadata
                
                if not metadata or not metadata.get('/Title'):
                    self.issues["missingMetadata"].append({
                        "severity": "high",
                        "description": "PDF is missing document title in metadata",
                        "page": 1,
                        "recommendation": "Add document title in PDF properties using File > Properties > Description",
                    })
                
                if not metadata or not metadata.get('/Author'):
                    self.issues["missingMetadata"].append({
                        "severity": "medium",
                        "description": "PDF is missing author information",
                        "page": 1,
                        "recommendation": "Add author name in PDF metadata for better document identification",
                    })
                
                if not metadata or not metadata.get('/Subject'):
                    self.issues["missingMetadata"].append({
                        "severity": "low",
                        "description": "PDF is missing subject/description",
                        "page": 1,
                        "recommendation": "Add a brief description of the document content",
                    })
                
                # Check for language specification
                catalog = pdf_reader.trailer.get("/Root", {})
                if isinstance(catalog, PyPDF2.generic.IndirectObject):
                    catalog = catalog.get_object()
                
                lang = catalog.get("/Lang") if isinstance(catalog, dict) else None
                
                if not lang:
                    self.issues["missingLanguage"].append({
                        "severity": "medium",
                        "description": "PDF does not specify document language",
                        "page": 1,
                        "recommendation": "Set the document language in PDF properties (e.g., 'en-US' for English)",
                    })
                
                # Check if PDF is tagged
                mark_info = catalog.get("/MarkInfo") if isinstance(catalog, dict) else None
                is_tagged = False
                
                if mark_info:
                    if isinstance(mark_info, PyPDF2.generic.IndirectObject):
                        mark_info = mark_info.get_object()
                    is_tagged = mark_info.get("/Marked", False) if isinstance(mark_info, dict) else False
                
                if not is_tagged:
                    self.issues["untaggedContent"].append({
                        "severity": "high",
                        "description": "PDF is not tagged for accessibility - content structure is not defined",
                        "pages": list(range(1, len(pdf_reader.pages) + 1)),
                        "recommendation": "Use Adobe Acrobat Pro or similar tool to add tags and define document structure",
                    })
                
                print(f"[Analyzer] PyPDF2 analysis: {len(pdf_reader.pages)} pages, tagged: {is_tagged}, lang: {lang}")
                
        except Exception as e:
            print(f"[Analyzer] Error in PyPDF2 analysis: {e}")

    def _analyze_with_pdfplumber(self, pdf_path: str):
        """Analyze PDF using pdfplumber for content analysis"""
        try:
            tables_reviewed = False
            try:
                with open(pdf_path, 'rb') as file:
                    import PyPDF2
                    pdf_reader = PyPDF2.PdfReader(file)
                    
                    # Check if document is tagged and has table structures
                    catalog = pdf_reader.trailer.get("/Root", {})
                    if isinstance(catalog, PyPDF2.generic.IndirectObject):
                        catalog = catalog.get_object()
                    
                    # Check MarkInfo
                    mark_info = catalog.get("/MarkInfo") if isinstance(catalog, dict) else None
                    is_tagged = False
                    if mark_info:
                        if isinstance(mark_info, PyPDF2.generic.IndirectObject):
                            mark_info = mark_info.get_object()
                        is_tagged = mark_info.get("/Marked", False) if isinstance(mark_info, dict) else False
                    
                    # Check for StructTreeRoot (indicates structure tags exist)
                    has_struct_tree = catalog.get("/StructTreeRoot") if isinstance(catalog, dict) else None
                    
                    # If document is tagged and has structure tree, consider tables reviewed
                    if is_tagged and has_struct_tree:
                        tables_reviewed = True
                        print("[Analyzer] Document has structure tags - tables marked as reviewed")
            except Exception as e:
                print(f"[Analyzer] Could not check table review status: {e}")
            
            with pdfplumber.open(pdf_path) as pdf:
                total_images = 0
                total_tables = 0
                pages_with_images = []
                pages_with_tables = []
                total_form_fields = 0
                
                for page_num, page in enumerate(pdf.pages, start=1):
                    # Check for images
                    images = page.images
                    if images and len(images) > 0:
                        total_images += len(images)
                        pages_with_images.append(page_num)
                    
                    # Check for tables
                    tables = page.find_tables()
                    if tables and len(tables) > 0:
                        total_tables += len(tables)
                        pages_with_tables.append(page_num)
                    
                    # Check for form fields
                    if hasattr(page, 'annots') and page.annots:
                        total_form_fields += len(page.annots)
                
                if not self.issues["missingAltText"] and total_images > 0:
                    self.issues["missingAltText"].append({
                        "severity": "high",
                        "description": f"Found {total_images} image(s) that may lack alternative text descriptions",
                        "count": total_images,
                        "pages": pages_with_images[:10],
                        "recommendation": "Add descriptive alt text to all images using a PDF editor.",
                    })
                
                if not self.issues["tableIssues"] and total_tables > 0 and not tables_reviewed:
                    self.issues["tableIssues"].append({
                        "severity": "high",
                        "description": f"Found {total_tables} table(s) that may lack proper header markup",
                        "count": total_tables,
                        "pages": pages_with_tables[:10],
                        "recommendation": "Ensure all tables have properly marked header rows and columns.",
                    })
                elif tables_reviewed and total_tables > 0:
                    print(f"[Analyzer] Skipping {total_tables} table(s) - already reviewed and structured")
                
                if not self.issues["formIssues"] and total_form_fields > 0:
                    self.issues["formIssues"].append({
                        "severity": "high",
                        "description": f"Found {total_form_fields} form annotation(s) that may lack proper labels",
                        "count": total_form_fields,
                        "pages": pages_with_images[:10],
                        "recommendation": "Ensure all form fields have associated labels and tooltips.",
                    })
                
                if total_images > 0:
                    self.issues["poorContrast"].append({
                        "severity": "medium",
                        "description": "Document contains images - text contrast should be manually verified",
                        "count": total_images,
                        "pages": pages_with_images[:5],
                        "recommendation": "Manually check that all text has sufficient contrast ratio (4.5:1 for normal text)",
                    })
                
                print(f"[Analyzer] pdfplumber analysis: {total_images} images, {total_tables} tables, {total_form_fields} form fields")
                
        except Exception as e:
            print(f"[Analyzer] Error in pdfplumber analysis: {e}")

    def _use_simulated_analysis(
        self,
        context: Optional[str] = None,
        error: Optional[BaseException] = None,
        traceback_text: Optional[str] = None,
    ):
        """Fallback simulated analysis for demonstration"""
        debug_payload = {
            "context": context or "unknown",
        }
        if error:
            debug_payload["error"] = repr(error)
            debug_payload["errorType"] = error.__class__.__name__
        if traceback_text:
            debug_payload["traceback"] = traceback_text.strip()

        logger.error(
            "[Analyzer] Falling back after failure: %s",
            json.dumps(debug_payload, ensure_ascii=False),
        )
        print("[Analyzer] Returning partial analysis results due to failure")

        populated_categories = {
            key: len(value)
            for key, value in self.issues.items()
            if isinstance(value, list) and value
        }

        if populated_categories:
            logger.warning(
                "[Analyzer] Partial analysis available; populated categories: %s",
                json.dumps(populated_categories, ensure_ascii=False),
            )
        else:
            logger.warning(
                "[Analyzer] No analyzer results were produced before the failure"
            )

        # Simulated issues disabled to ensure consumers only see real findings.
        # self.issues["missingMetadata"].append({...})

    def calculate_compliance_score(self) -> int:
        """Calculate overall accessibility compliance score (0-100)"""
        try:
            total_issues = sum(len(v) for v in self.issues.values())
            
            if total_issues == 0:
                return 100
            
            high_severity = sum(
                len([i for i in v if isinstance(i, dict) and i.get("severity") == "high"])
                for v in self.issues.values()
            )
            medium_severity = sum(
                len([i for i in v if isinstance(i, dict) and i.get("severity") == "medium"])
                for v in self.issues.values()
            )
            low_severity = total_issues - high_severity - medium_severity

            score = 100 - (high_severity * 15) - (medium_severity * 5) - (low_severity * 2)
            return max(0, min(100, score))
        except Exception as e:
            print(f"[Analyzer] Error calculating score: {e}")
            return 50

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of the analysis"""
        try:
            total_issues = sum(len(v) for v in self.issues.values())
            high_severity = sum(
                len([i for i in v if isinstance(i, dict) and i.get("severity") == "high"])
                for v in self.issues.values()
            )
            medium_severity = sum(
                len([i for i in v if isinstance(i, dict) and i.get("severity") == "medium"])
                for v in self.issues.values()
            )

            return {
                "totalIssues": total_issues,
                "highSeverity": high_severity,
                "mediumSeverity": medium_severity,
                "complianceScore": self.calculate_compliance_score(),
            }
        except Exception as e:
            print(f"[Analyzer] Error getting summary: {e}")
            return {
                "totalIssues": 0,
                "highSeverity": 0,
                "mediumSeverity": 0,
                "complianceScore": 50,
            }

    @staticmethod
    def calculate_summary(results: Dict[str, List], verapdf_status: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Calculate summary statistics from analysis results.
        Used when loading historical scans from database.
        
        Args:
            results: Dictionary of accessibility issues by category
            verapdf_status: Optional veraPDF-style compliance data
            
        Returns:
            Summary statistics including total issues, severity counts, and compliance score
        """
        try:
            total_issues = sum(len(v) for v in results.values())
            
            high_severity = sum(
                len([i for i in v if isinstance(i, dict) and i.get("severity") == "high"])
                for v in results.values()
            )
            medium_severity = sum(
                len([i for i in v if isinstance(i, dict) and i.get("severity") == "medium"])
                for v in results.values()
            )
            low_severity = total_issues - high_severity - medium_severity

            # Calculate compliance score
            if total_issues == 0:
                compliance_score = 100
            else:
                compliance_score = 100 - (high_severity * 15) - (medium_severity * 5) - (low_severity * 2)
                compliance_score = max(0, min(100, compliance_score))

            summary = {
                "totalIssues": total_issues,
                "highSeverity": high_severity,
                "mediumSeverity": medium_severity,
                "complianceScore": compliance_score,
            }

            if isinstance(verapdf_status, dict):
                summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
                summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))

            return summary
        except Exception as e:
            print(f"[Analyzer] Error calculating summary from results: {e}")
            return {
                "totalIssues": 0,
                "highSeverity": 0,
                "mediumSeverity": 0,
                "complianceScore": 50,
            }

    def _analyze_with_wcag_validator(self, pdf_path: str):
        """Analyze PDF using built-in WCAG 2.1 and PDF/UA-1 validator"""
        try:
            print("[Analyzer] ========== WCAG VALIDATOR ANALYSIS ==========")
            print(f"[Analyzer] Analyzing: {pdf_path}")
            
            validator = WCAGValidator(pdf_path)
            validation_results = validator.validate()
            
            print(f"[Analyzer] Validation complete. Results keys: {list(validation_results.keys())}")
            
            # Merge WCAG issues
            if validation_results.get("wcagIssues"):
                wcag_count = len(validation_results["wcagIssues"])
                self.issues["wcagIssues"].extend(validation_results["wcagIssues"])
                print(f"[Analyzer] ✓ WCAG Validator found {wcag_count} WCAG 2.1 issues")
                for i, issue in enumerate(validation_results["wcagIssues"][:3]):
                    print(f"[Analyzer]   Issue {i+1}: {issue.get('criterion', 'N/A')} - {issue.get('description', 'N/A')[:80]}")
            
            # Merge PDF/UA issues
            if validation_results.get("pdfuaIssues"):
                pdfua_count = len(validation_results["pdfuaIssues"])
                self.issues["pdfuaIssues"].extend(validation_results["pdfuaIssues"])
                print(f"[Analyzer] ✓ WCAG Validator found {pdfua_count} PDF/UA-1 issues")
                for i, issue in enumerate(validation_results["pdfuaIssues"][:3]):
                    print(f"[Analyzer]   Issue {i+1}: {issue.get('clause', 'N/A')} - {issue.get('description', 'N/A')[:80]}")
            
            # Get compliance summary
            wcag_score = validation_results.get('wcagScore', 0)
            pdfua_score = validation_results.get('pdfuaScore', 0)
            wcag_compliance = validation_results.get('wcagCompliance', {})
            
            print("[Analyzer] ========== COMPLIANCE SCORES ==========")
            print(f"[Analyzer] WCAG 2.1 Compliance Score: {wcag_score}%")
            print(f"[Analyzer] PDF/UA-1 Compliance Score: {pdfua_score}%")
            print("[Analyzer] WCAG Levels:")
            print(f"[Analyzer]   Level A:   {'✓ PASS' if wcag_compliance.get('A', False) else '✗ FAIL'}")
            print(f"[Analyzer]   Level AA:  {'✓ PASS' if wcag_compliance.get('AA', False) else '✗ FAIL'}")
            print(f"[Analyzer]   Level AAA: {'✓ PASS' if wcag_compliance.get('AAA', False) else '✗ FAIL'}")
            print("[Analyzer] ========================================")
            
        except Exception as e:
            print("[Analyzer] ========== ERROR IN WCAG VALIDATION ==========")
            print(f"[Analyzer] Error: {e}")
            import traceback
            traceback.print_exc()
            print("[Analyzer] ==========================================")

    def _analyze_with_pdfa_validator(self, pdf_path: str):
        """Analyze PDF using PDF/A validator based on veraPDF library approach"""
        try:
            print("[Analyzer] ========== PDF/A VALIDATOR ANALYSIS ==========")
            print(f"[Analyzer] Analyzing: {pdf_path}")
            
            with pikepdf.open(pdf_path) as pdf:
                validation_results = validate_pdfa(pdf)
            
            print("[Analyzer] PDF/A validation complete")
            print(f"[Analyzer] Conformance Level: {validation_results.get('conformanceLevel', 'None')}")
            print(f"[Analyzer] Valid: {validation_results.get('isValid', False)}")
            
            # Merge PDF/A issues
            if validation_results.get("issues"):
                pdfa_count = len(validation_results["issues"])
                self.issues["pdfaIssues"].extend(validation_results["issues"])
                print(f"[Analyzer] ✓ PDF/A Validator found {pdfa_count} issues")
                
                # Show summary by severity
                summary = validation_results.get('summary', {})
                print(f"[Analyzer]   Critical: {summary.get('critical', 0)}")
                print(f"[Analyzer]   Error: {summary.get('error', 0)}")
                print(f"[Analyzer]   Warning: {summary.get('warning', 0)}")
                
                # Show first few issues
                for i, issue in enumerate(validation_results["issues"][:3]):
                    severity = issue.get('severity', 'unknown')
                    message = issue.get('message', 'N/A')
                    print(f"[Analyzer]   Issue {i+1} [{severity.upper()}]: {message[:80]}")
            
            print("[Analyzer] ==========================================")
            
        except Exception as e:
            print("[Analyzer] ========== ERROR IN PDF/A VALIDATION ==========")
            print(f"[Analyzer] Error: {e}")
            import traceback
            traceback.print_exc()
            print("[Analyzer] ============================================")
