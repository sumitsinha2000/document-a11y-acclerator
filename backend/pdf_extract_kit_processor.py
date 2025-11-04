"""
PDF Extract Kit Integration Module
Provides advanced PDF processing using PDF-Extract-Kit when available
"""

import os
import sys
import importlib
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from pathlib import Path
import json

if TYPE_CHECKING:
    from pdf_extract import PDFExtractor  # pragma: no cover
else:
    PDFExtractor = Any


class PDFExtractKitProcessor:
    """
    Advanced PDF processing using PDF-Extract-Kit.
    Falls back to basic processing if PDF-Extract-Kit is not available.
    """

    def __init__(self):
        self.available = False
        self.extractor = None
        self._initialize_pdf_extract_kit()

    def _initialize_pdf_extract_kit(self):
        """Initialize PDF-Extract-Kit if available"""
        try:
            # Try to import PDF-Extract-Kit modules
            # Adjust the import path based on your PDF-Extract-Kit installation
            module = importlib.import_module("pdf_extract")
            PDFExtractor = getattr(module, "PDFExtractor")

            self.extractor = PDFExtractor()
            self.available = True
            print("[PDF-Extract-Kit] Successfully initialized")
            
        except ImportError as e:
            print(f"[PDF-Extract-Kit] Not available: {e}")
            print("[PDF-Extract-Kit] Falling back to basic PDF processing")
            self.available = False
        except Exception as e:
            print(f"[PDF-Extract-Kit] Initialization error: {e}")
            self.available = False

    def is_available(self) -> bool:
        """Check if PDF-Extract-Kit is available"""
        return self.available

    def extract_content(self, pdf_path: str) -> Dict[str, Any]:
        """
        Extract comprehensive content from PDF using PDF-Extract-Kit.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing extracted content and structure
        """
        if not self.available:
            return self._basic_extraction(pdf_path)

        try:
            print(f"[PDF-Extract-Kit] Extracting content from {pdf_path}")
            
            # Use PDF-Extract-Kit for advanced extraction
            result = self.extractor.extract(pdf_path)
            
            # Process the extraction results
            processed_result = {
                "pages": [],
                "tables": [],
                "images": [],
                "forms": [],
                "structure": {},
                "metadata": {},
            }
            
            # Extract page-level information
            for page_num, page_data in enumerate(result.get("pages", []), start=1):
                page_info = {
                    "page_number": page_num,
                    "text": page_data.get("text", ""),
                    "layout": page_data.get("layout", {}),
                    "elements": page_data.get("elements", []),
                }
                processed_result["pages"].append(page_info)
            
            # Extract tables with structure
            for table in result.get("tables", []):
                table_info = {
                    "page": table.get("page", 1),
                    "bbox": table.get("bbox", []),
                    "rows": table.get("rows", []),
                    "columns": table.get("columns", []),
                    "has_header": table.get("has_header", False),
                    "cells": table.get("cells", []),
                }
                processed_result["tables"].append(table_info)
            
            # Extract images with metadata
            for image in result.get("images", []):
                image_info = {
                    "page": image.get("page", 1),
                    "bbox": image.get("bbox", []),
                    "type": image.get("type", "unknown"),
                    "has_alt_text": image.get("has_alt_text", False),
                    "alt_text": image.get("alt_text", ""),
                }
                processed_result["images"].append(image_info)
            
            # Extract form fields
            for form_field in result.get("forms", []):
                field_info = {
                    "page": form_field.get("page", 1),
                    "type": form_field.get("type", "text"),
                    "name": form_field.get("name", ""),
                    "label": form_field.get("label", ""),
                    "has_label": bool(form_field.get("label")),
                }
                processed_result["forms"].append(field_info)
            
            # Extract document structure
            processed_result["structure"] = {
                "headings": result.get("headings", []),
                "paragraphs": result.get("paragraphs", []),
                "lists": result.get("lists", []),
                "reading_order": result.get("reading_order", []),
            }
            
            # Extract metadata
            processed_result["metadata"] = result.get("metadata", {})
            
            print(f"[PDF-Extract-Kit] Extraction complete: {len(processed_result['pages'])} pages, "
                  f"{len(processed_result['tables'])} tables, {len(processed_result['images'])} images")
            
            return processed_result
            
        except Exception as e:
            print(f"[PDF-Extract-Kit] Extraction error: {e}")
            import traceback
            traceback.print_exc()
            return self._basic_extraction(pdf_path)

    def _basic_extraction(self, pdf_path: str) -> Dict[str, Any]:
        """Fallback basic extraction when PDF-Extract-Kit is not available"""
        print("[PDF-Extract-Kit] Using basic extraction fallback")
        
        import pdfplumber
        
        result = {
            "pages": [],
            "tables": [],
            "images": [],
            "forms": [],
            "structure": {},
            "metadata": {},
        }
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    # Extract text
                    text = page.extract_text() or ""
                    
                    result["pages"].append({
                        "page_number": page_num,
                        "text": text,
                        "layout": {},
                        "elements": [],
                    })
                    
                    # Extract tables
                    tables = page.find_tables()
                    for table in tables:
                        result["tables"].append({
                            "page": page_num,
                            "bbox": table.bbox if hasattr(table, 'bbox') else [],
                            "rows": len(table.rows) if hasattr(table, 'rows') else 0,
                            "columns": len(table.rows[0]) if hasattr(table, 'rows') and table.rows else 0,
                            "has_header": False,  # Cannot determine without advanced analysis
                            "cells": [],
                        })
                    
                    # Extract images
                    images = page.images
                    for image in images:
                        result["images"].append({
                            "page": page_num,
                            "bbox": [image.get('x0', 0), image.get('top', 0), 
                                   image.get('x1', 0), image.get('bottom', 0)],
                            "type": "image",
                            "has_alt_text": False,  # Cannot determine without advanced analysis
                            "alt_text": "",
                        })
                
        except Exception as e:
            print(f"[PDF-Extract-Kit] Basic extraction error: {e}")
        
        return result

    def analyze_accessibility(self, pdf_path: str) -> Dict[str, Any]:
        """
        Perform advanced accessibility analysis using PDF-Extract-Kit.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary containing accessibility issues and recommendations
        """
        content = self.extract_content(pdf_path)
        
        issues = {
            "structure": [],
            "tables": [],
            "images": [],
            "forms": [],
            "reading_order": [],
        }
        
        # Analyze structure
        if not content.get("structure", {}).get("headings"):
            issues["structure"].append({
                "severity": "high",
                "description": "Document lacks proper heading structure",
                "recommendation": "Add hierarchical headings (H1, H2, H3) to organize content",
            })
        
        # Analyze tables
        for table in content.get("tables", []):
            if not table.get("has_header"):
                issues["tables"].append({
                    "severity": "high",
                    "page": table.get("page", 1),
                    "description": f"Table on page {table.get('page', 1)} lacks header row markup",
                    "recommendation": "Mark the first row as table headers for screen reader navigation",
                })
        
        # Analyze images
        for image in content.get("images", []):
            if not image.get("has_alt_text"):
                issues["images"].append({
                    "severity": "high",
                    "page": image.get("page", 1),
                    "description": f"Image on page {image.get('page', 1)} lacks alternative text",
                    "recommendation": "Add descriptive alt text explaining the image content and purpose",
                })
        
        # Analyze forms
        for form_field in content.get("forms", []):
            if not form_field.get("has_label"):
                issues["forms"].append({
                    "severity": "high",
                    "page": form_field.get("page", 1),
                    "description": f"Form field '{form_field.get('name', 'unnamed')}' lacks a label",
                    "recommendation": "Add a descriptive label to help users understand the field purpose",
                })
        
        # Analyze reading order
        if not content.get("structure", {}).get("reading_order"):
            issues["reading_order"].append({
                "severity": "medium",
                "description": "Document reading order is not explicitly defined",
                "recommendation": "Define logical reading order for screen readers",
            })
        
        return issues


# Global instance
_pdf_extract_kit = None


def get_pdf_extract_kit() -> PDFExtractKitProcessor:
    """Get or create the global PDF-Extract-Kit processor instance"""
    global _pdf_extract_kit
    if _pdf_extract_kit is None:
        _pdf_extract_kit = PDFExtractKitProcessor()
    return _pdf_extract_kit
