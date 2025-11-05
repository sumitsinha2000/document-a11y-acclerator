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

NEON_DATABASE_URL = os.getenv("DATABASE_URL")

db_lock = threading.Lock()

UPLOAD_FOLDER = "uploads"
FIXED_FOLDER = "fixed"
pdf_generator = PDFGenerator()
GENERATED_PDFS_FOLDER = pdf_generator.output_dir


# === Database Connection ===
def get_db_connection():
    try:
        conn = psycopg2.connect(NEON_DATABASE_URL, cursor_factory=RealDictCursor)
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
    scan_id, filename, scan_results, batch_id=None, group_id=None, is_update=False
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

        if is_update:
            # === UPDATE EXISTING SCAN ===
            print(f"[Backend] 🔄 Updating scan record: {scan_id}")
            query = """
                UPDATE scans
                SET scan_results = %s,
                    upload_date = NOW(),
                    status = 'fixed'
                WHERE id = %s
            """
            c.execute(query, (json.dumps(formatted_results), scan_id))
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
                        created_at = NOW()
                """
                status = "completed"
                c.execute(
                    query,
                    (
                        scan_id,
                        filename,
                        json.dumps(formatted_results),
                        batch_id,
                        group_id,
                        status,
                    ),
                )
                conn.commit()

                if group_id:
                    update_group_count_query = """
                        UPDATE groups 
                        SET file_count = (SELECT COUNT(*) FROM scans WHERE group_id = %s)
                        WHERE id = %s
                    """
                    c.execute(update_group_count_query, (group_id, group_id))
                    conn.commit()

                print(
                    f"[Backend] ✅ Inserted new scan record: {scan_id} ({filename}) in group {group_id} with {formatted_results['summary']['totalIssues']} issues"
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

    scan_id = f"scan_{uuid.uuid4().hex}"
    upload_dir = Path(UPLOAD_FOLDER)
    upload_dir.mkdir(exist_ok=True)

    file_path = upload_dir / f"{scan_id}.pdf"
    file.save(str(file_path))
    print(f"[Backend] ✓ File saved: {file_path}")

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
        scan_id, file.filename, formatted_results, group_id=group_id
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

        conn = get_db_connection()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO batches (id, name, group_id, created_at, status, total_files, total_issues, unprocessed_files)
            VALUES (%s, %s, %s, NOW(), 'processing', %s, 0, %s)
        """,
            (batch_id, batch_name, group_id, len(pdf_files), len(pdf_files)),
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
                SUM(CASE WHEN status IN ('unprocessed', 'processing') THEN 1 ELSE 0 END) AS unprocessed_files,
                SUM(CASE WHEN status = 'fixed' THEN 1 ELSE 0 END) AS fixed_files
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

        if total_files == 0:
            batch_status = "empty"
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

            formatted_scans.append(
                {
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
            )

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

        save_success = False
        if changes_detected:
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
                    fix_metadata={
                        "engine_version": "1.0",
                        "processing_time": result.get("processingTime"),
                        "success_rate": result.get("successRate"),
                    },
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
            "scanResults": scan_results_after,
            "summary": summary_after,
            "fixesApplied": fixes_applied,
            "historyRecorded": save_success,
            "changesDetected": changes_detected,
            "successCount": success_count,
            "scanId": scan_id,
        }

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
        data = request.get_json()
        fixes = data.get("fixes", [])

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

            save_success = False
            if changes_detected:
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
                        fix_metadata={
                            "user_selected_fixes": len(fixes),
                            "engine_version": "1.0",
                        },
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

            return jsonify(
                {
                    "status": "success",
                    "fixedFile": result.get("fixedFile"),
                    "scanResults": scan_results_after,
                    "summary": summary_after,
                    "fixesApplied": fixes_applied,
                    "historyRecorded": save_success,
                    "changesDetected": changes_detected,
                }
            )
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

        save_fix_history(
            scan_id=scan_id,
            original_filename=original_filename,
            fixed_filename=pdf_path.name,
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
            },
        )

        update_scan_status(scan_id)

        return jsonify(
            {
                "success": True,
                "message": fix_result.get(
                    "message", "Manual fix applied successfully"
                ),
                "fixedFile": pdf_path.name,
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
    fixed_dir = Path(FIXED_FOLDER)

    file_path = None
    potential_filenames = [
        f"{scan_id}.pdf",
        scan_id,
    ]  # Try with and without .pdf extension

    # Prefer fixed file if available
    for filename in potential_filenames:
        path = fixed_dir / filename
        if path.exists():
            file_path = path
            break

    # If fixed file not found, look for the original upload
    if not file_path:
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

    return send_file(
        file_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=download_name,
    )


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

            history.append(
                {
                    "id": row["id"],
                    "scanId": row["scan_id"],
                    "originalFilename": row.get("original_filename")
                    or row.get("original_file"),
                    "fixedFilename": row.get("fixed_filename") or row.get("fixed_file"),
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
                }
            )

        return jsonify({"success": True, "history": history})

    except Exception as e:
        print(f"[Backend] ERROR getting fix history: {e}")
        import traceback

        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/download-fixed/<filename>", methods=["GET"])
def download_fixed_file(filename):
    """Download a fixed PDF file"""
    try:
        print(f"[Backend] Downloading fixed file: {filename}")

        fixed_dir = Path(FIXED_FOLDER)
        uploads_dir = Path(UPLOAD_FOLDER)

        # Try to find the file in fixed folder first, then uploads
        file_path = None
        for folder in [fixed_dir, uploads_dir]:
            # Try with and without .pdf extension
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

        print(f"[Backend] ✓ Serving fixed file: {file_path}")
        return send_file(
            file_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename if filename.endswith(".pdf") else f"{filename}.pdf",
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

        # Try multiple file path strategies
        file_path = None
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
):
    """
    Save fix history to the fix_history table.
    All fix records are stored exclusively in fix_history table.
    The scans table maintains only the initial scan data.
    """
    try:
        conn = get_db_connection()
        c = conn.cursor()

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
        check_query = "SELECT id FROM groups WHERE id = %s"
        result = execute_query(check_query, (group_id,), fetch=True)

        if not result or len(result) == 0:
            return jsonify({"error": "Group not found"}), 404

        # Update group
        query = """
            UPDATE groups 
            SET name = %s, description = %s
            WHERE id = %s
            RETURNING id, name, description, created_at, file_count
        """

        result = execute_query(query, (name, description, group_id), fetch=True)

        if result and len(result) > 0:
            group = dict(result[0])
            print(f"[Backend] ✓ Updated group: {name} ({group_id})")
            return jsonify({"group": group})
        else:
            return jsonify({"error": "Failed to update group"}), 500

    except psycopg2.IntegrityError:
        return jsonify({"error": "A group with this name already exists"}), 409
    except Exception as e:
        print(f"[Backend] Error updating group: {e}")
        import traceback

        traceback.print_exc()
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
            SELECT id, name, created_at, group_id
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
                }
            )

        avg_compliance = (
            round(total_compliance / len(processed_scans), 2) if processed_scans else 0
        )

        response = {
            "batchId": batch_id,
            "batchName": batch.get("name"),
            "createdAt": batch.get("created_at"),
            "groupId": batch.get("group_id"),
            "totalIssues": total_issues,
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
                for folder in [fixed_dir, uploads_dir]:
                    for candidate in [
                        folder / f"{scan_id}.pdf",
                        folder / scan_row.get("filename", ""),
                    ]:
                        if candidate and candidate.exists():
                            arcname = f"{safe_batch_name}/files/{candidate.name}"
                            zip_file.write(candidate, arcname)
                            pdf_added = True
                            print(f"[Backend] Added PDF to export: {candidate}")
                            break
                    if pdf_added:
                        break

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

            total_issues += summary.get("totalIssues", 0)
            total_compliance += summary.get("complianceScore", 0)

            if scan.get("status") == "fixed":
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
