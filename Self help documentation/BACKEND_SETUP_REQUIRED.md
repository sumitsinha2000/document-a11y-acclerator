# Backend Setup Required

## Current Status

The frontend application is successfully deployed to Vercel, but the backend API is not yet deployed. This is causing 404 errors when the frontend tries to fetch data.

## Errors You're Seeing

- `GET /api/scans 404 (Not Found)`
- `GET /api/groups 404 (Not Found)`
- `Error fetching scan history: AxiosError`
- `Error fetching groups: AxiosError`

## Why This Is Happening

The application has two parts:

1. **Frontend** (React + Vite) - ✅ Successfully deployed to Vercel
2. **Backend** (Flask API) - ❌ Not found in repository / Not deployed

The frontend is trying to call API endpoints that don't exist yet.

## Solution Options

### Option 1: Deploy Existing Backend (If You Have One)

If you have a backend codebase elsewhere:

1. **Add backend to repository:**

      ```markdown
      # Create backend directory
      mkdir backend
      cd backend

      # Add your Flask app files here
      # - app.py or server.py
      # - requirements.txt
      # - Any other backend files

      ```

2. **Deploy backend to Vercel:**

   ```bash
   cd backend
   vercel deploy --prod
   ```

3. **Update environment variable in Vercel:**
   - Go to Vercel project settings
   - Add environment variable: `VITE_API_URL=https://your-backend-url.vercel.app`
   - Redeploy frontend

### Option 2: Create New Backend

If you need to create a backend from scratch:

1. **Create Flask backend structure:**

   ```markdown
   backend/
   ├── app.py              # Main Flask application
   ├── requirements.txt    # Python dependencies
   ├── vercel.json        # Vercel configuration
   └── api/
       ├── **init**.py
       ├── routes.py      # API routes
       └── models.py      # Database models
   ```

2. **Required API endpoints:**
   - `GET /api/health` - Health check
   - `POST /api/scan` - Scan single document
   - `POST /api/scan-batch` - Scan multiple documents
   - `GET /api/scans` - Get all scans
   - `GET /api/groups` - Get all groups
   - `POST /api/groups` - Create new group
   - `GET /api/groups/:id` - Get group details
   - `PUT /api/groups/:id` - Update group
   - `DELETE /api/groups/:id` - Delete group
   - And other endpoints listed in `frontend/src/config/api.js`

3. **Deploy and configure as in Option 1**

### Option 3: Use Mock Data (Temporary)

For testing the frontend without a backend:

1. Create a mock API service in the frontend
2. Return sample data for development
3. This is only for testing - you'll need a real backend for production

### Option 4: Deploy to Alternative Platform

Instead of Vercel, you can deploy the backend to:

- **Railway.app** - Easy Python deployment
- **Render.com** - Free tier available
- **Heroku** - Classic PaaS option
- **AWS Lambda** - Serverless option

## Database Configuration

The Neon PostgreSQL database is already connected via Vercel integration. Your backend will need to:

1. Use the Neon connection string from environment variables
2. Create necessary tables for:
   - Scans
   - Groups
   - Fix history
   - Batch operations

## Next Steps

1. Choose one of the options above
2. Deploy your backend
3. Set the `VITE_API_URL` environment variable in Vercel
4. Redeploy the frontend
5. Test the application

## Current Frontend Configuration

The frontend is configured to call APIs at:

- Development: `http://localhost:5000` (when VITE_API_URL is not set)
- Production: Uses VITE_API_URL environment variable or relative URLs

The `vercel.json` is configured to rewrite `/api/*` requests to your backend URL, but you need to update it with your actual backend URL.
