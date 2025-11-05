"""
Unified Conformance Checker
Inspired by iText's PdfConformance abstraction for checking multiple standards
"""

from typing import Dict, List, Any, Optional
from enum import Enum
import pikepdf
import logging

from backend.wcag_validator import WCAGValidator
from backend.pdfa_validator import PDFAValidator
from backend.matterhorn_protocol import MatterhornProtocol

logger = logging.getLogger(__name__)


class ConformanceStandard(Enum):
    """Supported conformance standards"""
    PDF_A_1A = "PDF/A-1a"
    PDF_A_1B = "PDF/A-1b"
    PDF_A_2A = "PDF/A-2a"
    PDF_A_2B = "PDF/A-2b"
    PDF_A_3A = "PDF/A-3a"
    PDF_A_3B = "PDF/A-3b"
    PDF_UA_1 = "PDF/UA-1"
    WCAG_2_1_A = "WCAG 2.1 Level A"
    WCAG_2_1_AA = "WCAG 2.1 Level AA"
    WCAG_2_1_AAA = "WCAG 2.1 Level AAA"


class ConformanceLevel(Enum):
    """Conformance levels"""
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    NOT_APPLICABLE = "not_applicable"


class UnifiedConformanceChecker:
    """
    Unified conformance checker for multiple PDF standards.
    Inspired by iText's PdfConformance abstraction.
    """
    
    def __init__(self):
        self.wcag_validator = WCAGValidator()
        self.pdfa_validator = PDFAValidator()
        self.matterhorn_protocol = MatterhornProtocol()
    
    def check_conformance(
        self,
        pdf_path: str,
        standards: List[ConformanceStandard]
    ) -> Dict[str, Any]:
        """
        Check PDF conformance against multiple standards
        
        Args:
            pdf_path: Path to PDF file
            standards: List of standards to check against
            
        Returns:
            Dictionary with conformance results for each standard
        """
        results = {
            "file": pdf_path,
            "standards_checked": [s.value for s in standards],
            "overall_conformance": ConformanceLevel.PASS.value,
            "results": {},
            "summary": {
                "total_issues": 0,
                "critical_issues": 0,
                "warnings": 0
            }
        }
        
        try:
            with pikepdf.open(pdf_path) as pdf:
                for standard in standards:
                    standard_result = self._check_standard(pdf, standard)
                    results["results"][standard.value] = standard_result
                    
                    # Update overall conformance
                    if standard_result["conformance"] == ConformanceLevel.FAIL.value:
                        results["overall_conformance"] = ConformanceLevel.FAIL.value
                    
                    # Update summary
                    results["summary"]["total_issues"] += standard_result["issue_count"]
                    results["summary"]["critical_issues"] += standard_result["critical_count"]
                    results["summary"]["warnings"] += standard_result["warning_count"]
        
        except Exception as e:
            logger.error(f"Error checking conformance: {e}")
            results["error"] = str(e)
            results["overall_conformance"] = ConformanceLevel.FAIL.value
        
        return results
    
    def _check_standard(
        self,
        pdf: pikepdf.Pdf,
        standard: ConformanceStandard
    ) -> Dict[str, Any]:
        """Check conformance for a specific standard"""
        
        if standard in [ConformanceStandard.WCAG_2_1_A, ConformanceStandard.WCAG_2_1_AA, ConformanceStandard.WCAG_2_1_AAA]:
            return self._check_wcag(pdf, standard)
        elif standard in [ConformanceStandard.PDF_A_1A, ConformanceStandard.PDF_A_1B, 
                         ConformanceStandard.PDF_A_2A, ConformanceStandard.PDF_A_2B,
                         ConformanceStandard.PDF_A_3A, ConformanceStandard.PDF_A_3B]:
            return self._check_pdfa(pdf, standard)
        elif standard == ConformanceStandard.PDF_UA_1:
            return self._check_pdfua(pdf)
        else:
            return {
                "conformance": ConformanceLevel.NOT_APPLICABLE.value,
                "issues": [],
                "issue_count": 0,
                "critical_count": 0,
                "warning_count": 0
            }
    
    def _check_wcag(self, pdf: pikepdf.Pdf, standard: ConformanceStandard) -> Dict[str, Any]:
        """Check WCAG conformance"""
        issues = self.wcag_validator.validate(pdf)
        
        # Filter by level
        level = standard.value.split()[-1]  # Extract A, AA, or AAA
        filtered_issues = [
            issue for issue in issues
            if self._meets_wcag_level(issue, level)
        ]
        
        return {
            "conformance": ConformanceLevel.FAIL.value if filtered_issues else ConformanceLevel.PASS.value,
            "issues": filtered_issues,
            "issue_count": len(filtered_issues),
            "critical_count": len([i for i in filtered_issues if i.get("severity") == "HIGH"]),
            "warning_count": len([i for i in filtered_issues if i.get("severity") == "MEDIUM"])
        }
    
    def _check_pdfa(self, pdf: pikepdf.Pdf, standard: ConformanceStandard) -> Dict[str, Any]:
        """Check PDF/A conformance"""
        # Extract version and level from standard
        version = standard.value.split('-')[1][0]  # 1, 2, or 3
        level = standard.value.split('-')[1][1].lower()  # a or b
        
        issues = self.pdfa_validator.validate(pdf, f"PDF/A-{version}{level}")
        
        return {
            "conformance": ConformanceLevel.FAIL.value if issues else ConformanceLevel.PASS.value,
            "issues": issues,
            "issue_count": len(issues),
            "critical_count": len([i for i in issues if i.get("severity") == "HIGH"]),
            "warning_count": len([i for i in issues if i.get("severity") == "MEDIUM"])
        }
    
    def _check_pdfua(self, pdf: pikepdf.Pdf) -> Dict[str, Any]:
        """Check PDF/UA conformance using Matterhorn Protocol"""
        issues = self.matterhorn_protocol.validate(pdf)
        
        return {
            "conformance": ConformanceLevel.FAIL.value if issues else ConformanceLevel.PASS.value,
            "issues": issues,
            "issue_count": len(issues),
            "critical_count": len([i for i in issues if i.get("severity") == "HIGH"]),
            "warning_count": len([i for i in issues if i.get("severity") == "MEDIUM"]),
            "matterhorn_checkpoints": [i.get("checkpoint") for i in issues]
        }
    
    def _meets_wcag_level(self, issue: Dict[str, Any], level: str) -> bool:
        """Check if issue applies to the specified WCAG level"""
        issue_level = issue.get("level", "A")
        
        if level == "A":
            return issue_level == "A"
        elif level == "AA":
            return issue_level in ["A", "AA"]
        elif level == "AAA":
            return True  # All levels
        
        return False
    
    def generate_conformance_report(self, results: Dict[str, Any]) -> str:
        """Generate a human-readable conformance report"""
        report = []
        report.append("=" * 80)
        report.append("PDF CONFORMANCE REPORT")
        report.append("=" * 80)
        report.append(f"\nFile: {results['file']}")
        report.append(f"Overall Conformance: {results['overall_conformance'].upper()}")
        report.append(f"\nStandards Checked: {', '.join(results['standards_checked'])}")
        report.append(f"\nSummary:")
        report.append(f"  Total Issues: {results['summary']['total_issues']}")
        report.append(f"  Critical Issues: {results['summary']['critical_issues']}")
        report.append(f"  Warnings: {results['summary']['warnings']}")
        report.append("\n" + "=" * 80)
        
        for standard, result in results['results'].items():
            report.append(f"\n{standard}: {result['conformance'].upper()}")
            report.append(f"  Issues: {result['issue_count']}")
            
            if result['issues']:
                report.append(f"\n  Top Issues:")
                for issue in result['issues'][:5]:  # Show top 5
                    report.append(f"    - {issue.get('description', issue.get('message', 'Unknown issue'))}")
        
        report.append("\n" + "=" * 80)
        return "\n".join(report)
