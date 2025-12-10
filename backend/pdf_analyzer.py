"""
PDF Accessibility Analyzer Module
Real implementation using PyPDF2 and pdfplumber
Enhanced with PDF-Extract-Kit integration
"""

import json
import logging
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple, Set
import PyPDF2
import pdfplumber

try:
    from PyPDF2.generic import ContentStream, TextStringObject, ByteStringObject
except Exception:
    ContentStream = None
    TextStringObject = None
    ByteStringObject = None

try:
    import pikepdf
    PIKEPDF_AVAILABLE = True
except ImportError:
    pikepdf = None
    PIKEPDF_AVAILABLE = False
    print("[Analyzer] pikepdf not available - structure-aware analysis disabled")
# from pathlib import Path

try:
    from backend.pdf_extract_kit_processor import get_pdf_extract_kit
    PDF_EXTRACT_KIT_AVAILABLE = True
except ImportError:
    PDF_EXTRACT_KIT_AVAILABLE = False
    print("[Analyzer] PDF-Extract-Kit processor not available")

try:
    from backend.wcag_validator import WCAGValidator, build_figure_alt_lookup, has_figure_alt_text
    WCAG_VALIDATOR_AVAILABLE = True
except ImportError:
    WCAG_VALIDATOR_AVAILABLE = False
    WCAGValidator = None
    build_figure_alt_lookup = None
    has_figure_alt_text = None
    print("[Analyzer] WCAG validator not available")

from backend.utils.compliance_scoring import derive_wcag_score
from backend.utils.issue_registry import IssueRegistry

# PDF/A validation is intentionally disabled; the analyzer now focuses on WCAG 2.1 and PDF/UA-1.


logger = logging.getLogger("pdf-accessibility-analyzer")


class PDFAccessibilityAnalyzer:
    """
    Analyzes PDF documents for accessibility compliance.
    Checks for WCAG 2.1 compliance across multiple dimensions.
    Uses PDF-Extract-Kit when available for enhanced analysis.
    Includes built-in WCAG 2.1 and PDF/UA-1 validation
    """

    # Penalties used when calculating the compliance score.
    # Contrast-related checks rely on light heuristics, so their weight is intentionally lower.
    _CRITERION_PENALTIES = {
        "1.4.3": 5,
        "1.4.6": 3,
    }
    _SEVERITY_PENALTIES = {
        "high": 15,
        "medium": 5,
        "low": 2,
        "info": 0,
    }
    _LOW_CONTRAST_PENALTY = 3

    def __init__(self):
        self.issue_registry = IssueRegistry()
        self._initialize_issue_buckets()
        self._contrast_manual_note_added = False
        self._low_contrast_issue_count = 0
        self._analysis_errors: List[str] = []
        self._analysis_error_details: List[Dict[str, Any]] = []
        self._wcag_validator_metrics: Optional[Dict[str, Any]] = None
        self._verapdf_alt_findings: List[Dict[str, Any]] = []
        self._tagging_state = {
            "is_tagged": None,
            "has_struct_tree": None,
            "tables_reviewed": None,
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

    def _initialize_issue_buckets(self) -> None:
        """Reset analyzer issue buckets for a fresh run."""
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
            "linkIssues": [],
            "pdfuaIssues": [],
            "pdfaIssues": [],
        }

    def _metadata_text(self, value: Any) -> Optional[str]:
        """Return a clean metadata string or None if value is invalid."""
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return None

    def _normalize_issue_pages(self, issue: Dict[str, Any]) -> List[int]:
        """Return a normalized pages list from 'page' or 'pages' fields."""
        pages: List[int] = []
        if not isinstance(issue, dict):
            return pages

        candidate_pages = issue.get("pages")
        if candidate_pages is None and issue.get("page") is not None:
            candidate_pages = [issue.get("page")]

        if isinstance(candidate_pages, (list, tuple, set)):
            for entry in candidate_pages:
                try:
                    pages.append(int(entry))
                except Exception:
                    continue
        elif candidate_pages is not None:
            try:
                pages.append(int(candidate_pages))
            except Exception:
                pass

        return sorted(set(pages))

    def _infer_metadata_field(self, description: Optional[str]) -> Optional[str]:
        """Best-effort detection of which metadata field is missing."""
        if not description:
            return None
        lowered = description.lower()
        if "title" in lowered:
            return "title"
        if "author" in lowered:
            return "author"
        if "subject" in lowered or "description" in lowered:
            return "subject"
        return None

    def _kind_from_wcag_criterion(self, criterion: Optional[str], description: str) -> str:
        """Map WCAG criterion to an internal category for canonical issues."""
        code = (criterion or "").strip()
        desc_lower = description.lower()
        if code == "3.1.1":
            return "language"
        if code in {"1.4.3", "1.4.6"}:
            return "contrast"
        if code == "1.1.1":
            return "alt-text"
        if code == "2.4.2":
            return "metadata"
        if code == "2.4.4":
            return "links"
        if code == "3.3.2":
            return "forms"
        if code == "1.3.2":
            return "reading-order"
        if code == "1.3.1":
            if "table" in desc_lower:
                return "table"
            return "structure"
        return "wcag"

    def _kind_from_pdfua_clause(self, clause: Optional[str], description: str) -> str:
        """Map PDF/UA clauses to internal categories."""
        clause_text = (clause or "").lower()
        desc_lower = description.lower()
        if "7.5" in clause_text:
            return "table"
        if "7.1" in clause_text and ("tag" in desc_lower or "tagged" in desc_lower):
            return "tagging"
        if "7.18" in clause_text:
            return "forms"
        return "pdfua"

    def _resolve_issue_kind(
        self,
        bucket: str,
        issue: Dict[str, Any],
        criterion: Optional[str],
        clause: Optional[str],
        description: str,
    ) -> str:
        """Return the canonical category for the issue."""
        bucket_defaults = {
            "missingLanguage": "language",
            "missingMetadata": "metadata",
            "missingAltText": "alt-text",
            "poorContrast": "contrast",
            "untaggedContent": "tagging",
            "tableIssues": "table",
            "formIssues": "forms",
            "linkIssues": "links",
            "structureIssues": "structure",
            "readingOrderIssues": "reading-order",
        }
        if bucket == "wcagIssues":
            return self._kind_from_wcag_criterion(criterion, description)
        if bucket == "pdfuaIssues":
            desc_lower = description.lower()
            if "metadata stream" in desc_lower or "dc:title" in desc_lower or "metadata" in desc_lower:
                return "metadata"
            return self._kind_from_pdfua_clause(clause, description)
        return bucket_defaults.get(bucket, bucket)

    def _issue_extra(
        self,
        bucket: str,
        issue: Dict[str, Any],
        criterion: Optional[str],
        clause: Optional[str],
        description: str,
    ) -> Optional[str]:
        """Build an 'extra' token to keep issueIds stable but collision-free."""
        desc_lower = description.lower()
        if criterion == "3.1.1" or bucket == "missingLanguage":
            if "invalid" in desc_lower:
                return "language-invalid"
            return "language-missing"

        if bucket == "untaggedContent" or (
            clause and "14289-1:7.1" in clause and "tag" in desc_lower
        ):
            return "untagged"

        if (
            bucket == "tableIssues"
            or (criterion == "1.3.1" and "table" in desc_lower)
            or (clause and "14289-1:7.5" in clause)
        ):
            label = issue.get("tableLabel") or issue.get("description")
            pages = self._normalize_issue_pages(issue)
            if label:
                return label
            if pages:
                return f"table-{pages[0]}"
            return "table"

        if bucket == "missingMetadata" or criterion == "2.4.2":
            field = self._infer_metadata_field(description)
            return field or "metadata"

        if bucket == "missingAltText" or criterion == "1.1.1":
            return (
                issue.get("context")
                or issue.get("imageIndex")
                or issue.get("location")
                or description
            )

        if bucket == "poorContrast" or criterion in {"1.4.3", "1.4.6"}:
            return issue.get("textSample") or description

        if issue.get("context"):
            return str(issue.get("context"))

        return None

    def _extract_issue_meta(self, issue: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Collect lightweight metadata for canonical issue references."""
        meta_keys = (
            "context",
            "location",
            "imageIndex",
            "count",
            "contrastRatio",
            "textSample",
            "advisoryCriteria",
        )
        meta: Dict[str, Any] = {}
        for key in meta_keys:
            if key in issue:
                meta[key] = issue[key]
        return meta or None

    def _register_issue_for_bucket(self, bucket: str, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Attach an issueId and register a canonical issue for the bucket entry."""
        if not isinstance(issue, dict):
            return issue

        criterion_defaults = {
            "missingLanguage": "3.1.1",
            "missingAltText": "1.1.1",
            "poorContrast": "1.4.3",
            "tableIssues": "1.3.1",
            "formIssues": "3.3.2",
            "linkIssues": "2.4.4",
            "structureIssues": "1.3.1",
            "readingOrderIssues": "1.3.2",
            "missingMetadata": "2.4.2",
        }
        clause_defaults = {
            "untaggedContent": "ISO 14289-1:7.1",
            "tableIssues": "ISO 14289-1:7.5",
        }

        criterion = str(issue.get("criterion") or criterion_defaults.get(bucket) or "").strip() or None
        clause = issue.get("clause") or clause_defaults.get(bucket)
        description = (
            str(issue.get("description") or issue.get("message") or bucket).strip()
        )
        pages = self._normalize_issue_pages(issue)
        if pages and "pages" not in issue:
            issue["pages"] = pages
        severity = issue.get("severity") or "medium"

        kind = self._resolve_issue_kind(bucket, issue, criterion, clause, description)
        extra = self._issue_extra(bucket, issue, criterion, clause, description)
        use_pages_in_id = True
        document_level_criteria = {"3.1.1", "2.4.2"}
        if criterion in document_level_criteria:
            use_pages_in_id = False
        if bucket in {"missingLanguage", "missingMetadata"}:
            use_pages_in_id = False
        if bucket == "untaggedContent" or (clause and "14289-1:7.1" in clause):
            use_pages_in_id = False

        canonical = self.issue_registry.register_issue(
            kind=kind,
            criterion=criterion,
            clause=clause,
            pages=pages,
            use_pages_in_id=use_pages_in_id,
            severity=severity,
            description=description,
            wcag_criteria=issue.get("wcagCriteria"),
            pdfua_clause=clause,
            raw_source=bucket,
            penalty_weight=issue.get("penaltyWeight"),
            meta=self._extract_issue_meta(issue),
            extra=extra,
        )
        advisory_codes = issue.get("advisoryCriteria")
        if isinstance(advisory_codes, (list, tuple)):
            canonical.setdefault("advisoryCriteria", [])
            for code in advisory_codes:
                normalized_code = str(code).strip()
                if not normalized_code:
                    continue
                if normalized_code not in canonical["advisoryCriteria"]:
                    canonical["advisoryCriteria"].append(normalized_code)
        issue["issueId"] = canonical["issueId"]
        return issue

    def _canonicalize_and_attach_issue_ids(self) -> Dict[str, Any]:
        """Return results with canonical issues and issueIds attached to buckets."""
        self.issue_registry.reset()
        results: Dict[str, Any] = {}
        for bucket, payload in self.issues.items():
            if not isinstance(payload, list):
                results[bucket] = payload
                continue

            bucket_items: List[Any] = []
            for entry in payload:
                if isinstance(entry, dict):
                    bucket_items.append(self._register_issue_for_bucket(bucket, entry))
                else:
                    bucket_items.append(entry)
            results[bucket] = bucket_items

        results["issues"] = self.issue_registry.issues
        return results

    def _collect_canonical_issues(self, results: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Collect canonical issues from registry or provided results."""
        if hasattr(self, "issue_registry") and getattr(self, "issue_registry", None):
            canonical = self.issue_registry.issues
            if canonical:
                return canonical

        if isinstance(results, dict):
            canonical_list = results.get("issues")
            if isinstance(canonical_list, list):
                return canonical_list

        collected: List[Dict[str, Any]] = []
        source = results if isinstance(results, dict) else self.issues
        if isinstance(source, dict):
            for key, items in source.items():
                if key == "issues" or not isinstance(items, list):
                    continue
                for entry in items:
                    if isinstance(entry, dict):
                        collected.append(entry)
        return collected

    def analyze(self, pdf_path: str) -> Dict[str, Any]:
        """
        Perform comprehensive accessibility analysis on a PDF.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing all identified accessibility issues
        """
        print(f"[Analyzer] Starting analysis of {pdf_path}")
        self._initialize_issue_buckets()
        self.issue_registry.reset()
        self._contrast_manual_note_added = False
        self._low_contrast_issue_count = 0
        self._analysis_errors = []
        self._analysis_error_details = []
        self._wcag_validator_metrics = None
        self._verapdf_alt_findings = []
        self._tagging_state = {
            "is_tagged": None,
            "has_struct_tree": None,
            "tables_reviewed": None,
        }
        
        try:
            if self.pdf_extract_kit and self.pdf_extract_kit.is_available():
                print("[Analyzer] Using PDF-Extract-Kit for enhanced analysis")
                self._analyze_with_pdf_extract_kit(pdf_path)
            else:
                print("[Analyzer] Using standard analysis methods")
            
            self._analyze_with_pypdf2(pdf_path)
            self._analyze_with_pdfplumber(pdf_path)
            self._analyze_contrast_basic(pdf_path)
            
            if self.wcag_validator_available:
                print("[Analyzer] Running built-in WCAG 2.1 and PDF/UA-1 validation")
                self._analyze_with_wcag_validator(pdf_path)
            
            # PDF/A validation is disabled to keep analytics focused on WCAG 2.1 and PDF/UA checks.
            
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
        
        self._consolidate_poor_contrast_issues()
        results = self._canonicalize_and_attach_issue_ids()
        self.issues = results
        canonical_count = len(results.get("issues", [])) if isinstance(results, dict) else 0
        print(f"[Analyzer] Analysis complete, found {canonical_count} canonical issues")
        return results

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
            self._record_analysis_error(e, fatal=False)

    def _analyze_with_pypdf2(self, pdf_path: str):
        """Analyze PDF using PyPDF2 for metadata and structure"""
        try:
            with open(pdf_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)

                if getattr(pdf_reader, "is_encrypted", False):
                    if not self._try_decrypt_reader(pdf_reader):
                        self._record_analysis_error(
                            RuntimeError("PDF is password protected"),
                            fatal=True,
                        )
                        return
                
                # Check metadata
                metadata = pdf_reader.metadata

                title = self._metadata_text(metadata.get('/Title')) if metadata else None
                if not title:
                    self.issues["missingMetadata"].append({
                        "severity": "high",
                        "description": "PDF is missing document title in metadata",
                        "page": 1,
                        "recommendation": "Add document title in PDF properties using File > Properties > Description",
                    })

                author = self._metadata_text(metadata.get('/Author')) if metadata else None
                if not author:
                    self.issues["missingMetadata"].append({
                        "severity": "medium",
                        "description": "PDF is missing author information",
                        "page": 1,
                        "recommendation": "Add author name in PDF metadata for better document identification",
                    })

                subject = self._metadata_text(metadata.get('/Subject')) if metadata else None
                if not subject:
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
                self._tagging_state["is_tagged"] = bool(is_tagged)

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
            self._record_analysis_error(e, fatal=True)

    def _try_decrypt_reader(self, reader: PyPDF2.PdfReader) -> bool:
        """Attempt to decrypt the PDF with empty passwords."""
        passwords = ("", b"")
        for candidate in passwords:
            try:
                result = reader.decrypt(candidate)
            except Exception:
                continue
            if isinstance(result, str):
                if result:
                    return True
            elif result:
                return True
        return False

    def _analyze_with_pdfplumber(self, pdf_path: str):
        """Analyze PDF using pdfplumber for content analysis"""
        if self._analysis_errors:
            return
        try:
            tables_reviewed = False
            self._tagging_state["tables_reviewed"] = False
            self._tagging_state["has_struct_tree"] = False
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
                    self._tagging_state["has_struct_tree"] = has_struct_tree is not None
                    
                    # If document is tagged and has structure tree, consider tables reviewed
                    if is_tagged and has_struct_tree:
                        tables_reviewed = True
                        print("[Analyzer] Document has structure tags - tables marked as reviewed")
                    self._tagging_state["tables_reviewed"] = tables_reviewed
            except Exception as e:
                print(f"[Analyzer] Could not check table review status: {e}")
            
            with pdfplumber.open(pdf_path) as pdf:
                total_images = 0
                total_tables = 0
                pages_with_images = []
                pages_with_tables = []
                total_form_fields = 0
                image_candidates: List[Dict[str, Any]] = []
                
                for page_num, page in enumerate(pdf.pages, start=1):
                    # Check for images
                    images = page.images
                    if images and len(images) > 0:
                        total_images += len(images)
                        pages_with_images.append(page_num)
                        for img_index, image in enumerate(images, start=1):
                            image_candidates.append({
                                "page": page_num,
                                "pages": [page_num],
                                "imageIndex": img_index,
                                "xobjectName": self._normalize_xobject_name(image.get("name")),
                                "location": {
                                    "page": page_num,
                                    "imageIndex": img_index,
                                    "bbox": image.get("bbox"),
                                    "width": image.get("width"),
                                    "height": image.get("height"),
                                },
                            })
                    
                    # Check for tables
                    tables = page.find_tables()
                    if tables and len(tables) > 0:
                        total_tables += len(tables)
                        pages_with_tables.append(page_num)
                    
                    # Check for form fields
                    if hasattr(page, 'annots') and page.annots:
                        total_form_fields += len(page.annots)
                
                missing_alt_issues = self._collect_missing_alt_text_issues(pdf_path, image_candidates)
                self._verapdf_alt_findings = missing_alt_issues or []
                if self.wcag_validator_available:
                    # WCAGValidator will be the source of truth for missingAltText later.
                    self.issues["missingAltText"] = []
                elif self._verapdf_alt_findings:
                    self.issues["missingAltText"].extend(self._verapdf_alt_findings)
                
                if not self.issues["tableIssues"] and total_tables > 0 and not tables_reviewed:
                    table_issue = {
                        "severity": "high",
                        "description": f"Found {total_tables} table(s) that may lack proper header markup",
                        "count": total_tables,
                        "pages": pages_with_tables[:10],
                        "recommendation": "Ensure all tables have properly marked header rows and columns.",
                    }
                    self.issues["tableIssues"].append(table_issue)
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
                        "severity": "info",
                        "description": "Document contains images - text contrast should be manually verified",
                        "count": total_images,
                        "pages": pages_with_images[:5],
                        "penaltyWeight": 0,
                        "recommendation": "Manually check that all text has sufficient contrast ratio (4.5:1 for normal text)",
                    })
                    self._contrast_manual_note_added = True
                
                print(f"[Analyzer] pdfplumber analysis: {total_images} images, {total_tables} tables, {total_form_fields} form fields")
                self._sync_table_issues_to_pdfua()
                
        except Exception as e:
            print(f"[Analyzer] Error in pdfplumber analysis: {e}")
            self._record_analysis_error(e)

    def _collect_missing_alt_text_issues(
        self,
        pdf_path: str,
        image_candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Return precise missing-alt issues based on structure-aware scanning.

        These findings act as VeraPDF-style advisories until WCAGValidator confirms 1.1.1 failures.
        """
        if not image_candidates:
            return []

        structure_results = self._find_images_without_structure_alt(pdf_path)
        if structure_results is None:
            return self._fallback_missing_alt_issues(image_candidates)

        if not structure_results:
            return []

        candidate_map: Dict[Tuple[int, Optional[str]], List[Dict[str, Any]]] = defaultdict(list)
        for candidate in image_candidates:
            key = (candidate["page"], candidate.get("xobjectName"))
            candidate_map[key].append(candidate)

        issues: List[Dict[str, Any]] = []
        seen_refs: Set[Tuple[int, Optional[str]]] = set()

        for entry in structure_results:
            key = (entry["page"], entry.get("name"))
            if key in seen_refs:
                continue
            seen_refs.add(key)

            candidates = candidate_map.get(key)
            if not candidates:
                issues.append(self._format_missing_alt_issue(entry["page"], None))
                continue

            for candidate in candidates:
                issues.append(self._format_missing_alt_issue(entry["page"], candidate))

        return issues

    def _find_images_without_structure_alt(self, pdf_path: str) -> Optional[List[Dict[str, Any]]]:
        """Inspect the structure tree to identify images lacking alt text."""
        if not PIKEPDF_AVAILABLE:
            return None

        pdf_doc = None
        validator = None
        lookup = None
        results: List[Dict[str, Any]] = []

        try:
            pdf_doc = pikepdf.open(pdf_path)

            if WCAG_VALIDATOR_AVAILABLE and WCAGValidator:
                validator = WCAGValidator(pdf_path)
                validator.pdf = pdf_doc
                lookup = validator._get_figure_alt_lookup()
            elif build_figure_alt_lookup:
                lookup = build_figure_alt_lookup(pdf_doc)

            for page_index, page in enumerate(pdf_doc.pages, 1):
                if '/Resources' not in page or '/XObject' not in page.Resources:
                    continue
                xobjects = page.Resources.XObject
                for name, xobject in xobjects.items():
                    if xobject.get('/Subtype') != '/Image':
                        continue

                    has_alt = False
                    if validator:
                        has_alt = validator._has_alt_text(xobject)
                    else:
                        if '/Alt' in xobject or '/ActualText' in xobject:
                            has_alt = True
                        elif has_figure_alt_text and lookup:
                            has_alt = has_figure_alt_text(xobject, lookup)

                    if not has_alt:
                        results.append({
                            "page": page_index,
                            "name": self._normalize_xobject_name(str(name)),
                        })

        except Exception as exc:
            print(f"[Analyzer] Could not perform structure-aware alt text scan: {exc}")
            return None
        finally:
            if pdf_doc is not None:
                try:
                    pdf_doc.close()
                except Exception:
                    pass

        return results

    def _fallback_missing_alt_issues(self, image_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return legacy heuristic issues when structure-aware detection is unavailable."""
        issues: List[Dict[str, Any]] = []
        for candidate in image_candidates:
            issues.append({
                "severity": "medium",
                "description": f"Image on page {candidate['page']} may lack alternative text (structure analysis unavailable)",
                "page": candidate["page"],
                "pages": candidate.get("pages", [candidate["page"]]),
                "imageIndex": candidate.get("imageIndex"),
                "location": candidate.get("location"),
                "recommendation": "Add descriptive alt text to this image using a PDF editor.",
            })
        return issues

    def _format_missing_alt_issue(self, page_num: int, candidate: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Create a standardized issue record for an image missing alt text."""
        issue = {
            "severity": "high",
            "description": f"Image on page {page_num} has no associated alternative text or tagged Figure entry",
            "page": page_num,
            "pages": [page_num],
            "recommendation": "Add an Alt text entry to the Figure tag or XObject stream for this image.",
        }

        if candidate:
            issue.update({
                "pages": candidate.get("pages", [page_num]),
                "imageIndex": candidate.get("imageIndex"),
                "location": candidate.get("location"),
            })

        return issue

    def _sync_missing_alt_from_wcag(self, validation_results: Dict[str, Any]):
        """
        When WCAG Validator runs successfully, keep `missingAltText` empty so WCAG 1.1.1
        findings remain the single truth for missing alt text.
        """
        issues = validation_results.get("wcagIssues") or []
        alt_issues = [
            issue for issue in issues if str(issue.get("criterion")).strip() == "1.1.1"
        ]
        if alt_issues:
            # Keep the legacy bucket empty when WCAG is authoritative.
            self.issues["missingAltText"] = []
        else:
            self.issues["missingAltText"] = []

    def get_wcag_validator_metrics(self) -> Optional[Dict[str, Any]]:
        """Expose the latest WCAG/PDF-UA scores so summaries can prioritize them."""
        return self._wcag_validator_metrics

    @staticmethod
    def _normalize_xobject_name(name: Optional[Any]) -> Optional[str]:
        """Normalize XObject names so pdfplumber and pikepdf references match."""
        if not name:
            return None
        text = str(name)
        return text[1:] if text.startswith('/') else text

    def _sync_table_issues_to_pdfua(self):
        """Mirror generic table issues into PDF/UA clause 7.5 findings for reporting."""
        table_issues = self.issues.get("tableIssues") or []
        if not table_issues:
            return

        existing = set()
        for issue in self.issues.get("pdfuaIssues", []):
            clause = issue.get("clause")
            desc = issue.get("description")
            if not clause or not desc:
                continue
            existing.add((desc, clause))

        for issue in table_issues:
            if not isinstance(issue, dict):
                continue
            desc = issue.get("description")
            if not desc:
                continue
            key = (desc, "ISO 14289-1:7.5")
            if key in existing:
                continue
            pdfua_issue = {
                "description": desc,
                "clause": "ISO 14289-1:7.5",
                "severity": issue.get("severity", "medium"),
                "remediation": issue.get("recommendation", "Ensure table headers are identified and associated with data cells."),
                "pages": issue.get("pages"),
                "category": "pdfua",
            }
            self.issues["pdfuaIssues"].append(pdfua_issue)
            existing.add(key)

    def _analyze_contrast_basic(self, pdf_path: str):
        """
        Perform a lightweight contrast analysis by inspecting text color commands.
        Assumes a white background and only looks at rg/RG + Tj/TJ sequences.
        """
        if self._analysis_errors:
            return
        if ContentStream is None:
            self._ensure_manual_contrast_notice("PyPDF2 ContentStream helper unavailable")
            return

        try:
            with open(pdf_path, 'rb') as file_handle:
                reader = PyPDF2.PdfReader(file_handle)
                total_checked = 0
                for page_num, page in enumerate(reader.pages, start=1):
                    checked, _flagged = self._scan_page_for_low_contrast(page, reader, page_num)
                    total_checked += checked

                if total_checked == 0:
                    self._ensure_manual_contrast_notice("No analyzable text color data found")
        except Exception as exc:
            print(f"[Analyzer] Contrast analysis unavailable: {exc}")
            self._ensure_manual_contrast_notice("Contrast parsing failed")
            self._record_analysis_error(exc, fatal=False)

    def _scan_page_for_low_contrast(self, page, reader, page_num: int) -> Tuple[int, int]:
        """Scan a single page for text runs drawn with insufficient contrast."""
        if ContentStream is None:
            return (0, 0)

        try:
            contents = page.get_contents()
            if contents is None:
                return (0, 0)
            content_stream = ContentStream(contents, reader)
            operations = getattr(content_stream, "operations", [])
        except Exception:
            return (0, 0)

        fill_color: Optional[Tuple[float, float, float]] = None
        stroke_color: Optional[Tuple[float, float, float]] = None
        checked_runs = 0
        flagged_runs = 0
        background = (1.0, 1.0, 1.0)
        contrast_threshold = 4.5

        for operands, operator in operations:
            op_name = self._decode_operator(operator)
            if op_name == 'rg':
                color = self._extract_rgb_from_operands(operands)
                if color:
                    fill_color = color
            elif op_name == 'RG':
                color = self._extract_rgb_from_operands(operands)
                if color:
                    stroke_color = color
            elif op_name in ('Tj', 'TJ'):
                active_color = fill_color or stroke_color
                if active_color is None:
                    continue
                checked_runs += 1
                ratio = self._contrast_ratio(active_color, background)
                if ratio < contrast_threshold:
                    flagged_runs += 1
                    text_sample = self._extract_text_sample(operands)
                    self._record_low_contrast_issue(page_num, ratio, text_sample)

        return (checked_runs, flagged_runs)

    def _extract_rgb_from_operands(self, operands: List[Any]) -> Optional[Tuple[float, float, float]]:
        """Return normalized RGB tuple from PDF operator operands."""
        if not operands or len(operands) < 3:
            return None
        values: List[float] = []
        for operand in operands[:3]:
            try:
                values.append(max(0.0, min(1.0, float(operand))))
            except Exception:
                return None
        if len(values) != 3:
            return None
        return (values[0], values[1], values[2])

    def _relative_luminance(self, r: float, g: float, b: float) -> float:
        """Calculate relative luminance using WCAG 2.1 formula."""
        def _linearize(channel: float) -> float:
            if channel <= 0.03928:
                return channel / 12.92
            return ((channel + 0.055) / 1.055) ** 2.4

        r_lin = _linearize(r)
        g_lin = _linearize(g)
        b_lin = _linearize(b)
        return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin

    def _contrast_ratio(self, fg: Tuple[float, float, float], bg: Tuple[float, float, float]) -> float:
        """Return WCAG contrast ratio between two RGB tuples."""
        fg_lum = self._relative_luminance(*fg)
        bg_lum = self._relative_luminance(*bg)
        light = max(fg_lum, bg_lum)
        dark = min(fg_lum, bg_lum)
        return (light + 0.05) / (dark + 0.05)

    def _extract_text_sample(self, operands: List[Any]) -> Optional[str]:
        """Return a short normalized snippet from Tj/TJ operands."""
        if not operands:
            return None

        samples: List[str] = []

        def _normalize(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, str):
                return value
            if TextStringObject is not None and isinstance(value, TextStringObject):
                return str(value)
            if ByteStringObject is not None and isinstance(value, ByteStringObject):
                try:
                    return bytes(value).decode("utf-8", errors="ignore")
                except Exception:
                    return None
            if hasattr(value, "decode"):
                try:
                    return value.decode("utf-8", errors="ignore")
                except Exception:
                    return None
            return None

        for operand in operands:
            values = []
            if isinstance(operand, (list, tuple)):
                values = list(operand)
            else:
                values = [operand]

            for entry in values:
                snippet = _normalize(entry)
                if snippet:
                    cleaned = " ".join(snippet.split())
                    if cleaned:
                        samples.append(cleaned)
            if samples:
                break

        if not samples:
            return None

        joined = " ".join(samples).strip()
        if not joined:
            return None
        if len(joined) > 80:
            joined = joined[:79].rstrip() + "…"
        return joined

    def _decode_operator(self, operator: Any) -> str:
        """Decode an operator token from a ContentStream operation."""
        if isinstance(operator, bytes):
            try:
                return operator.decode('latin1')
            except Exception:
                return operator.decode('utf-8', errors='ignore')
        return str(operator)

    def _record_low_contrast_issue(self, page_num: int, ratio: float, text_sample: Optional[str] = None):
        """Append a low-contrast issue, limiting the total count."""
        max_entries = 25
        if self._low_contrast_issue_count >= max_entries:
            return

        self._low_contrast_issue_count += 1

        self.issues["poorContrast"].append({
            "severity": "medium",
            "criterion": "1.4.3",
            "level": "AA",
            "description": f"Text on page {page_num} has low contrast (~{ratio:.1f}:1) against assumed white background",
            "pages": [page_num],
            "contrastRatio": round(ratio, 2),
            "recommendation": "Increase text color contrast to at least 4.5:1 (WCAG 1.4.3 / 1.4.6).",
            "penaltyWeight": self._LOW_CONTRAST_PENALTY,
            "advisoryCriteria": ["1.4.6"],
        })
        if text_sample:
            self.issues["poorContrast"][-1]["textSample"] = text_sample

    def _ensure_manual_contrast_notice(self, reason: Optional[str] = None):
        """Ensure we log at least one manual contrast review reminder."""
        if self._contrast_manual_note_added:
            return

        description = "Document contrast requires manual review"
        if reason:
            description += f" ({reason})."
        else:
            description += "."

        self.issues["poorContrast"].append({
            "severity": "info",
            "description": description,
            "recommendation": "Manually verify that text meets WCAG 1.4.3/1.4.6 contrast thresholds.",
            "penaltyWeight": 0,
        })
        self._contrast_manual_note_added = True

    def _consolidate_poor_contrast_issues(self):
        """Merge duplicate contrast entries so summaries/fixes stay readable."""
        issues = self.issues.get("poorContrast")
        if not isinstance(issues, list) or not issues:
            self.issues["poorContrast"] = []
            return

        aggregated: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
        ordered: List[Dict[str, Any]] = []

        for issue in issues:
            if not isinstance(issue, dict):
                continue

            pages = issue.get("pages")
            if not isinstance(pages, list):
                single_page = issue.get("page")
                pages = [single_page] if single_page else []

            normalized_pages = tuple(pages or [])
            key = (
                issue.get("criterion"),
                normalized_pages,
                str(issue.get("description", "")).strip(),
                str(issue.get("severity", "")).lower(),
                issue.get("contrastRatio"),
            )

            raw_count = issue.get("count")
            if isinstance(raw_count, (int, float)):
                increment = max(1, int(round(raw_count)))
            else:
                increment = 1

            existing = aggregated.get(key)
            if existing:
                existing["count"] = existing.get("count", 0) + increment
                if not existing.get("pages") and pages:
                    existing["pages"] = list(pages)
                continue

            prepared = dict(issue)
            prepared["pages"] = list(pages)
            prepared["count"] = max(increment, 1)
            aggregated[key] = prepared
            ordered.append(prepared)

        self.issues["poorContrast"] = ordered

    def _record_analysis_error(self, error: Exception, fatal: Optional[bool] = None) -> None:
        """Capture analyzer errors for user-facing status propagation."""
        friendly_message, inferred_fatal, raw_message = self._classify_analysis_error(error)
        is_fatal = inferred_fatal if fatal is None else fatal
        entry = {
            "message": friendly_message,
            "rawMessage": raw_message,
            "fatal": bool(is_fatal),
            "errorType": error.__class__.__name__,
        }
        self._analysis_error_details.append(entry)

        log_level = logging.ERROR if is_fatal else logging.WARNING
        log_label = "Fatal" if is_fatal else "Non-fatal"
        log_context = raw_message or repr(error)
        logger.log(
            log_level,
            "[Analyzer] %s analysis error captured: %s",
            log_label,
            log_context,
        )

        if is_fatal and friendly_message not in self._analysis_errors:
            self._analysis_errors.append(friendly_message)

    def _classify_analysis_error(self, error: Exception) -> Tuple[str, bool, str]:
        """Return a friendly error message, fatality flag, and raw message."""
        try:
            raw_message = str(error).strip()
        except Exception:
            raw_message = ""
        normalized = raw_message.lower()

        encrypted_tokens = ("encrypt", "password", "decrypt", "security")
        truncated_tokens = (
            "truncat",
            "corrupt",
            "broken",
            "damaged",
            "malform",
            "end-of-file",
            "eof marker",
            "startxref",
            "xref",
            "not a pdf",
            "unable to get",
            "stream length",
            "unexpected end",
        )

        if any(token in normalized for token in encrypted_tokens):
            return (
                "We were unable to analyze this file because it is password protected.",
                True,
                raw_message,
            )
        if any(token in normalized for token in truncated_tokens):
            return (
                "We were unable to analyze this file because it appears to be truncated or corrupted.",
                True,
                raw_message,
            )
        return ("We were unable to analyze this file.", False, raw_message)

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

    def _determine_issue_penalty(self, issue: Dict[str, Any]) -> int:
        """Return the penalty weight for an issue, honoring overrides for contrast checks."""
        penalty = issue.get("penaltyWeight")
        if isinstance(penalty, (int, float)):
            return max(0, int(penalty))

        criterion = issue.get("criterion")
        if isinstance(criterion, str):
            normalized = criterion.strip()
            if normalized in self._CRITERION_PENALTIES:
                return self._CRITERION_PENALTIES[normalized]

        severity = str(issue.get("severity") or "medium").lower()
        return self._SEVERITY_PENALTIES.get(severity, self._SEVERITY_PENALTIES["medium"])

    def calculate_compliance_score(self) -> int:
        """Calculate overall accessibility compliance score (0-100)"""
        try:
            canonical_issues = self._collect_canonical_issues(self.issues)
            if not canonical_issues:
                return 100

            total_penalty = 0
            for issue in canonical_issues:
                if isinstance(issue, dict):
                    total_penalty += self._determine_issue_penalty(issue)

            score = 100 - total_penalty
            return max(0, min(100, score))
        except Exception as e:
            print(f"[Analyzer] Error calculating score: {e}")
            return 50

    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics of the analysis"""
        try:
            canonical_issues = self._collect_canonical_issues(self.issues)
            total_issues = len(canonical_issues)
            high_severity = len(
                [
                    i
                    for i in canonical_issues
                    if isinstance(i, dict)
                    and str(i.get("severity") or "").lower() in {"high", "critical"}
                ]
            )
            medium_severity = len(
                [
                    i
                    for i in canonical_issues
                    if isinstance(i, dict)
                    and str(i.get("severity") or "").lower() == "medium"
                ]
            )

            return {
                "totalIssues": total_issues,
                "totalIssuesRaw": total_issues,
                "highSeverity": high_severity,
                "mediumSeverity": medium_severity,
                "issuesRemaining": total_issues,
                "remainingIssues": total_issues,
                "issuesRemainingRaw": total_issues,
                "complianceScore": self.calculate_compliance_score(),
                "wcagCompliance": derive_wcag_score(self.issues),
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
            canonical_list = results.get("issues") if isinstance(results, dict) else None
            canonical_issues = canonical_list if isinstance(canonical_list, list) else []

            if not canonical_issues and isinstance(results, dict):
                canonical_issues = [
                    issue
                    for key, value in results.items()
                    if key != "issues"
                    and isinstance(value, list)
                    for issue in value
                    if isinstance(issue, dict)
                ]

            total_issues = len(canonical_issues)

            high_severity = len(
                [
                    i
                    for i in canonical_issues
                    if isinstance(i, dict)
                    and str(i.get("severity") or "").lower() in {"high", "critical"}
                ]
            )
            medium_severity = len(
                [
                    i
                    for i in canonical_issues
                    if isinstance(i, dict)
                    and str(i.get("severity") or "").lower() == "medium"
                ]
            )
            low_severity = max(total_issues - high_severity - medium_severity, 0)

            # Calculate compliance score
            if total_issues == 0:
                compliance_score = 100
            else:
                compliance_score = 100 - (high_severity * 15) - (medium_severity * 5) - (low_severity * 2)
                compliance_score = max(0, min(100, compliance_score))

            summary = {
                "totalIssues": total_issues,
                "totalIssuesRaw": total_issues,
                "highSeverity": high_severity,
                "mediumSeverity": medium_severity,
                "issuesRemaining": total_issues,
                "remainingIssues": total_issues,
                "issuesRemainingRaw": total_issues,
                "complianceScore": compliance_score,
            }

            derived_wcag = derive_wcag_score(results)
            if derived_wcag is not None:
                summary["wcagCompliance"] = derived_wcag

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
        """
        Analyze PDF using built-in WCAG 2.1 and PDF/UA-1 validator.
        WCAG 1.1.1 output controls missingAltText and primary compliance scores.
        """
        if self._analysis_errors:
            return
        try:
            self._wcag_validator_metrics = None
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
                link_issues = [
                    issue
                    for issue in validation_results.get("wcagIssues", [])
                    if issue.get("criterion") == "2.4.4"
                ]
                if link_issues:
                    self.issues["linkIssues"].extend(link_issues)
            
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
            self._wcag_validator_metrics = {
                "wcagScore": wcag_score,
                "pdfuaScore": pdfua_score,
                "wcagCompliance": wcag_compliance,
                "pdfuaCompliance": validation_results.get('pdfuaCompliance'),
            }
            # WCAG 1.1.1 output directly controls the missingAltText bucket.
            self._sync_missing_alt_from_wcag(validation_results)
            
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
            self._record_analysis_error(e, fatal=False)
            if self._verapdf_alt_findings and not self.issues["missingAltText"]:
                # WCAG validator failed; fall back to VeraPDF-style heuristics.
                self.issues["missingAltText"].extend(self._verapdf_alt_findings)
            print("[Analyzer] ==========================================")

    def _analyze_with_pdfa_validator(self, pdf_path: str):
        """PDF/A validation is disabled while focusing on WCAG 2.1 and PDF/UA-1 checking."""
        print("[Analyzer] PDF/A validation skipped (WCAG/PDF/UA focus).")
