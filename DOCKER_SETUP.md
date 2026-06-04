# Docker Setup Guide

This project is now fully containerized with Docker. Here's how to use it.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop) installed and running

## Quick Start

### 1. Start the Services

```bash
docker-compose up
```

This will:
- Pull the PostgreSQL image
- Build the backend Flask container
- Start both services on the same network
- Expose backend on `http://localhost:5000`
- Expose PostgreSQL on `localhost:5432`

### 2. Initialize the Database (First Time Only)

In a new terminal:

```bash
docker-compose exec backend flask db upgrade
```

This runs migrations and sets up your database schema.

### 3. Run Frontend (Separate Terminal)

The frontend continues to run locally as before:

```bash
cd frontend
npm install
npm run dev
```

Frontend will be on `http://localhost:5173` (or similar).

## Common Commands

### View Logs

```bash
# Backend logs
docker-compose logs backend -f

# Database logs
docker-compose logs postgres -f

# All services
docker-compose logs -f
```

### Stop Services

```bash
docker-compose down
```

This stops and removes containers but keeps database volumes.

### Rebuild After Code Changes

```bash
# Rebuild the backend image
docker-compose build

# Restart services
docker-compose up
```

Or in one command:
```bash
docker-compose up --build
```

### Access the Database

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U postgres -d social_ai_db

# Or use your GUI tool (DBeaver, pgAdmin):
# Host: localhost
# Port: 5432
# User: postgres
# Password: postgres123
# Database: social_ai_db
```

### Access Backend Container Shell

```bash
docker-compose exec backend bash
```

### Wipe Everything and Start Fresh

```bash
# Stop and remove everything (including volumes)
docker-compose down -v

# Start fresh
docker-compose up
```

## Environment Variables

The `docker-compose.yml` includes all environment variables from your `.env` file. To use different values:

**Option 1: Modify `.env` and restart**
```bash
# Edit .env with your actual credentials
docker-compose down
docker-compose up
```

**Option 2: Pass via command line**
```bash
ANTHROPIC_API_KEY=sk-ant-xxx docker-compose up
```

## Development Workflow

1. **Make code changes** — Backend code is mounted as a volume, so changes auto-reload
2. **Frontend continues normally** — `npm run dev` on your machine
3. **Backend reloads automatically** — Flask detects changes and restarts
4. **Database persists** — PostgreSQL data survives container restarts

## Production Deployment

When deploying to production:

1. Build the image:
   ```bash
   docker build -t social-ai-assistant:latest .
   ```

2. Push to registry (Docker Hub, AWS ECR, etc.):
   ```bash
   docker tag social-ai-assistant:latest your-registry/social-ai-assistant:latest
   docker push your-registry/social-ai-assistant:latest
   ```

3. Deploy on your hosting platform (Railway, Render, DigitalOcean, etc.)
   - Most platforms auto-detect `Dockerfile` and deploy automatically
   - Set environment variables on the platform dashboard
   - PostgreSQL can be provisioned separately or in Docker

## Troubleshooting

### "Port 5000 already in use"
```bash
# Change port in docker-compose.yml:
ports:
  - "5001:5000"  # Use 5001 instead
```

### "Database connection refused"
- Make sure `postgres` service started successfully: `docker-compose logs postgres`
- Wait a few seconds for postgres to be ready
- Check `POSTGRES_PASSWORD` matches in both services

### "Module not found" error
- Rebuild: `docker-compose build`
- Restart: `docker-compose up`

### Clear Everything and Start Over
```bash
docker-compose down -v
docker-compose up --build
```

## Notes

- **Volume mounts** — Backend code is mounted, so changes auto-reload
- **Database persistence** — `postgres_data` volume survives container restarts
- **Network** — Services communicate via service names (backend connects to `postgres:5432`)
- **Frontend** — Still runs locally, connects to backend on `http://localhost:5000`

You're now production-ready! 🎉











Let me check the channels.py file to see what endpoints are available:

Analyzed code

channels.py
Now let me read the full channel endpoints to understand what they do:

Read file(s)

channels.py
Perfect! Here's a complete guide for testing the channel routes in Postman:

Channel Routes Testing Guide
Prerequisites
Get your auth token by logging in first:

POST http://localhost:5000/api/auth/login
Body (raw JSON):
{
  "email": "admin@company.com",
  "password": "your_password"
}
Copy the returned access_token
In Postman, add the token to all requests:

Go to Authorization tab
Select type: Bearer Token
Paste your token
Endpoint 1: List All Channels
GET http://localhost:5000/api/channels

Method: GET
Headers: Authorization: Bearer {your_token}
Body: None
Expected Response: Returns all 7 channels with stats:
{
  "channels": [
    {
      "id": 1,
      "channel": "instagram_dm",
      "display_name": "Instagram DM",
      "enabled": true,
      "connected": true/false,
      "credentials_set": true/false,
      "webhook_url": "https://...",
      "message_count": 0,
      "unread_count": 0,
      "last_message_at": null,
      "created_at": "...",
      "updated_at": "..."
    }
    // ... 6 more channels
  ],
  "public_base_url": "http://localhost:5000"
}
Endpoint 2: Get Single Channel Details
GET http://localhost:5000/api/channels/{channel_id}

Method: GET
URL: Replace {channel_id} with 1-7
Example: http://localhost:5000/api/channels/1
Headers: Authorization: Bearer {your_token}
Body: None
Expected Response: Single channel object with full details
Endpoint 3: Update Channel (Enable/Disable)
PATCH http://localhost:5000/api/channels/{channel_id}

Method: PATCH
URL: Replace {channel_id} with 1-7
Example: http://localhost:5000/api/channels/1
Headers: Authorization: Bearer {your_token}
Body (raw JSON):
{
  "enabled": false
}
Expected Response: Updated channel object with new enabled state
Note: Creates an audit log entry
Endpoint 4: Test Channel Connection
POST http://localhost:5000/api/channels/{channel_id}/test

Method: POST
URL: Replace {channel_id} with 1-7
Example: http://localhost:5000/api/channels/1
Headers: Authorization: Bearer {your_token}
Body: None (or empty JSON {})
Expected Response: Mocked test result:
{
  "ok": true,
  "message": "Instagram DM connection healthy (mocked).",
  "checked_at": "2026-06-04T09:50:00+00:00",
  "mocked": true,
  "details": {
    "token_valid": true,
    "token_expires_in_days": 47,
    "webhook_subscribed": true,
    "permissions_granted": true
  }
}
If credentials missing (should fail gracefully):

{
  "ok": false,
  "reason": "credentials_not_set",
  "message": "Cannot test Instagram DM: required environment variables are not set (...)",
  "checked_at": "2026-06-04T09:50:00+00:00",
  "mocked": true
}
Test Scenarios
Scenario 1: List channels (basic test)

GET /api/channels
Should return 7 channels
Check that enabled/disabled status is correct
Scenario 2: Enable/Disable a channel

PATCH /api/channels/2 with {"enabled": false}
Verify response shows enabled: false
PATCH again with {"enabled": true} to re-enable
Check audit logs recorded the change
Scenario 3: Test connection with missing credentials

POST /api/channels/7 (tiktok_dm - no credentials in .env)
Should return ok: false with credentials_not_set reason
Scenario 4: Get single channel

GET /api/channels/1
Verify all fields present (stats, webhook_url, etc.)
Quick Postman Steps
Create folder "Channels" in your collection
Create 4 requests:
GET List Channels
GET Get Channel (with {{channel_id}} variable)
PATCH Update Channel
POST Test Channel
Set Authorization for all to Bearer Token with your token
Save and run each request
Let me know if you find any issues with the responses!

i need to test the channel routes...tell me the endpoints to test on postman and how