-- ============================================
-- PUBLIC SCHEMA - CORE TABLES
-- ============================================

-- Groups table
CREATE TABLE IF NOT EXISTS public.groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    file_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Create indexes for groups
CREATE INDEX IF NOT EXISTS idx_groups_name ON public.groups(name);
CREATE INDEX IF NOT EXISTS idx_groups_created_at ON public.groups(created_at);

-- Add comments
COMMENT ON TABLE public.groups IS 'Organizational groups for managing documents';
COMMENT ON COLUMN public.groups.id IS 'Primary key - group identifier';
COMMENT ON COLUMN public.groups.name IS 'Group name';
COMMENT ON COLUMN public.groups.description IS 'Group description';
COMMENT ON COLUMN public.groups.file_count IS 'Number of files in this group';

-- ============================================

-- Batches table
CREATE TABLE IF NOT EXISTS public.batches (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    group_id TEXT REFERENCES public.groups(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'pending',
    file_count INTEGER DEFAULT 0,
    total_files INTEGER DEFAULT 0,
    unprocessed_files INTEGER DEFAULT 0,
    fixed_count INTEGER DEFAULT 0,
    total_issues INTEGER DEFAULT 0,
    remaining_issues INTEGER DEFAULT 0,
    fixed_issues INTEGER DEFAULT 0,
    upload_date TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Create indexes for batches
CREATE INDEX IF NOT EXISTS idx_batches_group_id ON public.batches(group_id);
CREATE INDEX IF NOT EXISTS idx_batches_status ON public.batches(status);
CREATE INDEX IF NOT EXISTS idx_batches_upload_date ON public.batches(upload_date);
CREATE INDEX IF NOT EXISTS idx_batches_created_at ON public.batches(created_at);

-- Add comments
COMMENT ON TABLE public.batches IS 'Batch upload tracking and statistics';
COMMENT ON COLUMN public.batches.id IS 'Primary key - batch identifier';
COMMENT ON COLUMN public.batches.name IS 'Batch name';
COMMENT ON COLUMN public.batches.group_id IS 'Foreign key to groups table';
COMMENT ON COLUMN public.batches.status IS 'Batch status: pending, processing, completed, failed';
COMMENT ON COLUMN public.batches.file_count IS 'Number of files in batch';
COMMENT ON COLUMN public.batches.total_files IS 'Total files count';
COMMENT ON COLUMN public.batches.unprocessed_files IS 'Unprocessed files count';
COMMENT ON COLUMN public.batches.fixed_count IS 'Fixed files count';
COMMENT ON COLUMN public.batches.total_issues IS 'Total issues found across all files';
COMMENT ON COLUMN public.batches.remaining_issues IS 'Issues remaining to be fixed';
COMMENT ON COLUMN public.batches.fixed_issues IS 'Issues that have been fixed';

-- ============================================

-- Scans table (initial scan data - immutable)
CREATE TABLE IF NOT EXISTS public.scans (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    batch_id TEXT REFERENCES public.batches(id) ON DELETE CASCADE,
    group_id TEXT REFERENCES public.groups(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'pending',
    scan_results JSONB,
    total_issues INTEGER DEFAULT 0,
    issues_remaining INTEGER DEFAULT 0,
    issues_fixed INTEGER DEFAULT 0,
    upload_date TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

-- Create indexes for scans
CREATE INDEX IF NOT EXISTS idx_scans_batch_id ON public.scans(batch_id);
CREATE INDEX IF NOT EXISTS idx_scans_group_id ON public.scans(group_id);
CREATE INDEX IF NOT EXISTS idx_scans_status ON public.scans(status);
CREATE INDEX IF NOT EXISTS idx_scans_filename ON public.scans(filename);
CREATE INDEX IF NOT EXISTS idx_scans_upload_date ON public.scans(upload_date);
CREATE INDEX IF NOT EXISTS idx_scans_created_at ON public.scans(created_at);
CREATE INDEX IF NOT EXISTS idx_scans_scan_results ON public.scans USING GIN(scan_results);

-- Add comments
COMMENT ON TABLE public.scans IS 'Individual document scan records (initial scan data - immutable)';
COMMENT ON COLUMN public.scans.id IS 'Primary key - scan identifier';
COMMENT ON COLUMN public.scans.filename IS 'Original filename';
COMMENT ON COLUMN public.scans.batch_id IS 'Foreign key to batches table';
COMMENT ON COLUMN public.scans.group_id IS 'Foreign key to groups table';
COMMENT ON COLUMN public.scans.status IS 'Scan status: pending, processing, completed, failed, fixed';
COMMENT ON COLUMN public.scans.scan_results IS 'Initial scan results (issues found) - JSONB format';
COMMENT ON COLUMN public.scans.total_issues IS 'Total issues found in initial scan';
COMMENT ON COLUMN public.scans.issues_remaining IS 'Issues remaining to be fixed';
COMMENT ON COLUMN public.scans.issues_fixed IS 'Issues that have been fixed';
