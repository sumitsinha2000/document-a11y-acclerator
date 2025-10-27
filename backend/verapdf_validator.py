"""
veraPDF Validator Integration
Provides WCAG 2.1 and PDF/UA compliance validation using veraPDF CLI
"""

import subprocess
import json
import os
from typing import Dict, List, Any, Optional
from pathlib import Path


class VeraPDFValidator:
    """
    Integrates veraPDF CLI for comprehensive PDF/UA and WCAG 2.1 validation.
    veraPDF is an open-source industry-standard PDF validator.
    """
    
    def __init__(self):
        self.verapdf_command = None
        self.verapdf_available = self._check_verapdf_installation()
        if self.verapdf_available:
            print(f"[VeraPDF] veraPDF is available: {self.verapdf_command}")
        else:
            print("[VeraPDF] veraPDF not found - install from https://verapdf.org/")
    
    def _check_verapdf_installation(self) -> bool:
        """Check if veraPDF CLI is installed and accessible"""
        # Try 1: Check for verapdf wrapper script/executable
        try:
            result = subprocess.run(
                ['verapdf', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                self.verapdf_command = ['verapdf']
                print("[VeraPDF] Found verapdf wrapper script")
                return True
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        
        # Try 2: Check for Java and veraPDF JAR file
        java_available = self._check_java()
        if not java_available:
            print("[VeraPDF] Java not found - required for veraPDF JAR execution")
            return False
        
        # Look for veraPDF JAR in common locations
        jar_path = self._find_verapdf_jar()
        if jar_path:
            self.verapdf_command = ['java', '-jar', jar_path]
            print(f"[VeraPDF] Found veraPDF JAR: {jar_path}")
            return True
        
        return False
    
    def _check_java(self) -> bool:
        """Check if Java is installed and accessible"""
        try:
            result = subprocess.run(
                ['java', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print("[VeraPDF] Java is available")
                return True
        except (subprocess.SubprocessError, FileNotFoundError):
            pass
        return False
    
    def _find_verapdf_jar(self) -> Optional[str]:
        """Find veraPDF JAR file in common installation locations"""
        # Common installation paths
        possible_paths = [
            # Windows
            r"C:\Program Files\veraPDF\verapdf.jar",
            r"C:\Program Files (x86)\verapdf\verapdf.jar",
            r"C:\veraPDF\verapdf.jar",
            # User-specific Windows paths
            os.path.expanduser(r"~\verapdf\verapdf.jar"),
            os.path.expanduser(r"~\AppData\Local\ververapdfaPDF\verapdf.jar"),
            # Linux/Mac
            "/usr/local/verapdf/verapdf.jar",
            "/opt/verapdf/verapdf.jar",
            os.path.expanduser("~/verapdf/verapdf.jar"),
            # Environment variable
            os.environ.get('VERAPDF_JAR', ''),
        ]
        
        # Also check for verapdf-gui.jar (alternative name)
        jar_names = ['verapdf.jar', 'verapdf-gui.jar', 'verapdf-cli.jar']
        
        for base_path in possible_paths:
            if not base_path:
                continue
            
            # Check exact path
            if os.path.isfile(base_path):
                print(f"[VeraPDF] Found JAR at: {base_path}")
                return base_path
            
            # Check directory for JAR files
            if os.path.isdir(base_path):
                for jar_name in jar_names:
                    jar_path = os.path.join(base_path, jar_name)
                    if os.path.isfile(jar_path):
                        print(f"[VeraPDF] Found JAR at: {jar_path}")
                        return jar_path
            
            # Check parent directory
            parent_dir = os.path.dirname(base_path)
            if os.path.isdir(parent_dir):
                for jar_name in jar_names:
                    jar_path = os.path.join(parent_dir, jar_name)
                    if os.path.isfile(jar_path):
                        print(f"[VeraPDF] Found JAR at: {jar_path}")
                        return jar_path
        
        # Try to find in current directory and subdirectories
        current_dir = os.getcwd()
        for root, dirs, files in os.walk(current_dir):
            for jar_name in jar_names:
                if jar_name in files:
                    jar_path = os.path.join(root, jar_name)
                    print(f"[VeraPDF] Found JAR at: {jar_path}")
                    return jar_path
            # Don't search too deep
            if root.count(os.sep) - current_dir.count(os.sep) > 2:
                break
        
        return None
    
    def is_available(self) -> bool:
        """Check if veraPDF validator is available"""
        return self.verapdf_available
    
    def validate(self, pdf_path: str) -> Dict[str, Any]:
        """
        Validate PDF for PDF/UA and WCAG compliance using veraPDF.
        
        Args:
            pdf_path: Path to the PDF file to validate
            
        Returns:
            Dictionary containing validation results with WCAG and PDF/UA issues
        """
        if not self.verapdf_available or not self.verapdf_command:
            print("[VeraPDF] Validator not available, skipping validation")
            return self._get_empty_results()
        
        try:
            print(f"[VeraPDF] Validating {pdf_path}")
            
            command = self.verapdf_command + [
                '--format', 'json',  # JSON output for parsing
                '--flavour', 'ua1',  # PDF/UA-1 profile (accessibility)
                pdf_path
            ]
            
            print(f"[VeraPDF] Running command: {' '.join(command)}")
            
            # Run veraPDF with PDF/UA profile and JSON output
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=60  # 60 second timeout
            )
            
            if result.returncode != 0:
                print(f"[VeraPDF] Validation failed with return code {result.returncode}")
                print(f"[VeraPDF] Error: {result.stderr}")
                return self._get_empty_results()
            
            # Parse JSON output
            validation_data = json.loads(result.stdout)
            
            # Extract and categorize issues
            issues = self._parse_verapdf_results(validation_data)
            
            print(f"[VeraPDF] Found {len(issues.get('wcagIssues', []))} WCAG issues")
            print(f"[VeraPDF] Found {len(issues.get('pdfuaIssues', []))} PDF/UA issues")
            
            return issues
            
        except subprocess.TimeoutExpired:
            print("[VeraPDF] Validation timed out after 60 seconds")
            return self._get_empty_results()
        except json.JSONDecodeError as e:
            print(f"[VeraPDF] Failed to parse JSON output: {e}")
            return self._get_empty_results()
        except Exception as e:
            print(f"[VeraPDF] Validation error: {e}")
            import traceback
            traceback.print_exc()
            return self._get_empty_results()
    
    def _parse_verapdf_results(self, validation_data: Dict) -> Dict[str, Any]:
        """
        Parse veraPDF JSON output and categorize issues.
        
        Args:
            validation_data: Raw JSON data from veraPDF
            
        Returns:
            Categorized accessibility issues
        """
        issues = {
            'wcagIssues': [],
            'pdfuaIssues': [],
            'structureIssues': [],
            'metadataIssues': []
        }
        
        try:
            # Extract validation results
            jobs = validation_data.get('jobs', [])
            if not jobs:
                return issues
            
            job = jobs[0]
            validation_result = job.get('validationResult', {})
            
            # Check if document is compliant
            is_compliant = validation_result.get('compliant', False)
            
            if is_compliant:
                print("[VeraPDF] Document is PDF/UA compliant")
                return issues
            
            # Extract test assertions (failed checks)
            test_assertions = validation_result.get('testAssertions', [])
            
            for assertion in test_assertions:
                status = assertion.get('status')
                if status != 'FAILED':
                    continue
                
                # Extract issue details
                rule_id = assertion.get('ruleId', {})
                specification = rule_id.get('specification', '')
                clause = rule_id.get('clause', '')
                test_number = rule_id.get('testNumber', '')
                
                message = assertion.get('message', 'Accessibility issue detected')
                location = assertion.get('location', {})
                context = location.get('context', '')
                
                # Determine severity based on specification
                severity = self._determine_severity(specification, clause)
                
                # Categorize issue
                issue_data = {
                    'severity': severity,
                    'specification': specification,
                    'clause': clause,
                    'testNumber': test_number,
                    'description': message,
                    'context': context,
                    'recommendation': self._get_recommendation(specification, clause)
                }
                
                # Add to appropriate category
                if 'ISO 14289' in specification or 'PDF/UA' in specification:
                    issues['pdfuaIssues'].append(issue_data)
                
                # Map to WCAG categories
                wcag_mapping = self._map_to_wcag(specification, clause)
                if wcag_mapping:
                    issue_data['wcagCriterion'] = wcag_mapping['criterion']
                    issue_data['wcagLevel'] = wcag_mapping['level']
                    issues['wcagIssues'].append(issue_data)
                
                # Categorize by type
                if 'structure' in message.lower() or 'tag' in message.lower():
                    issues['structureIssues'].append(issue_data)
                elif 'metadata' in message.lower() or 'title' in message.lower():
                    issues['metadataIssues'].append(issue_data)
            
            print(f"[VeraPDF] Parsed {len(test_assertions)} test assertions")
            
        except Exception as e:
            print(f"[VeraPDF] Error parsing results: {e}")
            import traceback
            traceback.print_exc()
        
        return issues
    
    def _determine_severity(self, specification: str, clause: str) -> str:
        """Determine issue severity based on specification and clause"""
        # Critical PDF/UA requirements
        if any(keyword in clause.lower() for keyword in ['7.1', '7.2', '7.3']):
            return 'high'
        
        # Structure and tagging issues
        if 'structure' in specification.lower() or 'tag' in specification.lower():
            return 'high'
        
        # Metadata issues
        if 'metadata' in specification.lower():
            return 'medium'
        
        return 'medium'
    
    def _map_to_wcag(self, specification: str, clause: str) -> Optional[Dict[str, str]]:
        """
        Map PDF/UA requirements to WCAG 2.1 success criteria.
        
        Returns:
            Dictionary with 'criterion' and 'level' keys, or None
        """
        # Common mappings between PDF/UA and WCAG 2.1
        mappings = {
            '7.1': {'criterion': '1.3.1', 'level': 'A', 'name': 'Info and Relationships'},
            '7.2': {'criterion': '2.4.2', 'level': 'A', 'name': 'Page Titled'},
            '7.3': {'criterion': '3.1.1', 'level': 'A', 'name': 'Language of Page'},
            '7.4': {'criterion': '1.3.2', 'level': 'A', 'name': 'Meaningful Sequence'},
            '7.18': {'criterion': '1.1.1', 'level': 'A', 'name': 'Non-text Content'},
            '7.20': {'criterion': '1.3.1', 'level': 'A', 'name': 'Table Structure'},
        }
        
        # Extract clause number
        for key, value in mappings.items():
            if key in clause:
                return value
        
        return None
    
    def _get_recommendation(self, specification: str, clause: str) -> str:
        """Get remediation recommendation based on the issue type"""
        recommendations = {
            '7.1': 'Add proper document structure tags using a PDF editor',
            '7.2': 'Set document title in PDF metadata properties',
            '7.3': 'Specify document language in PDF properties (e.g., en-US)',
            '7.4': 'Ensure content reading order matches logical document flow',
            '7.18': 'Add alternative text descriptions to all images and figures',
            '7.20': 'Add proper table header markup and structure tags',
        }
        
        for key, recommendation in recommendations.items():
            if key in clause:
                return recommendation
        
        return 'Review and fix accessibility issue using Adobe Acrobat Pro or similar tool'
    
    def _get_empty_results(self) -> Dict[str, Any]:
        """Return empty results structure"""
        return {
            'wcagIssues': [],
            'pdfuaIssues': [],
            'structureIssues': [],
            'metadataIssues': []
        }
    
    def get_compliance_summary(self, validation_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate compliance summary from validation results.
        
        Args:
            validation_results: Results from validate() method
            
        Returns:
            Summary with compliance scores and issue counts
        """
        wcag_issues = len(validation_results.get('wcagIssues', []))
        pdfua_issues = len(validation_results.get('pdfuaIssues', []))
        total_issues = wcag_issues + pdfua_issues
        
        # Calculate compliance scores
        wcag_score = max(0, 100 - (wcag_issues * 10))
        pdfua_score = max(0, 100 - (pdfua_issues * 10))
        
        return {
            'wcagCompliance': wcag_score,
            'pdfuaCompliance': pdfua_score,
            'totalVeraPDFIssues': total_issues,
            'wcagIssueCount': wcag_issues,
            'pdfuaIssueCount': pdfua_issues,
            'isCompliant': total_issues == 0
        }
