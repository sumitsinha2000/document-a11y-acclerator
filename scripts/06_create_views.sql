-- ============================================
-- VIEWS
-- ============================================

-- Scan current state view
-- Combines initial scan data with latest fix history
CREATE OR REPLACE VIEW public.scan_current_state AS
SELECT 
    s.id AS scan_id,
    s.batch_id,
    s.group_id,
    s.filename,
    COALESCE(fh_latest.fixed_file, s.filename) AS fixed_filename,
    s.status,
    CASE 
        WHEN fh_latest.id IS NOT NULL THEN 'fixed'
        ELSE s.status
    END AS current_status,
    s.scan_results AS initial_scan_results,
    COALESCE(
        (
            SELECT jsonb_agg(fixes_applied ORDER BY applied_at)
            FROM public.fix_history
            WHERE fix_history.scan_id = s.id
        ),
        '[]'::jsonb
    ) AS fixes_applied,
    s.total_issues AS initial_total_issues,
    COALESCE(fh_latest.total_issues_after, s.total_issues) AS current_total_issues,
    COALESCE(fh_latest.high_severity_after, 0) AS current_high_severity,
    COALESCE(fh_latest.compliance_after, 0) AS current_compliance,
    fh_latest.id AS latest_fix_id,
    fh_latest.fix_type AS last_fix_type,
    fh_latest.applied_at AS last_fix_applied_at,
    s.upload_date,
    s.created_at
FROM 
    public.scans s
LEFT JOIN LATERAL (
    SELECT *
    FROM public.fix_history
    WHERE fix_history.scan_id = s.id
    ORDER BY applied_at DESC
    LIMIT 1
) fh_latest ON TRUE;

-- Add comment
COMMENT ON VIEW public.scan_current_state IS 'Current state view combining initial scans with latest fixes';
