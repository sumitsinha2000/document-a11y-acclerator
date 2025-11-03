-- ============================================
-- SEED DATA (Optional - for testing)
-- ============================================

-- Insert sample group
INSERT INTO public.groups (id, name, description, file_count, created_at)
VALUES 
    ('group_sample_001', 'Sample Group', 'A sample group for testing', 0, NOW())
ON CONFLICT (id) DO NOTHING;

-- Insert sample batch
INSERT INTO public.batches (
    id, name, group_id, status, file_count, total_files, 
    unprocessed_files, fixed_count, total_issues, remaining_issues, 
    fixed_issues, upload_date, created_at, updated_at
)
VALUES (
    'batch_sample_001', 'Sample Batch', 'group_sample_001', 'pending', 
    0, 0, 0, 0, 0, 0, 0, NOW(), NOW(), NOW()
)
ON CONFLICT (id) DO NOTHING;

-- Add comment
COMMENT ON SCRIPT IS 'Optional seed data for testing purposes';
