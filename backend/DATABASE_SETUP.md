# Database Setup Guide

## PostgreSQL (Neon) Setup

This application requires PostgreSQL. We recommend using Neon for easy cloud PostgreSQL hosting.

### Option 1: Using Neon (Recommended)

1. **Sign up for Neon** at <https://neon.tech>
2. **Create a new project**
3. **Copy your connection string** from the Neon dashboard
4. **Set the NEON_DATABASE_URL environment variable** in your `.env` file:

\`\`\`env
DATABASE_URL=postgresql://user:password@host/database?sslmode=require
\`\`\`

The application will automatically create the required tables on first run.

### Option 2: Local PostgreSQL

If you prefer to run PostgreSQL locally:

#### 1. Install PostgreSQL

**Windows:**
- Download from <https://www.postgresql.org/download/windows/>
- Run the installer and remember your password

**Mac:**
\`\`\`bash
brew install postgresql
brew services start postgresql
\`\`\`

**Linux:**
\`\`\`bash
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
\`\`\`

#### 2. Create Database

\`\`\`bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE accessibility_scans;

# Exit
\q
\`\`\`

#### 3. Install Python Package

\`\`\`bash
pip install psycopg2-binary
\`\`\`

#### 4. Configure Environment Variables

Create a `.env` file in the `backend` directory:

\`\`\`env
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/accessibility_scans
\`\`\`

Replace `yourpassword` with your PostgreSQL password.

#### 5. Start the Server

\`\`\`bash
python app.py
\`\`\`

The application will automatically create the required tables on first run.

## Database Schema

The application creates three tables:

### scans
- `id` (TEXT, PRIMARY KEY) - Unique scan identifier
- `filename` (TEXT) - Original filename
- `upload_date` (TIMESTAMP) - When the scan was uploaded
- `scan_results` (JSONB) - Scan results and summary
- `status` (TEXT) - Scan status (completed, fixed, etc.)
- `batch_id` (TEXT) - Associated batch ID (if part of batch)

### fix_history
- `id` (SERIAL, PRIMARY KEY) - Auto-incrementing ID
- `scan_id` (TEXT) - Reference to scans table
- `original_file` (TEXT) - Original filename
- `fixed_file` (TEXT) - Fixed filename
- `fixes_applied` (JSONB) - Array of applied fixes
- `success_count` (INTEGER) - Number of successful fixes
- `timestamp` (TIMESTAMP) - When fixes were applied

### batches
- `id` (TEXT, PRIMARY KEY) - Unique batch identifier
- `name` (TEXT) - Batch name
- `upload_date` (TIMESTAMP) - When batch was created
- `file_count` (INTEGER) - Number of files in batch
- `status` (TEXT) - Batch status
- `total_issues` (INTEGER) - Total issues across all files
- `fixed_count` (INTEGER) - Number of files with fixes applied

## Troubleshooting

### "DATABASE_URL environment variable not set" Error

Make sure you have set the DATABASE_URL in your `.env` file:

\`\`\`env
DATABASE_URL=postgresql://user:password@host/database
\`\`\`

### "no password supplied" Error

This means DATABASE_URL is missing the password. Update your `.env` file:

\`\`\`env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD_HERE@localhost:5432/accessibility_scans
\`\`\`

### "psycopg2 not installed" Error

Install the PostgreSQL driver:

\`\`\`bash
pip install psycopg2-binary
\`\`\`

### Connection Refused

Make sure PostgreSQL is running:

**Windows:** Check Services app for "postgresql" service  
**Mac:** `brew services list`  
**Linux:** `sudo systemctl status postgresql`

### Database Schema Mismatch

If you see errors about missing columns or tables, the database schema may be outdated. The application will automatically create missing tables, but if you have existing tables with different columns, you may need to:

1. **Backup your data** (if any)
2. **Drop the existing tables:**
   \`\`\`sql
   DROP TABLE IF EXISTS fix_history CASCADE;
   DROP TABLE IF EXISTS scans CASCADE;
   DROP TABLE IF EXISTS batches CASCADE;
   \`\`\`
3. **Restart the application** - it will recreate the tables with the correct schema

## Environment Variables

Required environment variables in `.env`:

\`\`\`env
# Database connection (REQUIRED)
DATABASE_URL=postgresql://user:password@host/database

# Optional: SambaNova AI for intelligent remediation
SAMBANOVA_API_KEY=your_api_key_here
\`\`\`
