"""
PDF Extract Kit Integration Module
Provides advanced PDF processing using PDF-Extract-Kit when available
"""

import os
import sys
import importlib
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from huggingface_hub import snapshot_download
import pdfplumber  # for fallback
import json
# --- Step 1: Dynamic model download (only once per cold start) ---
MODEL_DIR = "/tmp/pdf_extract_models"

if not os.path.exists(os.path.join(MODEL_DIR, "pdf_extract")):
    print("[PDF-Extract-Kit] Downloading model package from Hugging Face...")
    snapshot_download(
        repo_id="opendatalab/pdf-extract-kit-1.0",
        local_dir=MODEL_DIR,
        max_workers=8
    )
    print("[PDF-Extract-Kit] Download complete.")

# --- Step 2: Add to Python path so importlib can find it ---
sys.path.insert(0, MODEL_DIR)

if TYPE_CHECKING:
    from pdf_extract import PDFExtractor
else:
    PDFExtractor = Any


# --- Step 3: PDF Extract Kit Wrapper Class ---
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
            module = importlib.import_module("pdf_extract")
            extractor_class = getattr(module, "PDFExtractor", None)

            if extractor_class is None:
                raise ImportError("PDFExtractor not found in pdf_extract module")

            self.extractor = extractor_class()
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

    # --- Core extraction ---
    def extract_content(self, pdf_path: str) -> Dict[str, Any]:
        if not self.available:
            return self._basic_extraction(pdf_path)

        try:
            print(f"[PDF-Extract-Kit] Extracting content from {pdf_path}")
            result = self.extractor.extract(pdf_path)
            processed_result = {
                "pages": result.get("pages", []),
                "tables": result.get("tables", []),
                "images": result.get("images", []),
                "forms": result.get("forms", []),
                "structure": {
                    "headings": result.get("headings", []),
                    "paragraphs": result.get("paragraphs", []),
                    "lists": result.get("lists", []),
                    "reading_order": result.get("reading_order", []),
                },
                "metadata": result.get("metadata", {}),
            }

            print(f"[PDF-Extract-Kit] Extraction complete: "
                  f"{len(processed_result['pages'])} pages")
            return processed_result

        except Exception as e:
            print(f"[PDF-Extract-Kit] Extraction error: {e}")
            import traceback
            traceback.print_exc()
            return self._basic_extraction(pdf_path)

    # --- Fallback extraction using pdfplumber ---
    def _basic_extraction(self, pdf_path: str) -> Dict[str, Any]:
        print("[PDF-Extract-Kit] Using basic extraction fallback")
        result = {
            "pages": [], "tables": [], "images": [], "forms": [],
            "structure": {}, "metadata": {},
        }

        try:
            with pdfplumber.open(pdf_path) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""
                    result["pages"].append({"page_number": i, "text": text})
        except Exception as e:
            print(f"[Fallback extraction error] {e}")

        return result


# --- Step 4: Global instance helper ---
_pdf_extract_kit = None


def get_pdf_extract_kit() -> PDFExtractKitProcessor:
    global _pdf_extract_kit
    if _pdf_extract_kit is None:
        _pdf_extract_kit = PDFExtractKitProcessor()
    return _pdf_extract_kit
