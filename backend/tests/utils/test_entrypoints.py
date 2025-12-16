"""
Helper entrypoints that mirror the production scan pipeline for tests.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Union

from backend.utils.app_helpers import _analyze_pdf_document

PDF_FIXTURE_DIR = Path(__file__).parents[1] / "fixtures"


def _resolve_pdf_path(pdf: Union[Path, str]) -> Path:
    """Resolve a PDF path, defaulting to the fixture directory for relative names."""
    pdf_path = Path(pdf)
    if not pdf_path.is_absolute():
        pdf_path = PDF_FIXTURE_DIR / pdf_path
    return pdf_path


def run_scan_for_tests(pdf: Union[Path, str]) -> Dict[str, Any]:
    """
    Run the full analyzer pipeline the same way the API does and return the payload.
    Accepts either an absolute path or a fixture filename (resolved under fixtures/pdfs).
    """
    pdf_path = _resolve_pdf_path(pdf)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF fixture not found at {pdf_path}")
    return asyncio.run(_analyze_pdf_document(pdf_path))
