# Running the Social AI Assistant

## Prerequisites

- Python 3.9+
- Node.js 16+ and npm
- PostgreSQL 12+ (running locally or accessible)
- Git

## Setup

### 1. Backend Setup

```bash
# Navigate to project root
cd c:\Users\WorkPC\Documents\dev\social-ai-assistant

# Create a Python virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Create the database (if not already created)
# Make sure PostgreSQL is running and the DATABASE_URL in .env is correct
# Default: postgresql://postgres:postgres123@localhost:5432/social_ai

# Run database migrations
flask db upgrade

# (Optional) Create test users if needed
python create_test_users.py
```

### 2. Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# (Optional) Create a .env file if needed for environment variables
# For development, the vite proxy will handle API calls to localhost:5000
```

## Running the Application

### Option A: Run Both Backend and Frontend (Recommended for Development)

**Terminal 1 - Backend:**
```bash
# From project root, with venv activated
python -m flask run --host=127.0.0.1 --port=5000
```

**Terminal 2 - Frontend:**
```bash
# From frontend directory
npm run dev
```

Then open your browser to: **http://localhost:3000**

### Option B: Run Backend Only (for API testing)

```bash
# From project root, with venv activated
python -m flask run --host=127.0.0.1 --port=5000
```

API will be available at: **http://127.0.0.1:5000/api**

### Option C: Run Frontend Only (requires backend running separately)

```bash
# From frontend directory
npm run dev
```

Frontend will be available at: **http://localhost:3000**

## Test Credentials

After running `python create_test_users.py`, use these credentials to login:

| Email | Password | Role |
|-------|----------|------|
| admin@company.com | admin123 | admin |
| agent@company.com | agent123 | agent |
| supervisor@company.com | supervisor123 | supervisor |

## Important Notes

### API Base URL
- **Development**: The frontend uses a Vite proxy that forwards `/api` requests to `http://localhost:5000/api`
- **Production**: Update `VITE_API_BASE` environment variable or modify `frontend/src/api/messages.js` and `frontend/src/context/AuthContext.jsx`

### JWT Token
- Tokens are stored in localStorage under the key `authToken`
- Token expiration: 24 hours
- JWT Secret: `dev-jwt-secret-key-12345` (change in production)

### Database
- Default connection: `postgresql://postgres:postgres123@localhost:5432/social_ai`
- Update `DATABASE_URL` in `.env` if using different credentials
- Ensure PostgreSQL is running before starting the backend

### CORS
- CORS is enabled for all origins during development
- Update `app/__init__.py` CORS configuration for production

## Troubleshooting

### 401 Unauthorized Errors
- Ensure the token is being sent in the `Authorization: Bearer <token>` header
- Check that the token is stored in localStorage after login
- Verify JWT_SECRET_KEY matches between backend and frontend

### CORS Errors
- Make sure the backend is running on `http://127.0.0.1:5000` (not `localhost`)
- Check that CORS is properly configured in `app/__init__.py`
- Verify the frontend is making requests through the Vite proxy (use relative paths like `/api`)

### Database Connection Errors
- Ensure PostgreSQL is running
- Verify DATABASE_URL in `.env` is correct
- Check PostgreSQL credentials and permissions
- Run `flask db upgrade` to ensure schema is up to date

### Port Already in Use
- Backend default: 5000
- Frontend default: 3000
- Change ports with: `flask run --port=5001` or `npm run dev -- --port=3001`

## Development Workflow

1. **Make backend changes**: Restart Flask server (it auto-reloads on file changes)
2. **Make frontend changes**: Vite automatically hot-reloads
3. **Make database schema changes**: 
   - Create migration: `flask db migrate -m "description"`
   - Apply migration: `flask db upgrade`
4. **Test API endpoints**: Use Postman or curl with the JWT token

## Building for Production

### Backend
```bash
# Set environment variables for production
set FLASK_ENV=production
set SECRET_KEY=your-production-secret-key
set JWT_SECRET_KEY=your-production-jwt-secret

# Run with a production WSGI server (e.g., Gunicorn)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
```

### Frontend
```bash
cd frontend
npm run build
# Output will be in frontend/dist/
```

## API Documentation

See `ARCHITECTURE.md` for detailed API documentation and contract specifications.

## Support

For issues or questions, refer to:
- `ARCHITECTURE.md` - System design and API contracts
- `BACKEND.md` - Backend implementation details
- `CHAT.md` - Chat/messaging system documentation
