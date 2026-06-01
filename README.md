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

The repo runs as **two Railway services off the same GitHub repo**, distinguished
by their build/start commands (provided by `railway.toml` at the repo root for
the backend and `frontend/railway.toml` for the frontend).

1. **Provision two services from this repo.**
   - **Backend service:** uses the root `railway.toml` — installs
     `backend/requirements.txt` and starts `uvicorn app.main:app` on `$PORT`,
     with the health check at `/health`.
   - **Frontend service:** point its config path at `frontend/railway.toml` —
     it runs `npm install && npm run build`, then `npm start`.
   - Add the Railway **Postgres** plugin and share its `DATABASE_URL` with the
     backend service.

2. **Set env vars per service.**
   - **Backend:** `DATABASE_URL`, `APIFY_TOKEN`, `ANTHROPIC_API_KEY`,
     `MARCUS_PASSWORD`, `ANDREW_PASSWORD`. `FRONTEND_ORIGIN` is optional now
     (the proxy keeps the browser same-origin) — leave it unset/`*`.
   - **Frontend:** `BACKEND_URL`.

3. **Point the frontend at the backend.** The frontend proxies `/api/*` and
   `/health` to the backend via a Next.js rewrite (`next.config.mjs`), so the
   browser only ever talks to the frontend origin — no cross-origin Basic Auth
   prompt and no CORS. Set `BACKEND_URL` on the frontend service to the
   backend's **Railway internal URL** (e.g. `http://backend.railway.internal:8000`)
   so the two services talk over Railway's private network. `BACKEND_URL` is
   read server-side at request time (it is *not* a `NEXT_PUBLIC_*` var and not
   baked into the build), so a restart is enough — no rebuild required.

4. **Run migrations** against the production database once after first deploy:
   `cd backend && alembic upgrade head`.

### Auth

The dashboard uses HTTP Basic Auth handled natively by the browser — there's no
login page. Because the frontend proxies the API under its own origin, the
first request triggers the browser's sign-in prompt on that single origin;
v1 has two users, `marcus` and `andrew`, with passwords set via the
`*_PASSWORD` env vars above.
