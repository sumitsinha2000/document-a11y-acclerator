# Database Setup Scripts

Complete PostgreSQL database schema creation scripts for the Document A11y Accelerator application.

## 📋 Overview

These scripts create a complete database schema with:

- 8 tables across 2 schemas (public, neon_auth)
- Foreign key relationships
- Indexes for performance optimization
- Row Level Security (RLS) policies
- Triggers for automatic updates
- Views for data aggregation
- Sample seed data (optional)

## PDF Parser Note

The backend scanning pipeline has completed its migration from `PyPDF2` to `pypdf`, so any supplemental tooling or scripts referencing PDF metadata should assume the modern `pypdf` APIs used across the codebase.

## 🚀 Quick Start

### Option 1: Run All Scripts in Order

```bash
# Navigate to scripts directory
cd scripts

# Run all scripts in order
psql -U your_username -d your_database -f 01_create_schemas.sql
psql -U your_username -d your_database -f 02_create_auth_tables.sql
psql -U your_username -d your_database -f 03_create_core_tables.sql
psql -U your_username -d your_database -f 04_create_fix_history_table.sql
psql -U your_username -d your_database -f 05_create_notes_tables.sql
psql -U your_username -d your_database -f 06_create_views.sql
psql -U your_username -d your_database -f 07_create_functions.sql
psql -U your_username -d your_database -f 08_seed_data.sql
psql -U your_username -d your_database -f 09_grants_and_permissions.sql
psql -U your_username -d your_database -f 10_verify_schema.sql
```

### Option 2: Run All Scripts at Once

```bash
# Create a master script
cat 01_*.sql 02_*.sql 03_*.sql 04_*.sql 05_*.sql 06_*.sql 07_*.sql 08_*.sql 09_*.sql > complete_setup.sql

# Run the master script
psql -U your_username -d your_database -f complete_setup.sql

# Verify the setup
psql -U your_username -d your_database -f 10_verify_schema.sql
```

### Option 3: Using Docker

```bash
# Start PostgreSQL container
docker run --name doc-a11y-db \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=doc_a11y_accelerator \
  -p 5432:5432 \
  -d postgres:15

# Wait for PostgreSQL to start
sleep 5

# Run all scripts
for script in scripts/*.sql; do
  docker exec -i doc-a11y-db psql -U postgres -d doc_a11y_accelerator < "$script"
done
```

## 📁 Script Descriptions

### 01_create_schemas.sql

Creates the `public` and `neon_auth` schemas.

### 02_create_auth_tables.sql

Creates the `users_sync` table in the `neon_auth` schema for user authentication.

### 03_create_core_tables.sql

Creates core tables:

- `groups` - Organizational groups
- `batches` - Batch upload tracking
- `scans` - Individual document scans (immutable initial data)

### 04_create_fix_history_table.sql

Creates the `fix_history` table that stores all fix operations applied to documents.

### 05_create_notes_tables.sql

Creates notes-related tables with Row Level Security:

- `notes` - User notes
- `paragraphs` - Note paragraphs

### 06_create_views.sql

Creates the `scan_current_state` view that combines initial scan data with latest fixes.

### 07_create_functions.sql

Creates functions and triggers:

- `update_updated_at_column()` - Auto-update timestamps
- `update_batch_statistics()` - Auto-update batch stats
- `update_group_file_count()` - Auto-update group file counts

### 08_seed_data.sql

Optional seed data for testing purposes.

### 09_grants_and_permissions.sql

Sets up database permissions and grants.

### 10_verify_schema.sql

Verification queries to check the database setup.

## 🔑 Key Features

### Foreign Key Relationships

```markdown
groups (1) ──→ (many) batches
groups (1) ──→ (many) scans
batches (1) ──→ (many) scans
scans (1) ──→ (many) fix_history
notes (1) ──→ (many) paragraphs
```

### Automatic Updates

- Timestamps auto-update on record changes
- Batch statistics auto-calculate from scan data
- Group file counts auto-update when scans are added/removed

### Row Level Security (RLS)

- Users can only access their own notes
- Shared notes are accessible to all users
- Policies enforce data isolation

### Performance Optimization

- Indexes on foreign keys
- Indexes on frequently queried columns
- GIN indexes on JSONB columns for fast JSON queries

## 🔍 Verification

After running all scripts, verify the setup:

```sql
-- Check all tables
SELECT schemaname, tablename 
FROM pg_tables 
WHERE schemaname IN ('public', 'neon_auth')
ORDER BY schemaname, tablename;

-- Check all indexes
SELECT schemaname, tablename, indexname 
FROM pg_indexes 
WHERE schemaname IN ('public', 'neon_auth')
ORDER BY schemaname, tablename;

-- Check RLS policies
SELECT schemaname, tablename, policyname 
FROM pg_policies 
WHERE schemaname IN ('public', 'neon_auth')
ORDER BY schemaname, tablename;
```

## 🔧 Configuration

### Environment Variables

Update your `.env` file with the database connection string:

```env
NEON_DATABASE_URL=postgresql://username:password@localhost:5432/doc_a11y_accelerator
NEON_DATABASE_URL=postgresql://username:password@localhost:5432/doc_a11y_accelerator
```

### Connection String Format

```markdown
postgresql://[user]:[password]@[host]:[port]/[database]
```

## 🛠️ Troubleshooting

### Issue: Permission Denied

```bash
# Grant superuser privileges
psql -U postgres -c "ALTER USER your_username WITH SUPERUSER;"
```

### Issue: Database Already Exists

```bash
# Drop and recreate database
psql -U postgres -c "DROP DATABASE IF EXISTS doc_a11y_accelerator;"
psql -U postgres -c "CREATE DATABASE doc_a11y_accelerator;"
```

### Issue: Extension Not Found

```bash
# Install PostgreSQL contrib package
# Ubuntu/Debian
sudo apt-get install postgresql-contrib

# macOS
brew install postgresql
```

## 📊 Data Architecture

### Initial Scan Flow

1. Document uploaded → `groups` table
2. Batch created → `batches` table
3. Document scanned → `scans` table (immutable initial data)

### Fix Application Flow

1. Fixes applied → `fix_history` table (new record for each fix)
2. View updated → `scan_current_state` view (auto-updates)
3. Batch stats updated → `batches` table (via trigger)

### Current State Access

- Always read from `scan_current_state` view
- View combines initial scan + latest fix data
- Provides real-time current state without modifying original data

## 📝 Notes

- All timestamps use `TIMESTAMP WITHOUT TIME ZONE` for consistency
- JSONB columns use GIN indexes for fast queries
- Foreign keys use `ON DELETE CASCADE` for automatic cleanup
- RLS policies require setting `app.current_user_id` session variable

## 🔐 Security Considerations

1. **Row Level Security**: Enabled on notes and paragraphs tables
2. **Foreign Key Constraints**: Prevent orphaned records
3. **Soft Deletes**: `users_sync` table supports soft deletes
4. **Audit Trail**: `fix_history` maintains complete fix history

## 📚 Additional Resources

- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Row Level Security Guide](https://www.postgresql.org/docs/current/ddl-rowsecurity.html)
- [JSONB Indexing](https://www.postgresql.org/docs/current/datatype-json.html)
