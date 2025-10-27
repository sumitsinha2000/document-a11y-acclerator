"""
Auto-Fix Module
Provides automated remediation suggestions and fixes for accessibility issues
"""

from typing import Dict, List, Any
import pikepdf
from pathlib import Path
import datetime


class AutoFixEngine:
    """
    Generates automated fixes and remediation suggestions for accessibility issues.
    Provides actionable steps to improve PDF accessibility.
    """

    def __init__(self):
        self.fixes = {}

    def generate_fixes(self, issues: Dict[str, List[Any]]) -> Dict[str, Any]:
        """
        Generate automated fixes for identified accessibility issues.
        
        Args:
            issues: Dictionary of accessibility issues from analyzer
            
        Returns:
            Dictionary with suggested fixes and automation options
        """
        fixes = {
            "automated": [],
            "semiAutomated": [],
            "manual": [],
            "estimatedTime": 0,
        }

        # Automated fixes - can be applied programmatically
        if issues.get("missingMetadata"):
            fixes["automated"].append({
                "category": "missingMetadata",
                "action": "Add default metadata",
                "description": "Automatically add document title and basic metadata",
                "impact": "high",
                "timeEstimate": "< 1 minute",
            })

        if issues.get("missingLanguage"):
            fixes["automated"].append({
                "category": "missingLanguage",
                "action": "Set document language",
                "description": "Automatically set document language to English (en-US)",
                "impact": "medium",
                "timeEstimate": "< 1 minute",
            })

        # Semi-automated fixes - require review
        if issues.get("missingAltText"):
            fixes["semiAutomated"].append({
                "category": "missingAltText",
                "action": "Generate alt text suggestions",
                "description": "AI-powered alt text suggestions for images (requires review)",
                "impact": "high",
                "timeEstimate": "10-30 minutes",
            })

        # Manual fixes - require human intervention
        if issues.get("untaggedContent"):
            fixes["manual"].append({
                "category": "untaggedContent",
                "action": "Tag content structure",
                "description": "Manually tag content with semantic structure using PDF editor",
                "impact": "high",
                "timeEstimate": "30-60 minutes",
            })

        if issues.get("poorContrast"):
            fixes["manual"].append({
                "category": "poorContrast",
                "action": "Improve text contrast",
                "description": "Adjust colors to meet WCAG contrast requirements",
                "impact": "medium",
                "timeEstimate": "15-30 minutes",
            })

        if issues.get("tableIssues"):
            fixes["manual"].append({
                "category": "tableIssues",
                "action": "Fix table structure",
                "description": "Add proper table headers and markup for complex tables",
                "impact": "high",
                "timeEstimate": "20-40 minutes",
            })

        if issues.get("formIssues"):
            fixes["manual"].append({
                "category": "formIssues",
                "action": "Add form field labels",
                "description": "Associate descriptive labels with all form fields",
                "impact": "high",
                "timeEstimate": "15-30 minutes",
            })

        # Calculate total estimated time
        total_time = len(fixes["automated"]) * 1 + len(fixes["semiAutomated"]) * 15 + len(fixes["manual"]) * 35
        fixes["estimatedTime"] = total_time

        return fixes

    def apply_automated_fixes(self, pdf_path: str) -> Dict[str, Any]:
        """
        Apply automated fixes to a PDF while preserving existing structure.
        Uses pikepdf for better PDF structure preservation.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary with applied fixes and results
        """
        try:
            print(f"[AutoFix] Applying automated fixes to {pdf_path}")
            
            input_path = Path(pdf_path)
            
            if not input_path.exists():
                return {
                    "success": False,
                    "fixesApplied": [],
                    "message": f"File not found: {pdf_path}",
                }
            
            original_name = input_path.stem
            if original_name.startswith('scan_'):
                parts = original_name.split('_')
                if len(parts) >= 3:
                    original_name = '_'.join(parts[3:])
            original_name = original_name.replace('_fixed', '')
            
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            output_filename = f"{original_name}_fixed_{timestamp}.pdf"
            output_path = input_path.parent / output_filename
            
            fixes_applied = []
            
            with pikepdf.open(pdf_path, allow_overwriting_input=True) as pdf:
                # Get existing metadata
                with pdf.open_metadata() as meta:
                    # Add metadata only if missing
                    if not meta.get('dc:title'):
                        meta['dc:title'] = original_name.replace('_', ' ').title()
                        fixes_applied.append("Added document title")
                    
                    if not meta.get('dc:creator'):
                        meta['dc:creator'] = ["Document Author"]
                        fixes_applied.append("Added author information")
                    
                    if not meta.get('dc:description'):
                        meta['dc:description'] = "Accessibility-enhanced document"
                        fixes_applied.append("Added document description")
                    
                    if not meta.get('pdf:Keywords'):
                        meta['pdf:Keywords'] = "accessible, PDF, document"
                        fixes_applied.append("Added document keywords")
                    
                    # Always update producer and modification date
                    meta['pdf:Producer'] = "PDF Accessibility Accelerator"
                    meta['xmp:ModifyDate'] = datetime.datetime.now().isoformat()
                
                # Set document language if not present
                if '/Lang' not in pdf.Root:
                    pdf.Root.Lang = 'en-US'
                    fixes_applied.append("Set document language to en-US")
                    print("[AutoFix] Set document language")
                
                if '/MarkInfo' not in pdf.Root:
                    pdf.Root.MarkInfo = pikepdf.Dictionary(Marked=True)
                    fixes_applied.append("Marked document as tagged")
                    print("[AutoFix] Marked document as tagged")
                
                # Save with linearization for better compatibility
                pdf.save(output_path, linearize=True)
            
            print(f"[AutoFix] Fixes applied successfully: {fixes_applied}")
            print(f"[AutoFix] Output file created: {output_path}")
            
            if not output_path.exists():
                return {
                    "success": False,
                    "fixesApplied": [],
                    "message": "Failed to create output file",
                }
            
            try:
                with pikepdf.open(output_path) as verify_pdf:
                    page_count = len(verify_pdf.pages)
                    print(f"[AutoFix] Verified output PDF: {page_count} pages")
                    
                    # Verify metadata was actually added
                    with verify_pdf.open_metadata() as verify_meta:
                        if verify_meta.get('dc:title'):
                            print(f"[AutoFix] Verified metadata: Title = {verify_meta['dc:title']}")
            except Exception as e:
                print(f"[AutoFix] Warning: Output PDF verification failed: {e}")
                # Delete the corrupted file
                output_path.unlink(missing_ok=True)
                return {
                    "success": False,
                    "fixesApplied": [],
                    "message": f"Output PDF is invalid: {str(e)}",
                }
            
            return {
                "success": True,
                "fixesApplied": fixes_applied,
                "fixedFile": output_filename,
                "outputPath": str(output_path),
                "successCount": len(fixes_applied),
                "message": f"Applied {len(fixes_applied)} automated fix(es) successfully",
            }
                
        except Exception as e:
            print(f"[AutoFix] Error applying fixes: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                "success": False,
                "fixesApplied": [],
                "message": f"Error applying fixes: {str(e)}",
            }
