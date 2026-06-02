# MCG Lead Engine

A Facebook groups scraper and lead-management tool for a Chicago hard money real
estate brokerage. It pulls posts from public Facebook investor groups via Apify,
runs them through an AI scoring agent (Anthropic Claude), surfaces high-intent
leads in a simple dashboard, and is deployed to Railway.

## Stack

- **Backend:** Python + FastAPI
- **Database:** Postgres on Railway (async SQLAlchemy + asyncpg, Alembic migrations)
- **Frontend:** Next.js 14 (App Router) + TypeScript + Tailwind CSS
- **Deployment:** Railway
- **External APIs:** Apify (Facebook scraping), Anthropic Claude (scoring agent)

## Project Structure

```
mcg-facebook-engine/
├── backend/            # FastAPI application
│   ├── app/
│   │   ├── main.py     # FastAPI app + /health endpoint
│   │   ├── db.py       # Async SQLAlchemy engine, session, get_db dependency
│   │   ├── routes/     # API route modules
│   │   ├── agents/     # AI scoring agents
│   │   └── scrapers/   # Apify scrapers
│   ├── migrations/     # SQL migrations
│   ├── requirements.txt
│   └── .env.example
├── frontend/           # Next.js app
└── .devcontainer/      # Codespaces config (Python 3.11 + Node 20)
```

## Local Development (Codespaces-friendly)

The repo ships with a `.devcontainer` configured for **Python 3.11** and
**Node 20**, so a fresh Codespace has both runtimes ready.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your values
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`, with the health check at
`http://localhost:8000/health`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The app will be available at `http://localhost:3000`.

## Environment Variables

Backend variables live in `backend/.env` (see `backend/.env.example`):

| Variable            | Description                                            |
| ------------------- | ------------------------------------------------------ |
| `DATABASE_URL`      | Postgres connection string (`postgresql+asyncpg://…`)  |
| `APIFY_TOKEN`       | Apify API token for Facebook scraping                  |
| `ANTHROPIC_API_KEY` | Anthropic API key for the Claude scoring agent         |
| `MARCUS_PASSWORD`   | HTTP Basic Auth password for user `marcus`             |
| `ANDREW_PASSWORD`   | HTTP Basic Auth password for user `andrew`             |
| `FRONTEND_ORIGIN`   | Allowed CORS origin (the frontend URL; `*` for dev)    |

The frontend needs one variable (see `frontend/.env.example`):

| Variable      | Description                                                       |
| ------------- | ---------------------------------------------------------------- |
| `BACKEND_URL` | Backend API base URL, used server-side by the Next.js rewrite proxy. Not exposed to the browser. |

### Database setup

Provision a Postgres instance on Railway, copy the `DATABASE_URL` from the
Railway dashboard into `backend/.env`, then run migrations with:

```bash
cd backend && alembic upgrade head
```

## Deployment (Railway)

The repo runs as a **single Railway service** that serves both the Next.js
frontend and the FastAPI backend from the **same container**. Nixpacks installs
both runtimes and dependencies (see the root `nixpacks.toml`), and a startup
script (`start.sh`) launches both processes.

**Architecture**

- **Next.js** runs on `$PORT` (Railway-assigned, public-facing). The browser
  only ever talks to this origin.
- **FastAPI/uvicorn** runs on internal `localhost:8000` (bound to `127.0.0.1`,
  not exposed publicly).
- `/api/*` and `/health` requests hit Next.js and are proxied internally to
  `http://localhost:8000` via the Next.js rewrite in `next.config.mjs`
  (`BACKEND_URL` defaults to `http://localhost:8000`, which now serves both
  local dev and Railway production since the backend lives in the same
  container).
- `start.sh` runs Alembic migrations, then launches uvicorn as a background
  process and `npm start` in the foreground. When the container dies (Railway
  restart), both processes die together as one process group.

1. **Provision one service from this repo.** Nixpacks auto-detects the root
   `nixpacks.toml`, installs Python 3.11 + Node 20, installs
   `backend/requirements.txt` and `frontend` deps, builds the Next.js
   production bundle, and starts everything via `bash start.sh`.
   Add the Railway **Postgres** plugin and share its `DATABASE_URL` with the
   service.

2. **Set env vars on the service:** `DATABASE_URL`, `APIFY_TOKEN`,
   `ANTHROPIC_API_KEY`, `MARCUS_PASSWORD`, `ANDREW_PASSWORD`.

3. **Migrations run automatically** on every startup via `start.sh`
   (`alembic upgrade head`) before any traffic is served — no manual step
   needed after deploy.

### Auth

The dashboard uses HTTP Basic Auth handled natively by the browser — there's no
login page. Because the frontend proxies the API under its own origin, the
first request triggers the browser's sign-in prompt on that single origin;
v1 has two users, `marcus` and `andrew`, with passwords set via the
`*_PASSWORD` env vars above.
