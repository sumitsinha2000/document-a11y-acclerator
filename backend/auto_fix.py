"""
Legacy Auto-Fix Module
Compatibility wrapper that forwards to the modern remediation engine.
"""

from typing import Any, Dict, Optional
from pathlib import Path
import warnings

from backend.auto_fix_engine import AutoFixEngine as ModernAutoFixEngine


class AutoFixEngine:
    """Legacy automated fix engine kept for compatibility/testing."""

    def __init__(self) -> None:
        self._engine = ModernAutoFixEngine()

    def _warn_deprecated(self, method: str) -> None:
        warnings.warn(
            "backend.auto_fix.AutoFixEngine is deprecated; use backend.auto_fix_engine.AutoFixEngine instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        print(
            f"[LegacyAutoFixEngine] backend.auto_fix.AutoFixEngine.{method} -> "
            f"backend.auto_fix_engine.AutoFixEngine.{method}"
        )

    def _looks_like_scan_data(self, scan_data: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(scan_data, dict):
            return False
        return any(
            key in scan_data
            for key in ("resolved_file_path", "scan_results", "scanResults", "filename", "file_path")
        )

    def _looks_like_path(self, value: Any) -> bool:
        if isinstance(value, Path):
            return True
        if not isinstance(value, str):
            return False
        return value.endswith(".pdf") or "/" in value or "\\" in value

    def _normalize_result(self, result: Any) -> Any:
        if not isinstance(result, dict):
            return result
        if "fixedTempPath" in result and "outputPath" not in result:
            result["outputPath"] = result["fixedTempPath"]
        result.setdefault("fixesApplied", [])
        result.setdefault("successCount", len(result.get("fixesApplied") or []))
        if "message" not in result and "error" in result:
            result["message"] = result["error"]
        return result

    def generate_fixes(self, scan_results: Dict[str, Any]) -> Dict[str, Any]:
        self._warn_deprecated("generate_fixes")
        return self._engine.generate_fixes(scan_results)

    def apply_automated_fixes(
        self, pdf_path: str, scan_results: Optional[Dict[str, Any]] = None, tracker=None
    ) -> Dict[str, Any]:
        self._warn_deprecated("apply_automated_fixes")

        if self._looks_like_scan_data(scan_results) or not self._looks_like_path(pdf_path):
            result = self._engine.apply_automated_fixes(pdf_path, scan_results or {}, tracker)
            return self._normalize_result(result)

        input_path = Path(pdf_path)
        scan_id = f"legacy_{input_path.stem}"
        payload = scan_results
        if isinstance(scan_results, dict):
            inner_results = scan_results.get("results")
            if isinstance(inner_results, dict):
                payload = inner_results

        scan_data = {
            "filename": input_path.name,
            "resolved_file_path": str(input_path),
            "scan_results": payload,
        }
        result = self._engine.apply_automated_fixes(scan_id, scan_data, tracker=None)
        return self._normalize_result(result)
