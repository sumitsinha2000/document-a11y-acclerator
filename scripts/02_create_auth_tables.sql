-- ============================================
-- NEON_AUTH SCHEMA TABLES
-- ============================================

-- Users sync table for authentication
CREATE TABLE IF NOT EXISTS neon_auth.users_sync (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    raw_json JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for users_sync
CREATE INDEX IF NOT EXISTS idx_users_sync_email ON neon_auth.users_sync(email);
CREATE INDEX IF NOT EXISTS idx_users_sync_created_at ON neon_auth.users_sync(created_at);
CREATE INDEX IF NOT EXISTS idx_users_sync_deleted_at ON neon_auth.users_sync(deleted_at) WHERE deleted_at IS NOT NULL;

-- Add comments
COMMENT ON TABLE neon_auth.users_sync IS 'User authentication and profile data';
COMMENT ON COLUMN neon_auth.users_sync.id IS 'Primary key - user identifier';
COMMENT ON COLUMN neon_auth.users_sync.email IS 'User email address';
COMMENT ON COLUMN neon_auth.users_sync.name IS 'User display name';
COMMENT ON COLUMN neon_auth.users_sync.raw_json IS 'Raw user data from authentication provider';
COMMENT ON COLUMN neon_auth.users_sync.deleted_at IS 'Soft delete timestamp';
