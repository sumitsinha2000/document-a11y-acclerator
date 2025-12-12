# Document A11y Accelerator

Automated PDF accessibility scanning and remediation tool with WCAG 2.1, PDF/UA, and Section 508 compliance validation.

## ✨ User Experience

The application features a **professional loading screen** that:

- Displays a sleek progress bar animation
- Showcases 4 key features with smooth transitions
- Takes approximately 10 seconds to complete
- Automatically transitions to the main upload page

## Features

- 📄 **PDF Scanning**: Automated accessibility issue detection
- 🔧 **Auto-Fix**: Intelligent remediation of common issues
- 📊 **Compliance Reports**: WCAG 2.1, PDF/UA, Section 508 validation
- 🎯 **Project Management**: Organize documents by projects/clients
- 📁 **Folder Processing**: Handle multiple documents simultaneously
- 📈 **Dashboard**: Visual analytics and progress tracking
- 🌙 **Dark Mode**: Full dark mode support
- 📱 **Responsive**: Works on desktop, tablet, and mobile
- ⚡ **React + Vite**: Fast, modern web application

## Tech Stack

- **Frontent**: React 18 + Vite, Axios, Tailwind CSS
- **Backend**: Python FastAPI, PDF Extract Kit
- **Database**: Online PostgreSQL database
- **Deployment**: Vercel
- **PDF Processing**: pypdf (metadata/contrast/annotation), pikepdf, pdfplumber
- **Validation**: Built-in WCAG 2.1 & PDF/UA-1 validator, veraPDF (optional)

The backend and its pytest suites now fully depend on `pypdf` instead of the legacy `PyPDF2` package for metadata, annotation, and structure analysis, completing the migration referenced elsewhere in the repository.

## Quick Start

### Prerequisites

- Node.js 18+ and npm
- Python 3.8+
- PostgreSQL (currently Aiven)

### Installation

1. **Clone the repository**

   ```bash
   git clone <https://github.com/sumitsinha2000/document-a11y-acclerator>
   cd document-a11y-acclerator
   ```

2. **Install frontend dependencies**

   ```bash
   cd frontend
   npm install
   ```

3. **Install backend dependencies**

   ```bash
   cd backend
   pip install -r requirements.txt
   ```

4. **Set up environment variables**

   1. **Frontend**
      - Duplicate `frontend/.example.env` and rename the copy to `.env`,  
        or manually create `frontend/.env` with:

        ```env
        VITE_BACKEND_URL=http://localhost:5000
        ```

   2. **Backend**
      - Duplicate `backend/.example.env` and rename the copy to `.env`.
      - Update any required values inside the file.

5. **Set up the database**

   ```bash
   # Run the SQL scripts in order
   psql -U your_user -d your_database -f scripts/01_create_schemas.sql
   psql -U your_user -d your_database -f scripts/02_create_auth_tables.sql
   # ... continue with remaining scripts
   ```

### Development

Run both frontend and backend:

```bash
# Terminal 1: Backend
cd backend
python app.py

# Terminal 2: Frontend (Main App)
cd frontend
npm run dev
```

Visit <http://localhost:3000> - you'll see the loading screen with feature showcase, then the main upload page.

## Testing

### Backend tests (FastAPI + pytest)

Backend tests live under `backend/tests/` and are run with `pytest`.

From the project root:

```bash
cd backend
pytest -v
```

Notes:

- Tests tagged `slow_pdf` open real PDFs; skip them with `pytest -v -m "not slow_pdf"` if you just want the fast suites.
- The Accessible University regression (`alt_fallback`) is excluded by default via `pytest.ini`. Run it explicitly with `pytest -v -m alt_fallback --override-ini addopts=`.

More details at [backend/tests/README.md](/backend/tests/README.md)

### Snapshot fixtures

Normalized analyzer payloads under `backend/tests/fixtures/expected/` keep the integration suites stable; the full workflow is documented in [backend/tests/fixtures/expected/README.md](backend/tests/fixtures/expected/README.md).

- Refer to the above README to update snapshots

- `python -m backend.tests.utils.dump_expected_snapshots --pdf <fixture>` for a single PDF. Always review the generated diffs before committing changes so regressions stay caught.

## Deployment

See [DEPLOYMENT.md](/documentation/DEPLOYMENT.md) for detailed deployment instructions.

### Quick Deploy to Vercel

1. Deploy backend to your preferred platform (Vercel, Railway, Render)
2. Set `VITE_BACKEND_URL` in Vercel environment variables
3. Update `vercel.json` rewrites with your backend URL
4. Push to main branch or run `vercel --prod`

## Project Structure

```markdown
document-a11y-acclerator/
├── frontend/              # React + Vite main application ⭐
│   ├── src/
│   │   ├── App.jsx       # Main application component
│   │   ├── components/   # React components
│   │   │   ├── LoadingScreen.jsx  # Professional loading screen
│   │   │   ├── UploadArea.jsx     # Main upload interface
│   │   │   └── ...
│   │   ├── contexts/     # React contexts
│   │   └── main.jsx      # Entry point
│   ├── dist/             # Build output
│   ├── package.json      # Frontend dependencies
│   └── vite.config.js    # Vite configuration
├── backend/              # Flask backend
│   ├── app.py           # Main Flask application
│   └── requirements.txt # Python dependencies
├── scripts/             # Database setup scripts
├── app/                 # Next.js (not used in production)
└── vercel.json          # Vercel configuration (deploys frontend/)
```

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

## Usage

1. **Launch**: Professional loading screen showcases key features
2. **Upload PDFs**: Upload single or multiple PDF files for accessibility scanning
3. **View Results**: Review detected accessibility issues organized by severity
4. **Apply Fixes**: Use automated fixes or manual editing tools to remediate issues
5. **Export**: Download fixed PDFs or export results as ZIP files
6. **History**: Access previous scans and batch uploads from the History page
7. **Groups**: Organize documents by projects or clients
8. **Dashboard**: Monitor progress and compliance metrics

## Documentation

- [Deployment Guide](./documentation/DEPLOYMENT.md) - Complete deployment instructions
- [Database Setup](./backend/documentation/DATABASE_SETUP.md) - Database configuration
- [Built-in WCAG Validator Info](./backend/documentation/WCAG_VALIDATOR_INFO.md) - Validation details
- [veraPDF Setup Guide](./backend/documentation/VERAPDF_SETUP.md) - Optional enhanced validation
- [PDF Extract Kit Setup](./backend/documentation/PDF_EXTRACT_KIT_SETUP.md) - Advanced PDF analysis
- [PostgreSQL Setup](./backend/documentation/POSTGRESQL_SETUP.md) - Database configuration
- [Installation Troubleshooting](./backend/documentation/INSTALLATION_TROUBLESHOOTING.md) - Common issues

## Troubleshooting

### Backend Connection Issues

If you see "ERR_CONNECTION_REFUSED" errors:

1. Make sure the backend server is running on port 5000
2. Check that `VITE_BACKEND_URL` is set correctly (use `import.meta.env.VITE_BACKEND_URL` in code)
3. Verify your database configuration

### Database Issues

- **PostgreSQL**: Ensure PostgreSQL is running and credentials are correct
- **Neon**: Verify Neon integration is connected in Vercel

### Installation Issues

See [INSTALLATION_TROUBLESHOOTING.md](./backend/documentation/INSTALLATION_TROUBLESHOOTING.md) for common solutions.

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

## License

[Your License Here]

## Support

For issues and questions:

- Open an issue on GitHub
- Check the documentation in the `/backend` directory
- Review the [DEPLOYMENT.md](/documentation/DEPLOYMENT.md) guide

## Acknowledgments

Built with modern web technologies and accessibility best practices.
