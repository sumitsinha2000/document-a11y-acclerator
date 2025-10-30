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

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

NEON_DATABASE_URL = os.getenv("DATABASE_URL")

db_lock = threading.Lock()


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


# === Fixed save_scan_to_db ===
def save_scan_to_db(scan_id, filename, scan_results, is_update=False, batch_id=None):
    """
    Unified save logic:
    - Inserts a new record if is_update=False (always creates a new scan even if same file name).
    - Updates the existing record if is_update=True.
    """
    conn = None
    c = None
    try:
        conn = get_db_connection()
        c = conn.cursor()

        if is_update:
            # === UPDATE EXISTING SCAN ===
            print(f"[Backend] 🔄 Updating scan record: {scan_id}")
            query = '''
                UPDATE scans
                SET scan_results = %s,
                    filename = %s,
                    upload_date = NOW(),
                    status = 'updated'
                WHERE id = %s
            '''
            c.execute(query, (json.dumps(scan_results), filename, scan_id))
            conn.commit()
            print(f"[Backend] ✅ Updated existing scan successfully: {scan_id}")
            return scan_id

        else:
            # === INSERT NEW SCAN (always new record, even same filename) ===
            try:
                unique_id = f"scan_{uuid.uuid4().hex}"
                query = '''
                    INSERT INTO scans (id, filename, scan_results, batch_id, status, upload_date)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                '''
                status = 'completed'
                c.execute(query, (unique_id, filename, json.dumps(scan_results), batch_id, status))
                conn.commit()
                print(f"[Backend] ✅ Inserted new scan record: {unique_id} ({filename})")
                return unique_id

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


# === PDF Scan ===
@app.route("/api/scan", methods=["POST"])
def scan_pdf():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    if not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files supported"}), 400

    scan_id = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
    upload_dir = Path("uploads")
    upload_dir.mkdir(exist_ok=True)
    file_path = upload_dir / f"{scan_id}.pdf"
    file.save(str(file_path))
    print(f"[Backend] ✓ File saved: {file_path}")

    analyzer = PDFAccessibilityAnalyzer()
    scan_results = analyzer.analyze(str(file_path))
    summary = analyzer.calculate_summary(scan_results)
    fix_suggestions = generate_fix_suggestions(scan_results)

    saved_id = save_scan_to_db(scan_id, file.filename, {"results": scan_results, "summary": summary})
    print(f"[Backend] ✓ Scan record saved as {saved_id}")

    return jsonify({
        "scanId": saved_id,
        "filename": file.filename,
        "summary": summary,
        "results": scan_results,
        "fixes": fix_suggestions,
        "timestamp": datetime.now().isoformat()
    })


# === Scan History ===
@app.route("/api/scans", methods=["GET"])
def get_scans():
    scans = execute_query(
        "SELECT id, filename, upload_date, status FROM scans ORDER BY upload_date DESC",
        fetch=True
    )
    return jsonify({"scans": scans})


# === Apply Fixes ===
@app.route("/api/apply-fixes/<scan_id>", methods=["POST"])
def apply_fixes(scan_id):
    data = request.get_json()
    fixes = data.get("fixes", [])
    filename = data.get("filename", "fixed_document.pdf")

    print(f"[Backend] Applying fixes for scan: {scan_id}")

    progress_id = create_progress_tracker(scan_id)
    engine = AutoFixEngine(progress_id)
    fixed_path, summary = engine.apply_fixes(scan_id, fixes)

    # ✅ update existing scan with new results
    save_scan_to_db(scan_id, filename, summary, is_update=True)
    return jsonify({"status": "success", "fixedFile": fixed_path, "summary": summary})


# === Apply Semi-Automated Fixes ===
@app.route("/api/apply-semi-automated-fixes/<scan_id>", methods=["POST"])
def apply_semi_automated_fixes(scan_id):
    data = request.get_json()
    fixes = data.get("fixes", [])
    filename = data.get("filename", "semi_fixed.pdf")

    progress_id = create_progress_tracker(scan_id)
    engine = AutoFixEngine(progress_id)
    fixed_path, summary = engine.apply_fixes(scan_id, fixes, semi_automated=True)

    # ✅ update existing scan with new results
    save_scan_to_db(scan_id, filename, summary, is_update=True)
    return jsonify({"status": "success", "fixedFile": fixed_path, "summary": summary})


# === Download File ===
@app.route("/api/download/<path:scan_id>", methods=["GET"])
def download_file(scan_id):
    uploads_dir = Path("uploads")
    fixed_dir = Path("fixed")

    file_path = None
    for folder in [fixed_dir, uploads_dir]:
        path = folder / f"{scan_id}.pdf"
        if path.exists():
            file_path = path
            break

    if not file_path:
        return jsonify({"error": "File not found"}), 404

    return send_file(
        file_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{scan_id}.pdf"
    )


# === Progress Tracker ===
@app.route("/api/progress/<scan_id>", methods=["GET"])
def get_progress(scan_id):
    progress = get_progress_tracker(scan_id)
    return jsonify(progress)


# === History Component ===
@app.route("/api/history", methods=["GET", "OPTIONS"])
def get_history():
    """Get all scans and batches for history view"""
    if request.method == "OPTIONS":
        return "", 200
    
    try:
        # Get all individual scans
        scans = execute_query(
            """
            SELECT id, filename, upload_date as "uploadDate", status, 
                   total_issues, critical_issues, error_issues, warning_issues
            FROM scans 
            ORDER BY upload_date DESC
            """,
            fetch=True
        )
        
        # Add summary to each scan
        for scan in scans:
            scan['summary'] = {
                'totalIssues': scan.get('total_issues', 0),
                'critical': scan.get('critical_issues', 0),
                'error': scan.get('error_issues', 0),
                'warning': scan.get('warning_issues', 0)
            }
        
        # Get all batches (if batch table exists)
        batches = []
        try:
            batches = execute_query(
                """
                SELECT batch_id as "batchId", name, upload_date as "uploadDate", 
                       status, file_count as "fileCount", total_issues as "totalIssues"
                FROM batches 
                ORDER BY upload_date DESC
                """,
                fetch=True
            )
        except Exception as e:
            print(f"[Backend] No batches table or error: {e}")
        
        return jsonify({
            "scans": scans,
            "batches": batches
        })
    except Exception as e:
        print(f"[Backend] Error fetching history: {e}")
        return jsonify({"error": str(e)}), 500


# === Fix History ===
@app.route("/api/fix-history/<scan_id>", methods=["GET", "OPTIONS"])
def get_fix_history(scan_id):
    """Get fix history for a specific scan"""
    if request.method == "OPTIONS":
        return "", 200
    
    try:
        print(f"[Backend] Fetching fix history for scan: {scan_id}")
        
        fixes = execute_query(
            """
            SELECT id, scan_id as "scanId", fix_type as "fixType", 
                   description, status, applied_at as "appliedAt",
                   page_number as "pageNumber", element_type as "elementType"
            FROM fix_history 
            WHERE scan_id = %s 
            ORDER BY applied_at DESC
            """,
            (scan_id,),
            fetch=True
        )
        
        print(f"[Backend] Found {len(fixes)} fixes for scan {scan_id}")
        return jsonify({"fixes": fixes})
    except Exception as e:
        print(f"[Backend] Error fetching fix history: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    print("[Backend] 🚀 Starting Flask server...")
    app.run(host="0.0.0.0", port=5000, debug=True)
