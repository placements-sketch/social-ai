# 🚀 Social AI Assistant — Startup Guide

## Quick Start (Recommended)

### Option 1: Automated Startup (Windows)

**Double-click one of these files:**
- `START.bat` — For Command Prompt
- `START.ps1` — For PowerShell

This will automatically open two terminal windows:
1. **Backend** (Flask) on `http://127.0.0.1:5000`
2. **Frontend** (React) on `http://localhost:3000`

Then open your browser to `http://localhost:3000` and log in.

---

## Manual Startup (If Automated Doesn't Work)

### Step 1: Start Backend (Terminal 1)

```bash
cd c:\Users\WorkPC\Documents\dev\social-ai-assistant
python run.py
```

You should see:
```
 * Running on http://127.0.0.1:5000
 * Debugger is active!
```

### Step 2: Start Frontend (Terminal 2)

```bash
cd c:\Users\WorkPC\Documents\dev\social-ai-assistant\frontend
npm run dev
```

You should see:
```
  VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:5173/
  ➜  press h to show help
```

### Step 3: Open Browser

Go to `http://localhost:3000` (or the URL shown in Terminal 2)

---

## Login Credentials

Use any of these test accounts:

| Email | Password | Role |
|-------|----------|------|
| `admin@company.com` | `admin123` | Admin (full access) |
| `agent@company.com` | `agent123` | Agent (limited access) |
| `supervisor@company.com` | `supervisor123` | Supervisor (moderate access) |

---

## Stopping the Servers

**To stop:**
- Press `Ctrl+C` in each terminal window
- Or close the terminal windows

---

## Troubleshooting

### Backend won't start: "ModuleNotFoundError"
- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Or just run `python run.py` (packages are installed globally)

### Frontend won't start: "npm: command not found"
- Install Node.js from https://nodejs.org/
- Then run `npm install` in the `frontend` folder

### Can't log in after refresh
- Check browser console (F12) for `[AUTH]` messages
- Check backend terminal for error logs
- Make sure both servers are running

### Port already in use
- Backend: Change port in `run.py` (default: 5000)
- Frontend: Change port in `frontend/vite.config.js` (default: 3000)

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Browser (localhost:3000)             │
│                   React Frontend App                    │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP/JSON
                         ↓
┌─────────────────────────────────────────────────────────┐
│              Backend API (127.0.0.1:5000)               │
│                  Flask + PostgreSQL                     │
│  - Authentication (JWT tokens)                          │
│  - Messages & Conversations                             │
│  - Products & Inventory                                 │
│  - Automation Rules                                     │
│  - Analytics & Logs                                     │
└─────────────────────────────────────────────────────────┘
```

---

## What's Running

### Backend (Flask)
- **Port:** 127.0.0.1:5000
- **Database:** PostgreSQL (localhost:5432)
- **Features:** Auth, API endpoints, AI integration
- **Logs:** Printed to terminal

### Frontend (React)
- **Port:** localhost:3000 (or 5173 with Vite)
- **Framework:** React 18 + Vite
- **Styling:** Tailwind CSS
- **State:** React Context (Auth)

---

## Development Tips

### Hot Reload
- **Backend:** Changes auto-reload (Flask debug mode)
- **Frontend:** Changes auto-reload (Vite HMR)

### Debug Mode
- **Backend:** Open `http://127.0.0.1:5000/debug` for Flask debugger
- **Frontend:** Open DevTools (F12) for React DevTools

### Database
- Connect to PostgreSQL: `postgresql://postgres:postgres123@localhost:5432/social_ai`
- Use pgAdmin4 to browse tables

---

## Next Steps

Once both servers are running:
1. Log in with test credentials
2. Explore the admin dashboard
3. Check the Notifications dropdown (bell icon)
4. Try the Messages, Products, and other pages
5. Read the ROADMAP.md for what's being built next

---

## Need Help?

- Check `README.md` for project overview
- Check `PROJECT_OVERVIEW.md` for architecture details
- Check `ROADMAP.md` for upcoming features
- Check backend terminal for error logs
- Check browser console (F12) for frontend errors
