from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import json
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import psycopg2
from psycopg2.extras import RealDictCursor
import time  # Import time for sleep
import shutil # Import shutil for file copy

from pdf_analyzer import PDFAccessibilityAnalyzer
from fix_suggestions import generate_fix_suggestions

from dotenv import load_dotenv
load_dotenv()  # Load .env file before accessing environment variables

# Get database URL from environment (try multiple possible variable names)
NEON_NEON_NEON_NEON_DATABASE_URL = os.getenv('DATABASE_URL') # Changed NEON_DATABASE_URL to DATABASE_URL
# Ensure that if DATABASE_URL is not set, it tries NEON_DATABASE_URL or NEON_POSTGRES_URL
if not NEON_NEON_NEON_DATABASE_URL:
    NEON_NEON_NEON_DATABASE_URL = os.getenv('DATABASE_URL')


if not NEON_NEON_NEON_DATABASE_URL:
    print("[Backend] ✗ CRITICAL ERROR: No DATABASE_URL found in environment variables!")
    print("[Backend] Please set one of: DATABASE_URL, NEON_DATABASE_URL, or NEON_POSTGRES_URL")
    raise Exception("DATABASE_URL not configured")
else:
    print(f"[Backend] ✓ Database URL configured: {NEON_NEON_NEON_DATABASE_URL[:30]}...")

# Determine database type from environment
# NEON_DATABASE_URL = os.environ.get('NEON_DATABASE_URL', '') # This line is now redundant due to the above change

# Import appropriate database library
try:
    # This import is now handled by the DATABASE_URL check above, but kept for clarity
    # import psycopg2
    # from psycopg2.extras import RealDictCursor
    print("[Backend] Using PostgreSQL database")
except ImportError:
    print("[Backend] ERROR: psycopg2 not installed")
    print("[Backend] Install with: pip install psycopg2-binary")
    raise ImportError("psycopg2 is required. Install with: pip install psycopg2-binary")

# Redundant imports, already imported above
# from pdf_analyzer import PDFAccessibilityAnalyzer
# from fix_suggestions import generate_fix_suggestions

from fix_progress_tracker import create_progress_tracker, get_progress_tracker, remove_progress_tracker, FixProgressTracker # Import FixProgressTracker

try:
    from ocr_processor import OCRProcessor
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("Info: OCR processor not available")

try:
    from auto_fix_engine import AutoFixEngine
    AUTO_FIX_AVAILABLE = True
    print("[Backend] ✓ AutoFixEngine loaded successfully")
except ImportError as e:
    AUTO_FIX_AVAILABLE = False
    print(f"[Backend] ✗ Auto-fix engine not available: {e}")
    print("[Backend] Make sure pikepdf is installed: pip install pikepdf")
    print("[Backend] ℹ Using fallback fix suggestions generator (suggestions only, no auto-apply)")
except Exception as e:
    AUTO_FIX_AVAILABLE = False
    print(f"[Backend] ✗ Failed to load AutoFixEngine: {e}")
    print("[Backend] ℹ Using fallback fix suggestions generator (suggestions only, no auto-apply)")
    import traceback
    traceback.print_exc()

try:
    from pdf_generator import PDFGenerator
    PDF_GENERATOR_AVAILABLE = True
except ImportError:
    PDF_GENERATOR_AVAILABLE = False
    print("Info: PDF generator not available")

# Import SambaNova AI remediation engine
try:
    from sambanova_remediation import get_ai_remediation_engine
    AI_REMEDIATION_ENGINE = get_ai_remediation_engine()
    AI_REMEDIATION_AVAILABLE = AI_REMEDIATION_ENGINE is not None
    if AI_REMEDIATION_AVAILABLE:
        print("[Backend] ✓ SambaNova AI remediation engine loaded successfully")
    else:
        print("[Backend] ℹ SambaNova AI remediation not configured (set SAMBANOVA_API_KEY)")
except ImportError as e:
    AI_REMEDIATION_AVAILABLE = False
    AI_REMEDIATION_ENGINE = None
    print(f"[Backend] ℹ SambaNova AI remediation not available: {e}")
except Exception as e:
    AI_REMEDIATION_AVAILABLE = False
    AI_REMEDIATION_ENGINE = None
    print(f"[Backend] ✗ Failed to load SambaNova AI remediation: {e}")

app = Flask(__name__)
CORS(app)

db_lock = threading.Lock()

def get_db_connection():
    """Get a PostgreSQL database connection"""
    try:
        conn = psycopg2.connect(
            NEON_NEON_NEON_DATABASE_URL,
            cursor_factory=RealDictCursor,
            connect_timeout=10
        )
        print("[Backend] ✓ Database connection established")
        return conn
    except psycopg2.OperationalError as e:
        print(f"[Backend] ✗ Database connection failed: {e}")
        print(f"[Backend] DATABASE_URL: {NEON_NEON_NEON_DATABASE_URL[:50]}...")
        raise Exception(f"Failed to connect to database: {e}")
    except Exception as e:
        print(f"[Backend] ✗ Unexpected database error: {e}")
        raise

def execute_query(query, params=None, fetch=False):
    """Execute a database query with proper error handling"""
    query_type = query.strip().split()[0].upper() if query else 'UNKNOWN'
    print(f"[Backend] Executing {query_type} query...")
    
    with db_lock:
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            if params:
                print(f"[Backend] Query params: {params[:3] if len(params) > 3 else params}...")
                cursor.execute(query, params)
            else:
                cursor.execute(query)

            if fetch:
                result = cursor.fetchall()
                print(f"[Backend] ✓ {query_type} returned {len(result) if result else 0} rows")
                return result
            else:
                conn.commit()
                print(f"[Backend] ✓ {query_type} committed successfully")
                return True
                
        except psycopg2.Error as e:
            print(f"[Backend] ✗ PostgreSQL error in {query_type}: {e}")
            print(f"[Backend] Error code: {e.pgcode}")
            print(f"[Backend] Error details: {e.pgerror}")
            if conn:
                conn.rollback()
            raise Exception(f"Database error: {e}")
            
        except Exception as e:
            print(f"[Backend] ✗ Unexpected error in {query_type}: {e}")
            if conn:
                conn.rollback()
            raise
            
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
                print(f"[Backend] Database connection closed")

def init_db():
    """Initialize PostgreSQL database for storing scan history"""
    print("[Backend] Initializing database...")
    try:
        conn = get_db_connection()
        c = conn.cursor()

        print("[Backend] Creating scans table...")
        c.execute('''
            CREATE TABLE IF NOT EXISTS scans (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                scan_results JSONB NOT NULL,
                status TEXT DEFAULT 'completed',
                batch_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        print("[Backend] Creating fix_history table...")
        c.execute('''
            CREATE TABLE IF NOT EXISTS fix_history (
                id SERIAL PRIMARY KEY,
                scan_id TEXT NOT NULL,
                original_file TEXT NOT NULL,
                fixed_file TEXT NOT NULL,
                fixes_applied JSONB NOT NULL,
                success_count INTEGER DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (scan_id) REFERENCES scans(id) ON DELETE CASCADE
            )
        ''')

        print("[Backend] Creating batches table...")
        c.execute('''
            CREATE TABLE IF NOT EXISTS batches (
                id TEXT PRIMARY KEY,
                name TEXT,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                file_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                total_issues INTEGER DEFAULT 0,
                fixed_count INTEGER DEFAULT 0
            )
        ''')

        conn.commit()
        conn.close()
        print(f"[Backend] ✓ PostgreSQL database initialized successfully")
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public'
        """)
        tables = [row['table_name'] for row in c.fetchall()]
        print(f"[Backend] ✓ Verified tables exist: {tables}")
        conn.close()
        
    except Exception as e:
        print(f"[Backend] ✗ Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        raise

def save_scan_to_db(filename, scan_results, summary, scan_id=None):
    """Save or update scan results in the database using UPSERT"""
    try:
        # Ensure filename has .pdf extension
        if not filename.endswith('.pdf'):
            filename = f"{filename}.pdf"
        
        # Use unified query execution to save scan (thread-safe with db_lock)
        if scan_id:
            # UPSERT: Update existing scan
            query = """
                INSERT INTO scans (id, filename, scan_results, status, created_at)
                VALUES (%s, %s, %s, 'completed', NOW())
                ON CONFLICT (id) 
                DO UPDATE SET 
                    scan_results = EXCLUDED.scan_results,
                    status = 'completed',
                    created_at = NOW()
                RETURNING id
            """
            result = execute_query(query, (scan_id, filename, json.dumps({'results': scan_results, 'summary': summary})), fetch=True)
            final_scan_id = result[0]['id'] if result else scan_id
        else:
            # Insert new scan
            generated_scan_id = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename.replace('.pdf', '')}"
            query = """
                INSERT INTO scans (id, filename, scan_results, status, created_at)
                VALUES (%s, %s, %s, 'completed', NOW())
                RETURNING id
            """
            result = execute_query(query, (generated_scan_id, filename, json.dumps({'results': scan_results, 'summary': summary})), fetch=True)
            final_scan_id = result[0]['id'] if result else generated_scan_id
        
        print(f"[Backend] Saved scan to database: {final_scan_id}")
        return final_scan_id
        
    except Exception as e:
        print(f"[Backend] Error saving scan to database: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_scan_history():
    """Retrieve all scan history - only latest version of each file"""
    print("[Backend] Fetching scan history...")
    try:
        query = '''
            SELECT DISTINCT ON (filename) 
                id, filename, upload_date, status 
            FROM scans 
            ORDER BY filename, upload_date DESC
        '''
        scans = execute_query(query, fetch=True)
        print(f"[Backend] ✓ Found {len(scans)} unique scans in history")

        return [
            {
                'id': scan['id'],
                'filename': scan['filename'],
                'uploadDate': scan['upload_date'].isoformat() if scan['upload_date'] else None,
                'status': scan['status']
            }
            for scan in scans
        ]
    except Exception as e:
        print(f"[Backend] ✗ Error fetching scan history: {e}")
        raise

# Helper function to ensure fixes always have correct structure
def get_empty_fixes_structure():
    """Return empty fixes structure with correct format"""
    return {
        "automated": [],
        "semiAutomated": [],
        "manual": [],
        "estimatedTime": 0
    }

def ensure_fixes_structure(fixes):
    """Ensure fixes object has the correct structure"""
    if not isinstance(fixes, dict):
        print(f"[Backend] WARNING: fixes is not a dict, it's {type(fixes)}. Returning empty structure.")
        return get_empty_fixes_structure()

    # Ensure all required keys exist
    if 'automated' not in fixes:
        fixes['automated'] = []
    if 'semiAutomated' not in fixes:
        fixes['semiAutomated'] = []
    if 'manual' not in fixes:
        fixes['manual'] = []
    if 'estimatedTime' not in fixes:
        fixes['estimatedTime'] = 0

    return fixes

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    print("[Backend] Health check requested")
    return jsonify({'status': 'ok'})

@app.route('/api/scan', methods=['POST'])
def scan_pdf():
    """
    Endpoint to scan a PDF for accessibility issues
    Expects multipart/form-data with 'file' field
    """
    print("[Backend] Received scan request")

    if 'file' not in request.files:
        print("[Backend] Error: No file in request")
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        print("[Backend] Error: Empty filename")
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.lower().endswith('.pdf'):
        print("[Backend] Error: Not a PDF file")
        return jsonify({'error': 'Only PDF files are supported'}), 400

    try:
        print(f"[Backend] Processing file: {file.filename}")

        scan_id = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.path.splitext(file.filename)[0]}"

        upload_dir = Path('uploads')
        upload_dir.mkdir(exist_ok=True)

        file_path = upload_dir / scan_id
        file.save(str(file_path))
        print(f"[Backend] File saved to: {file_path}")

        summary = None
        try:
            analyzer = PDFAccessibilityAnalyzer()
            scan_results = analyzer.analyze(str(file_path))
            print(f"[Backend] Analysis complete, found {sum(len(v) for v in scan_results.values())} issues")

            try:
                summary = analyzer.calculate_summary(scan_results)
                print(f"[Backend] Summary calculated: {summary.get('totalIssues', 0)} total issues, {summary.get('complianceScore', 0)}% compliance")
            except Exception as summary_error:
                print(f"[Backend] Error calculating summary: {summary_error}")
                summary = {'totalIssues': 0, 'complianceScore': 0}

            verapdf_status = {
                'isActive': False,
                'wcagCompliance': None,
                'pdfuaCompliance': None,
                'totalVeraPDFIssues': 0
            }

            if hasattr(analyzer, 'wcag_validator_available') and analyzer.wcag_validator_available:
                verapdf_status['isActive'] = True
                # Calculate compliance from veraPDF issues
                wcag_issues = len(scan_results.get('wcagIssues', []))
                pdfua_issues = len(scan_results.get('pdfuaIssues', []))
                verapdf_status['wcagCompliance'] = max(0, 100 - (wcag_issues * 10))
                verapdf_status['pdfuaCompliance'] = max(0, 100 - (pdfua_issues * 10))
                verapdf_status['totalVeraPDFIssues'] = wcag_issues + pdfua_issues
                print(f"[Backend] veraPDF validation: WCAG {verapdf_status['wcagCompliance']}%, PDF/UA {verapdf_status['pdfuaCompliance']}%")

        except Exception as e:
            print(f"[Backend] Error during PDF analysis: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'PDF analysis failed: {str(e)}'}), 500

        ocr_results = {'isScanned': False, 'confidence': 0}
        if OCR_AVAILABLE:
            try:
                ocr_processor = OCRProcessor()
                ocr_results = ocr_processor.detect_scanned_content(str(file_path))
            except Exception as e:
                print(f"[Backend] Warning: OCR processing failed: {e}")

        fix_suggestions = get_empty_fixes_structure()

        print(f"[Backend] AUTO_FIX_AVAILABLE = {AUTO_FIX_AVAILABLE}")

        if AUTO_FIX_AVAILABLE:
            try:
                print("[Backend] Generating fix suggestions with AutoFixEngine...")
                auto_fix_engine = AutoFixEngine()
                generated_fixes = auto_fix_engine.generate_fixes(scan_results)
                fix_suggestions = ensure_fixes_structure(generated_fixes)
            except Exception as e:
                print(f"[Backend] ERROR: AutoFixEngine failed, using fallback: {e}")
                fix_suggestions = generate_fix_suggestions(scan_results)
        else:
            print("[Backend] Using fallback fix suggestions generator...")
            fix_suggestions = generate_fix_suggestions(scan_results)

        fix_suggestions = ensure_fixes_structure(fix_suggestions)
        automated_count = len(fix_suggestions.get('automated', []))
        semi_count = len(fix_suggestions.get('semiAutomated', []))
        manual_count = len(fix_suggestions.get('manual', []))
        total_fixes = automated_count + semi_count + manual_count
        print(f"[Backend] Generated {total_fixes} fix suggestions: {automated_count} automated, {semi_count} semi-automated, {manual_count} manual")

        # Persist scan so single-file workflows match batch behavior
        try:
            # Pass original filename to save_scan_to_db for correct storage
            save_scan_to_db(file.filename, scan_results, summary, scan_id=scan_id)
            print(f"[Backend] ✓ Scan saved to database")
        except Exception as db_error:
            print(f"[Backend] ERROR saving scan results to database: {db_error}")
            import traceback
            traceback.print_exc()

        response_data = {
            'scanId': scan_id,
            'filename': file.filename,
            'timestamp': datetime.now().isoformat(),
            'results': scan_results,
            'summary': summary,
            'fixes': fix_suggestions,
            'verapdfStatus': verapdf_status,  # Add veraPDF status to response
            'batchId': None,
            'uploadDate': datetime.now().isoformat()
        }

        print(f"[Backend] Sending response with {total_fixes} fix suggestions")
        return jsonify(response_data), 200

    except Exception as e:
        error_message = f"Error processing PDF: {str(e)}"
        print(f"[Backend] Error: {error_message}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': error_message}), 500

@app.route('/api/scans', methods=['GET'])
def get_scans():
    """Get scan history"""
    try:
        scans = get_scan_history()
        return jsonify({'scans': scans}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/scan/<scan_id>', methods=['GET'])
def get_scan_details(scan_id):
    """Get detailed results for a specific scan"""
    try:
        print(f"[Backend] ========== LOADING SCAN: {scan_id} ==========")

        # Use unified query execution to get scan data
        query = f'SELECT filename, scan_results, upload_date, batch_id FROM scans WHERE id = %s'
        result = execute_query(query, (scan_id,), fetch=True)

        if not result:
            print(f"[Backend] Scan not found in database: {scan_id}")
            # Try to find the file in uploads directory
            upload_path = os.path.join('uploads', scan_id)
            if os.path.exists(upload_path):
                print(f"[Backend] File exists in uploads, analyzing now...")
                try:
                    analyzer = PDFAccessibilityAnalyzer()
                    results = analyzer.analyze(upload_path)
                    summary = analyzer.calculate_summary(results)

                    verapdf_status = {
                        'isActive': False,
                        'wcagCompliance': None,
                        'pdfuaCompliance': None,
                        'totalVeraPDFIssues': 0
                    }

                    if hasattr(analyzer, 'wcag_validator_available') and analyzer.wcag_validator_available:
                        verapdf_status['isActive'] = True
                        wcag_issues = len(results.get('wcagIssues', []))
                        pdfua_issues = len(results.get('pdfuaIssues', []))
                        verapdf_status['wcagCompliance'] = max(0, 100 - (wcag_issues * 10))
                        verapdf_status['pdfuaCompliance'] = max(0, 100 - (pdfua_issues * 10))
                        verapdf_status['totalVeraPDFIssues'] = wcag_issues + pdfua_issues

                    fixes = get_empty_fixes_structure()
                    if AUTO_FIX_AVAILABLE:
                        try:
                            auto_fix_engine = AutoFixEngine()
                            generated_fixes = auto_fix_engine.generate_fixes(results)
                            fixes = ensure_fixes_structure(generated_fixes)
                        except Exception as e:
                            print(f"[Backend] Error generating fixes: {e}")
                            fixes = generate_fix_suggestions(results)
                    else:
                        fixes = generate_fix_suggestions(results)

                    scan_data_for_db = {
                        'results': results,
                        'summary': summary
                    }
                    # Use unified query execution to save scan
                    save_scan_to_db(os.path.basename(upload_path), results, summary, scan_id=scan_id)
                    print(f"[Backend] ✓ Scan added to database")

                    return jsonify({
                        'scanId': scan_id,
                        'filename': os.path.basename(upload_path),
                        'results': results,
                        'summary': summary,
                        'fixes': fixes,
                        'uploadDate': datetime.now().isoformat(),
                        'verapdfStatus': verapdf_status  # Add veraPDF status
                    }), 200
                except Exception as e:
                    print(f"[Backend] ERROR analyzing file: {e}")
                    import traceback
                    traceback.print_exc()
                    return jsonify({'error': f'Failed to analyze file: {str(e)}'}), 500
            else:
                print(f"[Backend] File not found in uploads either")
                return jsonify({'error': 'Scan not found'}), 404

        print(f"[Backend] ✓ Found scan in database: {result[0]['filename']}")

        scan_data = result[0]['scan_results']
        if isinstance(scan_data, str):
            scan_data = json.loads(scan_data)

        # Handle both old format (just results) and new format (results + summary)
        if isinstance(scan_data, dict) and 'results' in scan_data:
            results = scan_data['results']
            summary = scan_data.get('summary')
        else:
            # Old format - just results
            results = scan_data
            summary = None

        # If summary is missing, regenerate it from results
        if not summary:
            print("[Backend] Summary missing, regenerating...")
            analyzer = PDFAccessibilityAnalyzer()
            summary = analyzer.calculate_summary(results)

        verapdf_status = {
            'isActive': False,
            'wcagCompliance': None,
            'pdfuaCompliance': None,
            'totalVeraPDFIssues': 0
        }

        # Check if results contain veraPDF issues
        if 'wcagIssues' in results or 'pdfuaIssues' in results:
            verapdf_status['isActive'] = True
            wcag_issues = len(results.get('wcagIssues', []))
            pdfua_issues = len(results.get('pdfuaIssues', []))
            verapdf_status['wcagCompliance'] = max(0, 100 - (wcag_issues * 10))
            verapdf_status['pdfuaCompliance'] = max(0, 100 - (pdfua_issues * 10))
            verapdf_status['totalVeraPDFIssues'] = wcag_issues + pdfua_issues

        print(f"[Backend] Fetching applied fixes from fix_history for scan: {scan_id}")
        applied_fixes_query = '''
            SELECT fixes_applied, success_count, timestamp, fixed_file
            FROM fix_history
            WHERE scan_id = %s
            ORDER BY timestamp DESC
            LIMIT 1
        '''
        applied_fixes_result = execute_query(applied_fixes_query, (scan_id,), fetch=True)

        applied_fixes_data = None
        if applied_fixes_result and len(applied_fixes_result) > 0:
            latest_fix = applied_fixes_result[0]
            fixes_applied = latest_fix['fixes_applied']
            if isinstance(fixes_applied, str):
                fixes_applied = json.loads(fixes_applied)

            applied_fixes_data = {
                'fixesApplied': fixes_applied,
                'successCount': latest_fix['success_count'],
                'timestamp': latest_fix['timestamp'].isoformat() if latest_fix['timestamp'] else None,
                'fixedFile': latest_fix['fixed_file']
            }
            print(f"[Backend] ✓ Found {latest_fix['success_count']} applied fixes from {latest_fix['timestamp']}")
        else:
            print(f"[Backend] No applied fixes found in fix_history for this scan")

        fixes = get_empty_fixes_structure()

        if AUTO_FIX_AVAILABLE:
            try:
                auto_fix_engine = AutoFixEngine()
                generated_fixes = auto_fix_engine.generate_fixes(results)
                fixes = ensure_fixes_structure(generated_fixes)
            except Exception as e:
                print(f"[Backend] ERROR: AutoFixEngine failed: {e}")
                fixes = generate_fix_suggestions(results)
        else:
            fixes = generate_fix_suggestions(results)

        fixes = ensure_fixes_structure(fixes)

        response_data = {
            'scanId': scan_id,
            'filename': result[0]['filename'],
            'results': results,
            'summary': summary,
            'fixes': fixes,
            'uploadDate': result[0]['upload_date'].isoformat() if result[0]['upload_date'] else None,
            'batchId': result[0]['batch_id'] if result[0]['batch_id'] else None,
            'verapdfStatus': verapdf_status,
            'appliedFixes': applied_fixes_data  # Add applied fixes to response
        }

        print(f"[Backend] ✓ Returning scan details for {result[0]['filename']}")
        return jsonify(response_data), 200
    except Exception as e:
        print(f"[Backend] ========== ERROR LOADING SCAN ==========")
        print(f"[Backend] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/export/<scan_id>', methods=['GET'])
def export_scan(scan_id):
    """Export scan results as JSON"""
    try:
        query = f'SELECT filename, scan_results, upload_date FROM scans WHERE id = %s'
        result = execute_query(query, (scan_id,), fetch=True)

        if not result:
            return jsonify({'error': 'Scan not found'}), 404

        scan_data = result[0]['scan_results']
        if isinstance(scan_data, str):
            scan_data = json.loads(scan_data)

        export_data = {
            'scanId': scan_id,
            'filename': result[0]['filename'],
            'uploadDate': result[0]['upload_date'].isoformat() if result[0]['upload_date'] else None,
            'results': scan_data
        }

        return jsonify(export_data), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/fixes/<scan_id>', methods=['GET'])
def get_fix_suggestions(scan_id):
    """Get auto-fix suggestions for a scan"""
    if not AUTO_FIX_AVAILABLE:
        return jsonify({'error': 'Auto-fix engine not available'}), 503

    try:
        query = f'SELECT scan_results FROM scans WHERE id = %s'
        result = execute_query(query, (scan_id,), fetch=True)

        if not result:
            return jsonify({'error': 'Scan not found'}), 404

        scan_data = result[0]['scan_results']
        if isinstance(scan_data, str):
            issues = json.loads(scan_data)
        else:
            issues = scan_data

        auto_fix_engine = AutoFixEngine()
        fixes = auto_fix_engine.generate_fixes(issues)

        return jsonify({'scanId': scan_id, 'fixes': fixes}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/apply-fixes/<scan_id>', methods=['POST'])
def apply_fixes(scan_id):
    """Apply automated fixes to a PDF with AI enhancement and progress tracking"""
    try:
        from fix_progress_tracker import create_progress_tracker # This was already imported

        tracker = create_progress_tracker(scan_id, total_steps=10) # Existing import and usage

        data = request.get_json()
        use_ai = data.get('useAI', False)

        print(f"[Backend] Applying {'AI-powered' if use_ai else 'traditional'} fixes to scan: {scan_id}")

        step_id = tracker.add_step(
            "Initialize Fix Process",
            "Preparing to apply automated fixes to the PDF",
            "pending"
        )
        tracker.start_step(step_id)

        if not AUTO_FIX_AVAILABLE:
            tracker.fail_step(step_id, "Auto-fix engine is not available")
            tracker.fail_all("Auto-fix engine is not available")
            return jsonify({
                'success': False,
                'message': 'Auto-fix functionality is not available. Please check server configuration.'
            }), 503

        tracker.complete_step(step_id, "Fix process initialized successfully")

        step_id = tracker.add_step(
            "Load Scan Data",
            "Loading scan results and PDF file",
            "pending"
        )
        tracker.start_step(step_id)

        query = f'SELECT filename, scan_results FROM scans WHERE id = %s'
        scan_data_result = execute_query(query, (scan_id,), fetch=True)

        if not scan_data_result:
            tracker.fail_step(step_id, f"Scan not found: {scan_id}")
            tracker.fail_all(f"Scan not found: {scan_id}")
            return jsonify({'success': False, 'message': 'Scan not found'}), 404

        scan_filename = scan_data_result[0]['filename']
        scan_results_json = scan_data_result[0]['scan_results']

        scan_data = {
            'filename': scan_filename,
            'results': json.loads(scan_results_json) if isinstance(scan_results_json, str) else scan_results_json
        }
        tracker.complete_step(step_id, f"Loaded scan data for {scan_data.get('filename', 'unknown')}")

        from auto_fix_engine import AutoFixEngine # Ensure AutoFixEngine is imported here
        fix_engine = AutoFixEngine()
        result = fix_engine.apply_automated_fixes(scan_id, scan_data, tracker)

        if result.get('success'):
            try:
                # Ensure the filename ends with .pdf
                if not scan_filename.endswith('.pdf'):
                    scan_filename = f"{scan_filename}.pdf"

                # Construct the fixed file path
                fixed_filename = f"{scan_id}_fixed.pdf" # Use a distinct name for the fixed file
                fixed_path = os.path.join('uploads', fixed_filename)

                # Ensure the fixed file is copied or moved to the correct path if it's not already there
                # The apply_automated_fixes function is expected to return the path to the fixed file.
                # For this merge, we assume result['fixed_file'] is the path to the modified PDF.
                original_fixed_file_path = result.get('fixed_file')
                if original_fixed_file_path and original_fixed_file_path != fixed_path:
                    if os.path.exists(original_fixed_file_path):
                        shutil.copy2(original_fixed_file_path, fixed_path)
                        print(f"[Backend] Copied fixed file from '{original_fixed_file_path}' to '{fixed_path}'")
                    else:
                        print(f"[Backend] Warning: Original fixed file not found at '{original_fixed_file_path}'")
                elif not os.path.exists(fixed_path) and original_fixed_file_path == fixed_path:
                    print(f"[Backend] Fixed file already at correct path: {fixed_path}")
                else:
                    print(f"[Backend] Warning: Could not determine or locate the fixed file. Expected path: {fixed_path}")
                    # Attempt to handle if the fix_engine modifies the original file in place and `result['fixed_file']` is incorrect or missing
                    if os.path.exists(os.path.join('uploads', scan_id)):
                        fixed_path = os.path.join('uploads', scan_id) # Fallback to original if modified in place
                        print(f"[Backend] Using original file path as fixed path: {fixed_path}")


                print(f"[Backend] Re-scanning fixed file: {fixed_filename} from path: {fixed_path}")
                
                step_id = tracker.add_step(
                    "Re-scan Fixed PDF",
                    "Analyzing fixed PDF to verify improvements",
                    "pending"
                )
                tracker.start_step(step_id)
                
                analyzer = PDFAccessibilityAnalyzer()
                new_scan_results = analyzer.analyze(fixed_path) # Use the confirmed fixed_path
                new_summary = analyzer.calculate_summary(new_scan_results)
                
                print(f"[Backend] New scan results: {new_summary.get('totalIssues', 0)} issues")
                print(f"[Backend] New compliance score: {new_summary.get('complianceScore', 0)}%")
                
                tracker.complete_step(step_id, f"Re-scan complete: {new_summary.get('totalIssues', 0)} issues remaining")
                
                scan_data_updated = {
                    'results': new_scan_results,
                    'summary': new_summary
                }
                
                update_query = '''
                    UPDATE scans
                    SET scan_results = %s, status = %s
                    WHERE id = %s
                '''
                execute_query(update_query, (json.dumps(scan_data_updated), 'fixed', scan_id))
                print(f"[Backend] ✓ Updated scan record with new results")
                
                step_id = tracker.add_step(
                    "Generate New Fix Suggestions",
                    "Creating fix suggestions for remaining issues",
                    "pending"
                )
                tracker.start_step(step_id)
                
                new_fixes = get_empty_fixes_structure()
                if AUTO_FIX_AVAILABLE:
                    try:
                        auto_fix_engine = AutoFixEngine()
                        generated_fixes = auto_fix_engine.generate_fixes(new_scan_results)
                        new_fixes = ensure_fixes_structure(generated_fixes)
                    except Exception as e:
                        print(f"[Backend] Error generating new fixes: {e}")
                        new_fixes = generate_fix_suggestions(new_scan_results)
                else:
                    new_fixes = generate_fix_suggestions(new_scan_results)
                
                tracker.complete_step(step_id, f"Generated {len(new_fixes.get('automated', []))} new fix suggestions")
                
                insert_query = '''
                    INSERT INTO fix_history (scan_id, original_file, fixed_file, fixes_applied, success_count)
                    VALUES (%s, %s, %s, %s, %s)
                '''
                # Ensure original file name also has .pdf extension for consistency
                original_filename_with_ext = f"{scan_id}.pdf" if not scan_filename.endswith('.pdf') else scan_filename

                execute_query(insert_query, (
                    scan_id,
                    original_filename_with_ext,  # Original file with .pdf extension
                    fixed_filename,              # Fixed file with .pdf extension
                    json.dumps(result.get('fixesApplied', [])),
                    result.get('successCount', 0)
                ))
                print(f"[Backend] ✓ Saved {result.get('successCount', 0)} fixes to fix_history table")
                
                tracker.complete_all()
                print(f"[Backend] ✓ Successfully applied {result.get('successCount', 0)} fixes")
                
                return jsonify({
                    'success': True,
                    'message': f"Successfully applied {result.get('successCount', 0)} fixes",
                    'fixedFile': fixed_filename,
                    'fixesApplied': result.get('fixesApplied', []),
                    'successCount': result.get('successCount', 0),
                    'newScanResults': new_scan_results,
                    'newSummary': new_summary,
                    'newFixes': new_fixes
                }), 200
                
            except Exception as rescan_error:
                print(f"[Backend] ERROR: Failed to re-scan fixed file: {rescan_error}")
                import traceback
                traceback.print_exc()
                tracker.fail_all(f"Re-scan failed: {str(rescan_error)}")
                
                try:
                    insert_query = '''
                        INSERT INTO fix_history (scan_id, original_file, fixed_file, fixes_applied, success_count)
                        VALUES (%s, %s, %s, %s, %s)
                    '''
                    original_filename_with_ext = f"{scan_id}.pdf" if not scan_filename.endswith('.pdf') else scan_filename
                    execute_query(insert_query, (
                        scan_id,
                        original_filename_with_ext,
                        fixed_filename,
                        json.dumps(result.get('fixesApplied', [])),
                        result.get('successCount', 0)
                    ))
                except Exception as history_error:
                    print(f"[Backend] ERROR: Failed to save fix history: {history_error}")
                
                return jsonify({
                    'success': False,
                    'message': f"Fixes applied but re-scan failed: {str(rescan_error)}",
                    'error': str(rescan_error)
                }), 500
        else:
            tracker.fail_all(result.get('error', 'Unknown error'))
            return jsonify({
                'success': False,
                'message': result.get('error', 'Failed to apply fixes'),
                'error': result.get('error', 'Unknown error')
            }), 500
            
    except Exception as e:
        print(f"[Backend] ERROR in apply_fixes: {e}")
        import traceback
        traceback.print_exc()
        if 'tracker' in locals():
            tracker.fail_all(str(e))
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/fix-progress/<scan_id>', methods=['GET'])
def get_fix_progress(scan_id):
    """Get the current progress of fix operations"""
    try:
        tracker = get_progress_tracker(scan_id)
        if not tracker:
            return jsonify({
                'error': 'No active fix operation found for this scan',
                'scanId': scan_id,
                'status': 'not_found'
            }), 404

        progress = tracker.get_progress()
        return jsonify(progress)
    except Exception as e:
        print(f"[Backend] Error getting fix progress: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/apply-semi-automated-fixes/<scan_id>', methods=['POST'])
def apply_semi_automated_fixes(scan_id):
    """Apply semi-automated fixes to a scanned PDF"""
    try:
        from fix_progress_tracker import create_progress_tracker # Already imported

        tracker = create_progress_tracker(scan_id, total_steps=8)

        data = request.get_json()
        use_ai = data.get('useAI', False)

        print(f"[Backend] Applying {'AI-powered' if use_ai else 'traditional'} semi-automated fixes to scan: {scan_id}")

        step_id = tracker.add_step(
            "Initialize Semi-Automated Fix Process",
            "Preparing to apply semi-automated fixes to the PDF",
            "pending"
        )
        tracker.start_step(step_id)

        # Check if auto-fix is available
        if not AUTO_FIX_AVAILABLE:
            tracker.fail_step(step_id, "Auto-fix engine is not available")
            tracker.fail_all("Auto-fix engine is not available")
            return jsonify({
                'success': False,
                'message': 'Auto-fix functionality is not available. Please check server configuration.'
            }), 503

        tracker.complete_step(step_id, "Semi-automated fix process initialized successfully")

        # Get scan data
        step_id = tracker.add_step(
            "Load Scan Data",
            "Loading scan results and PDF file",
            "pending"
        )
        tracker.start_step(step_id)

        # Use unified query execution to get scan data
        query = f'SELECT filename, scan_results FROM scans WHERE id = %s'
        scan_data_result = execute_query(query, (scan_id,), fetch=True)

        if not scan_data_result:
            tracker.fail_step(step_id, f"Scan not found: {scan_id}")
            tracker.fail_all(f"Scan not found: {scan_id}")
            return jsonify({'success': False, 'message': 'Scan not found'}), 404

        scan_filename = scan_data_result[0]['filename']
        scan_results_json = scan_data_result[0]['scan_results']

        scan_data = {
            'filename': scan_filename,
            'results': json.loads(scan_results_json) if isinstance(scan_results_json, str) else scan_results_json
        }
        tracker.complete_step(step_id, f"Loaded scan data for {scan_data.get('filename', 'unknown')}")

        # Apply semi-automated fixes with progress tracking
        if use_ai:
            # Check if AI remediation is available
            if not AI_REMEDIATION_AVAILABLE:
                tracker.fail_step(step_id, "AI remediation engine is not available.")
                tracker.fail_all("AI remediation engine is not available.")
                return jsonify({
                    'success': False,
                    'message': 'AI remediation functionality is not available. Set SAMBANOVA_API_KEY.'
                }), 503

            # AI fixes not available - fall back to traditional fixes
            from auto_fix_engine import AutoFixEngine # Ensure imported
            fix_engine = AutoFixEngine()
            result = fix_engine.apply_semi_automated_fixes(scan_id, scan_data, tracker)
        else:
            from auto_fix_engine import AutoFixEngine # Ensure imported
            fix_engine = AutoFixEngine()
            result = fix_engine.apply_semi_automated_fixes(scan_id, scan_data, tracker)

        if result.get('success'):
            try:
                # Ensure original filename ends with .pdf for consistency
                original_filename_with_ext = scan_filename if scan_filename.endswith('.pdf') else f"{scan_filename}.pdf"

                insert_query = '''
                    INSERT INTO fix_history (scan_id, original_file, fixed_file, fixes_applied, success_count)
                    VALUES (%s, %s, %s, %s, %s)
                '''
                execute_query(insert_query, (
                    scan_id,
                    original_filename_with_ext,
                    result.get('fixedFile', scan_id), # Use provided fixedFile or default to scan_id
                    json.dumps(result.get('fixesApplied', [])),
                    result.get('successCount', 0)
                ))
                print(f"[Backend] ✓ Saved {result.get('successCount', 0)} fixes to fix_history table")
            except Exception as history_error:
                print(f"[Backend] ERROR: Failed to save fix history: {history_error}")
                import traceback
                traceback.print_exc()
            
            step_id = tracker.add_step(
                "Re-scan Fixed PDF",
                "Analyzing fixed PDF to verify improvements",
                "pending"
            )
            tracker.start_step(step_id)

            try:
                # Re-analyze the fixed PDF
                fixed_path = os.path.join('uploads', result.get('fixedFile', f"{scan_id}.pdf"))
                analyzer = PDFAccessibilityAnalyzer()
                new_scan_results = analyzer.analyze(fixed_path)

                new_summary = analyzer.calculate_summary(new_scan_results)
                
                print(f"[Backend] ✓ Calculated new summary:")
                print(f"[Backend]   Total issues: {new_summary.get('totalIssues', 0)}")
                print(f"[Backend]   Compliance score: {new_summary.get('complianceScore', 0)}%")
                print(f"[Backend]   High severity: {new_summary.get('highSeverity', 0)}")

                # Update scan results in database with proper summary
                scan_data_updated = {
                    'results': new_scan_results,
                    'summary': new_summary  # Store calculated summary instead of None
                }

                update_query = f'UPDATE scans SET scan_results = %s, status = %s WHERE id = %s'
                execute_query(update_query, (json.dumps(scan_data_updated), 'fixed', scan_id))
                
                print(f"[Backend] ✓ Database updated with new scan results and summary")

                # Generate new fix suggestions
                if AUTO_FIX_AVAILABLE:
                    auto_fix_engine = AutoFixEngine()
                    new_fixes = auto_fix_engine.generate_fixes(new_scan_results)
                else:
                    new_fixes = generate_fix_suggestions(new_scan_results)

                result['newScanResults'] = new_scan_results
                result['newFixes'] = new_fixes
                result['newSummary'] = new_summary  # Include summary in response

                tracker.complete_step(step_id, f"Re-scan complete: {len(new_scan_results.get('wcagIssues', []))} WCAG issues, {len(new_scan_results.get('pdfuaIssues', []))} PDF/UA issues", result_data={'newScanResults': new_scan_results, 'newFixes': new_fixes, 'newSummary': new_summary})
                print(f"[Backend] Re-scan complete: {len(new_scan_results.get('wcagIssues', []))} WCAG issues, {len(new_scan_results.get('pdfuaIssues', []))} PDF/UA issues")
                print(f"[Backend] Step completed with resultData stored")
            except Exception as rescan_error:
                print(f"[Backend] Warning: Re-scan failed: {rescan_error}")
                tracker.skip_step(step_id, f"Re-scan failed: {str(rescan_error)}")

            tracker.complete_all()
            return jsonify(result)
        else:
            tracker.fail_all(result.get('error', 'Unknown error'))
            return jsonify(result), 500
    except Exception as e:
        print(f"[Backend] Error applying semi-automated fixes: {str(e)}")
        import traceback
        traceback.print_exc()

        if 'tracker' in locals():
            tracker.fail_all(str(e))

        return jsonify({
            'success': False,
            'message': f'Error applying semi-automated fixes: {str(e)}'
        }), 500

@app.route('/api/fix-history/<scan_id>', methods=['GET'])
def get_fix_history(scan_id):
    """Get fix history for a specific scan"""
    try:
        # Use unified query execution for fetch
        query = '''
            SELECT id, original_file, fixed_file, fixes_applied, success_count, timestamp
            FROM fix_history
            WHERE scan_id = %s
            ORDER BY timestamp DESC
        '''
        history = execute_query(query, (scan_id,), fetch=True)

        return jsonify({
            'scanId': scan_id,
            'history': [
                {
                    'id': h['id'],
                    'originalFile': h['original_file'],
                    'fixedFile': h['fixed_file'],
                    'fixesApplied': h['fixes_applied'] if isinstance(h['fixes_applied'], list) else json.loads(h['fixes_applied']),
                    'successCount': h['success_count'],
                    'timestamp': h['timestamp'].isoformat() if h['timestamp'] else None
                }
                for h in history
            ]
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download-fixed/<path:identifier>', methods=['GET'])
def download_fixed_file(identifier):
    """Download a fixed PDF file by scan_id or filename"""
    try:
        print(f"[Backend] Download request for: {identifier}")
        
        # Try to find the file in fix_history first (most recent fix)
        cursor = None
        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute("""
                SELECT fixed_file, scan_id 
                FROM fix_history 
                WHERE scan_id = %s OR fixed_file LIKE %s
                ORDER BY timestamp DESC 
                LIMIT 1
            """, (identifier, f"%{identifier}%"))
            
            result = cursor.fetchone()
            
            file_path = None
            download_name = None

            if result:
                # Use the fixed file
                fixed_file = result['fixed_file']
                
                # Ensure .pdf extension
                if not fixed_file.endswith('.pdf'):
                    fixed_file = f"{fixed_file}.pdf"
                
                # Check multiple possible locations
                possible_paths = [
                    os.path.join('uploads', fixed_file),
                    os.path.join('uploads', os.path.basename(fixed_file)),
                    fixed_file,
                    os.path.join('uploads', f"{result['scan_id']}.pdf"),
                ]
                
                for path in possible_paths:
                    print(f"[Backend] Checking path: {path}")
                    if os.path.exists(path):
                        file_path = path
                        break
                
                download_name = os.path.basename(fixed_file)

            if not file_path:
                # Try to find in scans table if no fixed file found or if identifier matches scan_id directly
                cursor.execute("""
                    SELECT id as scan_id, filename 
                    FROM scans 
                    WHERE id = %s OR filename LIKE %s
                    LIMIT 1
                """, (identifier, f"%{identifier}%"))
                result = cursor.fetchone()
                
                if not result:
                    print(f"[Backend] No record found for: {identifier}")
                    return jsonify({'error': 'Scan not found'}), 404
                
                # Use the original file if no fixed version exists
                file_path = os.path.join('uploads', result['filename'])
                download_name = result['filename']
            
            # Verify file exists and is not empty
            if not os.path.exists(file_path):
                print(f"[Backend] File does not exist: {file_path}")
                return jsonify({'error': 'File not found on disk'}), 404
            
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                print(f"[Backend] File is empty: {file_path}")
                return jsonify({'error': 'File is empty'}), 500
            
            print(f"[Backend] Sending file: {download_name} ({file_size} bytes) from {file_path}")
            
            return send_file(
                file_path,
                mimetype='application/pdf',
                as_attachment=True,
                download_name=download_name
            )
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        
    except Exception as e:
        print(f"[Backend] Error downloading file: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/generate-pdf', methods=['POST'])
def generate_pdf():
    """Generate an accessible or inaccessible PDF for testing"""
    if not PDF_GENERATOR_AVAILABLE:
        return jsonify({'error': 'PDF generator not available'}), 503

    try:
        data = request.get_json()
        company_name = data.get('companyName', 'BrightPath Consulting')
        services = data.get('services', None)
        pdf_type = data.get('pdfType', 'inaccessible')
        accessibility_options = data.get('accessibilityOptions', None)

        print(f"[PDFGen] Generating {pdf_type} PDF for: {company_name}")

        generator = PDFGenerator()

        if pdf_type == 'accessible':
            pdf_path = generator.create_accessible_pdf(company_name, services)
        else:
            pdf_path = generator.create_inaccessible_pdf(company_name, services, accessibility_options)

        filename = os.path.basename(pdf_path)

        print(f"[PDFGen] PDF generated: {filename}")

        return jsonify({
            'success': True,
            'filename': filename,
            'path': pdf_path,
            'message': f'Generated {pdf_type} PDF: {filename}'
        }), 200
    except Exception as e:
        print(f"[PDFGen] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/generated-pdfs', methods=['GET'])
def get_generated_pdfs():
    """Get list of generated PDFs"""
    if not PDF_GENERATOR_AVAILABLE:
        return jsonify({'error': 'PDF generator not available'}), 503

    try:
        generator = PDFGenerator()
        pdfs = generator.get_generated_pdfs()

        return jsonify({
            'pdfs': pdfs,
            'count': len(pdfs)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/download-generated/<filename>', methods=['GET'])
def download_generated_pdf(filename):
    """Download a generated PDF"""
    try:
        from flask import send_file

        if not filename.endswith('.pdf'):
            filename = filename + '.pdf'

        file_path = os.path.join('generated_pdfs', filename)

        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404

        return send_file(file_path, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/pdf-file/<scan_id>', methods=['GET'])
def get_pdf_file(scan_id):
    """Serve PDF file for viewing in the editor"""
    try:
        from flask import send_file

        file_path = os.path.join('uploads', scan_id)

        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404

        return send_file(file_path, mimetype='application/pdf')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/apply-manual-fix/<scan_id>', methods=['POST'])
def apply_manual_fix(scan_id):
    """Apply a manual fix to the PDF"""
    try:
        data = request.get_json()
        fix_type = data.get('fixType')
        fix_data = data.get('fixData')
        page = data.get('page', 1)

        print(f"[ManualFix] ========== APPLYING MANUAL FIX ==========")
        print(f"[ManualFix] Scan ID: {scan_id}")
        print(f"[ManualFix] Fix type: {fix_type}")
        print(f"[ManualFix] Page: {page}")
        print(f"[ManualFix] Fix data: {fix_data}")

        pdf_path = os.path.join('uploads', scan_id)

        if not os.path.exists(pdf_path):
            print(f"[ManualFix] ERROR: PDF file not found at {pdf_path}")
            return jsonify({'error': 'PDF file not found'}), 404

        if not AUTO_FIX_AVAILABLE:
            print("[ManualFix] ERROR: AutoFixEngine not available")
            return jsonify({'error': 'Auto-fix engine not available. Install pikepdf: pip install pikepdf'}), 503

        print(f"[ManualFix] Using AutoFixEngine to apply fix...")
        auto_fix_engine = AutoFixEngine()

        # Apply the specific manual fix using AutoFixEngine
        fix_result = None
        if fix_type == 'addAltText':
            fix_result = auto_fix_engine.apply_single_fix(pdf_path, {
                'type': 'addAltText',
                'data': fix_data,
                'page': page
            })
        elif fix_type == 'tagContent':
            fix_result = auto_fix_engine.apply_single_fix(pdf_path, {
                'type': 'tagContent',
                'data': fix_data,
                'page': page
            })
        elif fix_type == 'fixTableStructure':
            fix_result = auto_fix_engine.apply_single_fix(pdf_path, {
                'type': 'fixTableStructure',
                'data': fix_data,
                'page': page
            })
        elif fix_type == 'addFormLabel':
            fix_result = auto_fix_engine.apply_single_fix(pdf_path, {
                'type': 'addFormLabel',
                'data': fix_data,
                'page': page
            })
        else:
            print(f"[ManualFix] ERROR: Unsupported fix type: {fix_type}")
            return jsonify({'error': f'Unsupported fix type: {fix_type}'}), 400

        if not fix_result or not fix_result.get('success'):
            error_msg = fix_result.get('error', 'Unknown error') if fix_result else 'Fix failed'
            print(f"[ManualFix] ERROR: {error_msg}")
            return jsonify({'error': error_msg}), 500

        print(f"[ManualFix] ✓ Fix applied successfully: {fix_result.get('description', '')}")

        print(f"[ManualFix] Re-scanning fixed PDF to update results...")
        new_summary = None
        new_results = None
        try:
            analyzer = PDFAccessibilityAnalyzer()
            new_results = analyzer.analyze(pdf_path)
            new_summary = analyzer.calculate_summary(new_results)

            print(f"[ManualFix] ✓ Re-scan complete:")
            print(f"[ManualFix]   Total issues: {new_summary.get('totalIssues', 0)}")
            print(f"[ManualFix]   Compliance: {new_summary.get('complianceScore', 0)}%")
            print(f"[ManualFix]   Results keys: {list(new_results.keys())}")

            # Update the scan record with new results
            scan_data_for_db = {
                'results': new_results,
                'summary': new_summary
            }

            print(f"[ManualFix] Updating database with new scan data...")
            print(f"[ManualFix]   Scan data size: {len(json.dumps(scan_data_for_db))} bytes")

            update_query = f'''
                UPDATE scans
                SET scan_results = %s
                WHERE id = %s
            '''

            try:
                execute_query(update_query, (json.dumps(scan_data_for_db), scan_id))
                print(f"[ManualFix] ✓ Database updated successfully")

                # Verify the update by reading it back
                verify_query = f'SELECT scan_results FROM scans WHERE id = %s'
                verify_result = execute_query(verify_query, (scan_id,), fetch=True)

                if verify_result:
                    verified_data = verify_result[0]['scan_results']
                    if isinstance(verified_data, str):
                        verified_data = json.loads(verified_data)
                    verified_summary = verified_data.get('summary', {})
                    print(f"[ManualFix] ✓ Verified database update:")
                    print(f"[ManualFix]   Verified total issues: {verified_summary.get('totalIssues', 0)}")
                    print(f"[ManualFix]   Verified compliance: {verified_summary.get('complianceScore', 0)}%")
                else:
                    print(f"[ManualFix] WARNING: Could not verify database update")

            except Exception as db_error:
                print(f"[ManualFix] ERROR: Database update failed: {db_error}")
                import traceback
                traceback.print_exc()
                # Continue anyway, but log the error

            # Save fix history
            try:
                insert_query = f'''
                    INSERT INTO fix_history (scan_id, original_file, fixed_file, fixes_applied, success_count)
                    VALUES (%s, %s, %s, %s, %s)
                '''
                execute_query(insert_query, (
                    scan_id,
                    scan_id,
                    scan_id,  # Same file, modified in place
                    json.dumps([{
                        'type': fix_type,
                        'description': fix_result.get('description', ''),
                        'data': fix_data,
                        'page': page
                    }]),
                    1
                ))
                print(f"[ManualFix] ✓ Saved fix history")
            except Exception as history_error:
                print(f"[ManualFix] WARNING: Failed to save fix history: {history_error}")
                # Continue anyway

        except Exception as rescan_error:
            print(f"[ManualFix] ERROR: Failed to re-scan PDF: {rescan_error}")
            import traceback
            traceback.print_exc()
            # Return error since we couldn't update the results
            return jsonify({
                'error': f'Fix applied but failed to re-scan: {str(rescan_error)}'
            }), 500

        print(f"[ManualFix] ========== MANUAL FIX COMPLETE ==========")

        return jsonify({
            'success': True,
            'message': fix_result.get('description', 'Fix applied successfully'),
            'fixType': fix_type,
            'summary': new_summary,
            'results': new_results
        }), 200

    except Exception as e:
        print(f"[ManualFix] ========== ERROR ==========")
        print(f"[ManualFix] Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

def process_single_file(file, idx, batch_id, total_files):
    """
    Process a single PDF file for batch scanning
    Returns a tuple of (scan_result, issue_count) or (None, 0) on error
    """
    print(f"\n[Backend] ========== FILE {idx+1}/{total_files}: {file.filename} ==========")
    try:
        scan_id = f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{idx}_{os.path.splitext(file.filename)[0]}"
        print(f"[Backend] Generated scan_id: {scan_id}")

        upload_dir = Path('uploads')
        upload_dir.mkdir(exist_ok=True)

        file_path = upload_dir / scan_id
        print(f"[Backend] Saving file to: {file_path}")

        try:
            file.save(str(file_path))
            file_size = os.path.getsize(file_path)
            print(f"[Backend] ✓ File saved successfully ({file_size} bytes)")
        except Exception as save_error:
            print(f"[Backend] ERROR saving file: {save_error}")
            raise

        print(f"[Backend] Starting PDF analysis...")
        try:
            analyzer = PDFAccessibilityAnalyzer()
            issues = analyzer.analyze(str(file_path))
            issue_count = sum(len(v) if isinstance(v, list) else 0 for v in issues.values())
            print(f"[Backend] ✓ Analysis complete: {issue_count} issues found")
            print(f"[Backend] Issue categories: {list(issues.keys())}")
        except Exception as analysis_error:
            print(f"[Backend] ERROR during analysis: {analysis_error}")
            import traceback
            traceback.print_exc()
            raise

        try:
            summary = analyzer.calculate_summary(issues)
            print(f"[Backend] ✓ Summary calculated: {summary.get('totalIssues', 0)} total issues, {summary.get('complianceScore', 0)}% compliance")
        except Exception as summary_error:
            print(f"[Backend] ERROR calculating summary: {summary_error}")
            summary = {'totalIssues': 0, 'complianceScore': 0}

        fixes = get_empty_fixes_structure()
        try:
            if AUTO_FIX_AVAILABLE:
                auto_fix_engine = AutoFixEngine()
                generated_fixes = auto_fix_engine.generate_fixes(issues)
                fixes = ensure_fixes_structure(generated_fixes)
            else:
                fixes = generate_fix_suggestions(issues)

            fixes = ensure_fixes_structure(fixes)
            fix_count = len(fixes.get('automated', [])) + len(fixes.get('semiAutomated', [])) + len(fixes.get('manual', []))
            print(f"[Backend] ✓ Generated {fix_count} fix suggestions")
        except Exception as fix_error:
            print(f"[Backend] ERROR generating fixes: {fix_error}")
            fixes = get_empty_fixes_structure()

        try:
            # Use unified query execution to save scan (thread-safe with db_lock)
            save_scan_to_db(file.filename, issues, summary, scan_id=scan_id)
            print(f"[Backend] ✓ Scan saved to database")
        except Exception as db_error:
            print(f"[Backend] ERROR saving scan to database: {db_error}")
            import traceback
            traceback.print_exc()

        issue_count = summary.get('totalIssues', 0)

        scan_result = {
            'scanId': scan_id,
            'filename': file.filename,
            'results': issues,
            'summary': summary,
            'fixes': fixes
        }

        print(f"[Backend] ✓ Completed scan for {file.filename}: {issue_count} issues")

        return (scan_result, issue_count)

    except Exception as e:
        print(f"[Backend] ========== ERROR PROCESSING {file.filename} ==========")
        print(f"[Backend] Error: {e}")
        import traceback
        traceback.print_exc()
        return (None, 0)

@app.route('/api/scan-batch', methods=['POST'])
def scan_batch():
    """
    Endpoint to scan multiple PDFs as a batch with parallel processing
    Expects multipart/form-data with multiple 'files' fields
    """
    print("[Backend] ========== BATCH SCAN REQUEST ==========")
    print(f"[Backend] Request method: {request.method}")
    print(f"[Backend] Request content type: {request.content_type}")
    print(f"[Backend] Request files keys: {list(request.files.keys())}")
    print(f"[Backend] Request form keys: {list(request.form.keys())}")

    if 'files' not in request.files:
        print("[Backend] ERROR: 'files' key not found in request.files")
        print(f"[Backend] Available keys: {list(request.files.keys())}")
        return jsonify({'error': 'No files provided', 'availableKeys': list(request.files.keys())}), 400

    files = request.files.getlist('files')
    print(f"[Backend] Retrieved {len(files)} files from request.files.getlist('files')")

    for i, f in enumerate(files):
        print(f"[Backend] File {i+1}: filename='{f.filename}', content_type='{f.content_type}', size={f.content_length if hasattr(f, 'content_length') else 'unknown'}")

    if len(files) == 0:
        print("[Backend] ERROR: files list is empty after getlist")
        return jsonify({'error': 'No files selected'}), 400

    pdf_files = []
    for f in files:
        if f.filename and f.filename.lower().endswith('.pdf'):
            pdf_files.append(f)
            print(f"[Backend] ✓ Accepted PDF: {f.filename}")
        else:
            print(f"[Backend] ✗ Rejected non-PDF: {f.filename}")

    print(f"[Backend] Filtered to {len(pdf_files)} PDF files out of {len(files)} total files")

    if len(pdf_files) == 0:
        print("[Backend] ERROR: No PDF files found after filtering")
        return jsonify({'error': 'No PDF files found'}), 400

    try:
        # Create batch ID
        batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"[Backend] ========== CREATING BATCH: {batch_id} ==========")
        print(f"[Backend] Batch will contain {len(pdf_files)} files")

        try:
            # Use unified query execution for batch creation
            query = '''
                INSERT INTO batches (id, name, file_count, status)
                VALUES (%s, %s, %s, %s)
            '''
            execute_query(query, (batch_id, f"Batch {datetime.now().strftime('%Y-%m-%d %H:%M')}", len(pdf_files), 'processing'))
            print(f"[Backend] ✓ Batch record created in database")
        except Exception as db_error:
            print(f"[Backend] ERROR creating batch record: {db_error}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': f'Database error: {str(db_error)}'}), 500

        scan_results = []
        total_issues = 0

        print(f"[Backend] ========== PROCESSING {len(pdf_files)} FILES IN PARALLEL ==========")

        # Use max 4 workers to avoid overwhelming the system
        max_workers = min(4, len(pdf_files))
        print(f"[Backend] Using {max_workers} parallel workers")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all files for processing
            future_to_file = {
                executor.submit(process_single_file, file, idx, batch_id, len(pdf_files)): (file, idx)
                for idx, file in enumerate(pdf_files)
            }

            # Collect results as they complete
            for future in as_completed(future_to_file):
                file, idx = future_to_file[future]
                try:
                    scan_result, issue_count = future.result()
                    if scan_result:
                        scan_result['batchId'] = batch_id # Assign batchId to scan result
                        scan_results.append(scan_result)
                        total_issues += issue_count
                        print(f"[Backend] ✓ Collected result for {file.filename}")
                    else:
                        print(f"[Backend] ✗ Failed to process {file.filename}")
                except Exception as exc:
                    print(f"[Backend] ✗ Exception processing {file.filename}: {exc}")
                    import traceback
                    traceback.print_exc()

        print(f"\n[Backend] ========== BATCH PROCESSING COMPLETE ==========")
        print(f"[Backend] Successfully processed: {len(scan_results)}/{len(pdf_files)} files")
        print(f"[Backend] Total issues found: {total_issues}")

        try:
            # Use unified query execution to update batch status
            query = '''
                UPDATE batches
                SET status = %s, total_issues = %s, file_count = %s
                WHERE id = %s
            '''
            execute_query(query, ('completed', total_issues, len(scan_results), batch_id))
            print(f"[Backend] ✓ Batch record updated")
        except Exception as db_error:
            print(f"[Backend] ERROR updating batch record: {db_error}")

        response_data = {
            'batchId': batch_id,
            'fileCount': len(scan_results),
            'totalIssues': total_issues,
            'scans': scan_results
        }

        print(f"[Backend] ========== SENDING RESPONSE ==========")
        print(f"[Backend] Response structure:")
        print(f"[Backend]   batchId: {batch_id}")
        print(f"[Backend]   fileCount: {len(scan_results)}")
        print(f"[Backend]   totalIssues: {total_issues}")
        print(f"[Backend]   scans array length: {len(scan_results)}")

        return jsonify(response_data), 200

    except Exception as e:
        error_message = f"Error processing batch: {str(e)}"
        print(f"[Backend] ========== FATAL ERROR ==========")
        print(f"[Backend] {error_message}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': error_message}), 500

@app.route('/api/batch/<batch_id>/fix-all', methods=['POST'])
def fix_all_batch(batch_id):
    """Apply automated fixes to all files in a batch"""
    if not AUTO_FIX_AVAILABLE:
        return jsonify({'error': 'Auto-fix engine not available. Install pikepdf: pip install pikepdf'}), 503

    try:
        print(f"[Backend] ========== FIX ALL BATCH: {batch_id} ==========")

        # Use unified query execution to get scans
        query = f'SELECT id, filename, batch_id FROM scans WHERE batch_id = %s'
        scans = execute_query(query, (batch_id,), fetch=True)

        print(f"[Backend] Found {len(scans)} scans in batch {batch_id}")

        if not scans:
            print(f"[Backend] ERROR: No scans found for batch_id: {batch_id}")
            return jsonify({'error': 'Batch not found or empty'}), 404

        results = []
        success_count = 0

        for scan in scans:
            scan_id = scan['id']
            filename = scan['filename']
            db_batch_id = scan['batch_id'] # Keep track of original batch ID
            
            try:
                # Construct the path to the original PDF file
                original_pdf_path = os.path.join('uploads', scan_id)

                if not os.path.exists(original_pdf_path):
                    print(f"[Backend] ERROR: File not found: {original_pdf_path}")
                    results.append({
                        'scanId': scan_id,
                        'filename': filename,
                        'success': False,
                        'error': 'File not found'
                    })
                    continue

                print(f"[Backend] Applying fixes to: {filename}")
                auto_fix_engine = AutoFixEngine()
                # apply_automated_fixes should return the path to the fixed file
                result = auto_fix_engine.apply_automated_fixes(scan_id, {'filename': filename, 'results': {}}, tracker=None) # Pass empty tracker for now

                if result.get('success'):
                    success_count += 1

                    # Construct the path to the fixed file
                    fixed_filename = f"{scan_id}_fixed.pdf"
                    fixed_path = os.path.join('uploads', fixed_filename)

                    # Ensure the fixed file is correctly located and named
                    if result.get('fixed_file') and result.get('fixed_file') != fixed_path:
                        if os.path.exists(result['fixed_file']):
                            shutil.copy2(result['fixed_file'], fixed_path)
                            print(f"[Backend] Copied fixed file from '{result['fixed_file']}' to '{fixed_path}'")
                        else:
                            print(f"[Backend] Warning: Original fixed file not found at '{result['fixed_file']}'")
                    elif not os.path.exists(fixed_path) and result.get('fixed_file') == fixed_path:
                        print(f"[Backend] Fixed file already at correct path: {fixed_path}")
                    else:
                        print(f"[Backend] Warning: Could not determine or locate the fixed file. Expected path: {fixed_path}")

                    # Re-scan the fixed file to get updated results
                    print(f"[Backend] Re-scanning fixed file: {fixed_filename} from path: {fixed_path}")

                    analyzer = PDFAccessibilityAnalyzer()
                    new_scan_results = analyzer.analyze(fixed_path)
                    new_summary = analyzer.calculate_summary(new_scan_results)

                    print(f"[Backend] New scan results: {new_summary.get('totalIssues', 0)} issues, {new_summary.get('complianceScore', 0)}% compliance")

                    scan_data_updated = {
                        'results': new_scan_results,
                        'summary': new_summary
                    }

                    update_query = f'''
                        UPDATE scans
                        SET scan_results = %s, status = %s
                        WHERE id = %s
                    '''
                    execute_query(update_query, (json.dumps(scan_data_updated), 'fixed', scan_id))
                    print(f"[Backend] ✓ Updated scan record with new results")

                    insert_query = f'''
                        INSERT INTO fix_history (scan_id, original_file, fixed_file, fixes_applied, success_count)
                        VALUES (%s, %s, %s, %s, %s)
                    '''
                    # Ensure original filename has .pdf extension
                    original_filename_with_ext = filename if filename.endswith('.pdf') else f"{filename}.pdf"
                    execute_query(insert_query, (
                        scan_id,
                        original_filename_with_ext,
                        fixed_filename,
                        json.dumps(result.get('fixesApplied', [])),
                        result.get('successCount', 0)
                    ))
                    print(f"[Backend] ✓ Fixes applied successfully to {filename}")

                else:
                    print(f"[Backend] ✗ Fix failed for {filename}: {result.get('error', 'Unknown error')}")

                results.append({
                    'scanId': scan_id,
                    'filename': filename,
                    'success': result.get('success', False),
                    'fixedFile': fixed_filename if result.get('success') else None,
                    'fixesApplied': result.get('fixesApplied', []),
                    'successCount': result.get('successCount', 0),
                    'error': result.get('error')
                })

            except Exception as e:
                print(f"[Backend] ERROR fixing {filename}: {e}")
                import traceback
                traceback.print_exc()
                results.append({
                    'scanId': scan_id,
                    'filename': filename,
                    'success': False,
                    'error': str(e)
                })

        # Use unified query execution to update batch status
        update_query = f'''
            UPDATE batches
            SET status = %s, fixed_count = %s
            WHERE id = %s
        '''
        execute_query(update_query, ('fixed', success_count, batch_id))

        print(f"[Backend] ========== BATCH FIXES COMPLETE ==========")
        print(f"[Backend] Success: {success_count}/{len(scans)} files")

        return jsonify({
            'batchId': batch_id,
            'totalFiles': len(scans),
            'successCount': success_count,
            'results': results
        }), 200

    except Exception as e:
        print(f"[Backend] ========== ERROR FIXING BATCH ==========")
        print(f"[Backend] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/batch/<batch_id>/fix-file/<path:scan_id>', methods=['POST'])
def fix_batch_file(batch_id, scan_id):
    """Apply automated fixes to a single file in a batch"""
    if not AUTO_FIX_AVAILABLE:
        return jsonify({'error': 'Auto-fix engine not available. Install pikepdf: pip install pikepdf'}), 503

    try:
        print(f"[Backend] ========== FIXING FILE ==========")
        print(f"[Backend] Batch ID: {batch_id}")
        print(f"[Backend] Scan ID: {scan_id}")

        # Use unified query execution to get scan details
        query = f'SELECT filename, batch_id FROM scans WHERE id = %s'
        result = execute_query(query, (scan_id,), fetch=True)

        if not result:
            print(f"[Backend] Scan {scan_id} not found in database")
            pdf_path = os.path.join('uploads', scan_id)
            if os.path.exists(pdf_path):
                print(f"[Backend] File exists but not in database, adding it now...")
                try:
                    analyzer = PDFAccessibilityAnalyzer()
                    results = analyzer.analyze(pdf_path)
                    summary = analyzer.calculate_summary(results)

                    scan_data_for_db = {
                        'results': results,
                        'summary': summary
                    }

                    # Use unified query execution to add scan
                    save_scan_to_db(os.path.basename(pdf_path), results, summary, scan_id=scan_id)
                    print(f"[Backend] ✓ Scan added to database")
                except Exception as e:
                    print(f"[Backend] ERROR adding scan to database: {e}")
                    import traceback
                    traceback.print_exc()
                    return jsonify({'error': f'Failed to add scan: {str(e)}'}), 500
            else:
                print(f"[Backend] File not found: {pdf_path}")
                return jsonify({'error': 'PDF file not found'}), 404
        else:
            filename = result[0]['filename']
            db_batch_id = result[0]['batch_id']
            print(f"[Backend] ✓ Found scan: {filename}, batch_id: {db_batch_id}")

        # Construct the path to the original PDF file
        pdf_path = os.path.join('uploads', scan_id)

        if not os.path.exists(pdf_path):
            print(f"[Backend] ERROR: File not found: {pdf_path}")
            return jsonify({'error': 'PDF file not found'}), 404

        print(f"[Backend] ✓ File found, applying fixes...")
        auto_fix_engine = AutoFixEngine()
        # apply_automated_fixes should return the path to the fixed file
        fix_result = auto_fix_engine.apply_automated_fixes(scan_id, {'filename': filename, 'results': {}}, tracker=None) # Pass empty tracker for now

        if fix_result.get('success'):
            # Construct the fixed file path
            fixed_filename = f"{scan_id}_fixed.pdf"
            fixed_path = os.path.join('uploads', fixed_filename)

            # Ensure the fixed file is correctly located and named
            if fix_result.get('fixed_file') and fix_result.get('fixed_file') != fixed_path:
                if os.path.exists(fix_result['fixed_file']):
                    shutil.copy2(fix_result['fixed_file'], fixed_path)
                    print(f"[Backend] Copied fixed file from '{fix_result['fixed_file']}' to '{fixed_path}'")
                else:
                    print(f"[Backend] Warning: Original fixed file not found at '{fix_result['fixed_file']}'")
            elif not os.path.exists(fixed_path) and fix_result.get('fixed_file') == fixed_path:
                print(f"[Backend] Fixed file already at correct path: {fixed_path}")
            else:
                print(f"[Backend] Warning: Could not determine or locate the fixed file. Expected path: {fixed_path}")

            # Re-scan the fixed file
            try:
                # Re-scan the fixed PDF to get updated results
                print(f"[Backend] Re-scanning fixed file: {fixed_filename} from path: {fixed_path}")

                analyzer = PDFAccessibilityAnalyzer()
                new_results = analyzer.analyze(fixed_path)
                new_summary = analyzer.calculate_summary(new_results)

                print(f"[Backend] New scan results: {new_summary.get('totalIssues', 0)} issues, {new_summary.get('complianceScore', 0)}% compliance")

                scan_data_updated = {
                    'results': new_results,
                    'summary': new_summary
                }

                update_query = f'''
                    UPDATE scans
                    SET scan_results = %s, status = %s
                    WHERE id = %s
                '''
                execute_query(update_query, (json.dumps(scan_data_updated), 'fixed', scan_id))
                print(f"[Backend] ✓ Updated scan record with new results")

                insert_query = f'''
                    INSERT INTO fix_history (scan_id, original_file, fixed_file, fixes_applied, success_count)
                    VALUES (%s, %s, %s, %s, %s)
                '''
                # Ensure original filename has .pdf extension
                original_filename_with_ext = filename if filename.endswith('.pdf') else f"{filename}.pdf"
                execute_query(insert_query, (
                    scan_id,
                    original_filename_with_ext,
                    fixed_filename,
                    json.dumps(fix_result.get('fixesApplied', [])),
                    fix_result.get('successCount', 0)
                ))
                print(f"[Backend] ✓ Fixes applied successfully: {fix_result.get('successCount', 0)} fixes")
            except Exception as db_err:
                print(f"[Backend] Database error saving fix history: {db_err}")
                import traceback
                traceback.print_exc()
                # Continue anyway, the fix was applied
        else:
            print(f"[Backend] ✗ Fix failed: {fix_result.get('error', 'Unknown error')}")

        return jsonify(fix_result), 200

    except Exception as e:
        print(f"[Backend] ========== ERROR FIXING FILE ==========")
        print(f"[Backend] Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/batch/<batch_id>/export', methods=['GET'])
def export_batch(batch_id):
    """Export all fixed PDFs in a batch as a ZIP file"""
    try:
        from flask import send_file
        import zipfile
        import io

        print(f"[Backend] Exporting batch: {batch_id}")

        # Get all scans in the batch
        # Use unified query execution for export
        query = '''
            SELECT s.id, s.filename, fh.fixed_file
            FROM scans s
            LEFT JOIN fix_history fh ON s.id = fh.scan_id
            WHERE s.batch_id = %s
        '''
        scans = execute_query(query, (batch_id,), fetch=True)

        if not scans:
            return jsonify({'error': 'Batch not found or empty'}), 404

        # Create ZIP file in memory
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for scan in scans:
                # Use fixed file if available, otherwise use original
                fixed_file_db_entry = scan['fixed_file'] # from fix_history
                scan_id = scan['id']
                original_filename = scan['filename']

                # Ensure original filename has .pdf extension
                if not original_filename.endswith('.pdf'):
                    original_filename = f"{original_filename}.pdf"

                file_to_add_path = None
                download_filename = original_filename

                if fixed_file_db_entry:
                    # Check if the fixed file exists
                    potential_fixed_path = os.path.join('uploads', fixed_file_db_entry)
                    if os.path.exists(potential_fixed_path):
                        file_to_add_path = potential_fixed_path
                        download_filename = fixed_file_db_entry # Use the name from DB entry
                        print(f"[Backend] Found fixed file: {download_filename}")
                    else:
                        print(f"[Backend] Fixed file '{fixed_file_db_entry}' not found on disk, falling back to original scan file.")
                
                # If fixed file not found or not applicable, try to use the original scan file
                if not file_to_add_path:
                    original_scan_path = os.path.join('uploads', scan_id)
                    if os.path.exists(original_scan_path):
                        file_to_add_path = original_scan_path
                        # download_filename remains original_filename
                        print(f"[Backend] Using original scan file: {scan_id}")
                    else:
                        print(f"[Backend] Original scan file not found for scan_id: {scan_id}. Skipping.")

                if file_to_add_path and os.path.exists(file_to_add_path):
                    zip_file.write(file_to_add_path, download_filename)
                    print(f"[Backend] Added to ZIP: {download_filename}")
                else:
                    print(f"[Backend] Could not find file to add for scan {scan_id}. Skipping.")


        zip_buffer.seek(0)

        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'{batch_id}.zip'
        )

    except Exception as e:
        print(f"[Backend] Error exporting batch: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/batch/<batch_id>', methods=['GET', 'DELETE'])
def batch_operations(batch_id):
    """Get or delete batch details"""
    if request.method == 'GET':
        try:
            query = 'SELECT * FROM batches WHERE id = %s'
            batch = execute_query(query, (batch_id,), fetch=True)

            if not batch:
                return jsonify({'error': 'Batch not found'}), 404

            query = '''
                SELECT id, filename, scan_results, upload_date
                FROM scans
                WHERE batch_id = %s
                ORDER BY upload_date
            '''
            scans = execute_query(query, (batch[0]['id'],), fetch=True) # Use batch[0]['id']

            scan_details = []
            for scan in scans:
                scan_data = scan['scan_results']
                if isinstance(scan_data, str):
                    scan_data = json.loads(scan_data)

                if isinstance(scan_data, dict) and 'summary' in scan_data:
                    summary = scan_data['summary']
                else:
                    results = scan_data.get('results', scan_data)
                    analyzer = PDFAccessibilityAnalyzer()
                    summary = analyzer.calculate_summary(results)

                scan_details.append({
                    'scanId': scan['id'],
                    'filename': scan['filename'],
                    'summary': summary,
                    'uploadDate': scan['upload_date'].isoformat() if scan['upload_date'] else None
                })

            return jsonify({
                'batchId': batch[0]['id'],
                'name': batch[0]['name'],
                'uploadDate': batch[0]['upload_date'].isoformat() if batch[0]['upload_date'] else None,
                'fileCount': batch[0]['file_count'],
                'status': batch[0]['status'],
                'totalIssues': batch[0]['total_issues'],
                'fixedCount': batch[0]['fixed_count'],
                'scans': scan_details
            }), 200

        except Exception as e:
            print(f"[Backend] Error fetching batch details: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

    elif request.method == 'DELETE':
        try:
            print(f"[Backend] ========== DELETING BATCH: {batch_id} ==========")

            # Get all scans in the batch
            query = f'SELECT id FROM scans WHERE batch_id = %s'
            scans = execute_query(query, (batch_id,), fetch=True)

            if not scans:
                print(f"[Backend] No scans found for batch {batch_id}")
                return jsonify({'error': 'Batch not found'}), 404

            print(f"[Backend] Found {len(scans)} scans to delete")

            # Delete physical files
            deleted_files = 0
            for scan in scans:
                scan_id = scan['id']
                # Original file
                original_file_path = os.path.join('uploads', scan_id)
                if os.path.exists(original_file_path):
                    try:
                        os.remove(original_file_path)
                        deleted_files += 1
                        print(f"[Backend] ✓ Deleted original file: {original_file_path}")
                    except Exception as e:
                        print(f"[Backend] ✗ Failed to delete original file {original_file_path}: {e}")
                
                # Fixed file (look for scan_id_fixed.pdf)
                fixed_file_path = os.path.join('uploads', f"{scan_id}_fixed.pdf")
                if os.path.exists(fixed_file_path):
                    try:
                        os.remove(fixed_file_path)
                        deleted_files += 1
                        print(f"[Backend] ✓ Deleted fixed file: {fixed_file_path}")
                    except Exception as e:
                        print(f"[Backend] ✗ Failed to delete fixed file {fixed_file_path}: {e}")

            # Delete fix history records
            for scan in scans:
                delete_query = 'DELETE FROM fix_history WHERE scan_id = %s'
                execute_query(delete_query, (scan['id'],))
            print(f"[Backend] ✓ Deleted fix history records")

            # Delete scan records
            delete_scans_query = 'DELETE FROM scans WHERE batch_id = %s'
            execute_query(delete_scans_query, (batch_id,))
            print(f"[Backend] ✓ Deleted {len(scans)} scan records")

            # Delete batch record
            delete_batch_query = 'DELETE FROM batches WHERE id = %s'
            execute_query(delete_batch_query, (batch_id,))
            print(f"[Backend] ✓ Deleted batch record")

            print(f"[Backend] ========== BATCH DELETION COMPLETE ==========")
            print(f"[Backend] Deleted {deleted_files} physical files")

            return jsonify({
                'success': True,
                'message': f'Batch deleted successfully',
                'deletedFiles': deleted_files,
                'deletedScans': len(scans)
            }), 200

        except Exception as e:
            print(f"[Backend] ========== ERROR DELETING BATCH ==========")
            print(f"[Backend] Error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get complete upload history including batches and individual scans"""
    try:
        print("[Backend] ========== FETCHING HISTORY ==========")

        # Get all batches
        batches_query = 'SELECT * FROM batches ORDER BY upload_date DESC'
        batches_result = execute_query(batches_query, fetch=True)

        batches = []
        for batch in batches_result:
            # Get scans for this batch
            scans_query = '''
                SELECT id, filename, scan_results, upload_date
                FROM scans
                WHERE batch_id = %s
                ORDER BY upload_date
            '''
            scans = execute_query(scans_query, (batch['id'],), fetch=True)

            scan_list = []
            for scan in scans:
                scan_data = scan['scan_results']
                if isinstance(scan_data, str):
                    scan_data = json.loads(scan_data)

                if isinstance(scan_data, dict) and 'summary' in scan_data:
                    summary = scan_data['summary']
                else:
                    results = scan_data.get('results', scan_data)
                    analyzer = PDFAccessibilityAnalyzer()
                    summary = analyzer.calculate_summary(results)

                scan_list.append({
                    'scanId': scan['id'],
                    'filename': scan['filename'],
                    'summary': summary,
                    'uploadDate': scan['upload_date'].isoformat() if scan['upload_date'] else None
                })

            batches.append({
                'batchId': batch['id'],
                'name': batch['name'],
                'uploadDate': batch['upload_date'].isoformat() if batch['upload_date'] else None,
                'fileCount': batch['file_count'],
                'status': batch['status'],
                'totalIssues': batch['total_issues'],
                'fixedCount': batch['fixed_count'],
                'scans': scan_list
            })

        # Get individual scans (no batch_id)
        individual_query = '''
            SELECT id, filename, scan_results, upload_date, status
            FROM scans
            WHERE batch_id IS NULL
            ORDER BY upload_date DESC
        '''
        individual_scans = execute_query(individual_query, fetch=True)

        scans = []
        for scan in individual_scans:
            scan_data = scan['scan_results']
            if isinstance(scan_data, str):
                scan_data = json.loads(scan_data)

            if isinstance(scan_data, dict) and 'summary' in scan_data:
                summary = scan_data['summary']
            else:
                results = scan_data.get('results', scan_data)
                analyzer = PDFAccessibilityAnalyzer()
                summary = analyzer.calculate_summary(results)

            scans.append({
                'id': scan['id'],
                'filename': scan['filename'],
                'uploadDate': scan['upload_date'].isoformat() if scan['upload_date'] else None,
                'status': scan['status'],
                'summary': summary,
                'batchId': None
            })

        print(f"[Backend] ✓ Found {len(batches)} batches and {len(scans)} individual scans")

        return jsonify({
            'batches': batches,
            'scans': scans,
            'totalBatches': len(batches),
            'totalScans': len(scans)
        }), 200

    except Exception as e:
        print(f"[Backend] Error fetching history: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# --- SambaNova AI Endpoints ---

@app.route('/api/ai-analyze/<scan_id>', methods=['POST'])
def ai_analyze_scan(scan_id):
    """Use SambaNova AI to analyze scan and provide intelligent remediation strategies"""
    if not AI_REMEDIATION_AVAILABLE:
        return jsonify({
            'error': 'AI remediation not available. Set SAMBANOVA_API_KEY environment variable.'
        }), 503

    try:
        print(f"[AI] ========== AI ANALYSIS: {scan_id} ==========")

        # Get scan results
        query = f'SELECT scan_results FROM scans WHERE id = %s'
        result = execute_query(query, (scan_id,), fetch=True)

        if not result:
            return jsonify({'error': 'Scan not found'}), 404

        scan_data = result[0]['scan_results']
        if isinstance(scan_data, str):
            scan_data = json.loads(scan_data)

        if isinstance(scan_data, dict) and 'results' in scan_data:
            issues = scan_data['results']
        else:
            issues = scan_data

        print(f"[AI] Analyzing {sum(len(v) for v in issues.values())} issues with SambaNova AI...")

        # Use AI to analyze issues
        ai_analysis = AI_REMEDIATION_ENGINE.analyze_issues(issues)

        # Get prioritized fixes
        prioritized_fixes = AI_REMEDIATION_ENGINE.prioritize_fixes(issues)

        print(f"[AI] ✓ AI analysis complete")

        return jsonify({
            'success': True,
            'scanId': scan_id,
            'aiAnalysis': ai_analysis,
            'prioritizedFixes': prioritized_fixes,
            'model': AI_REMEDIATION_ENGINE.model
        }), 200

    except Exception as e:
        print(f"[AI] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-generate-alt-text', methods=['POST'])
def ai_generate_alt_text():
    """Generate alt text for an image using SambaNova AI"""
    if not AI_REMEDIATION_AVAILABLE:
        return jsonify({
            'error': 'AI remediation not available. Set SAMBANOVA_API_KEY environment variable.'
        }), 503

    try:
        data = request.get_json()
        image_context = data.get('imageContext', {})

        print(f"[AI] Generating alt text for image on page {image_context.get('page', 'Unknown')}")

        alt_text = AI_REMEDIATION_ENGINE.generate_alt_text(image_context)

        return jsonify({
            'success': True,
            'altText': alt_text
        }), 200

    except Exception as e:
        print(f"[AI] ERROR generating alt text: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-suggest-structure/<scan_id>', methods=['POST'])
def ai_suggest_structure(scan_id):
    """Get AI suggestions for document structure"""
    if not AI_REMEDIATION_AVAILABLE:
        return jsonify({
            'error': 'AI remediation not available. Set SAMBANOVA_API_KEY environment variable.'
        }), 503

    try:
        data = request.get_json()
        content_analysis = data.get('contentAnalysis', {})

        print(f"[AI] Generating structure suggestions for {scan_id}")

        structure_suggestion = AI_REMEDIATION_ENGINE.suggest_document_structure(content_analysis)

        return jsonify({
            'success': True,
            'scanId': scan_id,
            'structureSuggestion': structure_suggestion
        }), 200

    except Exception as e:
        print(f"[AI] ERROR suggesting structure: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-fix-strategy/<scan_id>', methods=['POST'])
def ai_fix_strategy(scan_id):
    """Generate AI fix strategy for specific issue type and category"""
    if not AI_REMEDIATION_AVAILABLE:
        return jsonify({
            'error': 'AI remediation not available. Set SAMBANOVA_API_KEY environment variable.'
        }), 503

    try:
        data = request.get_json()
        issue_type = data.get('issueType', 'general')
        fix_category = data.get('fixCategory', 'automated')
        issues = data.get('issues', [])

        print(f"[AI] Generating {fix_category} fix strategy for {issue_type} issues (count: {len(issues)})")

        strategy = AI_REMEDIATION_ENGINE.generate_fix_strategy(issue_type, issues, fix_category)

        return jsonify({
            'success': True,
            'scanId': scan_id,
            'strategy': strategy
        }), 200

    except Exception as e:
        print(f"[AI] ERROR generating fix strategy: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-manual-guide', methods=['POST'])
def ai_manual_guide():
    """Generate detailed manual fix guide for a specific issue"""
    if not AI_REMEDIATION_AVAILABLE:
        return jsonify({
            'error': 'AI remediation not available. Set SAMBANOVA_API_KEY environment variable.'
        }), 503

    try:
        data = request.get_json()
        issue = data.get('issue', {})

        print(f"[AI] Generating manual fix guide for: {issue.get('description', 'Unknown issue')}")

        guide = AI_REMEDIATION_ENGINE.generate_manual_fix_guide(issue)

        return jsonify({
            'success': True,
            'guide': guide
        }), 200

    except Exception as e:
        print(f"[AI] ERROR generating manual guide: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ai-apply-fixes/<scan_id>', methods=['POST'])
def ai_apply_fixes(scan_id):
    """Use SambaNova AI to directly apply intelligent fixes to the PDF"""
    if not AI_REMEDIATION_AVAILABLE:
        return jsonify({
            'error': 'AI remediation not available. Set SAMBANOVA_API_KEY environment variable.'
        }), 503

    try:
        # Ensure the original PDF file exists
        pdf_path = os.path.join('uploads', scan_id)
        if not os.path.exists(pdf_path):
            # If the original scan ID file doesn't exist, try to find the correct filename from the DB
            query_filename = f'SELECT filename FROM scans WHERE id = %s'
            filename_result = execute_query(query_filename, (scan_id,), fetch=True)
            if filename_result:
                original_filename = filename_result[0]['filename']
                if not original_filename.endswith('.pdf'):
                    original_filename += '.pdf'
                pdf_path = os.path.join('uploads', original_filename)

        if not os.path.exists(pdf_path):
            print(f"[AI Direct Fix] Error: File not found for scan_id {scan_id} at {pdf_path}")
            return jsonify({'error': f'PDF file not found: {scan_id}'}), 404

        print(f"[AI Direct Fix] ========== AI DIRECT FIX: {scan_id} ==========")
        print(f"[AI Direct Fix] Using file: {pdf_path}")

        # Get current scan results to understand issues
        query = f'SELECT scan_results FROM scans WHERE id = %s'
        result = execute_query(query, (scan_id,), fetch=True)

        if not result:
            return jsonify({'error': 'Scan not found'}), 404

        scan_data = result[0]['scan_results']
        if isinstance(scan_data, str):
            scan_data = json.loads(scan_data)

        if isinstance(scan_data, dict) and 'results' in scan_data:
            issues = scan_data['results']
        else:
            issues = scan_data

        print(f"[AI Direct Fix] Applying AI-powered fixes to {sum(len(v) for v in issues.values())} issue categories...")

        # Use AI to apply fixes directly
        fix_result = AI_REMEDIATION_ENGINE.apply_ai_powered_fixes(pdf_path, issues)

        if fix_result.get('success') and fix_result.get('fixedFile'):
            # Construct the path for the fixed file
            fixed_filename = fix_result['fixedFile']
            fixed_path = os.path.join('uploads', fixed_filename)

            # Ensure the fixed file is correctly located
            if fix_result.get('fixed_file_path') and fix_result.get('fixed_file_path') != fixed_path:
                if os.path.exists(fix_result['fixed_file_path']):
                    shutil.copy2(fix_result['fixed_file_path'], fixed_path)
                    print(f"[AI Direct Fix] Copied fixed file from '{fix_result['fixed_file_path']}' to '{fixed_path}'")
                else:
                    print(f"[AI Direct Fix] Warning: AI-generated fixed file not found at '{fix_result['fixed_file_path']}'")
            elif not os.path.exists(fixed_path) and fix_result.get('fixed_file_path') == fixed_path:
                print(f"[AI Direct Fix] Fixed file already at correct path: {fixed_path}")
            else:
                print(f"[AI Direct Fix] Warning: Could not determine or locate the AI fixed file. Expected path: {fixed_path}")
                # If the AI engine modifies in place, use that path
                if os.path.exists(os.path.join('uploads', scan_id)):
                    fixed_path = os.path.join('uploads', scan_id)
                    print(f"[AI Direct Fix] Using original file path as fixed path: {fixed_path}")


            try:
                # Re-scan the fixed PDF to get updated results
                print(f"[AI Direct Fix] Re-scanning AI-fixed file: {fixed_filename} from path: {fixed_path}")

                analyzer = PDFAccessibilityAnalyzer()
                new_results = analyzer.analyze(fixed_path)
                new_summary = analyzer.calculate_summary(new_results)

                print(f"[AI Direct Fix] ✓ Re-scan complete:")
                print(f"[AI Direct Fix]   Total issues: {new_summary.get('totalIssues', 0)}")
                print(f"[AI Direct Fix]   Compliance: {new_summary.get('complianceScore', 0)}%")

                # Update the scan record with new results
                scan_data_updated = {
                    'results': new_results,
                    'summary': new_summary
                }

                print(f"[AI Direct Fix] Updating database with new scan data...")
                update_query = f'''
                    UPDATE scans
                    SET scan_results = %s, status = %s
                    WHERE id = %s
                '''
                execute_query(update_query, (json.dumps(scan_data_updated), 'ai_fixed', scan_id))
                print(f"[AI Direct Fix] ✓ Database updated successfully")

                # Add new results and summary to the response
                fix_result['newResults'] = new_results
                fix_result['newSummary'] = new_summary

                # Save fix history
                insert_query = f'''
                    INSERT INTO fix_history (scan_id, original_file, fixed_file, fixes_applied, success_count)
                    VALUES (%s, %s, %s, %s, %s)
                '''
                # Ensure original filename has .pdf extension
                original_filename = filename_result[0]['filename'] if filename_result else scan_id
                original_filename_with_ext = original_filename if original_filename.endswith('.pdf') else f"{original_filename}.pdf"

                execute_query(insert_query, (
                    scan_id,
                    original_filename_with_ext,
                    fixed_filename,
                    json.dumps(fix_result.get('fixesApplied', [])),
                    fix_result.get('successCount', 0)
                ))
                print(f"[AI Direct Fix] ✓ Fix history saved for {scan_id}")

            except Exception as rescan_error:
                print(f"[AI Direct Fix] ERROR: Failed to re-scan PDF: {rescan_error}")
                import traceback
                traceback.print_exc()
                return jsonify({
                    'error': f'AI fixes applied but failed to re-scan: {str(rescan_error)}'
                }), 500

        return jsonify(fix_result), 200

    except Exception as e:
        print(f"[AI Direct Fix] ERROR: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    try:
        init_db()
        print("[Backend] ✓ Server starting on http://localhost:5000")
        app.run(debug=True, port=5000)
    except Exception as e:
        print(f"[Backend] ✗ Failed to start server: {e}")
        print("[Backend] Check your database configuration:")
        print(f"[Backend]   DATABASE_URL={NEON_NEON_NEON_DATABASE_URL}")
        import traceback
        traceback.print_exc()
