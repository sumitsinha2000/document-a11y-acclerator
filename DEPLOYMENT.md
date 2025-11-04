# Deployment Guide

## Deploying to Vercel

This application consists of three parts:
1. Next.js app (this repository)
2. React + Vite frontend (`/frontend` directory)
3. Flask backend (`/backend` directory)

### Option 1: All-in-One Vercel Deployment

#### Step 1: Deploy the Backend

The Flask backend can be deployed as a Vercel serverless function:

1. Create a new Vercel project for the backend
2. Set the root directory to `backend`
3. Add a `vercel.json` in the backend directory:

\`\`\`json
{
  "builds": [
    {
      "src": "app.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "app.py"
    }
  ]
}
\`\`\`

4. Deploy and note the URL (e.g., `https://your-backend.vercel.app`)

#### Step 2: Configure Environment Variables

In your Vercel project settings, add:

\`\`\`
NEXT_PUBLIC_BACKEND_URL=https://your-backend.vercel.app
NEON_NEON_DATABASE_URL=your-neon-connection-string
\`\`\`

#### Step 3: Deploy the Next.js App

\`\`\`bash
vercel --prod
\`\`\`

### Option 2: Separate Deployments

#### Backend Deployment (Railway/Render)

1. Deploy Flask backend to Railway or Render
2. Note the backend URL

#### Frontend Deployment (Vercel)

1. Deploy this Next.js app to Vercel
2. Set environment variables:
   - `NEXT_PUBLIC_BACKEND_URL`: Your backend URL
   - `NEON_DATABASE_URL`: Your database connection string

### Development vs Production

- **Development**: The Next.js app proxies requests to `localhost:3000` (frontend) and `localhost:5000` (backend)
- **Production**: The Next.js app shows deployment instructions and requires proper backend URL configuration

### CORS Configuration

Make sure your Flask backend has CORS enabled:

\`\`\`python
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["https://document-a11y-acclerator.vercel.app"])
\`\`\`

### Testing Production Build Locally

\`\`\`bash
npm run build
npm start
\`\`\`

Then visit `http://localhost:3000` to see the production version.
