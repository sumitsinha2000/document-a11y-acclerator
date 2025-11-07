from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import json
from datetime import datetime
import threading
import time
from pathlib import Path
import shutil
import uuid  # ✅ Added import for unique ID generation
import re

import psycopg2
from psycopg2.extras import RealDictCursor

from pdf_analyzer import PDFAccessibilityAnalyzer
from fix_suggestions import generate_fix_suggestions
from auto_fix_engine import AutoFixEngine
from fix_progress_tracker import create_progress_tracker, get_progress_tracker
from pdf_generator import PDFGenerator
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

DATABASE_URL = os.getenv("DATABASE_URL")

db_lock = threading.Lock()

UPLOAD_FOLDER = "uploads"
FIXED_FOLDER = "fixed"
pdf_generator = PDFGenerator()
GENERATED_PDFS_FOLDER = pdf_generator.output_dir


VERSION_FILENAME_PATTERN = re.compile(r"_v(\d+)\.pdf$", re.IGNORECASE)


def _truthy(value):
    """Small helper to interpret truthy string query params."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _fixed_scan_dir(scan_id, ensure_exists=False):
    """Return the directory that stores versioned fixed PDFs for the scan."""
    path = Path(FIXED_FOLDER) / str(scan_id)
    if ensure_exists:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _sanitize_version_base(original_name, fallback):
    """Generate a safe base filename for versioned PDFs."""
    candidate = ""
    if original_name:
        candidate = Path(original_name).stem
    candidate = secure_filename(candidate) if candidate else ""
    if not candidate:
        candidate = secure_filename(str(fallback)) or str(fallback)
    return candidate


def _extract_version_from_path(path_obj):
    """Extract numeric version from filename like *_v3.pdf."""
    match = VERSION_FILENAME_PATTERN.search(path_obj.name)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            return None
    return None


def get_versioned_files(scan_id):
    """List all stored fixed PDF versions for a scan."""
    scan_dir = _fixed_scan_dir(scan_id, ensure_exists=False)
    if not scan_dir.exists():
        return []

    base_dir = Path(FIXED_FOLDER)
    entries = []
    for path in scan_dir.glob("*.pdf"):
        version_number = _extract_version_from_path(path)
        if version_number is None:
            continue
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        entries.append(
            {
                "version": version_number,
                "absolute_path": path,
                "relative_path": str(path.relative_to(base_dir)),
                "filename": path.name,
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime),
            }
        )

    entries.sort(key=lambda item: item["version"])
    return entries


def get_fixed_version(scan_id, version=None):
    """Return metadata for the latest or a specific fixed version."""
    versions = get_versioned_files(scan_id)
    if not versions:
        return None
    if version is None:
        return versions[-1]
    for entry in versions:
        if entry["version"] == version:
            return entry
    return None


def archive_fixed_pdf_version(scan_id, original_filename, source_path=None):
    """
    Copy the latest fixed PDF into the versioned archive directory.
    Returns metadata with version, filenames, and paths.
    """
    source = Path(source_path) if source_path else resolve_uploaded_file_path(scan_id)
    if not source or not source.exists():
        print(
            f"[Backend] ⚠ Cannot archive fixed PDF for {scan_id}; source file missing ({source_path})"
        )
        return None

    target_dir = _fixed_scan_dir(scan_id, ensure_exists=True)
    base_name = _sanitize_version_base(original_filename, scan_id)
    versions = get_versioned_files(scan_id)
    next_version = versions[-1]["version"] + 1 if versions else 1
    destination = target_dir / f"{base_name}_v{next_version}.pdf"

    while destination.exists():
        next_version += 1
        destination = target_dir / f"{base_name}_v{next_version}.pdf"

    shutil.copy2(source, destination)
    print(
        f"[Backend] ✓ Archived fixed PDF version V{next_version}: {destination}"
    )

    try:
        size = destination.stat().st_size
    except FileNotFoundError:
        size = None

    return {
        "version": next_version,
        "absolute_path": destination,
        "relative_path": str(destination.relative_to(Path(FIXED_FOLDER))),
        "filename": destination.name,
        "size": size,
    }


def prune_fixed_versions(scan_id, keep_latest=True):
    """Remove older archived fixed PDFs while optionally retaining the newest."""
    versions = get_versioned_files(scan_id)
    if not versions:
        return {"removed": 0, "removedFiles": [], "remainingVersions": 0}

    keep_count = 1 if keep_latest else 0
    if keep_count < 0:
        keep_count = 0
    if keep_count >= len(versions):
        return {
            "removed": 0,
            "removedFiles": [],
            "remainingVersions": len(versions),
        }

    cutoff_index = len(versions) - keep_count
    to_remove = versions[:cutoff_index]
    removed_files = []

    for entry in to_remove:
        path = entry["absolute_path"]
        try:
            if path.exists():
                path.unlink()
                removed_files.append(entry["relative_path"])
        except Exception as exc:
            print(f"[Backend] ⚠ Failed to delete version file {path}: {exc}")

    scan_dir = _fixed_scan_dir(scan_id)
    if scan_dir.exists():
        try:
            if not any(scan_dir.iterdir()):
                scan_dir.rmdir()
        except OSError:
            pass

    remaining_versions = len(versions) - len(removed_files)
    return {
        "removed": len(removed_files),
        "removedFiles": removed_files,
        "remainingVersions": remaining_versions,
    }


def should_scan_now(req):
    """Determine whether scan should run immediately based on request form data."""
    if not req:
        return True

    candidates = [
        req.form.get("scan_mode"),
        req.form.get("scanMode"),
        req.form.get("scan_now"),
        req.form.get("scanNow"),
        req.form.get("start_scan"),
        req.form.get("startScan"),
    ]

    for value in candidates:
        if value is None:
            continue
        normalized = str(value).strip().lower()
        if normalized in {
            "defer",
            "deferred",
            "upload",
            "upload_only",
            "upload-only",
            "no",
            "false",
            "0",
        }:
            return False
        if normalized in {
            "scan",
            "scan_now",
            "scan-now",
            "yes",
            "true",
            "1",
        }:
            return True
    return True


def build_placeholder_scan_payload():
    """Create a minimal scan payload for uploads where analysis is deferred."""
    base_status = build_verapdf_status({})
    return {
        "results": {},
        "summary": {
            "totalIssues": 0,
            "highSeverity": 0,
            "mediumSeverity": 0,
            "lowSeverity": 0,
            "complianceScore": 0,
        },
        "verapdfStatus": base_status,
        "fixes": [],
    }


def resolve_uploaded_file_path(scan_id, scan_record=None):
    """Locate the uploaded PDF for a scan."""
    uploads_dir = Path(UPLOAD_FOLDER)
    candidates = [
        uploads_dir / f"{scan_id}.pdf",
        uploads_dir / scan_id,
    ]

    if scan_record:
        possible_filename = scan_record.get("filename")
        if possible_filename:
            candidates.append(uploads_dir / secure_filename(possible_filename))

        stored_path = scan_record.get("file_path") if isinstance(scan_record, dict) else None
        if stored_path:
            candidates.append(Path(stored_path))

    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)

    latest_version = get_fixed_version(scan_id)
    if latest_version:
        return latest_version["absolute_path"]

    return None


# === Database Connection ===
def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"[Backend] ✗ Database connection failed: {e}")
        raise


def execute_query(query, params=None, fetch=False):
    with db_lock:
        conn = None
        cur = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(query, params or ())
            if fetch:
                result = cur.fetchall()
                conn.close()
                return result
            else:
                conn.commit()
                conn.close()
                return True
        except Exception as e:
            if conn:
                conn.rollback()
                conn.close()
            print(f"[Backend] ✗ Query execution failed: {e}")
            raise


def build_verapdf_status(results, analyzer=None):
    """Normalize veraPDF-style compliance status based on available data."""
    status = {
        "isActive": False,
        "wcagCompliance": None,
        "pdfuaCompliance": None,
        "totalVeraPDFIssues": 0,
    }

    if analyzer and hasattr(analyzer, "get_verapdf_status"):
        try:
            computed = analyzer.get_verapdf_status()
            if computed:
                return computed
        except Exception as e:
            print(f"[Backend] Warning: analyzer.get_verapdf_status failed: {e}")

    if not isinstance(results, dict):
        return status

    wcag_issues = len(results.get("wcagIssues", []))
    pdfua_issues = len(results.get("pdfuaIssues", []))

    total = wcag_issues + pdfua_issues
    status["totalVeraPDFIssues"] = total

    if total == 0:
        # No issues detected; assume compliance
        status["isActive"] = True
        status["wcagCompliance"] = 100
        status["pdfuaCompliance"] = 100
        return status

    if wcag_issues or pdfua_issues:
        status["isActive"] = True
        status["wcagCompliance"] = (
            max(0, 100 - wcag_issues * 10) if wcag_issues or pdfua_issues else 100
        )
        status["pdfuaCompliance"] = (
            max(0, 100 - pdfua_issues * 10) if pdfua_issues or wcag_issues else 100
        )

    return status


# === Fixed save_scan_to_db ===
def scan_results_changed(
    issues_before,
    summary_before,
    compliance_before,
    issues_after,
    summary_after,
    compliance_after,
):
    """Detect if there is any meaningful change between two scan states."""

    def _normalize_summary(summary):
        if not isinstance(summary, dict):
            return {}
        return summary

    def _normalize_issues(issues):
        if issues is None:
            return "{}"
        if isinstance(issues, (bytes, bytearray, memoryview)):
            try:
                issues = issues.decode()
            except Exception:
                issues = bytes(issues).decode(errors="ignore")
        if isinstance(issues, str):
            return issues
        try:
            return json.dumps(issues, sort_keys=True, default=str)
        except Exception:
            return str(issues)

    summary_before = _normalize_summary(summary_before)
    summary_after = _normalize_summary(summary_after)

    def _to_int(value):
        try:
            if value is None:
                return 0
            return int(round(float(value)))
        except Exception:
            return 0

    def _to_float(value):
        try:
            if value is None:
                return 0.0
            return round(float(value), 2)
        except Exception:
            return 0.0

    total_before = _to_int(summary_before.get("totalIssues", 0))
    total_after = _to_int(summary_after.get("totalIssues", total_before))
    high_before = _to_int(summary_before.get("highSeverity", 0))
    high_after = _to_int(summary_after.get("highSeverity", high_before))
    compliance_before_val = _to_float(compliance_before)
    compliance_after_val = _to_float(compliance_after)

    if total_before != total_after:
        return True
    if high_before != high_after:
        return True
    if compliance_before_val != compliance_after_val:
        return True

    return _normalize_issues(issues_before or {}) != _normalize_issues(
        issues_after or {}
    )


def save_scan_to_db(
    scan_id,
    filename,
    scan_results,
    batch_id=None,
    group_id=None,
    is_update=False,
    status=None,
    total_issues=None,
    issues_remaining=None,
    issues_fixed=None,
):
    """
    Unified save logic with group support:
    - Inserts a new record if is_update=False (always creates a new scan even if same file name).
    - Updates the existing record if is_update=True with "fixed" status.
    - Properly stores scan_results as JSONB with all issue data
    """
    conn = None
    c = None
    try:
        conn = get_db_connection()
        c = conn.cursor()

        if isinstance(scan_results, dict):
            if "results" in scan_results and "summary" in scan_results:
                formatted_results = dict(scan_results)
                if "verapdfStatus" not in formatted_results:
                    verapdf_status = build_verapdf_status(
                        formatted_results.get("results", {})
                    )
                    formatted_results["verapdfStatus"] = verapdf_status
                    try:
                        formatted_results["summary"] = (
                            PDFAccessibilityAnalyzer.calculate_summary(
                                formatted_results.get("results", {}), verapdf_status
                            )
                        )
                    except Exception as summary_error:
                        print(
                            f"[Backend] Warning: unable to recompute summary: {summary_error}"
                        )
            else:
                results_only = scan_results
                verapdf_status = build_verapdf_status(results_only)
                summary = PDFAccessibilityAnalyzer.calculate_summary(
                    results_only, verapdf_status
                )
                formatted_results = {
                    "results": results_only,
                    "summary": summary,
                    "verapdfStatus": verapdf_status,
                }
        else:
            formatted_results = scan_results

        # Ensure summary/results keys exist for downstream consumers
        if not isinstance(formatted_results, dict):
            formatted_results = {}
        formatted_results.setdefault("results", {})
        formatted_results.setdefault("summary", {})
        formatted_results.setdefault("verapdfStatus", build_verapdf_status({}))

        status_value = status or ("fixed" if is_update else "completed")
        total_issues_value = total_issues
        issues_remaining_value = issues_remaining
        issues_fixed_value = issues_fixed

        summary_data = formatted_results.get("summary") or {}
        if total_issues_value is None:
            total_issues_value = summary_data.get("totalIssues")
        if issues_remaining_value is None:
            issues_remaining_value = summary_data.get("totalIssues")
        if issues_fixed_value is None and summary_data:
            # Prefer stored value, otherwise derive from existing columns later
            issues_fixed_value = summary_data.get("issuesFixed")

        if is_update:
            # === UPDATE EXISTING SCAN ===
            print(f"[Backend] 🔄 Updating scan record: {scan_id}")
            query = """
                UPDATE scans
                SET scan_results = %s,
                    upload_date = NOW(),
                    status = %s,
                    total_issues = COALESCE(%s, total_issues),
                    issues_remaining = COALESCE(%s, issues_remaining),
                    issues_fixed = COALESCE(%s, issues_fixed)
                WHERE id = %s
            """
            c.execute(
                query,
                (
                    json.dumps(formatted_results),
                    status_value,
                    total_issues_value,
                    issues_remaining_value,
                    issues_fixed_value,
                    scan_id,
                ),
            )
            conn.commit()
            print(f"[Backend] ✅ Updated existing scan successfully: {scan_id}")
            return scan_id

        else:
            # === INSERT NEW SCAN (always new record, even same filename) ===
            try:
                query = """
                    INSERT INTO scans (id, filename, scan_results, batch_id, group_id, status, upload_date, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (id) DO UPDATE
                    SET scan_results = EXCLUDED.scan_results,
                        status = EXCLUDED.status,
                        group_id = EXCLUDED.group_id,
                        total_issues = COALESCE(EXCLUDED.total_issues, scans.total_issues),
                        issues_remaining = COALESCE(EXCLUDED.issues_remaining, scans.issues_remaining),
                        issues_fixed = COALESCE(EXCLUDED.issues_fixed, scans.issues_fixed),
                        created_at = NOW()
                """
                c.execute(
                    query,
                    (
                        scan_id,
                        filename,
                        json.dumps(formatted_results),
                        batch_id,
                        group_id,
                        status_value,
                    ),
                )
                if any(
                    value is not None
                    for value in (
                        total_issues_value,
                        issues_remaining_value,
                        issues_fixed_value,
                    )
                ):
                    c.execute(
                        """
                        UPDATE scans
                        SET total_issues = COALESCE(%s, total_issues),
                            issues_remaining = COALESCE(%s, issues_remaining),
                            issues_fixed = COALESCE(%s, issues_fixed)
                        WHERE id = %s
                    """,
                        (
                            total_issues_value,
                            issues_remaining_value,
                            issues_fixed_value,
                            scan_id,
                        ),
                    )
                conn.commit()

                issues_for_log = summary_data.get("totalIssues")
                if group_id:
                    update_group_count_query = """
                        UPDATE groups 
                        SET file_count = (SELECT COUNT(*) FROM scans WHERE group_id = %s)
                        WHERE id = %s
                    """
                    c.execute(update_group_count_query, (group_id, group_id))
                    conn.commit()

                print(
                    f"[Backend] ✅ Inserted new scan record: {scan_id} ({filename}) in group {group_id} with {issues_for_log or 0} issues"
                )
                return scan_id

            except Exception as e:
                conn.rollback()
                print(f"[Backend] ✗ Insert failed: {e}")
                import traceback

                traceback.print_exc()
                return None

    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[Backend] ✗ Failed to save scan: {e}")
        import traceback

        traceback.print_exc()
        return None
    finally:
        if c:
            c.close()
        if conn:
            conn.close()


# === Health Check ===
@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})


# === PDF Generator ===
@app.route("/api/generate-pdf", methods=["POST"])
def generate_pdf():
    payload = request.get_json(silent=True) or {}
    pdf_type = (payload.get("pdfType") or "inaccessible").lower()
    company_name = payload.get("companyName") or "BrightPath Consulting"
    services = payload.get("services") if isinstance(payload.get("services"), list) else None
    accessibility_options = (
        payload.get("accessibilityOptions")
        if isinstance(payload.get("accessibilityOptions"), dict)
        else None
    )

    try:
        if pdf_type == "accessible":
            output_path = pdf_generator.create_accessible_pdf(company_name, services)
        else:
            output_path = pdf_generator.create_inaccessible_pdf(
                company_name, services, accessibility_options
            )

        filename = os.path.basename(output_path)
        return jsonify({"filename": filename}), 201
    except Exception as e:
        print(f"[Backend] ✗ PDF generation failed: {e}")
        return jsonify({"error": "Failed to generate PDF"}), 500


@app.route("/api/generated-pdfs", methods=["GET"])
def list_generated_pdfs():
    try:
        pdfs = pdf_generator.get_generated_pdfs()
        return jsonify({"pdfs": pdfs})
    except Exception as e:
        print(f"[Backend] ✗ Listing generated PDFs failed: {e}")
        return jsonify({"error": "Unable to list generated PDFs"}), 500


@app.route("/api/download-generated/<path:filename>", methods=["GET"])
def download_generated_pdf(filename):
    safe_name = secure_filename(filename)
    if safe_name != filename:
        return jsonify({"error": "Invalid filename"}), 400

    file_path = os.path.join(GENERATED_PDFS_FOLDER, safe_name)
    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    return send_file(file_path, as_attachment=True, mimetype="application/pdf")


# === PDF Scan ===
@app.route("/api/scan", methods=["POST"])
def scan_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files supported"}), 400

    group_id = request.form.get("group_id")
    if not group_id:
        return jsonify({"error": "Group ID is required"}), 400

    scan_now = should_scan_now(request)
    scan_id = f"scan_{uuid.uuid4().hex}"
    upload_dir = Path(UPLOAD_FOLDER)
    upload_dir.mkdir(exist_ok=True)

    file_path = upload_dir / f"{scan_id}.pdf"
    file.save(str(file_path))
    print(f"[Backend] ✓ File saved: {file_path}")

    if not scan_now:
        placeholder_results = build_placeholder_scan_payload()
        saved_id = save_scan_to_db(
            scan_id,
            file.filename,
            placeholder_results,
            group_id=group_id,
            status="uploaded",
            total_issues=0,
            issues_remaining=0,
            issues_fixed=0,
        )
        print(
            f"[Backend] ✓ Deferred scan created for {saved_id} (group {group_id})"
        )
        return jsonify(
            {
                "scanId": saved_id,
                "filename": file.filename,
                "groupId": group_id,
                "status": "uploaded",
                "summary": placeholder_results.get("summary", {}),
                "results": placeholder_results.get("results", {}),
                "fixes": placeholder_results.get("fixes", []),
                "timestamp": datetime.now().isoformat(),
                "verapdfStatus": placeholder_results.get("verapdfStatus"),
                "scanDeferred": True,
            }
        )

    analyzer = PDFAccessibilityAnalyzer()
    scan_results = analyzer.analyze(str(file_path))
    verapdf_status = build_verapdf_status(scan_results, analyzer)
    summary = analyzer.calculate_summary(scan_results, verapdf_status)
    if isinstance(summary, dict) and verapdf_status:
        summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
        summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))

    fix_suggestions = generate_fix_suggestions(scan_results)

    formatted_results = {
        "results": scan_results,
        "summary": summary,
        "verapdfStatus": verapdf_status,
        "fixes": fix_suggestions,
    }

    saved_id = save_scan_to_db(
        scan_id,
        file.filename,
        formatted_results,
        group_id=group_id,
        status="completed",
        total_issues=summary.get("totalIssues", 0),
        issues_remaining=summary.get("totalIssues", 0),
        issues_fixed=0,
    )
    total_issues = formatted_results.get("summary", {}).get("totalIssues", 0)
    print(
        f"[Backend] ✓ Scan record saved as {saved_id} with {total_issues} issues in group {group_id}"
    )

    return jsonify(
        {
            "scanId": saved_id,
            "filename": file.filename,
            "groupId": group_id,
            "summary": formatted_results["summary"],
            "results": scan_results,
            "fixes": fix_suggestions,
            "timestamp": datetime.now().isoformat(),
            "verapdfStatus": verapdf_status,
        }
    )


@app.route("/api/scan/<scan_id>/start", methods=["POST"])
def start_deferred_scan(scan_id):
    """Trigger analysis for an existing upload that was previously deferred."""
    try:
        scan_record = get_scan_by_id(scan_id)
        if not scan_record:
            return jsonify({"error": "Scan not found"}), 404

        file_path = resolve_uploaded_file_path(scan_id, scan_record)
        if not file_path or not file_path.exists():
            return jsonify({"error": "Original file not found for scanning"}), 404

        analyzer = PDFAccessibilityAnalyzer()
        scan_results = analyzer.analyze(str(file_path))
        verapdf_status = build_verapdf_status(scan_results, analyzer)
        summary = analyzer.calculate_summary(scan_results, verapdf_status)
        if isinstance(summary, dict) and verapdf_status:
            summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
            summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))

        fix_suggestions = generate_fix_suggestions(scan_results)
        formatted_results = {
            "results": scan_results,
            "summary": summary,
            "verapdfStatus": verapdf_status,
            "fixes": fix_suggestions,
        }

        total_issues = summary.get("totalIssues", 0) if isinstance(summary, dict) else 0
        issues_remaining = total_issues

        save_scan_to_db(
            scan_id,
            scan_record.get("filename"),
            formatted_results,
            batch_id=scan_record.get("batch_id"),
            group_id=scan_record.get("group_id"),
            is_update=True,
            status="completed",
            total_issues=total_issues,
            issues_remaining=issues_remaining,
            issues_fixed=0,
        )

        # For batch scans, maintain the 'unprocessed' state for downstream flows
        batch_id = scan_record.get("batch_id")
        if batch_id:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE scans
                SET status = 'unprocessed',
                    total_issues = %s,
                    issues_remaining = %s
                WHERE id = %s
            """,
                (total_issues, issues_remaining, scan_id),
            )
            conn.commit()
            cur.close()
            conn.close()
            update_batch_statistics(batch_id)

        response_status = "unprocessed" if batch_id else "completed"

        return jsonify(
            {
                "scanId": scan_id,
                "filename": scan_record.get("filename"),
                "groupId": scan_record.get("group_id"),
                "batchId": batch_id,
                "summary": summary,
                "results": scan_results,
                "fixes": fix_suggestions,
                "verapdfStatus": verapdf_status,
                "status": response_status,
                "timestamp": datetime.now().isoformat(),
            }
        )

    except Exception as e:
        print(f"[Backend] ✗ Error starting deferred scan {scan_id}: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Scan History ===
@app.route("/api/scans", methods=["GET"])
def get_scans():
    scans = execute_query(
        "SELECT id, filename, upload_date, status FROM scans ORDER BY upload_date DESC",
        fetch=True,
    )
    return jsonify({"scans": scans})


# === Batch Upload ===
@app.route("/api/scan-batch", methods=["POST"])
def scan_batch():
    """Handle batch file upload with group assignment"""
    try:
        if "files" not in request.files:
            return jsonify({"error": "No files provided"}), 400

        files = request.files.getlist("files")
        group_id = request.form.get("group_id")
        batch_name = request.form.get(
            "batch_name", f"Batch {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        if not group_id:
            return jsonify({"error": "Group ID is required"}), 400

        if not files or len(files) == 0:
            return jsonify({"error": "No files provided"}), 400

        pdf_files = [f for f in files if f.filename.lower().endswith(".pdf")]
        skipped_files = [f.filename for f in files if not f.filename.lower().endswith(".pdf")]

        if not pdf_files:
            return jsonify({"error": "No PDF files provided"}), 400

        # Create batch record
        batch_id = f"batch_{uuid.uuid4().hex}"
        scan_now = should_scan_now(request)
        batch_initial_status = "processing" if scan_now else "uploaded"

        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO batches (id, name, group_id, created_at, status, total_files, total_issues, unprocessed_files)
            VALUES (%s, %s, %s, NOW(), %s, %s, 0, %s)
        """,
            (
                batch_id,
                batch_name,
                group_id,
                batch_initial_status,
                len(pdf_files),
                len(pdf_files),
            ),
        )
        conn.commit()
        c.close()
        conn.close()

        print(
            f"[Backend] ✓ Created batch: {batch_id} with {len(pdf_files)} PDF files in group {group_id} (skipped {len(skipped_files)})"
        )

        # Process each file
        scan_results = []
        total_batch_issues = 0

        upload_dir = Path(UPLOAD_FOLDER)
        upload_dir.mkdir(exist_ok=True)

        processed_files = len(pdf_files)
        successful_scans = 0

        for file in pdf_files:
            analyzer = PDFAccessibilityAnalyzer()

            scan_id = f"scan_{uuid.uuid4().hex}"
            file_path = upload_dir / f"{scan_id}.pdf"
            file.save(str(file_path))

            if not scan_now:
                placeholder_results = build_placeholder_scan_payload()
                saved_id = save_scan_to_db(
                    scan_id,
                    file.filename,
                    placeholder_results,
                    batch_id=batch_id,
                    group_id=group_id,
                    status="uploaded",
                    total_issues=0,
                    issues_remaining=0,
                    issues_fixed=0,
                )

                if not saved_id:
                    continue

                scan_results.append(
                    {
                        "scanId": saved_id,
                        "filename": file.filename,
                        "totalIssues": 0,
                        "status": "uploaded",
                        "summary": placeholder_results.get("summary", {}),
                        "results": placeholder_results.get("results", {}),
                        "verapdfStatus": placeholder_results.get("verapdfStatus"),
                        "fixes": placeholder_results.get("fixes", []),
                        "groupId": group_id,
                        "batchId": batch_id,
                    }
                )
                continue

            # Analyze PDF
            scan_data = analyzer.analyze(str(file_path))
            verapdf_status = build_verapdf_status(scan_data, analyzer)
            summary = analyzer.calculate_summary(scan_data, verapdf_status)
            if isinstance(summary, dict) and verapdf_status:
                summary.setdefault(
                    "wcagCompliance", verapdf_status.get("wcagCompliance")
                )
                summary.setdefault(
                    "pdfuaCompliance", verapdf_status.get("pdfuaCompliance")
                )

            # Calculate total issues
            total_issues = summary.get("totalIssues", 0)
            total_batch_issues += total_issues

            # Format results
            formatted_results = {
                "results": scan_data,
                "summary": summary,
                "verapdfStatus": verapdf_status,
                "fixes": generate_fix_suggestions(scan_data),
            }

            # Save to database with batch_id and group_id
            saved_id = save_scan_to_db(
                scan_id,
                file.filename,
                formatted_results,
                batch_id=batch_id,
                group_id=group_id,
                status="completed",
                total_issues=total_issues,
                issues_remaining=total_issues,
                issues_fixed=0,
            )

            if not saved_id:
                continue

            # Update scan with issue counts
            conn = get_db_connection()
            c = conn.cursor()
            c.execute(
                """
                UPDATE scans 
                SET total_issues = %s, issues_remaining = %s, status = 'unprocessed'
                WHERE id = %s
            """,
                (total_issues, total_issues, saved_id),
            )
            conn.commit()
            c.close()
            conn.close()

            scan_results.append(
                {
                    "scanId": saved_id,
                    "filename": file.filename,
                    "totalIssues": total_issues,
                    "status": "unprocessed",
                    "summary": summary,
                    "results": scan_data,
                    "verapdfStatus": verapdf_status,
                    "fixes": formatted_results.get("fixes", []),
                    "groupId": group_id,
                    "batchId": batch_id,
                }
            )
            successful_scans += 1

        # Update batch with total issues
        conn = get_db_connection()
        c = conn.cursor()
        if not scan_now:
            unprocessed_files = len(pdf_files)
            batch_status = "uploaded"
        else:
            unprocessed_files = max(len(pdf_files) - successful_scans, 0)
            if successful_scans == len(pdf_files):
                batch_status = "completed"
            elif successful_scans == 0:
                batch_status = "failed"
            else:
                batch_status = "partial"

        c.execute(
            """
            UPDATE batches 
            SET total_issues = %s, remaining_issues = %s, unprocessed_files = %s, status = %s, total_files = %s
            WHERE id = %s
        """,
            (
                total_batch_issues,
                total_batch_issues,
                unprocessed_files,
                batch_status,
                len(pdf_files),
                batch_id,
            ),
        )
        conn.commit()
        c.close()
        conn.close()

        update_batch_statistics(batch_id)

        print(
            f"[Backend] ✓ Batch upload complete: {len(scan_results)} files, {total_batch_issues} total issues"
        )

        return jsonify(
            {
                "batchId": batch_id,
                "groupId": group_id,
                "scans": scan_results,
                "totalIssues": total_batch_issues,
                "timestamp": datetime.now().isoformat(),
                "processedFiles": processed_files,
                "successfulScans": successful_scans,
                "skippedFiles": skipped_files,
                "scanDeferred": not scan_now,
            }
        )

    except Exception as e:
        print(f"[Backend] Error in batch upload: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def update_batch_statistics(batch_id):
    """Recalculate and persist aggregate metrics for a batch."""
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_files,
                COALESCE(SUM(total_issues), 0) AS total_issues,
                COALESCE(SUM(issues_remaining), 0) AS remaining_issues,
                COALESCE(SUM(issues_fixed), 0) AS fixed_issues,
                SUM(CASE WHEN status IN ('unprocessed', 'processing', 'uploaded') THEN 1 ELSE 0 END) AS unprocessed_files,
                SUM(CASE WHEN status = 'fixed' THEN 1 ELSE 0 END) AS fixed_files,
                SUM(CASE WHEN status = 'uploaded' THEN 1 ELSE 0 END) AS uploaded_files
            FROM scans
            WHERE batch_id = %s
        """,
            (batch_id,),
        )

        stats = cursor.fetchone() or {}

        total_files = stats.get("total_files") or 0
        total_issues = stats.get("total_issues") or 0
        remaining_issues = stats.get("remaining_issues") or 0
        fixed_issues = stats.get("fixed_issues")
        if fixed_issues is None:
            fixed_issues = max(total_issues - remaining_issues, 0)
        unprocessed_files = stats.get("unprocessed_files") or 0
        fixed_files = stats.get("fixed_files") or 0
        uploaded_files = stats.get("uploaded_files") or 0

        if total_files == 0:
            batch_status = "empty"
        elif uploaded_files == total_files:
            batch_status = "uploaded"
        elif uploaded_files > 0:
            batch_status = "partial"
        elif remaining_issues == 0:
            batch_status = "completed"
        elif fixed_files == 0 and unprocessed_files == total_files:
            batch_status = "processing"
        else:
            batch_status = "partial"

        cursor.execute(
            """
            UPDATE batches
            SET total_files = %s,
                total_issues = %s,
                remaining_issues = %s,
                fixed_issues = %s,
                unprocessed_files = %s,
                status = %s
            WHERE id = %s
        """,
            (
                total_files,
                total_issues,
                remaining_issues,
                fixed_issues,
                unprocessed_files,
                batch_status,
                batch_id,
            ),
        )

        conn.commit()
        print(
            f"[Backend] ✓ Batch {batch_id} statistics updated: total={total_issues}, remaining={remaining_issues}, status={batch_status}"
        )
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"[Backend] ⚠ Failed to update batch statistics: {e}")
        import traceback

        traceback.print_exc()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# === Scan History ===
@app.route("/api/history", methods=["GET"])
def get_history():
    """Get all scans and batches with full details for history page"""
    try:
        print("[v0] Fetching history...")

        batches_query = """
            SELECT b.id as "batchId", b.name, b.group_id as "groupId", g.name as "groupName",
                   b.created_at as "uploadDate", b.status, b.total_files as "fileCount",
                   b.total_issues as "totalIssues", b.fixed_issues as "fixedIssues",
                   b.remaining_issues as "remainingIssues", b.unprocessed_files as "unprocessedFiles"
            FROM batches b
            LEFT JOIN groups g ON b.group_id = g.id
            ORDER BY b.created_at DESC
        """
        batches = execute_query(batches_query, fetch=True)

        scans_query = """
            SELECT s.id, s.filename, s.status, 
                   COALESCE(s.upload_date, s.created_at) as "uploadDate",
                   s.created_at, s.batch_id as "batchId", s.group_id as "groupId",
                   g.name as "groupName", 
                   COALESCE(s.total_issues, 0) as "totalIssues",
                   COALESCE(s.issues_fixed, 0) as "issuesFixed", 
                   COALESCE(s.issues_remaining, s.total_issues, 0) as "issuesRemaining",
                   s.scan_results
            FROM scans s
            LEFT JOIN groups g ON s.group_id = g.id
            WHERE s.batch_id IS NULL
            ORDER BY COALESCE(s.upload_date, s.created_at) DESC
        """
        scans = execute_query(scans_query, fetch=True)

        formatted_scans = []
        for scan in scans:
            scan_dict = dict(scan)

            # Parse scan_results to calculate issues if not set
            scan_results = scan_dict.get("scan_results", {})
            if isinstance(scan_results, str):
                try:
                    scan_results = json.loads(scan_results)
                except Exception as e:
                    print(f"[Backend] Warning: Failed to parse scan_results JSON: {e}")
                    scan_results = {}

            results = scan_results.get("results", scan_results)

            # Calculate total issues if not set or zero
            total_issues = scan_dict.get("totalIssues", 0)
            if not total_issues and results:
                total_issues = sum(
                    len(v) if isinstance(v, list) else 0 for v in results.values()
                )

            # Set default status
            status = scan_dict.get("status") or "unprocessed"

            entry = {
                "id": scan_dict["id"],
                "filename": scan_dict["filename"],
                "uploadDate": scan_dict.get("uploadDate"),
                "status": status,
                "groupId": scan_dict.get("groupId"),
                "groupName": scan_dict.get("groupName"),
                "totalIssues": total_issues,
                "issuesFixed": scan_dict.get("issuesFixed", 0),
                "issuesRemaining": scan_dict.get("issuesRemaining", total_issues),
                "batchId": scan_dict.get("batchId"),
            }

            latest_entry = get_fixed_version(scan_dict["id"])
            if latest_entry:
                entry["latestVersion"] = latest_entry["version"]
                entry["latestFixedFile"] = latest_entry["relative_path"]
                entry["hasFixVersions"] = True
            else:
                entry["hasFixVersions"] = False

            formatted_scans.append(entry)

        print(f"[v0] Returning {len(batches)} batches and {len(formatted_scans)} scans")
        return jsonify(
            {"batches": [dict(b) for b in batches], "scans": formatted_scans}
        )

    except Exception as e:
        print(f"[Backend] Error fetching history: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Apply Fixes ===
def _perform_automated_fix(scan_id, data=None, expected_batch_id=None):
    tracker = None
    payload = data or {}
    if payload.get("useAI"):
        print("[Backend] AI-powered automated fixes requested but feature is disabled.")
        return 400, {"success": False, "error": "AI-powered automated fixes are no longer available."}
    try:
        filename = payload.get("filename", "fixed_document.pdf")

        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"

        print(f"[Backend] 🔧 Applying automated fixes for scan: {scan_id}")

        scan_data = get_scan_by_id(scan_id)
        if not scan_data:
            return 404, {"error": "Scan not found", "success": False}

        if expected_batch_id and scan_data.get("batch_id") != expected_batch_id:
            return (
                404,
                {
                    "error": f"Scan {scan_id} does not belong to batch {expected_batch_id}",
                    "success": False,
                },
            )

        original_filename = scan_data.get("filename")
        if not original_filename:
            print(f"[Backend] ERROR: No filename found in scan data")
            return (
                400,
                {"error": "Scan filename not found", "success": False},
            )

        print(f"[Backend] Original filename: {original_filename}")

        initial_scan_results = scan_data.get("scan_results", {})
        if isinstance(initial_scan_results, str):
            try:
                initial_scan_results = json.loads(initial_scan_results)
            except json.JSONDecodeError:
                initial_scan_results = {}
        issues_before = initial_scan_results.get("results", {})
        summary_before = (
            initial_scan_results.get("summary", {})
            if isinstance(initial_scan_results, dict)
            else {}
        )
        compliance_before = summary_before.get("complianceScore", 0)
        total_issues_before = summary_before.get("totalIssues", 0)
        high_severity_before = summary_before.get("highSeverity", 0)

        tracker = create_progress_tracker(scan_id)

        engine = AutoFixEngine()
        result = engine.apply_automated_fixes(scan_id, scan_data, tracker)

        if not result.get("success"):
            error_message = result.get("error", "Unknown error")
            if tracker:
                tracker.fail_all(error_message)
            return 500, {"success": False, "error": error_message}

        if tracker:
            tracker.complete_all()

        fixes_applied = result.get("fixesApplied", [])
        fixed_filename = result.get("fixedFile") or filename
        if not fixes_applied and result.get("fixedIssues"):
            fixes_applied = [
                {
                    "type": "automated",
                    "issueType": issue.get("type", "unknown"),
                    "description": issue.get("description", "Automated fix applied"),
                    "timestamp": datetime.now().isoformat(),
                }
                for issue in result.get("fixedIssues", [])
            ]

        scan_results_after = result.get("scanResults", {}) or {}
        issues_after = scan_results_after.get("results", {})
        summary_after = scan_results_after.get("summary", {}) or {}
        compliance_after = summary_after.get("complianceScore", compliance_before)
        total_issues_after = summary_after.get("totalIssues", total_issues_before)
        high_severity_after = summary_after.get("highSeverity", high_severity_before)

        changes_detected = scan_results_changed(
            issues_before=issues_before,
            summary_before=summary_before,
            compliance_before=compliance_before,
            issues_after=issues_after,
            summary_after=summary_after,
            compliance_after=compliance_after,
        )

        formatted_results = {
            "results": issues_after,
            "summary": summary_after,
            "verapdfStatus": scan_results_after.get("verapdfStatus"),
            "fixes": result.get("suggestions", []),
        }

        save_scan_to_db(
            scan_id,
            original_filename,
            formatted_results,
            batch_id=scan_data.get("batch_id"),
            group_id=scan_data.get("group_id"),
            is_update=True,
        )

        archive_info = None
        if changes_detected:
            archive_info = archive_fixed_pdf_version(
                scan_id=scan_id,
                original_filename=original_filename,
                source_path=resolve_uploaded_file_path(scan_id, scan_data),
            )
            if archive_info:
                fixed_filename = archive_info["relative_path"]

        save_success = False
        if changes_detected:
            metadata_payload = {
                "engine_version": "1.0",
                "processing_time": result.get("processingTime"),
                "success_rate": result.get("successRate"),
            }
            if archive_info:
                metadata_payload.update(
                    {
                        "version": archive_info["version"],
                        "versionLabel": f"V{archive_info['version']}",
                        "relativePath": archive_info["relative_path"],
                        "storedFilename": archive_info["filename"],
                        "fileSize": archive_info["size"],
                    }
                )
            save_success = bool(
                save_fix_history(
                    scan_id=scan_id,
                    original_filename=original_filename,
                    fixed_filename=fixed_filename,
                    fixes_applied=fixes_applied,
                    fix_type="automated",
                    issues_before=issues_before,
                    issues_after=issues_after,
                    compliance_before=compliance_before,
                    compliance_after=compliance_after,
                    total_issues_before=total_issues_before,
                    total_issues_after=total_issues_after,
                    high_severity_before=high_severity_before,
                    high_severity_after=high_severity_after,
                    fix_suggestions=result.get("suggestions", []),
                    fix_metadata=metadata_payload,
                    version=archive_info["version"] if archive_info else None,
                )
            )
        else:
            print(
                "[Backend] ℹ No changes detected after automated fixes; skipping fix history entry."
            )

        if changes_detected and not save_success:
            print(
                "[Backend] WARNING: Fix history save failed, but fix was applied successfully"
            )

        update_scan_status(scan_id)

        batch_id = scan_data.get("batch_id")
        if batch_id:
            update_batch_statistics(batch_id)

        success_count = len(fixes_applied) if fixes_applied else len(result.get("fixedIssues", []))
        if not success_count:
            success_count = result.get("successCount", 0)

        response = {
            "success": True,
            "status": "success",
            "fixedFile": fixed_filename,
            "fixedFilePath": fixed_filename,
            "scanResults": scan_results_after,
            "summary": summary_after,
            "fixesApplied": fixes_applied,
            "historyRecorded": save_success,
            "changesDetected": changes_detected,
            "successCount": success_count,
            "scanId": scan_id,
        }
        if archive_info:
            response["version"] = archive_info["version"]
            response["versionLabel"] = f"V{archive_info['version']}"
            response["fixedFile"] = archive_info["relative_path"]
            response["fixedFilePath"] = archive_info["relative_path"]

        return 200, response

    except Exception as e:
        print(f"[Backend] ERROR in automated fix: {e}")
        import traceback

        traceback.print_exc()
        if tracker:
            tracker.fail_all(str(e))
        return 500, {"error": str(e), "success": False}


@app.route("/api/apply-fixes/<scan_id>", methods=["POST"])
def apply_fixes(scan_id):
    data = request.get_json(silent=True) or {}
    status, payload = _perform_automated_fix(scan_id, data)
    return jsonify(payload), status


@app.route("/api/batch/<batch_id>/fix-file/<scan_id>", methods=["POST"])
def apply_batch_fix(batch_id, scan_id):
    data = request.get_json(silent=True) or {}
    status, payload = _perform_automated_fix(
        scan_id, data, expected_batch_id=batch_id
    )
    if status == 200:
        payload.setdefault("batchId", batch_id)
    return jsonify(payload), status


@app.route("/api/batch/<batch_id>/fix-all", methods=["POST"])
def apply_batch_fix_all(batch_id):
    scans = execute_query(
        "SELECT id FROM scans WHERE batch_id = %s",
        (batch_id,),
        fetch=True,
    )

    if not scans:
        return (
            jsonify(
                {"success": False, "error": f"No scans found for batch {batch_id}"}
            ),
            404,
        )

    success_count = 0
    errors = []

    for scan in scans:
        scan_id = scan.get("id") if isinstance(scan, dict) else scan[0]
        status, payload = _perform_automated_fix(
            scan_id, {}, expected_batch_id=batch_id
        )
        if status == 200 and payload.get("success"):
            success_count += 1
        else:
            errors.append(
                {
                    "scanId": scan_id,
                    "error": payload.get("error", "Unknown error"),
                }
            )

    update_batch_statistics(batch_id)

    total_files = len(scans)
    response_payload = {
        "success": success_count > 0,
        "successCount": success_count,
        "totalFiles": total_files,
        "errors": errors,
        "batchId": batch_id,
    }

    status_code = 200 if success_count > 0 else 500
    return jsonify(response_payload), status_code


# === Apply Semi-Automated Fixes ===
@app.route("/api/apply-semi-automated-fixes/<scan_id>", methods=["POST"])
def apply_semi_automated_fixes(scan_id):
    tracker = None
    try:
        data = request.get_json(silent=True) or {}
        fixes = data.get("fixes", [])
        if data.get("useAI"):
            print("[Backend] AI-powered semi-automated fixes requested but feature is disabled.")
            return (
                jsonify(
                    {
                        "error": "AI-powered semi-automated fixes are no longer available.",
                        "success": False,
                    }
                ),
                400,
            )

        print(f"[Backend] 🔧 Applying semi-automated fixes for scan: {scan_id}")

        scan_data = get_scan_by_id(scan_id)
        if not scan_data:
            return jsonify({"error": "Scan not found"}), 404

        original_filename = scan_data.get("filename")
        if not original_filename:
            print(f"[Backend] ERROR: No filename found in scan data")
            return jsonify({"error": "Scan filename not found"}), 400

        print(f"[Backend] Original filename: {original_filename}")
        print(f"[Backend] Fixes to apply: {len(fixes)}")

        # Get initial state
        initial_scan_results = scan_data.get("scan_results", {})
        if isinstance(initial_scan_results, str):
            try:
                initial_scan_results = json.loads(initial_scan_results)
            except json.JSONDecodeError:
                initial_scan_results = {}
        issues_before = initial_scan_results.get("results", {})
        summary_before = (
            initial_scan_results.get("summary", {})
            if isinstance(initial_scan_results, dict)
            else {}
        )
        compliance_before = summary_before.get("complianceScore", 0)
        total_issues_before = summary_before.get("totalIssues", 0)
        high_severity_before = summary_before.get("highSeverity", 0)

        tracker = create_progress_tracker(scan_id)

        engine = AutoFixEngine()
        result = engine.apply_semi_automated_fixes(scan_id, scan_data, tracker)

        if result.get("success"):
            if tracker:
                tracker.complete_all()

            fixes_applied = result.get("fixesApplied", [])
            if not fixes_applied and fixes:
                fixes_applied = [
                    {
                        "type": "semi-automated",
                        "issueType": fix.get("type", "unknown"),
                        "description": fix.get(
                            "description", "Semi-automated fix applied"
                        ),
                        "timestamp": datetime.now().isoformat(),
                    }
                    for fix in fixes
                ]

            # Get after state
            scan_results_after = result.get("scanResults", {}) or {}
            issues_after = scan_results_after.get("results", {})
            summary_after = scan_results_after.get("summary", {}) or {}
            compliance_after = summary_after.get("complianceScore", compliance_before)
            total_issues_after = summary_after.get("totalIssues", total_issues_before)
            high_severity_after = summary_after.get(
                "highSeverity", high_severity_before
            )
            fixed_filename = result.get("fixedFile")

            changes_detected = scan_results_changed(
                issues_before=issues_before,
                summary_before=summary_before,
                compliance_before=compliance_before,
                issues_after=issues_after,
                summary_after=summary_after,
                compliance_after=compliance_after,
            )

            formatted_results = {
                "results": issues_after,
                "summary": summary_after,
                "verapdfStatus": scan_results_after.get("verapdfStatus"),
                "fixes": result.get("suggestions", []),
            }

            save_scan_to_db(
                scan_id,
                original_filename,
                formatted_results,
                batch_id=scan_data.get("batch_id"),
                group_id=scan_data.get("group_id"),
                is_update=True,
            )

            archive_info = None
            if changes_detected:
                archive_info = archive_fixed_pdf_version(
                    scan_id=scan_id,
                    original_filename=original_filename,
                    source_path=resolve_uploaded_file_path(scan_id, scan_data),
                )
                if archive_info:
                    fixed_filename = archive_info["relative_path"]

            save_success = False
            if changes_detected:
                metadata_payload = {
                    "user_selected_fixes": len(fixes),
                    "engine_version": "1.0",
                }
                if archive_info:
                    metadata_payload.update(
                        {
                            "version": archive_info["version"],
                            "versionLabel": f"V{archive_info['version']}",
                            "relativePath": archive_info["relative_path"],
                            "storedFilename": archive_info["filename"],
                            "fileSize": archive_info["size"],
                        }
                    )
                save_success = bool(
                    save_fix_history(
                        scan_id=scan_id,
                        original_filename=original_filename,
                        fixed_filename=fixed_filename,
                        fixes_applied=fixes_applied,
                        fix_type="semi-automated",
                        issues_before=issues_before,
                        issues_after=issues_after,
                        compliance_before=compliance_before,
                        compliance_after=compliance_after,
                        total_issues_before=total_issues_before,
                        total_issues_after=total_issues_after,
                        high_severity_before=high_severity_before,
                        high_severity_after=high_severity_after,
                        fix_suggestions=fixes,
                        fix_metadata=metadata_payload,
                        version=archive_info["version"] if archive_info else None,
                    )
                )
            else:
                print(
                    "[Backend] ℹ No changes detected after semi-automated fixes; skipping fix history entry."
                )

            if changes_detected and not save_success:
                print(
                    f"[Backend] WARNING: Fix history save failed, but fix was applied successfully"
                )

            update_scan_status(scan_id)

            response_payload = {
                "status": "success",
                "fixedFile": fixed_filename,
                "fixedFilePath": fixed_filename,
                "scanResults": scan_results_after,
                "summary": summary_after,
                "fixesApplied": fixes_applied,
                "historyRecorded": save_success,
                "changesDetected": changes_detected,
            }
            if archive_info:
                response_payload["version"] = archive_info["version"]
                response_payload["versionLabel"] = f"V{archive_info['version']}"
                response_payload["fixedFile"] = archive_info["relative_path"]
                response_payload["fixedFilePath"] = archive_info["relative_path"]

            return jsonify(response_payload)
        else:
            if tracker:
                tracker.fail_all(result.get("error", "Unknown error"))
            return jsonify(
                {"status": "error", "error": result.get("error", "Unknown error")}
            ), 500

    except Exception as e:
        print(f"[Backend] ERROR in apply_semi_automated_fixes: {e}")
        import traceback

        traceback.print_exc()
        if tracker:
            tracker.fail_all(str(e))
        return jsonify({"error": str(e)}), 500


@app.route("/api/apply-manual-fix/<scan_id>", methods=["POST"])
def apply_manual_fix(scan_id):
    try:
        data = request.get_json() or {}
        fix_type = data.get("fixType")
        fix_data = data.get("fixData", {})
        page = data.get("page", 1)

        if not fix_type:
            return jsonify({"error": "fixType is required"}), 400

        scan_data = get_scan_by_id(scan_id)
        if not scan_data:
            return jsonify({"error": "Scan not found"}), 404

        original_filename = scan_data.get("filename")
        if not original_filename:
            return jsonify({"error": "Scan filename not found"}), 400

        raw_scan_results = scan_data.get("scan_results", {})
        if isinstance(raw_scan_results, str):
            try:
                raw_scan_results = json.loads(raw_scan_results)
            except json.JSONDecodeError:
                raw_scan_results = {}

        issues_before = {}
        compliance_before = 0
        if isinstance(raw_scan_results, dict):
            issues_before = raw_scan_results.get("results", {}) or {}
            compliance_before = (
                raw_scan_results.get("summary", {}).get("complianceScore", 0)
            )

        pdf_path = Path(UPLOAD_FOLDER) / f"{scan_id}.pdf"
        if not pdf_path.exists():
            possible_paths = [
                Path(UPLOAD_FOLDER) / scan_id,
                Path(UPLOAD_FOLDER) / f"{scan_id.replace('.pdf', '')}.pdf",
            ]
            if original_filename:
                possible_paths.append(Path(UPLOAD_FOLDER) / original_filename)
            if scan_data.get("file_path"):
                possible_paths.append(Path(scan_data["file_path"]))

            for candidate in possible_paths:
                if candidate and candidate.exists():
                    pdf_path = candidate
                    break

        if not pdf_path.exists():
            return jsonify({"error": "PDF file not found"}), 404

        engine = AutoFixEngine()
        fix_result = engine.apply_manual_fix(str(pdf_path), fix_type, fix_data, page)

        if not fix_result.get("success"):
            return jsonify(
                {"error": fix_result.get("error", "Failed to apply manual fix")}
            ), 500

        rescan_data = engine._analyze_fixed_pdf(str(pdf_path))
        summary = rescan_data.get("summary", {}) or {}
        results = rescan_data.get("results", {}) or {}
        verapdf_status = rescan_data.get("verapdfStatus")
        suggestions = rescan_data.get("suggestions", [])

        formatted_results = {
            "results": results,
            "summary": summary,
            "verapdfStatus": verapdf_status,
            "fixes": suggestions,
        }

        save_scan_to_db(
            scan_id,
            original_filename,
            formatted_results,
            batch_id=scan_data.get("batch_id"),
            group_id=scan_data.get("group_id"),
            is_update=True,
        )

        fixes_applied = [
            {
                "type": "manual",
                "issueType": fix_type,
                "description": fix_result.get(
                    "description", "Manual fix applied successfully"
                ),
                "page": page,
                "timestamp": datetime.now().isoformat(),
                "metadata": fix_data,
            }
        ]

        archive_info = archive_fixed_pdf_version(
            scan_id=scan_id,
            original_filename=original_filename,
            source_path=pdf_path,
        )
        archived_filename = (
            archive_info["relative_path"] if archive_info else pdf_path.name
        )

        save_fix_history(
            scan_id=scan_id,
            original_filename=original_filename,
            fixed_filename=archived_filename,
            fixes_applied=fixes_applied,
            fix_type="manual",
            issues_before=issues_before,
            issues_after=results,
            compliance_before=compliance_before,
            compliance_after=summary.get("complianceScore", compliance_before),
            fix_suggestions=suggestions,
            fix_metadata={
                "page": page,
                "manual": True,
                "version": archive_info["version"] if archive_info else None,
                "versionLabel": f"V{archive_info['version']}"
                if archive_info
                else None,
                "relativePath": archived_filename,
                "storedFilename": archive_info["filename"]
                if archive_info
                else pdf_path.name,
                "fileSize": archive_info["size"] if archive_info else None,
            },
            version=archive_info["version"] if archive_info else None,
        )

        update_scan_status(scan_id)

        return jsonify(
            {
                "success": True,
                "message": fix_result.get(
                    "message", "Manual fix applied successfully"
                ),
                "fixedFile": archived_filename,
                "fixedFilePath": archived_filename,
                "version": archive_info["version"] if archive_info else None,
                "versionLabel": f"V{archive_info['version']}"
                if archive_info
                else None,
                "summary": summary,
                "results": results,
                "scanResults": formatted_results,
                "fixesApplied": fixes_applied,
                "verapdfStatus": verapdf_status,
                "fixSuggestions": suggestions,
            }
        )

    except Exception as e:
        print(f"[Backend] ERROR in apply_manual_fix: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Download File ===
@app.route("/api/download/<path:scan_id>", methods=["GET"])
def download_file(scan_id):
    """Download the original or fixed PDF file associated with a scan ID."""
    uploads_dir = Path(UPLOAD_FOLDER)

    version_param = request.args.get("version")
    allow_old = _truthy(request.args.get("allowDownload"))
    selected_version = None
    versions = get_versioned_files(scan_id)

    if versions:
        latest = versions[-1]
        selected_version = latest
        if version_param:
            try:
                requested_version = int(version_param)
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid version specified"}), 400

            match = next(
                (entry for entry in versions if entry["version"] == requested_version),
                None,
            )
            if not match:
                return jsonify({"error": f"Version {requested_version} not found"}), 404

            if match["version"] != latest["version"] and not allow_old:
                return (
                    jsonify(
                        {
                            "error": "Only the latest version is downloadable by default",
                            "latestVersion": latest["version"],
                            "requestedVersion": match["version"],
                        }
                    ),
                    403,
                )
            selected_version = match

        file_path = selected_version["absolute_path"]
    else:
        file_path = None
        potential_filenames = [f"{scan_id}.pdf", scan_id]
        for filename in potential_filenames:
            path = uploads_dir / filename
            if path.exists():
                file_path = path
                break

    if not file_path:
        return jsonify({"error": "File not found"}), 404

    # Determine download name: Use original filename if possible, otherwise scan_id
    original_scan_data = get_scan_by_id(scan_id)
    download_name = (
        original_scan_data.get("filename", f"{scan_id}.pdf")
        if original_scan_data
        else f"{scan_id}.pdf"
    )
    if selected_version:
        stem = Path(download_name).stem
        download_name = f"{stem}_V{selected_version['version']}.pdf"

    return send_file(
        file_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name,
    )


@app.route("/api/scan/<scan_id>/prune-fixed", methods=["POST"])
def prune_fixed_files(scan_id):
    """Delete older fixed PDF versions, keeping only the latest unless specified."""
    try:
        payload = request.get_json(silent=True) or {}
        keep_latest = payload.get("keepLatest", True)

        result = prune_fixed_versions(scan_id, keep_latest=bool(keep_latest))
        message = (
            "No previous versions were found."
            if result["removed"] == 0
            else f"Removed {result['removed']} older version(s)."
        )
        return jsonify(
            {
                "success": True,
                "message": message,
                "removed": result["removed"],
                "removedFiles": result["removedFiles"],
                "remainingVersions": result["remainingVersions"],
            }
        )
    except Exception as exc:
        print(f"[Backend] Error pruning fixed versions for {scan_id}: {exc}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


# === Progress Tracker ===
@app.route("/api/progress/<scan_id>", methods=["GET"])
def get_fix_progress(scan_id):
    """Get real-time progress of fix application"""
    try:
        tracker = get_progress_tracker(scan_id)
        if not tracker:
            return jsonify(
                {"error": "No progress tracking found for this scan", "scanId": scan_id}
            ), 404

        progress = tracker.get_progress()
        return jsonify(progress), 200

    except Exception as e:
        print(f"[Backend] Error getting fix progress: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/fix-progress/<scan_id>", methods=["GET"])
def get_fix_progress_alias(scan_id):
    """Alias endpoint for /api/progress - ensures frontend compatibility"""
    return get_fix_progress(scan_id)


@app.route("/api/fix-history/<scan_id>", methods=["GET"])
def get_fix_history(scan_id):
    """Get fix history for a scan"""
    try:
        print(f"[Backend] 📜 Fetching fix history for scan: {scan_id}")

        def _deserialize_json(value, default):
            if value in (None, "", b"", bytearray()):
                return default
            if isinstance(value, (dict, list)):
                return value
            if isinstance(value, memoryview):
                value = value.tobytes()
            if isinstance(value, (bytes, bytearray)):
                value = value.decode()
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    print(f"[Backend] Warning: Failed to decode JSON field, returning default")
            return default

        conn = get_db_connection()
        c = conn.cursor()

        query = """
            SELECT 
                id,
                scan_id,
                original_file,
                original_filename,
                fixed_file,
                fixed_filename,
                fixes_applied,
                fix_suggestions,
                issues_before,
                issues_after,
                fix_metadata,
                applied_at,
                fix_type,
                total_issues_before,
                total_issues_after,
                compliance_before,
                compliance_after
            FROM fix_history
            WHERE scan_id = %s
            ORDER BY applied_at DESC
        """

        c.execute(query, (scan_id,))
        results = c.fetchall()

        c.close()
        conn.close()

        history = []
        for row in results:
            fixes_applied = _deserialize_json(row.get("fixes_applied"), [])
            issues_before = _deserialize_json(row.get("issues_before"), {})
            issues_after = _deserialize_json(row.get("issues_after"), {})
            fix_metadata = _deserialize_json(row.get("fix_metadata"), {})
            fix_suggestions = _deserialize_json(row.get("fix_suggestions"), [])

            version_number = None
            version_label = None
            relative_path = row.get("fixed_filename") or row.get("fixed_file")
            stored_filename = None
            file_size = None
            if isinstance(fix_metadata, dict):
                version_number = fix_metadata.get("version", version_number)
                version_label = fix_metadata.get("versionLabel", version_label)
                relative_path = fix_metadata.get("relativePath", relative_path)
                stored_filename = fix_metadata.get("storedFilename")
                file_size = fix_metadata.get("fileSize")

            history.append(
                {
                    "id": row["id"],
                    "scanId": row["scan_id"],
                    "originalFilename": row.get("original_filename")
                    or row.get("original_file"),
                    "fixedFilename": row.get("fixed_filename") or row.get("fixed_file"),
                    "fixedFilePath": relative_path,
                    "fixesApplied": fixes_applied,
                    "issuesBefore": issues_before,
                    "issuesAfter": issues_after,
                    "fixSuggestions": fix_suggestions,
                    "metadata": fix_metadata,
                    "appliedAt": row["applied_at"].isoformat()
                    if row["applied_at"]
                    else None,
                    "fixType": row["fix_type"],
                    "totalIssuesBefore": row["total_issues_before"],
                    "totalIssuesAfter": row["total_issues_after"],
                    "complianceBefore": row["compliance_before"],
                    "complianceAfter": row["compliance_after"],
                    "version": version_number,
                    "versionLabel": version_label,
                    "storedFilename": stored_filename,
                    "fileSize": file_size,
                    "downloadable": False,
                    "viewable": False,
                }
            )

        assigned_versions = []
        for entry in reversed(history):
            if entry["version"] is None:
                entry["version"] = len(assigned_versions) + 1
                entry["versionLabel"] = f"V{entry['version']}"
            assigned_versions.append(entry["version"])

        latest_version = max(assigned_versions) if assigned_versions else None
        version_files = {
            info["version"]: info for info in get_versioned_files(scan_id)
        }

        for entry in history:
            info = version_files.get(entry["version"])
            if info:
                entry["storedFilename"] = entry["storedFilename"] or info["filename"]
                entry["fixedFilePath"] = entry["fixedFilePath"] or info["relative_path"]
                entry["fileSize"] = entry["fileSize"] or info["size"]
                entry["versionCreatedAt"] = (
                    info["created_at"].isoformat() if info["created_at"] else None
                )
            entry["isLatest"] = (
                latest_version is not None and entry["version"] == latest_version
            )
            file_available = info is not None
            entry["downloadable"] = entry["isLatest"] and file_available
            entry["viewable"] = entry["downloadable"]
            if not entry.get("versionLabel"):
                entry["versionLabel"] = f"V{entry['version']}"

        version_history = sorted(
            [
                {
                    "version": entry["version"],
                    "label": entry["versionLabel"],
                    "appliedAt": entry["appliedAt"],
                    "downloadable": entry["downloadable"],
                    "relativePath": entry.get("fixedFilePath"),
                }
                for entry in history
            ],
            key=lambda item: item["version"],
            reverse=True,
        )

        return jsonify(
            {
                "success": True,
                "history": history,
                "latestVersion": latest_version,
                "versions": version_history,
            }
        )

    except Exception as e:
        print(f"[Backend] ERROR getting fix history: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/download-fixed/<path:filename>", methods=["GET"])
def download_fixed_file(filename):
    """Download a fixed PDF file"""
    try:
        print(f"[Backend] Downloading fixed file: {filename}")

        fixed_dir = Path(FIXED_FOLDER)
        uploads_dir = Path(UPLOAD_FOLDER)

        allow_old = _truthy(request.args.get("allowDownload"))
        version_param = request.args.get("version")
        scan_id_param = request.args.get("scanId")

        file_path = None
        selected_version = None
        scan_id_for_version = scan_id_param

        try:
            requested_path = (fixed_dir / filename).resolve()
        except Exception:
            requested_path = None

        base_fixed_resolved = fixed_dir.resolve()
        if (
            requested_path
            and requested_path.exists()
            and str(requested_path).startswith(str(base_fixed_resolved))
        ):
            file_path = requested_path
            scan_id_for_version = requested_path.parent.name
            version_number = _extract_version_from_path(requested_path)
            if scan_id_for_version:
                versions = get_versioned_files(scan_id_for_version)
                latest = versions[-1] if versions else None
                if version_number and latest:
                    selected_version = next(
                        (
                            entry
                            for entry in versions
                            if entry["version"] == version_number
                        ),
                        None,
                    )
                    if (
                        selected_version
                        and version_number != latest["version"]
                        and not allow_old
                    ):
                        return (
                            jsonify(
                                {
                                    "error": "Only the latest version is downloadable by default",
                                    "latestVersion": latest["version"],
                                    "requestedVersion": version_number,
                                }
                            ),
                            403,
                        )
        else:
            target_scan_id = scan_id_param or filename
            versions = get_versioned_files(target_scan_id)
            if versions:
                latest = versions[-1]
                selected_version = latest
                if version_param:
                    try:
                        requested_number = int(version_param)
                    except (ValueError, TypeError):
                        return jsonify({"error": "Invalid version specified"}), 400
                    match = next(
                        (
                            entry
                            for entry in versions
                            if entry["version"] == requested_number
                        ),
                        None,
                    )
                    if not match:
                        return jsonify(
                            {"error": f"Version {requested_number} not found"}
                        ), 404
                    if match["version"] != latest["version"] and not allow_old:
                        return (
                            jsonify(
                                {
                                    "error": "Only the latest version is downloadable by default",
                                    "latestVersion": latest["version"],
                                    "requestedVersion": match["version"],
                                }
                            ),
                            403,
                        )
                    selected_version = match

                file_path = selected_version["absolute_path"]
                scan_id_for_version = target_scan_id
            else:
                # Legacy fallback: search fixed and upload directories by raw filename
                for folder in [fixed_dir, uploads_dir]:
                    for ext in ["", ".pdf"]:
                        path = folder / f"{filename}{ext}"
                        if path.exists():
                            file_path = path
                            break
                    if file_path:
                        break

        if not file_path:
            print(f"[Backend] Fixed file not found: {filename}")
            return jsonify({"error": "File not found"}), 404

        original_filename = None
        if scan_id_for_version:
            scan_record = get_scan_by_id(scan_id_for_version)
            if scan_record:
                original_filename = scan_record.get("filename")

        if selected_version and original_filename:
            download_name = f"{Path(original_filename).stem}_V{selected_version['version']}.pdf"
        elif selected_version:
            download_name = selected_version["filename"]
        else:
            download_name = Path(file_path).name
            if not download_name.lower().endswith(".pdf"):
                download_name = f"{download_name}.pdf"

        print(f"[Backend] ✓ Serving fixed file: {file_path}")
        return send_file(
            file_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=download_name,
        )

    except Exception as e:
        print(f"[Backend] Error downloading fixed file: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Serve PDF File for Preview ===
@app.route("/api/pdf-file/<scan_id>", methods=["GET"])
def serve_pdf_file(scan_id):
    """Serve PDF file for preview in PDF Editor"""
    try:
        uploads_dir = Path(UPLOAD_FOLDER)
        fixed_dir = Path(FIXED_FOLDER)

        version_param = request.args.get("version")
        file_path = None

        if version_param:
            try:
                requested_version = int(version_param)
            except (ValueError, TypeError):
                return jsonify({"error": "Invalid version parameter"}), 400
            version_info = get_fixed_version(scan_id, requested_version)
            if version_info:
                file_path = version_info["absolute_path"]
        else:
            latest_version = get_fixed_version(scan_id)
            if latest_version:
                file_path = latest_version["absolute_path"]

        if not file_path:
            # Try multiple file path strategies (legacy behavior)
            for folder in [fixed_dir, uploads_dir]:
                for ext in ["", ".pdf"]:
                    path = folder / f"{scan_id}{ext}"
                    if path.exists():
                        file_path = path
                        break
                if file_path:
                    break

        if not file_path:
            print(f"[Backend] PDF file not found for scan: {scan_id}")
            return jsonify({"error": "PDF file not found"}), 404

        return send_file(
            file_path,
            mimetype="application/pdf",
            as_attachment=False,  # Serve inline for preview
        )
    except Exception as e:
        print(f"[Backend] Error serving PDF file: {e}")
        return jsonify({"error": str(e)}), 500


# === Export Scan ===
@app.route("/api/export/<scan_id>", methods=["GET"])
def export_scan(scan_id):
    """Export scan data for report generation"""
    try:
        print(f"[Backend] Exporting scan data for: {scan_id}")

        # Get scan data
        scan_data = get_scan_by_id(scan_id)
        if not scan_data:
            return jsonify({"error": "Scan not found"}), 404

        # Parse scan_results
        scan_results = scan_data.get("scan_results", {})
        if isinstance(scan_results, str):
            scan_results = json.loads(scan_results)

        results = scan_results.get("results", scan_results)
        summary = scan_results.get("summary", {})
        verapdf_status = scan_results.get("verapdfStatus")

        if verapdf_status is None:
            verapdf_status = build_verapdf_status(results)

        # Ensure summary has all required fields
        if not summary or "totalIssues" not in summary:
            try:
                summary = PDFAccessibilityAnalyzer.calculate_summary(
                    results, verapdf_status
                )
            except Exception as calc_error:
                print(
                    f"[Backend] Warning: unable to regenerate summary for export: {calc_error}"
                )
                total_issues = sum(
                    len(v) if isinstance(v, list) else 0 for v in results.values()
                )
                summary = {
                    "totalIssues": total_issues,
                    "highSeverity": len(
                        [
                            i
                            for issues in results.values()
                            if isinstance(issues, list)
                            for i in issues
                            if isinstance(i, dict)
                            and i.get("severity") in ["high", "critical"]
                        ]
                    ),
                    "complianceScore": max(0, 100 - total_issues * 2),
                }

        if isinstance(summary, dict) and verapdf_status:
            summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
            summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))

        export_data = {
            "scanId": scan_data["id"],
            "filename": scan_data["filename"],
            "uploadDate": scan_data.get("upload_date", scan_data.get("created_at")),
            "status": scan_data.get("status", "completed"),
            "summary": summary,
            "results": results,
            "verapdfStatus": verapdf_status,
        }

        print(f"[Backend] ✓ Export data prepared for: {scan_id}")
        return jsonify(export_data)

    except Exception as e:
        print(f"[Backend] Error exporting scan: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Individual Scan Details ===
@app.route("/api/scan/<scan_id>", methods=["GET"])
def get_scan(scan_id):
    """Fetch individual scan details by scan_id with WCAG and PDF/A stats"""
    try:
        print(f"[Backend] Fetching scan details for: {scan_id}")

        # Try multiple query strategies to find the scan
        query = "SELECT * FROM scans WHERE id = %s"
        result = execute_query(query, (scan_id,), fetch=True)

        if not result or len(result) == 0:
            # Try without .pdf extension
            scan_id_no_ext = scan_id.replace(".pdf", "")
            result = execute_query(query, (scan_id_no_ext,), fetch=True)

        if not result or len(result) == 0:
            # Try by filename
            query = "SELECT * FROM scans WHERE filename = %s ORDER BY created_at DESC LIMIT 1"
            result = execute_query(query, (scan_id,), fetch=True)

        if result and len(result) > 0:
            scan = dict(result[0])

            scan_results = scan.get("scan_results", {})
            if isinstance(scan_results, str):
                scan_results = json.loads(scan_results)

            results = scan_results.get("results", scan_results)
            summary = scan_results.get("summary", {})
            verapdf_status = scan_results.get("verapdfStatus")

            if verapdf_status is None:
                verapdf_status = build_verapdf_status(results)

            if (
                not summary
                or "totalIssues" not in summary
                or summary.get("totalIssues", 0) == 0
            ):
                try:
                    summary = PDFAccessibilityAnalyzer.calculate_summary(
                        results, verapdf_status
                    )
                except Exception as calc_error:
                    print(
                        f"[Backend] Warning: failed to rebuild summary for scan {scan_id}: {calc_error}"
                    )
                    total_issues = sum(
                        len(v) if isinstance(v, list) else 0 for v in results.values()
                    )
                    summary = {
                        "totalIssues": total_issues,
                        "highSeverity": len(
                            [
                                i
                                for issues in results.values()
                                if isinstance(issues, list)
                                for i in issues
                                if isinstance(i, dict)
                                and i.get("severity") in ["high", "critical"]
                            ]
                        ),
                        "complianceScore": max(0, 100 - total_issues * 2),
                    }
            if isinstance(summary, dict) and verapdf_status:
                summary.setdefault(
                    "wcagCompliance", verapdf_status.get("wcagCompliance")
                )
                summary.setdefault(
                    "pdfuaCompliance", verapdf_status.get("pdfuaCompliance")
                )

            fix_suggestions = generate_fix_suggestions(results)

            version_entries = get_versioned_files(scan["id"])
            latest_version = version_entries[-1] if version_entries else None

            response_data = {
                "scanId": scan["id"],
                "id": scan["id"],
                "filename": scan["filename"],  # Use original filename from database
                "fileName": scan["filename"],
                "uploadDate": scan.get("upload_date", scan.get("created_at")),
                "timestamp": scan.get("upload_date", scan.get("created_at")),
                "status": scan.get("status", "completed"),
                "results": results,
                "summary": summary,
                "fixes": fix_suggestions,
                "verapdfStatus": verapdf_status
                or {
                    "isActive": False,
                    "wcagCompliance": None,
                    "pdfuaCompliance": None,
                    "totalVeraPDFIssues": len(results.get("wcagIssues", []))
                    + len(results.get("pdfaIssues", []))
                    + len(results.get("pdfuaIssues", [])),
                },
            }
            if latest_version:
                response_data["latestVersion"] = latest_version["version"]
                response_data["latestFixedFile"] = latest_version["relative_path"]
                response_data["versionHistory"] = [
                    {
                        "version": entry["version"],
                        "label": f"V{entry['version']}",
                        "relativePath": entry["relative_path"],
                        "createdAt": entry["created_at"].isoformat()
                        if entry["created_at"]
                        else None,
                        "fileSize": entry["size"],
                        "downloadable": entry["version"] == latest_version["version"],
                    }
                    for entry in reversed(version_entries)
                ]

            print(
                f"[Backend] ✓ Found scan: {scan_id}, Total issues: {summary.get('totalIssues', 0)}, WCAG: {summary.get('wcagCompliance', 0)}%, PDF/UA: {summary.get('pdfuaCompliance', 0)}%"
            )
            return jsonify(response_data)

        print(f"[Backend] Scan not found: {scan_id}")
        return jsonify({"error": f"Scan not found: {scan_id}"}), 404

    except Exception as e:
        print(f"[Backend] Error fetching scan: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Delete Scan ===
@app.route("/api/scan/<scan_id>", methods=["DELETE"])
def delete_scan(scan_id):
    """Delete an individual scan and its associated files"""
    try:
        print(f"[Backend] Deleting scan: {scan_id}")

        scan = get_scan_by_id(scan_id)
        if not scan:
            return jsonify({"error": "Scan not found"}), 404

        group_id = scan.get("group_id")

        # Delete physical files
        uploads_dir = Path(UPLOAD_FOLDER)
        fixed_dir = Path(FIXED_FOLDER)
        deleted_files = 0

        for folder in [uploads_dir, fixed_dir]:
            # Try with and without .pdf extension
            for ext in ["", ".pdf"]:
                file_path = folder / f"{scan_id}{ext}"
                if file_path.exists():
                    file_path.unlink()
                    deleted_files += 1
                    print(f"[Backend] Deleted file: {file_path}")

        version_dir = fixed_dir / scan_id
        if version_dir.exists() and version_dir.is_dir():
            removed_count = sum(1 for path in version_dir.glob("**/*") if path.is_file())
            shutil.rmtree(version_dir, ignore_errors=True)
            deleted_files += removed_count
            print(f"[Backend] Deleted version history directory: {version_dir}")

        # Delete from database
        execute_query(
            "DELETE FROM fix_history WHERE scan_id = %s", (scan_id,), fetch=False
        )
        execute_query("DELETE FROM scans WHERE id = %s", (scan_id,), fetch=False)

        if group_id:
            update_group_file_count(group_id)
            print(f"[Backend] Updated file count for group: {group_id}")

        print(f"[Backend] ✓ Deleted scan {scan_id} ({deleted_files} files)")

        return jsonify(
            {
                "success": True,
                "message": f"Deleted scan and {deleted_files} file(s)",
                "deletedFiles": deleted_files,
                "groupId": group_id,
            }
        )

    except Exception as e:
        print(f"[Backend] Error deleting scan: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Save Fix History ===
def save_fix_history(
    scan_id,
    original_filename,
    fixed_filename,
    fixes_applied,
    fix_type="automated",
    batch_id=None,
    group_id=None,
    issues_before=None,
    issues_after=None,
    compliance_before=None,
    compliance_after=None,
    total_issues_before=0,
    total_issues_after=0,
    high_severity_before=0,
    high_severity_after=0,
    fix_suggestions=None,
    fix_metadata=None,
    version=None,
):
    """
    Save fix history to the fix_history table.
    All fix records are stored exclusively in fix_history table.
    The scans table maintains only the initial scan data.
    """
    try:
        conn = get_db_connection()
        c = conn.cursor()

        fix_metadata = dict(fix_metadata or {})
        if version is not None:
            fix_metadata.setdefault("version", version)
            fix_metadata.setdefault("versionLabel", f"V{version}")
            fix_metadata.setdefault("relativePath", fixed_filename)

        if not original_filename:
            print(
                f"[Backend] ⚠ original_filename is missing, retrieving from scan record..."
            )
            c.execute("SELECT filename FROM scans WHERE id = %s", (scan_id,))
            scan_record = c.fetchone()
            if scan_record and scan_record.get("filename"):
                original_filename = scan_record["filename"]
                print(
                    f"[Backend] ✓ Retrieved original_filename from scan: {original_filename}"
                )
            else:
                print(
                    f"[Backend] ✗ Could not retrieve original_filename for scan_id: {scan_id}"
                )
                conn.close()
                return None

        # Ensure fixed_filename is set
        if not fixed_filename:
            fixed_filename = original_filename.replace(".pdf", "_fixed.pdf")

        if total_issues_before == 0 and issues_before:
            # Count total issues from issues_before dictionary
            if isinstance(issues_before, dict):
                total_issues_before = sum(
                    len(issues)
                    for issues in issues_before.values()
                    if isinstance(issues, list)
                )
            print(f"[Backend] ✓ Calculated total_issues_before: {total_issues_before}")

        if total_issues_after == 0 and issues_after:
            # Count total issues from issues_after dictionary
            if isinstance(issues_after, dict):
                total_issues_after = sum(
                    len(issues)
                    for issues in issues_after.values()
                    if isinstance(issues, list)
                )
            print(f"[Backend] ✓ Calculated total_issues_after: {total_issues_after}")

        # If still 0, try to get from scan record
        if total_issues_before == 0:
            c.execute("SELECT total_issues FROM scans WHERE id = %s", (scan_id,))
            scan_record = c.fetchone()
            if scan_record and scan_record.get("total_issues"):
                total_issues_before = scan_record["total_issues"]
                print(
                    f"[Backend] ✓ Retrieved total_issues_before from scan: {total_issues_before}"
                )

        # Calculate high severity counts if not provided
        if high_severity_before == 0 and issues_before:
            if isinstance(issues_before, dict):
                for category, issues_list in issues_before.items():
                    if isinstance(issues_list, list):
                        high_severity_before += sum(
                            1
                            for issue in issues_list
                            if issue.get("severity") == "high"
                        )

        if high_severity_after == 0 and issues_after:
            if isinstance(issues_after, dict):
                for category, issues_list in issues_after.items():
                    if isinstance(issues_list, list):
                        high_severity_after += sum(
                            1
                            for issue in issues_list
                            if issue.get("severity") == "high"
                        )

        print(f"[Backend] 💾 Saving fix history:")
        print(f"[Backend]   - scan_id: {scan_id}")
        print(f"[Backend]   - original_filename: {original_filename}")
        print(f"[Backend]   - fixed_filename: {fixed_filename}")
        print(f"[Backend]   - fix_type: {fix_type}")
        print(
            f"[Backend]   - total_issues: {total_issues_before} → {total_issues_after}"
        )
        print(f"[Backend]   - compliance: {compliance_before}% → {compliance_after}%")

        # Get batch_id and group_id from scan if not provided
        if not batch_id or not group_id:
            c.execute("SELECT batch_id, group_id FROM scans WHERE id = %s", (scan_id,))
            scan_record = c.fetchone()
            if scan_record:
                if not batch_id:
                    batch_id = scan_record.get("batch_id")
                if not group_id:
                    group_id = scan_record.get("group_id")

        query = """
            INSERT INTO fix_history (
                scan_id, original_file, fixed_file, original_filename, fixed_filename,
                fixes_applied, fix_type, applied_at,
                batch_id, group_id,
                issues_before, issues_after,
                compliance_before, compliance_after,
                total_issues_before, total_issues_after,
                high_severity_before, high_severity_after,
                fix_suggestions, fix_metadata
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id
        """

        c.execute(
            query,
            (
                scan_id,
                original_filename,  # original_file
                fixed_filename,  # fixed_file
                original_filename,  # original_filename
                fixed_filename,  # fixed_filename
                json.dumps(fixes_applied) if fixes_applied else "[]",
                fix_type,
                datetime.now(),
                batch_id,
                group_id,
                json.dumps(issues_before) if issues_before else "{}",
                json.dumps(issues_after) if issues_after else "{}",
                compliance_before,
                compliance_after,
                total_issues_before,
                total_issues_after,
                high_severity_before,
                high_severity_after,
                json.dumps(fix_suggestions) if fix_suggestions else "[]",
                json.dumps(fix_metadata) if fix_metadata else "{}",
            ),
        )

        fix_history_id = c.fetchone()["id"]
        conn.commit()

        print(
            f"[Backend] ✓ Fix history saved (ID: {fix_history_id}): {original_filename} -> {fixed_filename}"
        )
        print(
            f"[Backend]   Fix type: {fix_type}, Issues: {total_issues_before} → {total_issues_after}"
        )

        update_query = """
            UPDATE scans
            SET status = 'fixed',
                issues_fixed = %s,
                issues_remaining = %s
            WHERE id = %s
        """
        c.execute(
            update_query,
            (total_issues_before - total_issues_after, total_issues_after, scan_id),
        )

        conn.commit()
        conn.close()

        print(f"[Backend] ✓ Scan status updated successfully")

        return fix_history_id

    except Exception as e:
        print(f"[Backend] ✗ Error saving fix history: {e}")
        import traceback

        traceback.print_exc()
        if "conn" in locals():
            conn.rollback()
            conn.close()
        print(
            f"[Backend] ⚠ WARNING: Fix history save failed, but fix was applied successfully"
        )
        return None


# === Get Scan by ID ===
def get_scan_by_id(scan_id):
    """Get scan by ID with multiple fallback strategies and ensure .pdf extension"""
    try:
        print(f"[Backend] Looking up scan: {scan_id}")

        # Strategy 1: Query by exact id
        query = "SELECT * FROM scans WHERE id = %s"
        result = execute_query(query, (scan_id,), fetch=True)

        if not result or len(result) == 0:
            # Try without .pdf extension
            scan_id_no_ext = scan_id.replace(".pdf", "")
            result = execute_query(query, (scan_id_no_ext,), fetch=True)

        if not result or len(result) == 0:
            # Try by filename
            query = "SELECT * FROM scans WHERE filename = %s ORDER BY created_at DESC LIMIT 1"
            result = execute_query(query, (scan_id,), fetch=True)

        if result and len(result) > 0:
            scan = dict(result[0])
            # Ensure consistency in filename handling if needed, though 'id' is primary
            # if 'file_path' in scan and not scan['file_path'].endswith('.pdf'):
            #     scan['file_path'] = f"{scan['file_path']}.pdf"
            print(f"[Backend] ✓ Found scan by id")
            return scan

        print(f"[Backend] ✗ Scan not found: {scan_id}")
        return None

    except Exception as e:
        print(f"[Backend] Error getting scan: {e}")
        import traceback

        traceback.print_exc()
        return None


def update_scan_status(scan_id):
    """Update scan status based on applied fixes and remaining issues"""
    try:
        conn = get_db_connection()
        c = conn.cursor()

        c.execute(
            """
            SELECT scan_results, issues_fixed, total_issues
            FROM scans
            WHERE id = %s
        """,
            (scan_id,),
        )

        result = c.fetchone()
        if not result:
            c.close()
            conn.close()
            print(f"[v0] Scan {scan_id} not found for status update")
            return None

        scan_results = result["scan_results"]
        if isinstance(scan_results, str):
            scan_results = json.loads(scan_results)

        # Get summary from scan_results
        summary = scan_results.get("summary", {})
        total_issues = summary.get("totalIssues", result.get("total_issues") or 0)

        # Determine status based on fix history
        c.execute(
            """
            SELECT COUNT(*) as fix_count
            FROM fix_history
            WHERE scan_id = %s
        """,
            (scan_id,),
        )

        fix_count_result = c.fetchone()
        has_fixes = fix_count_result and fix_count_result["fix_count"] > 0

        # Determine status
        if has_fixes and total_issues == 0:
            new_status = "fixed"
        elif has_fixes:
            new_status = "processed"
        elif total_issues == 0:
            new_status = "compliant"
        else:
            new_status = "unprocessed"

        # Update status
        c.execute(
            """
            UPDATE scans
            SET status = %s
            WHERE id = %s
        """,
            (new_status, scan_id),
        )

        conn.commit()
        c.close()
        conn.close()

        print(f"[v0] ✓ Scan status updated successfully")
        print(f"[v0] Updated scan {scan_id} status to: {new_status}")
        return new_status

    except Exception as e:
        print(f"[v0] Error updating scan status: {e}")
        import traceback

        traceback.print_exc()
        return None


@app.route("/api/groups", methods=["GET"])
def get_groups():
    """Get all groups with file counts"""
    try:
        print("[Backend] 📋 Fetching all groups...")
        query = """
            SELECT g.id, g.name, g.description, g.created_at,
                   COALESCE(g.file_count, 0) as file_count
            FROM groups g
            ORDER BY g.created_at DESC
        """
        groups = execute_query(query, fetch=True)

        groups_list = [dict(g) for g in groups] if groups else []

        print(f"[Backend] ✓ Returning {len(groups_list)} groups")
        for group in groups_list:
            print(
                f"[Backend]   - {group['name']} ({group['id']}) - {group['file_count']} files"
            )

        return jsonify({"groups": groups_list})
    except Exception as e:
        print(f"[Backend] ✗ Error fetching groups: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups", methods=["POST"])
def create_group():
    """Create a new group"""
    try:
        data = request.get_json()
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()

        if not name:
            return jsonify({"error": "Group name is required"}), 400

        if len(name) > 255:
            return jsonify(
                {"error": "Group name must be less than 255 characters"}
            ), 400

        group_id = f"group_{uuid.uuid4().hex}"

        conn = get_db_connection()
        c = conn.cursor()

        try:
            # Ensure name uniqueness (case-insensitive) before attempting insert
            c.execute(
                """
                SELECT id FROM groups
                WHERE LOWER(name) = LOWER(%s)
                LIMIT 1
            """,
                (name,),
            )

            if c.fetchone():
                c.close()
                conn.close()
                return jsonify({"error": "A group with this name already exists"}), 409

            # Insert group with explicit file_count initialization
            c.execute(
                """
                INSERT INTO groups (id, name, description, created_at, file_count)
                VALUES (%s, %s, %s, NOW(), 0)
                RETURNING id, name, description, created_at, file_count
            """,
                (group_id, name, description),
            )

            result = c.fetchone()
            conn.commit()

            if result:
                group = dict(result)
                print(f"[Backend] ✓ Created group: {name} ({group_id})")
                c.close()
                conn.close()
                return jsonify({"group": group}), 201
            else:
                conn.rollback()
                c.close()
                conn.close()
                return jsonify({"error": "Failed to create group"}), 500

        except psycopg2.IntegrityError as e:
            conn.rollback()
            c.close()
            conn.close()
            print(f"[Backend] ✗ Integrity error creating group: {e}")
            return jsonify({"error": "A group with this name already exists"}), 409
        except Exception as e:
            conn.rollback()
            c.close()
            conn.close()
            raise e

    except Exception as e:
        print(f"[Backend] Error creating group: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>", methods=["GET"])
def get_group(group_id):
    """Get group details with all scans"""
    try:
        query = """
            SELECT g.*, 
                   COUNT(s.id) as file_count
            FROM groups g
            LEFT JOIN scans s ON g.id = s.group_id
            WHERE g.id = %s
            GROUP BY g.id
        """
        result = execute_query(query, (group_id,), fetch=True)

        if not result or len(result) == 0:
            return jsonify({"error": "Group not found"}), 404

        group = dict(result[0])

        # Get all scans in this group
        scans_query = """
            SELECT id, filename, status, upload_date, created_at
            FROM scans
            WHERE group_id = %s
            ORDER BY upload_date DESC
        """
        scans = execute_query(scans_query, (group_id,), fetch=True)
        group["scans"] = scans

        return jsonify({"group": group})
    except Exception as e:
        print(f"[Backend] Error fetching group: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>", methods=["DELETE"])
def delete_group(group_id):
    """Delete a group (scans will have group_id set to NULL)"""
    try:
        # Check if group exists
        check_query = "SELECT id FROM groups WHERE id = %s"
        result = execute_query(check_query, (group_id,), fetch=True)

        if not result or len(result) == 0:
            return jsonify({"error": "Group not found"}), 404

        # Delete group (CASCADE will set group_id to NULL in scans)
        delete_query = "DELETE FROM groups WHERE id = %s"
        execute_query(delete_query, (group_id,), fetch=False)

        print(f"[Backend] ✓ Deleted group: {group_id}")
        return jsonify({"success": True, "message": "Group deleted successfully"})
    except Exception as e:
        print(f"[Backend] Error deleting group: {e}")
        return jsonify({"error": str(e)}), 500


# === Update Group ===
@app.route("/api/groups/<group_id>", methods=["PUT"])
def update_group(group_id):
    """Update group details"""
    try:
        data = request.get_json()
        name = data.get("name", "").strip()
        description = data.get("description", "").strip()

        if not name:
            return jsonify({"error": "Group name is required"}), 400

        # Check if group exists
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM groups WHERE id = %s", (group_id,))
        existing = cur.fetchone()

        if not existing:
            cur.close()
            conn.close()
            return jsonify({"error": "Group not found"}), 404

        # Ensure name uniqueness (case-insensitive) against other groups
        cur.execute(
            """
            SELECT id FROM groups
            WHERE LOWER(name) = LOWER(%s) AND id <> %s
            LIMIT 1
        """,
            (name, group_id),
        )
        if cur.fetchone():
            cur.close()
            conn.close()
            return jsonify({"error": "A group with this name already exists"}), 409

        cur.execute(
            """
            UPDATE groups
            SET name = %s, description = %s
            WHERE id = %s
            RETURNING id, name, description, created_at, file_count
        """,
            (name, description, group_id),
        )
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        if result:
            group = dict(result)
            print(f"[Backend] ✓ Updated group: {name} ({group_id})")
            return jsonify({"group": group})

        return jsonify({"error": "Failed to update group"}), 500

    except psycopg2.IntegrityError:
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({"error": "A group with this name already exists"}), 409
    except Exception as e:
        print(f"[Backend] Error updating group: {e}")
        import traceback

        traceback.print_exc()
        try:
            cur.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({"error": str(e)}), 500


# === Get Batch Details ===
@app.route("/api/batch/<batch_id>", methods=["GET"])
def get_batch_details(batch_id):
    """
    Returns all scans for a given batch with their current state.
    Combines initial scan data from scans table with latest fix data from fix_history.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Fetch batch details
        cur.execute(
            """
            SELECT 
                id,
                name,
                created_at,
                group_id,
                status,
                total_files,
                total_issues,
                fixed_issues,
                remaining_issues,
                unprocessed_files
            FROM batches
            WHERE id = %s
        """,
            (batch_id,),
        )
        batch = cur.fetchone()

        if not batch:
            return jsonify({"error": f"Batch {batch_id} not found"}), 404

        cur.execute(
            """
            SELECT 
                s.id AS scan_id,
                s.filename,
                s.scan_results,
                s.status,
                s.upload_date,
                s.group_id,
                s.total_issues as initial_total_issues,
                fh.id as fix_id,
                fh.fixed_filename,
                fh.fixes_applied,
                fh.applied_at,
                fh.fix_type,
                fh.total_issues_after,
                fh.compliance_after,
                fh.high_severity_after,
                fh.issues_after
            FROM scans s
            LEFT JOIN LATERAL (
                SELECT * FROM fix_history
                WHERE scan_id = s.id
                ORDER BY applied_at DESC
                LIMIT 1
            ) fh ON true
            WHERE s.batch_id = %s
            ORDER BY s.upload_date DESC
        """,
            (batch_id,),
        )
        scans = cur.fetchall()

        processed_scans = []
        total_issues = 0
        total_compliance = 0
        total_high = 0

        for scan in scans:
            # Parse initial scan results
            scan_results = scan.get("scan_results")
            if isinstance(scan_results, str):
                try:
                    scan_results = json.loads(scan_results)
                except Exception:
                    scan_results = {}

            initial_summary = (
                scan_results.get("summary", {})
                if isinstance(scan_results, dict)
                else {}
            )

            if scan.get("fix_id"):
                # Scan has been fixed - use data from fix_history
                current_issues = scan.get("total_issues_after", 0)
                current_compliance = scan.get("compliance_after", 0)
                current_high = scan.get("high_severity_after", 0)
                current_status = "fixed"
                fixes_applied = scan.get("fixes_applied", [])
            else:
                # Scan not fixed yet - use initial scan data
                current_issues = initial_summary.get("totalIssues", 0)
                current_compliance = initial_summary.get("complianceScore", 0)
                current_high = initial_summary.get("highSeverity", 0)
                current_status = scan.get("status", "scanned")
                fixes_applied = []

            # Aggregate stats
            total_issues += current_issues
            total_high += current_high
            total_compliance += current_compliance

            version_entries = get_versioned_files(scan["scan_id"])
            latest_version_entry = version_entries[-1] if version_entries else None
            version_history = (
                [
                    {
                        "version": entry["version"],
                        "label": f"V{entry['version']}",
                        "relativePath": entry["relative_path"],
                        "createdAt": entry["created_at"].isoformat()
                        if entry["created_at"]
                        else None,
                        "downloadable": entry["version"]
                        == latest_version_entry["version"],
                        "fileSize": entry["size"],
                    }
                    for entry in reversed(version_entries)
                ]
                if version_entries
                else []
            )

            processed_scans.append(
                {
                    "scanId": scan["scan_id"],
                    "filename": scan["filename"],
                    "status": current_status,
                    "uploadDate": scan.get("upload_date"),
                    "groupId": scan.get("group_id"),
                    "fixedFilename": scan.get("fixed_filename"),
                    "lastFixApplied": scan.get("applied_at"),
                    "fixType": scan.get("fix_type"),
                    "fixesApplied": fixes_applied,
                    "summary": {
                        "totalIssues": current_issues,
                        "highSeverity": current_high,
                        "complianceScore": current_compliance,
                    },
                    "initialSummary": {
                        "totalIssues": initial_summary.get("totalIssues", 0),
                        "highSeverity": initial_summary.get("highSeverity", 0),
                        "complianceScore": initial_summary.get("complianceScore", 0),
                    },
                    "results": scan_results.get("results", {})
                    if isinstance(scan_results, dict)
                    else {},
                    "latestVersion": latest_version_entry["version"]
                    if latest_version_entry
                    else None,
                    "latestFixedFile": latest_version_entry["relative_path"]
                    if latest_version_entry
                    else None,
                    "versionHistory": version_history,
                }
            )

        avg_compliance = (
            round(total_compliance / len(processed_scans), 2) if processed_scans else 0
        )

        batch_total_issues = batch.get("total_issues")
        batch_fixed_issues = batch.get("fixed_issues")
        batch_remaining_issues = batch.get("remaining_issues")
        batch_unprocessed_files = batch.get("unprocessed_files")
        batch_total_files = batch.get("total_files")

        response = {
            "batchId": batch_id,
            "batchName": batch.get("name"),
            "name": batch.get("name"),
            "createdAt": batch.get("created_at"),
            "uploadDate": batch.get("created_at"),
            "groupId": batch.get("group_id"),
            "status": batch.get("status"),
            "fileCount": batch_total_files if batch_total_files is not None else len(processed_scans),
            "totalIssues": batch_total_issues if batch_total_issues is not None else total_issues,
            "fixedIssues": batch_fixed_issues if batch_fixed_issues is not None else max(
                (batch_total_issues if batch_total_issues is not None else total_issues) - (batch_remaining_issues or 0), 0
            ),
            "remainingIssues": batch_remaining_issues if batch_remaining_issues is not None else max(
                total_issues - (batch_fixed_issues or 0), 0
            ),
            "unprocessedFiles": batch_unprocessed_files if batch_unprocessed_files is not None else sum(
                1
                for scan in processed_scans
                if (scan.get("status") or "").lower() in {"uploaded", "unprocessed", "processing"}
            ),
            "highSeverity": total_high,
            "avgCompliance": avg_compliance,
            "scans": processed_scans,
        }

        conn.close()
        return jsonify(response)

    except Exception as e:
        print(f"[Backend] ✗ Error fetching batch details: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": "Failed to load batch details"}), 500


# === Delete Batch ===
@app.route("/api/batch/<batch_id>", methods=["DELETE"])
def delete_batch(batch_id):
    """Delete a batch and all its scans"""
    try:
        print(f"[Backend] Deleting batch: {batch_id}")

        scans_query = "SELECT id, group_id FROM scans WHERE batch_id = %s"
        scans = execute_query(scans_query, (batch_id,), fetch=True)

        affected_groups = set()
        for scan in scans:
            if scan.get("group_id"):
                affected_groups.add(scan["group_id"])

        # Delete physical files
        uploads_dir = Path(UPLOAD_FOLDER)
        fixed_dir = Path(FIXED_FOLDER)
        deleted_files = 0

        for scan in scans:
            scan_id = scan["id"]
            for folder in [uploads_dir, fixed_dir]:
                for ext in ["", ".pdf"]:
                    file_path = folder / f"{scan_id}{ext}"
                    if file_path.exists():
                        file_path.unlink()
                        deleted_files += 1

        # Delete from database
        execute_query(
            "DELETE FROM fix_history WHERE scan_id IN (SELECT id FROM scans WHERE batch_id = %s)",
            (batch_id,),
            fetch=False,
        )
        execute_query("DELETE FROM scans WHERE batch_id = %s", (batch_id,), fetch=False)
        execute_query("DELETE FROM batches WHERE id = %s", (batch_id,), fetch=False)

        for group_id in affected_groups:
            update_group_file_count(group_id)
            print(f"[Backend] Updated file count for group: {group_id}")

        print(
            f"[Backend] ✓ Deleted batch {batch_id} with {len(scans)} scans and {deleted_files} files"
        )

        return jsonify(
            {
                "success": True,
                "message": f"Deleted batch with {len(scans)} scans",
                "deletedFiles": deleted_files,
                "affectedGroups": list(affected_groups),
            }
        )

    except Exception as e:
        print(f"[Backend] Error deleting batch: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# === Batch Download ===
@app.route("/api/batch/<batch_id>/download", methods=["GET"])
def download_batch(batch_id):
    """Download all files in a batch as a ZIP file"""
    try:
        import zipfile
        from io import BytesIO

        print(f"[Backend] Creating ZIP for batch: {batch_id}")

        # Get all scans in batch
        scans_query = "SELECT id, filename FROM scans WHERE batch_id = %s"
        scans = execute_query(scans_query, (batch_id,), fetch=True)

        if not scans or len(scans) == 0:
            return jsonify({"error": "No files found in batch"}), 404

        # Create ZIP file in memory
        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            uploads_dir = Path(UPLOAD_FOLDER)
            fixed_dir = Path(FIXED_FOLDER)

            for scan in scans:
                scan_id = scan["id"]
                filename = scan["filename"]

                # Try to find the file
                file_path = None
                for folder in [fixed_dir, uploads_dir]:
                    for ext in ["", ".pdf"]:
                        path = folder / f"{scan_id}{ext}"
                        if path.exists():
                            file_path = path
                            break
                    if file_path:
                        break

                if file_path:
                    # Add file to ZIP with original filename
                    zip_file.write(file_path, filename)
                    print(f"[Backend] Added to ZIP: {filename}")

        zip_buffer.seek(0)

        # Get batch name for filename
        batch_query = "SELECT name FROM batches WHERE id = %s"
        batch_result = execute_query(batch_query, (batch_id,), fetch=True)
        batch_name = batch_result[0]["name"] if batch_result else batch_id

        print(f"[Backend] ✓ ZIP created with {len(scans)} files")

        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"{batch_name}.zip",
        )

    except Exception as e:
        print(f"[Backend] Error creating batch ZIP: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/batch/<batch_id>/export", methods=["GET"])
def export_batch(batch_id):
    """Generate a ZIP containing batch metadata, scan summaries, and source/fixed PDFs."""
    try:
        import zipfile
        from io import BytesIO
        import re

        print(f"[Backend] Exporting batch package for: {batch_id}")

        update_batch_statistics(batch_id)

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            """
            SELECT id, name, group_id, created_at, status,
                   total_files, total_issues, fixed_issues,
                   remaining_issues, unprocessed_files
            FROM batches
            WHERE id = %s
        """,
            (batch_id,),
        )
        batch = cur.fetchone()

        if not batch:
            cur.close()
            conn.close()
            return jsonify({"error": f"Batch {batch_id} not found"}), 404

        cur.execute(
            """
            SELECT s.id, s.filename, s.scan_results, s.status, s.upload_date,
                   s.total_issues, s.issues_fixed, s.issues_remaining,
                   fh.fixed_filename, fh.fixes_applied, fh.applied_at, fh.fix_type,
                   fh.total_issues_after, fh.compliance_after, fh.high_severity_after
            FROM scans s
            LEFT JOIN LATERAL (
                SELECT *
                FROM fix_history
                WHERE scan_id = s.id
                ORDER BY applied_at DESC
                LIMIT 1
            ) fh ON true
            WHERE s.batch_id = %s
            ORDER BY COALESCE(s.upload_date, s.created_at)
        """,
            (batch_id,),
        )
        scans = cur.fetchall()

        cur.close()
        conn.close()

        if not scans:
            return jsonify({"error": "No scans found for this batch"}), 404

        def _sanitize(value: str, fallback: str) -> str:
            text = value or fallback
            return re.sub(r"[^A-Za-z0-9._-]", "_", text)

        def _deserialize_payload(value, fallback):
            if not value:
                return fallback
            if isinstance(value, (list, dict)):
                return value
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except Exception:
                    return fallback
            return fallback

        def _to_export_payload(scan_row):
            scan_results = scan_row.get("scan_results", {})
            if isinstance(scan_results, str):
                try:
                    scan_results = json.loads(scan_results)
                except Exception:
                    scan_results = {}

            results = scan_results.get("results", scan_results) or {}
            summary = scan_results.get("summary", {}) or {}
            verapdf_status = scan_results.get("verapdfStatus")

            if verapdf_status is None:
                verapdf_status = build_verapdf_status(results)

            if not summary or "totalIssues" not in summary:
                try:
                    summary = PDFAccessibilityAnalyzer.calculate_summary(
                        results, verapdf_status
                    )
                except Exception as calc_error:
                    print(
                        f"[Backend] Warning: unable to regenerate summary for export ({scan_row.get('id')}): {calc_error}"
                    )
                    total_issues = sum(
                        len(v) if isinstance(v, list) else 0 for v in results.values()
                    )
                    summary = {
                        "totalIssues": total_issues,
                        "highSeverity": 0,
                        "complianceScore": max(0, 100 - total_issues * 2),
                    }

            if isinstance(summary, dict) and verapdf_status:
                summary.setdefault("wcagCompliance", verapdf_status.get("wcagCompliance"))
                summary.setdefault("pdfuaCompliance", verapdf_status.get("pdfuaCompliance"))

            latest_fix = None
            if scan_row.get("applied_at"):
                fix_list = _deserialize_payload(scan_row.get("fixes_applied"), [])
                latest_fix = {
                    "fixedFilename": scan_row.get("fixed_filename"),
                    "fixType": scan_row.get("fix_type"),
                    "appliedAt": scan_row.get("applied_at").isoformat()
                    if scan_row.get("applied_at")
                    else None,
                    "fixesApplied": fix_list,
                    "totalIssuesAfter": scan_row.get("total_issues_after"),
                    "complianceAfter": scan_row.get("compliance_after"),
                    "highSeverityAfter": scan_row.get("high_severity_after"),
                }

            export_payload = {
                "scanId": scan_row.get("id"),
                "filename": scan_row.get("filename"),
                "status": scan_row.get("status"),
                "uploadDate": scan_row.get("upload_date").isoformat()
                if scan_row.get("upload_date")
                else None,
                "summary": summary,
                "results": results,
                "verapdfStatus": verapdf_status,
                "issues": {
                    "total": scan_row.get("total_issues"),
                    "fixed": scan_row.get("issues_fixed"),
                    "remaining": scan_row.get("issues_remaining"),
                },
                "latestFix": latest_fix,
            }

            return export_payload

        batch_name = batch.get("name") or batch_id
        safe_batch_name = _sanitize(batch_name, batch_id)

        export_summary = {
            "batch": {
                "id": batch_id,
                "name": batch_name,
                "groupId": batch.get("group_id"),
                "createdAt": batch.get("created_at").isoformat()
                if batch.get("created_at")
                else None,
                "status": batch.get("status"),
            },
            "totals": {
                "files": batch.get("total_files"),
                "issues": batch.get("total_issues"),
                "fixedIssues": batch.get("fixed_issues"),
                "remainingIssues": batch.get("remaining_issues"),
                "unprocessedFiles": batch.get("unprocessed_files"),
            },
            "generatedAt": datetime.utcnow().isoformat() + "Z",
        }

        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(
                f"{safe_batch_name}/batch_summary.json",
                json.dumps(export_summary, indent=2, default=str),
            )

            uploads_dir = Path(UPLOAD_FOLDER)
            fixed_dir = Path(FIXED_FOLDER)

            for scan_row in scans:
                scan_export = _to_export_payload(scan_row)
                sanitized_filename = _sanitize(scan_row.get("filename"), scan_row.get("id"))

                zip_file.writestr(
                    f"{safe_batch_name}/scans/{sanitized_filename}.json",
                    json.dumps(scan_export, indent=2, default=str),
                )

                scan_id = scan_row.get("id")
                pdf_added = False
                latest_fixed_entry = get_fixed_version(scan_id)
                if latest_fixed_entry:
                    arcname = (
                        f"{safe_batch_name}/files/{latest_fixed_entry['filename']}"
                    )
                    zip_file.write(latest_fixed_entry["absolute_path"], arcname)
                    pdf_added = True
                    print(
                        f"[Backend] Added latest fixed PDF to export: {latest_fixed_entry['absolute_path']}"
                    )

                if not pdf_added:
                    for candidate in [
                        uploads_dir / f"{scan_id}.pdf",
                        uploads_dir / scan_row.get("filename", ""),
                    ]:
                        if candidate and candidate.exists():
                            arcname = f"{safe_batch_name}/files/{candidate.name}"
                            zip_file.write(candidate, arcname)
                            pdf_added = True
                            print(f"[Backend] Added original PDF to export: {candidate}")
                            break

                version_entries = get_versioned_files(scan_id)
                if version_entries:
                    for entry in version_entries:
                        arcname = f"{safe_batch_name}/fixed/{scan_id}/{entry['filename']}"
                        zip_file.write(entry["absolute_path"], arcname)
                        print(
                            f"[Backend] Added version V{entry['version']} to export: {entry['absolute_path']}"
                        )
                else:
                    fixed_filename = scan_row.get("fixed_filename")
                    if fixed_filename:
                        fixed_path = fixed_dir / fixed_filename
                        if fixed_path.exists():
                            arcname = f"{safe_batch_name}/fixed/{fixed_filename}"
                            zip_file.write(fixed_path, arcname)
                            print(f"[Backend] Added fixed PDF to export: {fixed_path}")

        zip_buffer.seek(0)

        download_name = f"{safe_batch_name}.zip"
        print(
            f"[Backend] ✓ Batch export prepared: {download_name} with {len(scans)} scans"
        )

        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=download_name,
        )

    except Exception as e:
        print(f"[Backend] Error exporting batch: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def update_group_file_count(group_id):
    """Update the file_count for a group based on actual scans"""
    try:
        query = """
            UPDATE groups 
            SET file_count = (
                SELECT COUNT(*) 
                FROM scans 
                WHERE group_id = %s
            )
            WHERE id = %s
        """
        execute_query(query, (group_id, group_id), fetch=False)
        print(f"[Backend] ✓ Updated file count for group {group_id}")
    except Exception as e:
        print(f"[Backend] Error updating group file count: {e}")
        import traceback

        traceback.print_exc()


@app.route("/api/groups/<group_id>/files", methods=["GET"])
def get_group_files(group_id):
    """Get all files/scans for a specific group"""
    try:
        query = """
            SELECT id, filename, status, upload_date, 
                   total_issues, issues_fixed, scan_results
            FROM scans
            WHERE group_id = %s
            ORDER BY upload_date DESC
        """
        results = execute_query(query, (group_id,), fetch=True)

        files = []
        for row in results:
            scan_dict = dict(row)

            # Parse scan_results to get summary
            scan_results = scan_dict.get("scan_results", {})
            if isinstance(scan_results, str):
                try:
                    scan_results = json.loads(scan_results)
                except Exception as e:
                    print(f"[v0] Warning: failed to parse scan_results JSON: {e}")
                    scan_results = {}

            summary = scan_results.get("summary", {})

            files.append(
                {
                    "id": scan_dict["id"],
                    "filename": scan_dict["filename"],
                    "status": scan_dict.get("status", "unprocessed"),
                    "uploadDate": scan_dict.get("upload_date"),
                    "totalIssues": summary.get(
                        "totalIssues", scan_dict.get("total_issues", 0)
                    ),
                    "issuesFixed": scan_dict.get("issues_fixed", 0),
                    "complianceScore": summary.get("complianceScore", 0),
                }
            )

        return jsonify({"files": files})

    except Exception as e:
        print(f"[v0] Error fetching group files: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>/details", methods=["GET"])
def get_group_details(group_id):
    """
    Returns group-level summary with total files, issues, and compliance averages.
    Used by GroupDashboard.jsx
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Fetch basic group info
        cur.execute(
            """
            SELECT id, name, description, created_at
            FROM groups
            WHERE id = %s
        """,
            (group_id,),
        )
        group = cur.fetchone()

        if not group:
            return jsonify({"error": f"Group {group_id} not found"}), 404

        # Fetch scans in this group
        cur.execute(
            """
            SELECT scan_results, status
            FROM scans
            WHERE group_id = %s
        """,
            (group_id,),
        )
        scans = cur.fetchall()

        total_files = len(scans)
        total_issues = 0
        issues_fixed = 0
        total_compliance = 0
        fixed_count = 0
        severity_totals = {"high": 0, "medium": 0, "low": 0}
        category_totals = {}
        status_counts = {}

        for scan in scans:
            scan_results = scan.get("scan_results")
            if isinstance(scan_results, str):
                try:
                    scan_results = json.loads(scan_results)
                except Exception:
                    scan_results = {}

            summary = (
                scan_results.get("summary", {})
                if isinstance(scan_results, dict)
                else {}
            )
            results = (
                scan_results.get("results", {})
                if isinstance(scan_results, dict)
                else {}
            )

            total_issues += summary.get("totalIssues", 0)
            total_compliance += summary.get("complianceScore", 0)

            status_key = (scan.get("status") or "unknown").lower()
            status_counts[status_key] = status_counts.get(status_key, 0) + 1

            for category, issues in results.items():
                if not isinstance(issues, list):
                    continue
                category_totals[category] = category_totals.get(category, 0) + len(issues)
                for issue in issues:
                    if not isinstance(issue, dict):
                        continue
                    severity = (issue.get("severity") or "").lower()
                    if severity in severity_totals:
                        severity_totals[severity] += 1

            if status_key == "fixed":
                fixed_count += 1
                # This calculation of issues_fixed is a bit off. It sums up totalIssues of fixed files, not actual fixed issues.
                # A more accurate way would be to sum (total_issues_before - total_issues_after) from fix_history.
                # For now, we'll use this simplified approach.
                issues_fixed += summary.get("totalIssues", 0)

        avg_compliance = (
            round(total_compliance / total_files, 2) if total_files > 0 else 0
        )

        response = {
            "groupId": group["id"],
            "name": group["name"],
            "description": group.get("description", ""),
            "file_count": total_files,
            "total_issues": total_issues,
            "issues_fixed": issues_fixed,  # Note: This is total issues in files marked as 'fixed'
            "avg_compliance": avg_compliance,
            "fixed_files": fixed_count,
            "category_totals": category_totals,
            "severity_totals": severity_totals,
            "status_counts": status_counts,
        }

        conn.close()
        return jsonify(response)

    except Exception as e:
        print(f"[Backend] ✗ Error fetching group details for {group_id}: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": "Failed to fetch group details"}), 500


@app.route("/api/scan/<scan_id>/current-state", methods=["GET"])
def get_scan_current_state(scan_id):
    """
    Returns the current state of a scan by combining:
    1. Initial scan results from scans table
    2. Latest fix data from fix_history table

    This provides a complete view of the scan's current status.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get initial scan data
        cur.execute(
            """
            SELECT id, filename, batch_id, group_id, status, upload_date, 
                   scan_results, total_issues, issues_fixed, issues_remaining
            FROM scans
            WHERE id = %s
        """,
            (scan_id,),
        )

        scan = cur.fetchone()
        if not scan:
            return jsonify({"error": "Scan not found"}), 404

        # Get latest fix from fix_history
        cur.execute(
            """
            SELECT id, fixed_filename, fixes_applied, applied_at, fix_type,
                   issues_after, compliance_after, total_issues_after,
                   high_severity_after, fix_suggestions
            FROM fix_history
            WHERE scan_id = %s
            ORDER BY applied_at DESC
            LIMIT 1
        """,
            (scan_id,),
        )

        latest_fix = cur.fetchone()

        # Parse scan_results
        scan_results = scan.get("scan_results", {})
        if isinstance(scan_results, str):
            scan_results = json.loads(scan_results)

        # Build response
        response = {
            "scanId": scan["id"],
            "filename": scan["filename"],
            "batchId": scan.get("batch_id"),
            "groupId": scan.get("group_id"),
            "uploadDate": scan.get("upload_date"),
            "initialScan": {
                "results": scan_results.get("results", {}),
                "summary": scan_results.get("summary", {}),
                "totalIssues": scan.get("total_issues", 0),
            },
        }

        version_entries = get_versioned_files(scan_id)
        latest_version_entry = version_entries[-1] if version_entries else None

        # Add latest fix data if exists
        if latest_fix:
            response["currentState"] = {
                "status": "fixed",
                "fixedFilename": latest_fix.get("fixed_filename"),
                "lastFixApplied": latest_fix.get("applied_at"),
                "fixType": latest_fix.get("fix_type"),
                "fixesApplied": latest_fix.get("fixes_applied", []),
                "remainingIssues": latest_fix.get("issues_after", {}),
                "complianceScore": latest_fix.get("compliance_after", 0),
                "totalIssues": latest_fix.get("total_issues_after", 0),
                "highSeverity": latest_fix.get("high_severity_after", 0),
                "suggestions": latest_fix.get("fix_suggestions", []),
            }
            if latest_version_entry:
                response["currentState"]["version"] = latest_version_entry["version"]
                response["currentState"]["fixedFilePath"] = latest_version_entry[
                    "relative_path"
                ]
        else:
            response["currentState"] = {
                "status": scan.get("status", "scanned"),
                "remainingIssues": scan_results.get("results", {}),
                "complianceScore": scan_results.get("summary", {}).get(
                    "complianceScore", 0
                ),
                "totalIssues": scan.get("total_issues", 0),
                "highSeverity": scan_results.get("summary", {}).get("highSeverity", 0),
            }

        if latest_version_entry:
            response["latestVersion"] = latest_version_entry["version"]
            response["latestFixedFile"] = latest_version_entry["relative_path"]
            response["versionHistory"] = [
                {
                    "version": entry["version"],
                    "label": f"V{entry['version']}",
                    "relativePath": entry["relative_path"],
                    "createdAt": entry["created_at"].isoformat()
                    if entry["created_at"]
                    else None,
                    "downloadable": entry["version"] == latest_version_entry["version"],
                    "fileSize": entry["size"],
                }
                for entry in reversed(version_entries)
            ]

        conn.close()
        return jsonify(response)

    except Exception as e:
        print(f"[Backend] ERROR in get_scan_current_state: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    print("[Backend] 🚀 Starting Flask server...")
    app.run(host="0.0.0.0", port=5000, debug=True)
