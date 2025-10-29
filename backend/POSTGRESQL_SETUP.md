# PostgreSQL Setup Guide

## Installation

### macOS

```bash
brew install postgresql@15
brew services start postgresql@15
```

### Ubuntu/Debian

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
```

### Windows

Download and install from: <https://www.postgresql.org/download/windows/>

## Database Setup

1. Create the database:

    ```bash
    createdb accessibility_scans
    ```

    Or using psql:

    ```bash
    psql postgres
    CREATE DATABASE accessibility_scans;
    \q
    ```

2. Set the DATABASE_URL environment variable:

    ```bash
    export DATABASE_URL="postgresql://localhost/accessibility_scans"
    ```

    Or for a remote database:

    ```bash
    export DATABASE_URL="postgresql://username:password@host:port/database"
    ```

3. Install Python dependencies:

    ```bash
    pip install -r requirements.txt
    ```

4. Run the backend:

    ```bash
    python app.py
    ```

The database tables will be created automatically on first run.

## Database Schema

The application creates three tables:

### scans

- id (TEXT PRIMARY KEY)
- filename (TEXT)
- upload_date (TIMESTAMP)
- scan_results (JSONB)
- status (TEXT)
- batch_id (TEXT)

### fix_history

- id (SERIAL PRIMARY KEY)
- scan_id (TEXT)
- original_file (TEXT)
- fixed_file (TEXT)
- fixes_applied (JSONB)
- success_count (INTEGER)
- timestamp (TIMESTAMP)

### batches

- id (TEXT PRIMARY KEY)
- name (TEXT)
- upload_date (TIMESTAMP)
- file_count (INTEGER)
- status (TEXT)
- total_issues (INTEGER)
- fixed_count (INTEGER)

## Troubleshooting

### Connection Issues

If you get connection errors, check:

1. PostgreSQL is running: `pg_isready`
2. DATABASE_URL is set correctly
3. Database exists: `psql -l`

### Permission Issues

Grant permissions if needed:

```sql
GRANT ALL PRIVILEGES ON DATABASE accessibility_scans TO your_username;
