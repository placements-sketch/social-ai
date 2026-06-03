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
