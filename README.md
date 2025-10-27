# Document A11y Accelerator

An automated PDF accessibility scanning and remediation tool.

## Features

- Scan PDFs for accessibility issues
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

4. Start the backend server:
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

## Technology Stack

- **Frontend**: React, Vite, Tailwind CSS
- **Backend**: Python, Flask, PostgreSQL/SQLite
- **PDF Processing**: PyPDF2, pikepdf, pdf-extract-kit
