# Project Structure Explanation

## Overview

This repository contains a **React + Vite frontend** application with a **Python Flask backend**. The frontend is the main application that users interact with.

## Directory Structure

### `frontend/` - Main Application ⭐
This is the **primary application** that runs in production.

- **Technology**: React 18 + Vite
- **Port**: 3000 (development)
- **Deployment**: Vercel (configured via `vercel.json`)
- **Entry Point**: `frontend/src/main.jsx`
- **Main Component**: `frontend/src/App.jsx`

**Key Features**:
- Professional loading screen with progress bar
- Feature showcase slideshow
- Main upload interface
- Batch processing
- History and reports
- Dark mode support

### `backend/` - API Server
The Flask backend that handles PDF processing and database operations.

- **Technology**: Python Flask
- **Port**: 5000 (development)
- **Deployment**: Separate deployment (Vercel/Render/Railway)
- **Entry Point**: `backend/app.py`

### `app/` - Not Used in Production ⚠️
This directory contains a Next.js setup that is **NOT used in production**.

- It was created during development/testing
- The `vercel.json` is configured to deploy the `frontend/` directory instead
- You can safely ignore this directory for production deployments
- It may be used for development tools or documentation pages

### `scripts/` - Database Setup
SQL scripts for setting up the PostgreSQL database schema.

## Deployment Configuration

The `vercel.json` file at the root configures Vercel to:
1. Build from the `frontend/` directory
2. Output to `frontend/dist`
3. Proxy API requests to the backend

\`\`\`json
{
  "buildCommand": "cd frontend && npm install && npm run build",
  "outputDirectory": "frontend/dist",
  ...
}
\`\`\`

## Development Workflow

1. **Start Backend**: `cd backend && python app.py`
2. **Start Frontend**: `cd frontend && npm run dev`
3. **Access App**: `http://localhost:3000`

## Production Workflow

1. **Deploy Frontend**: Push to GitHub → Vercel auto-deploys from `frontend/`
2. **Deploy Backend**: Deploy Flask app separately
3. **Configure**: Set `VITE_BACKEND_URL` in Vercel environment variables

## Why Two Package.json Files?

- **Root `package.json`**: Contains Next.js dependencies (not used in production)
- **`frontend/package.json`**: Contains actual frontend dependencies (used in production)

For production, only the `frontend/package.json` matters.

## Summary

- ✅ **Use**: `frontend/` for the main application
- ✅ **Use**: `backend/` for the API server
- ✅ **Use**: `scripts/` for database setup
- ⚠️ **Ignore**: `app/` directory (Next.js, not used in production)
- ⚠️ **Ignore**: Root `package.json` (Next.js dependencies, not used in production)
