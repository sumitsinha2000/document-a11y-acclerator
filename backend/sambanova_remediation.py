"""
SambaNova AI-powered PDF Remediation Engine
Uses SambaNova's fast inference to intelligently suggest and apply PDF accessibility fixes
"""

import os
from typing import Dict, List, Any, Optional
from sambanova import SambaNova

class SambaNovaRemediationEngine:
    """AI-powered remediation engine using SambaNova for intelligent PDF accessibility fixes"""
    
    def __init__(self):
        """Initialize SambaNova client with API key from environment"""
        self.api_key = os.environ.get('SAMBANOVA_API_KEY')
        self.base_url = os.environ.get('SAMBANOVA_BASE_URL', 'https://api.sambanova.ai/v1')
        self.model = os.environ.get('SAMBANOVA_MODEL', 'Meta-Llama-3.3-70B-Instruct')
        
        if not self.api_key:
            raise ValueError("SAMBANOVA_API_KEY environment variable not set")
        
        self.client = SambaNova(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        print(f"[SambaNova] ✓ Initialized with model: {self.model}")
    
    def analyze_issues(self, issues: Dict[str, List[Any]]) -> Dict[str, Any]:
        """
        Analyze PDF accessibility issues using AI to provide intelligent remediation strategies
        
        Args:
            issues: Dictionary of accessibility issues by category
            
        Returns:
            Dictionary with AI-generated remediation strategies
        """
        try:
            # Prepare issue summary for AI analysis
            issue_summary = self._prepare_issue_summary(issues)
            
            # Create prompt for AI analysis
            prompt = self._create_analysis_prompt(issue_summary)
            
            print(f"[SambaNova] Analyzing {sum(len(v) for v in issues.values())} issues with AI...")
            
            # Call SambaNova API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert PDF accessibility remediation specialist. Analyze accessibility issues and provide actionable, prioritized remediation strategies following WCAG 2.1, PDF/UA-1, and PDF/A standards."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,  # Lower temperature for more consistent, factual responses
                max_tokens=2000
            )
            
            ai_response = response.choices[0].message.content
            print(f"[SambaNova] ✓ AI analysis complete")
            
            # Parse AI response into structured remediation plan
            remediation_plan = self._parse_ai_response(ai_response, issues)
            
            return remediation_plan
            
        except Exception as e:
            print(f"[SambaNova] ERROR: AI analysis failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'error': str(e),
                'strategies': []
            }
    
    def generate_alt_text(self, image_context: Dict[str, Any]) -> str:
        """
        Generate descriptive alt text for images using AI
        
        Args:
            image_context: Dictionary with image information (page, position, surrounding text)
            
        Returns:
            AI-generated alt text
        """
        try:
            prompt = f"""Generate concise, descriptive alt text for an image in a PDF document.

Context:
- Page: {image_context.get('page', 'Unknown')}
- Position: {image_context.get('position', 'Unknown')}
- Surrounding text: {image_context.get('surrounding_text', 'None')}
- Image type: {image_context.get('image_type', 'Unknown')}

Requirements:
- Be concise (max 125 characters)
- Describe the content and purpose
- Consider the document context
- Follow WCAG 2.1 guidelines

Alt text:"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an accessibility expert specializing in writing effective alt text for images in documents."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.5,
                max_tokens=100
            )
            
            alt_text = response.choices[0].message.content.strip()
            print(f"[SambaNova] ✓ Generated alt text: {alt_text[:50]}...")
            
            return alt_text
            
        except Exception as e:
            print(f"[SambaNova] ERROR: Alt text generation failed: {e}")
            return "Image description unavailable"
    
    def suggest_document_structure(self, content_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Suggest optimal document structure and tagging using AI
        
        Args:
            content_analysis: Analysis of document content
            
        Returns:
            Suggested structure with headings, reading order, and tags
        """
        try:
            prompt = f"""Analyze this PDF document content and suggest an optimal accessibility structure.

Document Analysis:
- Total pages: {content_analysis.get('total_pages', 'Unknown')}
- Has text: {content_analysis.get('has_text', False)}
- Has images: {content_analysis.get('has_images', False)}
- Has tables: {content_analysis.get('has_tables', False)}
- Current structure: {content_analysis.get('current_structure', 'None')}

Provide:
1. Suggested heading hierarchy (H1-H6)
2. Recommended reading order
3. Required structure tags
4. Logical document outline

Format as JSON with keys: headings, reading_order, tags, outline"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a PDF accessibility expert specializing in document structure and tagging for WCAG and PDF/UA compliance."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=1500
            )
            
            structure_suggestion = response.choices[0].message.content
            print(f"[SambaNova] ✓ Generated structure suggestions")
            
            # Parse JSON response
            import json
            try:
                structure_data = json.loads(structure_suggestion)
            except:
                # If not valid JSON, return as text
                structure_data = {
                    'raw_suggestion': structure_suggestion
                }
            
            return {
                'success': True,
                'structure': structure_data
            }
            
        except Exception as e:
            print(f"[SambaNova] ERROR: Structure suggestion failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def prioritize_fixes(self, issues: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        """
        Use AI to intelligently prioritize fixes based on impact and effort
        
        Args:
            issues: Dictionary of accessibility issues
            
        Returns:
            Prioritized list of fixes with reasoning
        """
        try:
            issue_summary = self._prepare_issue_summary(issues)
            
            prompt = f"""Prioritize these PDF accessibility issues for remediation.

Issues:
{issue_summary}

For each issue, provide:
1. Priority (Critical/High/Medium/Low)
2. Impact on accessibility (1-10)
3. Effort to fix (1-10)
4. Recommended fix order
5. Brief reasoning

Format as JSON array with keys: issue, priority, impact, effort, order, reasoning"""
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an accessibility expert who prioritizes remediation work based on WCAG impact and practical implementation effort."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            prioritization = response.choices[0].message.content
            print(f"[SambaNova] ✓ Generated fix prioritization")
            
            # Parse JSON response
            import json
            try:
                priority_data = json.loads(prioritization)
                if isinstance(priority_data, list):
                    return priority_data
                else:
                    return [priority_data]
            except:
                return [{
                    'raw_prioritization': prioritization
                }]
            
        except Exception as e:
            print(f"[SambaNova] ERROR: Prioritization failed: {e}")
            return []
    
    def _prepare_issue_summary(self, issues: Dict[str, List[Any]]) -> str:
        """Prepare a concise summary of issues for AI analysis"""
        summary_parts = []
        
        for category, issue_list in issues.items():
            if issue_list and len(issue_list) > 0:
                summary_parts.append(f"\n{category}: {len(issue_list)} issues")
                # Include first few issues as examples
                for i, issue in enumerate(issue_list[:3]):
                    if isinstance(issue, dict):
                        desc = issue.get('description', issue.get('message', str(issue)))
                    else:
                        desc = str(issue)
                    summary_parts.append(f"  - {desc}")
                
                if len(issue_list) > 3:
                    summary_parts.append(f"  ... and {len(issue_list) - 3} more")
        
        return "\n".join(summary_parts)
    
    def _create_analysis_prompt(self, issue_summary: str) -> str:
        """Create a detailed prompt for AI analysis"""
        return f"""Analyze these PDF accessibility issues and provide a comprehensive remediation strategy.

Issues Found:
{issue_summary}

Please provide:
1. Overall assessment of accessibility compliance
2. Critical issues that must be fixed first
3. Recommended remediation approach (automated vs manual)
4. Estimated effort and timeline
5. Specific actionable steps for each issue category
6. Best practices to prevent future issues

Focus on WCAG 2.1 Level AA, PDF/UA-1, and PDF/A compliance."""
    
    def _parse_ai_response(self, ai_response: str, original_issues: Dict[str, List[Any]]) -> Dict[str, Any]:
        """Parse AI response into structured remediation plan"""
        return {
            'success': True,
            'ai_analysis': ai_response,
            'total_issues': sum(len(v) for v in original_issues.values()),
            'issue_categories': list(original_issues.keys()),
            'recommendations': self._extract_recommendations(ai_response),
            'estimated_effort': self._extract_effort_estimate(ai_response)
        }
    
    def _extract_recommendations(self, ai_response: str) -> List[str]:
        """Extract actionable recommendations from AI response"""
        # Simple extraction - look for numbered lists or bullet points
        recommendations = []
        lines = ai_response.split('\n')
        
        for line in lines:
            line = line.strip()
            # Look for numbered items (1., 2., etc.) or bullet points (-, *, •)
            if line and (line[0].isdigit() or line.startswith(('-', '*', '•'))):
                # Clean up the line
                cleaned = line.lstrip('0123456789.-*• ').strip()
                if cleaned and len(cleaned) > 10:  # Ignore very short lines
                    recommendations.append(cleaned)
        
        return recommendations[:10]  # Return top 10 recommendations
    
    def _extract_effort_estimate(self, ai_response: str) -> str:
        """Extract effort estimate from AI response"""
        # Look for time-related keywords
        time_keywords = ['hour', 'day', 'week', 'minute', 'time', 'effort']
        lines = ai_response.lower().split('\n')
        
        for line in lines:
            if any(keyword in line for keyword in time_keywords):
                return line.strip()
        
        return "Effort estimate not provided"


def get_ai_remediation_engine() -> Optional[SambaNovaRemediationEngine]:
    """
    Get SambaNova remediation engine instance if API key is configured
    
    Returns:
        SambaNovaRemediationEngine instance or None if not configured
    """
    try:
        if os.environ.get('SAMBANOVA_API_KEY'):
            return SambaNovaRemediationEngine()
        else:
            print("[SambaNova] API key not configured, AI remediation unavailable")
            return None
    except Exception as e:
        print(f"[SambaNova] Failed to initialize: {e}")
        return None
