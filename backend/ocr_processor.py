"""
OCR Processing Module
Handles optical character recognition for scanned PDFs
"""

import pytesseract
from PIL import Image
import pdf2image
import io
from typing import Dict, List, Any
import PyPDF2
import pdfplumber


class OCRProcessor:
    """
    Processes PDFs with OCR to detect text in scanned documents.
    Identifies accessibility issues specific to scanned content.
    """

    def __init__(self):
        self.ocr_results = {
            "hasScannedContent": False,
            "textDetected": False,
            "ocrConfidence": 0,
            "issues": [],
        }

    def detect_scanned_content(self, pdf_path: str) -> Dict[str, Any]:
        """
        Detect if PDF contains scanned images without embedded text.
        
        Args:
            pdf_path: Path to the PDF file
            
        Returns:
            Dictionary with OCR detection results
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                pages_with_text = 0
                pages_with_images = 0
                scanned_pages = []
                total_confidence = 0
                confidence_count = 0
                
                for page_num, page in enumerate(pdf.pages, start=1):
                    # Check for embedded text
                    text = page.extract_text()
                    has_text = text and len(text.strip()) > 50  # At least 50 chars
                    
                    if has_text:
                        pages_with_text += 1
                    
                    # Check for images
                    images = page.images
                    if images and len(images) > 0:
                        pages_with_images += 1
                        
                        # If page has images but little/no text, it might be scanned
                        if not has_text:
                            scanned_pages.append(page_num)
                            
                            # Try OCR on the first few scanned pages to get confidence
                            if len(scanned_pages) <= 3:
                                try:
                                    # Convert page to image and run OCR
                                    images_from_page = pdf2image.convert_from_path(
                                        pdf_path,
                                        first_page=page_num,
                                        last_page=page_num,
                                        dpi=200
                                    )
                                    
                                    if images_from_page:
                                        # Run OCR with confidence data
                                        ocr_data = pytesseract.image_to_data(
                                            images_from_page[0],
                                            output_type=pytesseract.Output.DICT
                                        )
                                        
                                        # Calculate average confidence for detected text
                                        confidences = [
                                            int(conf) for conf in ocr_data['conf'] 
                                            if conf != '-1' and str(conf).isdigit()
                                        ]
                                        
                                        if confidences:
                                            avg_conf = sum(confidences) / len(confidences)
                                            total_confidence += avg_conf
                                            confidence_count += 1
                                            
                                except Exception as e:
                                    print(f"[OCR] Warning: Could not process page {page_num}: {e}")
                
                # Calculate results
                has_scanned = len(scanned_pages) > 0
                text_detected = pages_with_text > 0
                
                # Calculate overall OCR confidence (0-1 scale)
                ocr_confidence = 0
                if confidence_count > 0:
                    ocr_confidence = (total_confidence / confidence_count) / 100.0
                
                self.ocr_results["hasScannedContent"] = has_scanned
                self.ocr_results["textDetected"] = text_detected
                self.ocr_results["ocrConfidence"] = round(ocr_confidence, 2)
                self.ocr_results["issues"] = []
                
                # Add issues if scanned content detected
                if has_scanned:
                    self.ocr_results["issues"].append({
                        "type": "scanned_content",
                        "severity": "high",
                        "description": f"PDF contains {len(scanned_pages)} scanned page(s) without embedded text",
                        "pages": scanned_pages[:10],  # Limit to first 10 pages
                        "recommendation": "Run OCR to extract text and embed it in the PDF for accessibility. Consider using Adobe Acrobat Pro or similar tools.",
                    })
                    
                    if ocr_confidence < 0.7:
                        self.ocr_results["issues"].append({
                            "type": "low_ocr_quality",
                            "severity": "medium",
                            "description": f"OCR confidence is low ({ocr_confidence:.0%}), text extraction may be inaccurate",
                            "recommendation": "Consider rescanning documents at higher resolution (300+ DPI) for better text recognition.",
                        })
                
                print(f"[OCR] Analysis complete: {len(scanned_pages)} scanned pages found, confidence: {ocr_confidence:.2%}")
                
        except Exception as e:
            print(f"[OCR] Error during OCR processing: {e}")
            # Return safe defaults on error
            self.ocr_results["hasScannedContent"] = False
            self.ocr_results["textDetected"] = True
            self.ocr_results["ocrConfidence"] = 0
            self.ocr_results["issues"] = [{
                "type": "ocr_error",
                "severity": "low",
                "description": f"Could not perform OCR analysis: {str(e)}",
                "recommendation": "OCR analysis failed, but document may still be accessible.",
            }]

        return self.ocr_results

    def get_ocr_summary(self) -> Dict[str, Any]:
        """Get summary of OCR analysis"""
        return {
            "hasScannedContent": self.ocr_results["hasScannedContent"],
            "textDetected": self.ocr_results["textDetected"],
            "confidence": self.ocr_results["ocrConfidence"],
            "issueCount": len(self.ocr_results["issues"]),
        }
