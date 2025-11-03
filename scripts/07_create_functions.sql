-- ============================================
-- FUNCTIONS AND TRIGGERS
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for batches table
DROP TRIGGER IF EXISTS update_batches_updated_at ON public.batches;
CREATE TRIGGER update_batches_updated_at
    BEFORE UPDATE ON public.batches
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for users_sync table
DROP TRIGGER IF EXISTS update_users_sync_updated_at ON neon_auth.users_sync;
CREATE TRIGGER update_users_sync_updated_at
    BEFORE UPDATE ON neon_auth.users_sync
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for notes table
DROP TRIGGER IF EXISTS update_notes_updated_at ON public.notes;
CREATE TRIGGER update_notes_updated_at
    BEFORE UPDATE ON public.notes
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================

-- Function to update batch statistics
CREATE OR REPLACE FUNCTION update_batch_statistics()
RETURNS TRIGGER AS $$
BEGIN
    -- Update batch statistics when a scan is updated
    UPDATE public.batches
    SET 
        total_issues = (
            SELECT COALESCE(SUM(total_issues), 0)
            FROM public.scans
            WHERE batch_id = NEW.batch_id
        ),
        remaining_issues = (
            SELECT COALESCE(SUM(issues_remaining), 0)
            FROM public.scans
            WHERE batch_id = NEW.batch_id
        ),
        fixed_issues = (
            SELECT COALESCE(SUM(issues_fixed), 0)
            FROM public.scans
            WHERE batch_id = NEW.batch_id
        ),
        fixed_count = (
            SELECT COUNT(*)
            FROM public.scans
            WHERE batch_id = NEW.batch_id
            AND status = 'fixed'
        ),
        updated_at = NOW()
    WHERE id = NEW.batch_id;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to update batch statistics when scan changes
DROP TRIGGER IF EXISTS update_batch_stats_on_scan_change ON public.scans;
CREATE TRIGGER update_batch_stats_on_scan_change
    AFTER INSERT OR UPDATE ON public.scans
    FOR EACH ROW
    EXECUTE FUNCTION update_batch_statistics();

-- ============================================

-- Function to update group file count
CREATE OR REPLACE FUNCTION update_group_file_count()
RETURNS TRIGGER AS $$
BEGIN
    -- Update group file count when a scan is added or removed
    IF TG_OP = 'INSERT' THEN
        UPDATE public.groups
        SET file_count = file_count + 1
        WHERE id = NEW.group_id;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE public.groups
        SET file_count = GREATEST(file_count - 1, 0)
        WHERE id = OLD.group_id;
    END IF;
    
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Trigger to update group file count
DROP TRIGGER IF EXISTS update_group_file_count_trigger ON public.scans;
CREATE TRIGGER update_group_file_count_trigger
    AFTER INSERT OR DELETE ON public.scans
    FOR EACH ROW
    EXECUTE FUNCTION update_group_file_count();
