# Installation Troubleshooting Guide

## Common Installation Issues

### Issue 1: Build Error with Pillow (KeyError: '__version__')

**Error Message:**
\`\`\`
Getting requirements to build wheel did not run successfully
KeyError: '__version__'
\`\`\`

**Cause:** Outdated build tools (pip, setuptools, wheel) causing compatibility issues when building packages from source.

**Solution:**

Before installing requirements, update your build tools:

\`\`\`bash
# Update pip, setuptools, and wheel
python -m pip install --upgrade pip setuptools wheel

# Then install requirements
pip install -r requirements.txt
\`\`\`

### Issue 2: psycopg2-binary Installation Fails

**Error Message:**
\`\`\`
error: Microsoft Visual C++ 14.0 or greater is required
\`\`\`

**Solution (Windows):**

Option 1: Use the binary package (already in requirements.txt):
\`\`\`bash
pip install psycopg2-binary
\`\`\`

Option 2: If you still have issues, install PostgreSQL development libraries or use SQLite instead by setting in `.env`:
\`\`\`
USE_SQLITE=true
\`\`\`

### Issue 3: pytesseract or pdf2image Issues

**Error Message:**
\`\`\`
TesseractNotFoundError: tesseract is not installed
\`\`\`

**Solution:**

These packages require external binaries:

**Windows:**
1. Download Tesseract from: https://github.com/UB-Mannheim/tesseract/wiki
2. Install and add to PATH
3. Download Poppler from: https://github.com/oschwartz10612/poppler-windows/releases
4. Extract and add `bin` folder to PATH

**macOS:**
\`\`\`bash
brew install tesseract poppler
\`\`\`

**Linux:**
\`\`\`bash
sudo apt-get install tesseract-ocr poppler-utils
\`\`\`

### Issue 4: Permission Errors (Linux/macOS)

**Error Message:**
\`\`\`
PermissionError: [Errno 13] Permission denied
\`\`\`

**Solution:**

Don't use `sudo` with pip. Instead, use a virtual environment:

\`\`\`bash
# Create virtual environment
python -m venv venv

# Activate it
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install requirements
pip install -r requirements.txt
\`\`\`

## Complete Fresh Installation Steps

### Windows

\`\`\`bash
# 1. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# 2. Update build tools
python -m pip install --upgrade pip setuptools wheel

# 3. Install requirements
pip install -r requirements.txt

# 4. Set up environment variables
copy .env.example .env
# Edit .env with your database credentials

# 5. Run the application
python app.py
\`\`\`

### macOS/Linux

\`\`\`bash
# 1. Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# 2. Update build tools
python -m pip install --upgrade pip setuptools wheel

# 3. Install requirements
pip install -r requirements.txt

# 4. Set up environment variables
cp .env.example .env
# Edit .env with your database credentials

# 5. Run the application
python app.py
\`\`\`

## Verifying Installation

After installation, verify everything is working:

\`\`\`bash
# Check Python version (should be 3.8+)
python --version

# Check installed packages
pip list

# Test imports
python -c "import flask, PyPDF2, pdfplumber, pikepdf; print('All core packages imported successfully')"
\`\`\`

## Database Setup

### PostgreSQL (Recommended)

1. Install PostgreSQL from https://www.postgresql.org/download/
2. Create a database:
\`\`\`sql
CREATE DATABASE doc_a11y_db;
\`\`\`
3. Update `.env` with your credentials:
\`\`\`
DB_HOST=localhost
DB_PORT=5432
DB_NAME=doc_a11y_db
DB_USER=your_username
DB_PASSWORD=your_password
\`\`\`

### SQLite (Fallback)

If you don't want to set up PostgreSQL, use SQLite:

1. Update `.env`:
\`\`\`
USE_SQLITE=true
\`\`\`

The application will automatically create a SQLite database file.

## Getting Help

If you continue to experience issues:

1. Check the error message carefully
2. Ensure you're using Python 3.8 or higher
3. Make sure you're in a virtual environment
4. Try updating all build tools first
5. Check that external dependencies (Tesseract, Poppler) are installed if needed
6. Review the main README.md for additional setup instructions

## Environment-Specific Notes

### Conda Users

If you're using Conda instead of venv:

\`\`\`bash
# Create conda environment
conda create -n doc-a11y python=3.10
conda activate doc-a11y

# Update build tools
pip install --upgrade pip setuptools wheel

# Install requirements
pip install -r requirements.txt
\`\`\`

### Docker Users

If you prefer Docker, create a `Dockerfile`:

\`\`\`dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    poppler-utils \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Copy application
COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
\`\`\`

Build and run:
\`\`\`bash
docker build -t doc-a11y-accelerator .
docker run -p 5000:5000 doc-a11y-accelerator
