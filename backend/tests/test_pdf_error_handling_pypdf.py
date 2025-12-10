from pathlib import Path
from typing import Any, Dict, Optional

import pytest

from backend.routes import scans as scans_routes


FAILURE_STATUS = "error"
TRACEBACK_MARKERS = ("traceback", 'file "', "pdfreaderror", "exception")


def _require_fixture(filename: str) -> Path:
    """Return a PDF fixture path or skip the test if it is missing."""
    pdf_path = Path(__file__).resolve().parent / "fixtures" / "error_handling" / filename
    if not pdf_path.exists():
        pytest.skip(f"Fixture PDF {filename} was not found at {pdf_path}")
    return pdf_path


def _patch_scan_side_effects(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Stub out storage/DB dependencies so the scan API stays self-contained in tests."""

    def _fake_upload(file_path: str, file_name: str, folder: Optional[str] = None):
        destination = tmp_path / file_name
        destination.write_bytes(Path(file_path).read_bytes())
        return {"storage": "local", "path": str(destination)}

    monkeypatch.setattr(scans_routes, "upload_file_with_fallback", _fake_upload)
    monkeypatch.setattr(scans_routes, "_temp_storage_root", lambda: tmp_path)
    monkeypatch.setattr(
        scans_routes, "save_scan_to_db", lambda scan_id, *_args, **_kwargs: scan_id
    )
    monkeypatch.setattr(scans_routes, "update_group_file_count", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(scans_routes, "NEON_DATABASE_URL", None)


def _invoke_scan(
    client,
    pdf_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Dict[str, Any]:
    """Upload a PDF to the public scan endpoint and return the parsed payload."""
    _patch_scan_side_effects(monkeypatch, tmp_path)
    with pdf_path.open("rb") as pdf_file:
        response = client.post(
            "/api/scan",
            files={"file": (pdf_path.name, pdf_file.read(), "application/pdf")},
            data={"group_id": "test-group"},
        )

    assert response.status_code < 500, "Scan endpoint should not expose server errors"
    payload = response.json()
    assert isinstance(payload, dict), "Scan endpoint should return a JSON object"
    return payload


def _extract_status(payload: Dict[str, Any]) -> Optional[str]:
    """Return a normalized status/statusCode from the payload or its summary."""
    summary = payload.get("summary") or {}
    for container in (payload, summary):
        value = container.get("statusCode") or container.get("status")
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized:
                return normalized
    return None


def _extract_error_message(payload: Dict[str, Any]) -> Optional[str]:
    """Return the first user-facing error message available in the payload."""
    summary = payload.get("summary") or {}
    candidates = []
    for container in (payload, summary):
        for key in ("error", "message", "errorMessage", "detail", "details"):
            value = container.get(key) if isinstance(container, dict) else None
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip())
    return candidates[0] if candidates else None


def _assert_clean_failure(
    payload: Dict[str, Any],
    pdf_path: Path,
) -> None:
    """Assert the scan response reports a clean, user-facing failure."""
    status = _extract_status(payload)
    assert status == FAILURE_STATUS, f"Expected failure status '{FAILURE_STATUS}', got {status!r}"

    message = _extract_error_message(payload)
    assert message, "Failure response should include a user-facing error message"

    lowered = message.lower()
    for marker in TRACEBACK_MARKERS:
        assert marker not in lowered, f"Error message should not expose '{marker}'"
    assert str(pdf_path) not in message, "Error message should not leak file paths"


def _assert_failed_analysis_shape(payload: Dict[str, Any]) -> None:
    """Ensure failed scans expose analysisErrors without fabricated compliance."""
    results = payload.get("results") or {}
    errors = results.get("analysisErrors")
    assert isinstance(errors, list) and errors, "analysisErrors should contain user-facing entries"
    for entry in errors:
        assert isinstance(entry, dict), "Each analysis error should be an object"
        assert entry.get("message"), "Each analysis error must include a message"

    assert not results.get("issues"), "Failed analyses should not report canonical issues"
    assert not results.get("poorContrast"), "Failed analyses should not fabricate contrast issues"

    summary = payload.get("summary") or {}
    assert summary.get("status") == FAILURE_STATUS
    assert summary.get("statusCode") == FAILURE_STATUS
    assert not summary.get("complianceScore"), "Compliance score should not be populated for failures"
    assert not summary.get("wcagCompliance"), "WCAG compliance should not be populated for failures"
    assert not summary.get("pdfuaCompliance"), "PDF/UA compliance should not be populated for failures"

    error_message = payload.get("error")
    assert error_message == errors[0].get("message"), "Top-level error should mirror analysisErrors entry"
    assert not payload.get("fixes"), "Failed analyses should not include fix suggestions"


def test_encrypted_pdf_returns_failed_status_not_stacktrace(
    client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Encrypted PDFs without a password should be reported as clean failures."""
    pdf_path = _require_fixture("encrypted_no_password.pdf")
    payload = _invoke_scan(client, pdf_path, monkeypatch, tmp_path)
    _assert_clean_failure(payload, pdf_path)
    _assert_failed_analysis_shape(payload)


def test_corrupted_pdf_returns_failed_status(
    client, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Structurally corrupted PDFs should surface the same failure status and message shape."""
    pdf_path = _require_fixture("truncated.pdf")
    payload = _invoke_scan(client, pdf_path, monkeypatch, tmp_path)
    _assert_clean_failure(payload, pdf_path)
    _assert_failed_analysis_shape(payload)
