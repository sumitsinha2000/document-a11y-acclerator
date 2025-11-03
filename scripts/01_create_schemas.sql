-- Create schemas
CREATE SCHEMA IF NOT EXISTS neon_auth;
CREATE SCHEMA IF NOT EXISTS public;

-- Set search path
SET search_path TO public, neon_auth;
