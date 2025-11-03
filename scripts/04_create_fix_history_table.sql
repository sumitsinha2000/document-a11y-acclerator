-- ============================================
-- FIX HISTORY TABLE
-- ============================================

-- Fix history table (complete history of all fix operations)
CREATE TABLE IF NOT EXISTS public.fix_history (
    id SERIAL PRIMARY KEY,
    scan_id TEXT NOT NULL REFERENCES public.scans(id) ON DELETE CASCADE,
    batch_id TEXT REFERENCES public.batches(id) ON DELETE CASCADE,
    group_id TEXT REFERENCES public.groups(id) ON DELETE CASCADE,
    original_file TEXT NOT NULL,
    fixed_file TEXT NOT NULL,
    original_filename TEXT,
    fixed_filename TEXT,
    fix_type VARCHAR(50) DEFAULT 'automated',
    fixes_applied JSONB DEFAULT '[]'::jsonb,
    fix_suggestions JSONB,
    issues_before JSONB,
    issues_after JSONB,
    total_issues_before INTEGER DEFAULT 0,
    total_issues_after INTEGER DEFAULT 0,
    high_severity_before INTEGER DEFAULT 0,
    high_severity_after INTEGER DEFAULT 0,
    compliance_before INTEGER DEFAULT 0,
    compliance_after INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    fix_metadata JSONB DEFAULT '{}'::jsonb,
    applied_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    timestamp TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Create indexes for fix_history
CREATE INDEX IF NOT EXISTS idx_fix_history_scan_id ON public.fix_history(scan_id);
CREATE INDEX IF NOT EXISTS idx_fix_history_batch_id ON public.fix_history(batch_id);
CREATE INDEX IF NOT EXISTS idx_fix_history_group_id ON public.fix_history(group_id);
CREATE INDEX IF NOT EXISTS idx_fix_history_fix_type ON public.fix_history(fix_type);
CREATE INDEX IF NOT EXISTS idx_fix_history_applied_at ON public.fix_history(applied_at);
CREATE INDEX IF NOT EXISTS idx_fix_history_timestamp ON public.fix_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_fix_history_fixes_applied ON public.fix_history USING GIN(fixes_applied);
CREATE INDEX IF NOT EXISTS idx_fix_history_issues_before ON public.fix_history USING GIN(issues_before);
CREATE INDEX IF NOT EXISTS idx_fix_history_issues_after ON public.fix_history USING GIN(issues_after);
CREATE INDEX IF NOT EXISTS idx_fix_history_fix_metadata ON public.fix_history USING GIN(fix_metadata);

-- Add comments
COMMENT ON TABLE public.fix_history IS 'Complete history of all fix operations applied to documents';
COMMENT ON COLUMN public.fix_history.id IS 'Primary key - auto-incrementing fix history ID';
COMMENT ON COLUMN public.fix_history.scan_id IS 'Foreign key to scans table';
COMMENT ON COLUMN public.fix_history.batch_id IS 'Foreign key to batches table';
COMMENT ON COLUMN public.fix_history.group_id IS 'Foreign key to groups table';
COMMENT ON COLUMN public.fix_history.original_file IS 'Original filename (required)';
COMMENT ON COLUMN public.fix_history.fixed_file IS 'Fixed filename (required)';
COMMENT ON COLUMN public.fix_history.fix_type IS 'Type of fix: automated, semi-automated, ai';
COMMENT ON COLUMN public.fix_history.fixes_applied IS 'Array of fixes applied - JSONB format';
COMMENT ON COLUMN public.fix_history.fix_suggestions IS 'Fix suggestions - JSONB format';
COMMENT ON COLUMN public.fix_history.issues_before IS 'Issues before fix - JSONB format';
COMMENT ON COLUMN public.fix_history.issues_after IS 'Issues after fix - JSONB format';
COMMENT ON COLUMN public.fix_history.total_issues_before IS 'Total issues before fix';
COMMENT ON COLUMN public.fix_history.total_issues_after IS 'Total issues after fix';
COMMENT ON COLUMN public.fix_history.high_severity_before IS 'High severity issues before fix';
COMMENT ON COLUMN public.fix_history.high_severity_after IS 'High severity issues after fix';
COMMENT ON COLUMN public.fix_history.compliance_before IS 'Compliance score before fix (0-100)';
COMMENT ON COLUMN public.fix_history.compliance_after IS 'Compliance score after fix (0-100)';
COMMENT ON COLUMN public.fix_history.success_count IS 'Number of successful fixes';
COMMENT ON COLUMN public.fix_history.fix_metadata IS 'Additional metadata - JSONB format';
COMMENT ON COLUMN public.fix_history.applied_at IS 'Timestamp when fix was applied';
