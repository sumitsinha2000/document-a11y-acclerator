# Deployment Guide for Document A11y Accelerator

## Overview

This application uses **React + Vite** as the main frontend application, deployed directly to Vercel at `https://document-a11y-acclerator.vercel.app/`.

## Architecture

- **Frontend**: React + Vite (main application)
- **Backend**: Flask API (requires separate deployment)
- **Database**: Neon PostgreSQL (already connected via Vercel integration)

## Deployment Steps

### 1. Deploy Backend

Your Flask backend needs to be deployed separately. Choose one of these options:

#### Option A: Deploy to Vercel (Recommended)

1. Create a `vercel.json` in the `backend` directory:

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

2. Deploy the backend:
\`\`\`bash
cd backend
vercel deploy --prod
\`\`\`

3. Note the deployment URL (e.g., `https://your-backend.vercel.app`)

#### Option B: Deploy to Railway

1. Go to [Railway.app](https://railway.app)
2. Create new project from GitHub
3. Select your repository and set root directory to `backend`
4. Railway will auto-detect Flask and deploy
5. Note the deployment URL

#### Option C: Deploy to Render

1. Go to [Render.com](https://render.com)
2. Create new Web Service
3. Connect your GitHub repository
4. Set root directory to `backend`
5. Set build command: `pip install -r requirements.txt`
6. Set start command: `gunicorn app:app`
7. Note the deployment URL

### 2. Configure Environment Variables in Vercel

Go to your Vercel project settings → Environment Variables and add:

\`\`\`env
VITE_BACKEND_URL=https://your-backend-url.vercel.app
\`\`\`

**Important**: Replace `your-backend-url.vercel.app` with your actual deployed backend URL from Step 1.

The Neon database variables are automatically provided by the Vercel integration.

### 3. Update vercel.json

The `vercel.json` is already configured to build the frontend from the `frontend/` directory:

\`\`\`json
{
  "buildCommand": "cd frontend && npm install && npm run build",
  "outputDirectory": "frontend/dist",
  "installCommand": "cd frontend && npm install",
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://your-actual-backend-url.vercel.app/api/:path*"
    }
  ]
}
\`\`\`

Update the `destination` URL with your actual backend URL from Step 1.

### 4. Configure CORS in Backend

Update your Flask backend to allow requests from your Vercel domain:

\`\`\`python
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=[
    "https://document-a11y-acclerator.vercel.app",
    "http://localhost:3000"  # for local development
])
\`\`\`

### 5. Deploy to Vercel

\`\`\`bash
# Deploy to production
vercel --prod

# Or push to your main branch (if auto-deploy is enabled)
git push origin main
\`\`\`

## Local Development

For local development:

\`\`\`bash
# Terminal 1: Start backend
cd backend
python app.py

# Terminal 2: Start frontend
cd frontend
npm run dev
\`\`\`

Visit `http://localhost:3000` to see your app.

## Environment Variables

### Required for Production

- `VITE_BACKEND_URL` - Your deployed backend URL
- Neon database variables (automatically provided by Vercel integration)

### Local Development

Create `frontend/.env.local`:

\`\`\`env
VITE_BACKEND_URL=http://localhost:5000
\`\`\`

## Architecture Details

### Frontend (React + Vite)

The main application is built with:

- React 18
- Vite for fast development and optimized builds
- Axios for API calls
- Recharts for data visualization
- React PDF for document viewing
- Tailwind CSS for styling

### File Structure

\`\`\`
document-a11y-acclerator/
├── frontend/                 # Main React + Vite application
│   ├── src/
│   │   ├── App.jsx          # Main application component
│   │   ├── components/      # React components
│   │   ├── contexts/        # React contexts
│   │   └── main.jsx         # Entry point
│   ├── dist/                # Build output (generated)
│   ├── package.json         # Frontend dependencies
│   └── vite.config.js       # Vite configuration
├── backend/                 # Flask backend (deploy separately)
├── app/                     # Next.js (not used for main app)
└── vercel.json             # Vercel configuration
\`\`\`

## Troubleshooting

### API calls failing in production

1. **Check environment variable**: Verify `VITE_BACKEND_URL` is set correctly in Vercel
2. **Verify CORS**: Ensure CORS is configured in your backend to allow your Vercel domain
3. **Check backend logs**: Review your backend hosting platform logs for errors
4. **Test backend directly**: Try accessing your backend URL directly in a browser

### Build failures

1. **Dependencies**: Ensure all dependencies are in `frontend/package.json`
2. **Build command**: Verify the build command in `vercel.json` is correct
3. **Node version**: Check Node.js version compatibility (18+ recommended)

### Environment variables not working

1. **Prefix**: Ensure variables start with `VITE_` to be exposed to the client
2. **Rebuild**: Redeploy after adding environment variables
3. **Access**: Use `import.meta.env.VITE_BACKEND_URL` in your code

### Database connection issues

1. **Neon integration**: Verify Neon integration is connected in Vercel project settings
2. **Environment variables**: Check that database environment variables are set
3. **Backend connection**: Test database connection from your backend deployment

## Monitoring

- **Frontend**: Check Vercel deployment logs and analytics
- **Backend**: Check your backend hosting platform logs
- **Database**: Monitor Neon dashboard for connection and performance issues
- **Errors**: Use Vercel's error tracking and browser console

## Performance Optimization

### Vite Build Optimization

The build is configured with:

- Code splitting for vendor, charts, and PDF libraries
- Tree shaking for unused code
- Minification and compression
- Optimized chunk sizes

### Recommendations

1. Use lazy loading for heavy components
2. Implement proper loading states
3. Use React.memo for expensive components
4. Monitor bundle size with Vite's build analysis

## Support

For issues, check:

1. Vercel deployment logs
2. Backend application logs
3. Browser console errors
4. Network tab in browser DevTools
5. Neon database dashboard

## Next Steps

After successful deployment:

1. ✅ Test all features in production
2. ✅ Monitor error rates and performance
3. ✅ Set up custom domain (optional)
4. ✅ Configure analytics and monitoring
5. ✅ Set up CI/CD pipelines (optional)
