# Database Setup Guide

## Option 1: SQLite (Default - No Setup Required)

The application uses SQLite by default. No configuration needed!

The database file `accessibility_scans.db` will be created automatically when you start the server.

## Option 2: PostgreSQL (Optional)

If you want to use PostgreSQL instead:

### 1. Install PostgreSQL

**Windows:**

- Download from <https://www.postgresql.org/download/windows/>
- Run the installer and remember your password

**Mac:**

```bash
brew install postgresql
brew services start postgresql
```

**Linux:**

```bash
sudo apt-get install postgresql postgresql-contrib
sudo systemctl start postgresql
```

### 2. Create Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE accessibility_scans;

# Exit
\q
```

### 3. Install Python Package

```bash
pip install psycopg2-binary
```

### 4. Configure Environment Variables

Create a `.env` file in the `backend` directory:

```env
DATABASE_TYPE=postgresql
DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/accessibility_scans
```

Replace `yourpassword` with your PostgreSQL password.

### 5. Start the Server

```bash
python app.py
```

## Switching Between Databases

To switch from PostgreSQL back to SQLite:

1. Remove or comment out the DATABASE_TYPE and DATABASE_URL in `.env`
2. Or set `DATABASE_TYPE=sqlite`
3. Restart the server

## Troubleshooting

### "no password supplied" Error

This means DATABASE_URL is missing the password. Update your `.env` file:

```env
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD_HERE@localhost:5432/accessibility_scans
```

### "psycopg2 not installed" Error

Install the PostgreSQL driver:

```bash
pip install psycopg2-binary
```

### Connection Refused

Make sure PostgreSQL is running:

**Windows:** Check Services app for "postgresql" service
**Mac:** `brew services list`
**Linux:** `sudo systemctl status postgresql`
