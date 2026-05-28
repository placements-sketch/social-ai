# Social AI — Admin Frontend

React + Vite admin panel for the Social AI customer support system.

## Stack
- **React 18** + **React Router 6**
- **Vite 5** (dev server + build)
- **Tailwind CSS 3** (dark theme)
- **Recharts** (analytics charts)
- **Lucide React** (icons)

## Setup

```bash
# Install Node.js first: https://nodejs.org (LTS version)

cd frontend
npm install
npm run dev        # starts on http://localhost:3000
```

## Pages
| Route | Page |
|---|---|
| `/dashboard` | Live stats, activity feed, alerts |
| `/messages` | 3-panel inbox — conversations, chat, AI context |
| `/products` | Shopify + Odoo inventory with mismatch detector |
| `/ai` | Brand tone, system prompt, response rules |
| `/automation` | IF/THEN rule builder |
| `/channels` | Instagram + WhatsApp connection status |
| `/analytics` | Charts — intents, products, channel split |
| `/logs` | Full pipeline audit trail |
| `/settings` | API keys, webhooks, business hours |

## Connecting to the Flask backend
All API calls are proxied to `http://localhost:5000` via `vite.config.js`.
Replace mock data in `src/data/mock.js` with `fetch('/api/...')` calls as you build out the backend endpoints.
