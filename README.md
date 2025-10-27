# Document A11y Accelerator

An automated PDF accessibility scanning and remediation tool with WCAG 2.1, PDF/UA, and Section 508 compliance validation.

## Features

- Scan PDFs for accessibility issues
- **Built-in WCAG 2.1 and PDF/UA-1 validator** (no external dependencies required)
- **Enhanced validation with veraPDF** (optional)
- Batch processing support
- Automated fix suggestions
- Manual PDF editing capabilities
- PostgreSQL or SQLite database support
- Upload history tracking

## Setup

### Backend Setup

1. Navigate to the backend directory:
\`\`\`bash
cd backend
\`\`\`

2. Install Python dependencies:
\`\`\`bash
pip install -r requirements.txt
\`\`\`

3. (Optional) Configure PostgreSQL:
   - Create a `.env` file in the backend directory
   - Add your database credentials:
   \`\`\`
   DATABASE_TYPE=postgresql
   DATABASE_URL=postgresql://username:password@localhost:5432/database_name
   \`\`\`
   - If not configured, the app will use SQLite by default

4. **(Optional) Install veraPDF for Enhanced Validation**:
   - veraPDF provides industry-standard WCAG 2.1 and PDF/UA compliance checking
   - See [VERAPDF_SETUP.md](backend/VERAPDF_SETUP.md) for installation instructions
   - **Note**: The app includes a built-in WCAG validator and works perfectly without veraPDF

5. **(Optional) Install PDF-Extract-Kit for Advanced Analysis**:
   - See [PDF_EXTRACT_KIT_SETUP.md](backend/PDF_EXTRACT_KIT_SETUP.md) for installation instructions
   - Provides enhanced table detection, form analysis, and document structure analysis

6. Start the backend server:
\`\`\`bash
python app.py
\`\`\`

The backend will run on `http://localhost:5000`

### Frontend Setup

1. Navigate to the frontend directory:
\`\`\`bash
cd frontend
\`\`\`

2. Install dependencies:
\`\`\`bash
npm install
\`\`\`

3. Start the development server:
\`\`\`bash
npm run dev
\`\`\`

The frontend will run on `http://localhost:3000`

## Usage

1. **Upload PDFs**: Upload single or multiple PDF files for accessibility scanning
2. **View Results**: Review detected accessibility issues organized by severity
3. **Apply Fixes**: Use automated fixes or manual editing tools to remediate issues
4. **Export**: Download fixed PDFs or export results as ZIP files
5. **History**: Access previous scans and batch uploads from the History page

## Accessibility Standards

The tool validates PDFs against:

- **WCAG 2.1** (Web Content Accessibility Guidelines) - Level A, AA, and AAA
- **PDF/UA-1** (ISO 14289-1) - PDF Universal Accessibility standard
- **Section 508** - U.S. federal accessibility requirements

### Validation Layers

1. **Built-in WCAG 2.1 & PDF/UA-1 Validator** (Always Active):
   - No external dependencies required
   - Based on veraPDF WCAG algorithms
   - Comprehensive validation of 15+ WCAG criteria
   - PDF/UA-1 structure and tagging validation
   - Detailed issue reports with WCAG criterion references
   - Remediation recommendations for each issue
   - See [WCAG_VALIDATOR_INFO.md](backend/WCAG_VALIDATOR_INFO.md) for details

2. **Core Analysis** (Always Active):
   - Metadata validation
   - Document structure and tagging
   - Image alt text detection
   - Table structure analysis
   - Form field labels
   - Language specification
   - Color contrast checks

3. **Enhanced Analysis** (When PDF-Extract-Kit is installed):
   - Advanced layout analysis
   - Improved table detection
   - Better form field detection
   - Document structure analysis
   - Reading order validation

4. **Standards Validation** (When veraPDF is installed):
   - Official PDF Association validator
   - Most comprehensive WCAG 2.1 compliance checking
   - PDF/UA validation with detailed clause references
   - Section 508 compliance verification
   - Industry-standard validation results

### Which Validator Should I Use?

| Validator | Setup Required | Accuracy | Speed | Recommendation |
|-----------|---------------|----------|-------|----------------|
| **Built-in** | None | Good | Fast | **Recommended for most users** |
| **veraPDF** | Java + veraPDF | Excellent | Slower | Optional for maximum accuracy |

**For most users**: The built-in validator provides comprehensive WCAG 2.1 and PDF/UA-1 validation without any setup. It's fast, reliable, and covers all major accessibility requirements.

**For maximum accuracy**: Install veraPDF CLI for the official PDF Association validator with the most comprehensive validation available.

## Troubleshooting

### Backend Connection Issues

If you see "ERR_CONNECTION_REFUSED" errors:

1. Make sure the backend server is running:
   \`\`\`bash
   cd backend
   python app.py
   \`\`\`

2. Check that the backend is running on port 5000

3. Verify your database configuration (PostgreSQL or SQLite)

### Database Issues

- **PostgreSQL**: Ensure PostgreSQL is running and credentials are correct in `.env`
- **SQLite**: The app will automatically create `accessibility_scans.db` in the backend directory

### Installation Issues

If you encounter errors during `pip install -r requirements.txt`:

1. See [INSTALLATION_TROUBLESHOOTING.md](backend/INSTALLATION_TROUBLESHOOTING.md) for common solutions
2. Most issues are related to Pillow build dependencies
3. Try installing Pillow separately first: `pip install Pillow`

### veraPDF Not Detected

If veraPDF validation is not running (optional):

1. Verify veraPDF is installed: `verapdf --version` or `java -jar /path/to/verapdf.jar --version`
2. Ensure veraPDF is in your system PATH or set `VERAPDF_JAR` environment variable
3. Restart the backend server after installing veraPDF
4. Check backend logs for veraPDF initialization messages
5. **Note**: The app works perfectly without veraPDF using the built-in validator

## Technology Stack

- **Frontend**: React, Vite, Tailwind CSS
- **Backend**: Python, Flask, PostgreSQL/SQLite
- **PDF Processing**: PyPDF2, pikepdf, pdfplumber
- **Built-in Validation**: Custom WCAG 2.1 & PDF/UA-1 validator (based on veraPDF algorithms)
- **Enhanced Analysis**: PDF-Extract-Kit (optional)
- **Standards Validation**: veraPDF (optional)

## Documentation

- [Built-in WCAG Validator Info](backend/WCAG_VALIDATOR_INFO.md) - Comprehensive validation details
- [veraPDF Setup Guide](backend/VERAPDF_SETUP.md) - Optional enhanced validation
- [PDF-Extract-Kit Setup Guide](backend/PDF_EXTRACT_KIT_SETUP.md) - Advanced PDF analysis
- [PostgreSQL Setup Guide](backend/POSTGRESQL_SETUP.md) - Database configuration
- [Installation Troubleshooting](backend/INSTALLATION_TROUBLESHOOTING.md) - Common setup issues
