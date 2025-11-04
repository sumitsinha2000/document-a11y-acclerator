# Deployment Guide for Document A11y Accelerator

## Overview

This application is now configured to run directly on Vercel at `https://document-a11y-acclerator.vercel.app/` with the React frontend migrated to Next.js.

## Architecture

- **Frontend**: Next.js 16 application (migrated from React + Vite)
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
NEXT_PUBLIC_BACKEND_URL=https://your-backend-url.vercel.app
\`\`\`

**Important**: Replace `your-backend-url.vercel.app` with your actual deployed backend URL from Step 1.

The Neon database variables are automatically provided by the Vercel integration.

### 3. Update vercel.json

Update the `rewrites` section in `vercel.json` with your actual backend URL:

\`\`\`json
{
  "rewrites": [
    {
      "source": "/api/:path*",
      "destination": "https://your-actual-backend-url.vercel.app/api/:path*"
    }
  ]
}
\`\`\`

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

For local development, the app automatically uses `http://localhost:5000` for the backend:

\`\`\`bash
# Terminal 1: Start backend
cd backend
python app.py

# Terminal 2: Start frontend
npm run dev
\`\`\`

Visit `http://localhost:3000` to see your app.

## Environment Variables

### Required for Production

- `NEXT_PUBLIC_BACKEND_URL` - Your deployed backend URL
- Neon database variables (automatically provided by Vercel integration)

### Optional

- `NODE_ENV` - Set to `production` (automatically set by Vercel)

## Architecture Changes

### What Changed

The React + Vite frontend has been migrated to Next.js:

- ✅ All React components now run in Next.js
- ✅ No more localhost:3000 redirects or iframes
- ✅ Direct deployment to Vercel domain
- ✅ Improved performance with Next.js optimizations
- ✅ Better SEO and initial load times

### File Structure

\`\`\`
document-a11y-acclerator/
├── app/
│   ├── page.tsx              # Main application (migrated from frontend/src/App.jsx)
│   ├── layout.tsx            # Root layout
│   └── globals.css           # Global styles (includes frontend styles)
├── components/
│   └── frontend/             # All React components (to be migrated)
├── contexts/
│   └── NotificationContext.tsx  # Notification context
├── backend/                  # Flask backend (deploy separately)
└── vercel.json              # Vercel configuration
\`\`\`

## Troubleshooting

### API calls failing in production

1. **Check environment variable**: Verify `NEXT_PUBLIC_BACKEND_URL` is set correctly in Vercel
2. **Verify CORS**: Ensure CORS is configured in your backend to allow your Vercel domain
3. **Check backend logs**: Review your backend hosting platform logs for errors
4. **Test backend directly**: Try accessing your backend URL directly in a browser

### Components not loading

1. **Check imports**: Ensure all component imports use `@/components/frontend/` prefix
2. **Browser console**: Check browser console for import or runtime errors
3. **Dependencies**: Verify all required dependencies are in `package.json`

### Database connection issues

1. **Neon integration**: Verify Neon integration is connected in Vercel project settings
2. **Environment variables**: Check that database environment variables are set
3. **Backend connection**: Test database connection from your backend deployment

### Build failures

1. **Missing components**: Ensure all frontend components are migrated to `components/frontend/`
2. **TypeScript errors**: Check for type errors in the build logs
3. **Dependencies**: Run `npm install` to ensure all dependencies are installed

## Monitoring

- **Frontend**: Check Vercel deployment logs and analytics
- **Backend**: Check your backend hosting platform logs
- **Database**: Monitor Neon dashboard for connection and performance issues
- **Errors**: Use Vercel's error tracking and browser console

## Performance Optimization

### Next.js Benefits

- Server-side rendering for faster initial loads
- Automatic code splitting
- Image optimization
- Built-in caching strategies

### Recommendations

1. Use Next.js Image component for images
2. Implement proper loading states
3. Use React.memo for expensive components
4. Monitor Core Web Vitals in Vercel Analytics

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
