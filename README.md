# Aadi Academic Video Creation

Web application for preparing, reviewing and producing academic teaching videos. It is a product on the Aadi multitenant platform (sign-in through Aadi Identity) and uses the independent Video Engine (`aadiTechnology/ScriptToVideo`) only through its versioned API.

Docs: `docs/PRD_Aadi_Academic_Video_Creation_MVP.md`, `docs/architecture/ACADEMIC_INTEGRATION_ARCHITECTURE.md`, `docs/implementation/ACADEMIC_IMPLEMENTATION_PLAN.md`.

## Status

Done: lessons structure and language versions, sign-in through Aadi Identity with roles, package import and validation, academic review (Sprints 4 to 5). Next: video generation through the Video Engine, POC videos, Coolify deployment (see the plan).

## User guide

How to use the application, step by step with screens: `docs/user-guide/USER_GUIDE.md` (and a matching video for each part, see that file).

## Local setup

PostgreSQL is required (no SQLite). Start one and create a database:

```bash
docker run -d --name academic-test-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=academic_dev -p 15441:5432 postgres:16-alpine
```

Backend:

```bash
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements-dev.txt        # Windows; use .venv/bin/pip elsewhere
export DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:15441/academic_dev AUTH_MODE=dev
.venv/Scripts/python -m app.migrate
.venv/Scripts/python -m uvicorn app.main:app --port 8100
```

Frontend (second terminal): `cd frontend && npm install && npm run dev` then open http://localhost:5174 (the dev server proxies `/api` to port 8100).

`AUTH_MODE=dev` signs in a fixed development user and is refused when `APP_ENV=production`.

## Tests and build

```bash
cd backend && .venv/Scripts/python -m pytest -q       # needs PostgreSQL at 127.0.0.1:15441 (db academic_test) or ACADEMIC_TEST_DATABASE_URL
cd frontend && npm run build                           # type-check and production build
```

## Environment variables

See `.env.example` (names only). Secrets live in Coolify secrets or a git-ignored `.env`.
