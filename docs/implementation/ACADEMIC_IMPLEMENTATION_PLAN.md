# Academic Implementation Plan

Per-sprint limits: 20 new and 10 modified files unless the owner approves an exception. Each sprint ends with green tests, a verification record, a demo video in `docs/demos/` (made with ScriptToVideo plus screen captures) and a row in `docs/implementation/SPRINT_TRACKER.xlsx` (no secrets). Feature branches, merged to `main` after approval; no push without confirmation.

| Sprint | Scope | Main files (approx.) | Acceptance |
|---|---|---|---|
| 4 Foundation | Repo scaffold, FastAPI, React, Alembic, CRUD for class/subject/chapter/topic/lesson/language version, UUID ids, `.env.example`, README | ~18 new | Create a lesson with en, hi and mr versions; API tests and frontend build green |
| 5 Import and review | ZIP/CSV/JSON importer, canonical 5-column CSV, safe archive handling, size and encoding checks, actionable errors, prompt-spec generator for ChatGPT Free, review states (Draft, In Review, Changes Required, Approved, Rejected), approval gate | ~20 new, 8 modified (exception likely) | Invalid packages rejected with clear errors; reviewer approves; unapproved version cannot render |
| 6 Integration | `engine_client`, pinned contract, job mapping, idempotent submit, status polling, retry, asset copy, preview and download, Colab upload step, error mapping | ~16 new, 6 modified (plus engine-side fixes in the engine repo if needed) | Create, approve, render, preview and download with no manual file copying; duplicate click gives one job; restart keeps the job |
| 7 POC | Three Class 7 Science Photosynthesis videos (en, hi, mr), about 5 minutes each | content packages, test report | Script, pronunciation, subtitle sync, visuals, MP4 validity, duration, resolution and reproducibility checked; unvalidated languages stated as such |
| 8 Deploy and handover | Dockerfiles, Coolify compose, volumes, health checks, access restriction, backups and rollback docs, smoke test of the full flow | ~10 new | Deployed on Coolify as a separate resource; engine not public; smoke test passes |

## Sprint 4 expected files

New: `README.md`, `.env.example`, `backend/app/main.py`, `backend/app/config.py`, `backend/app/db.py`, `backend/app/models.py`, `backend/app/schemas.py`, `backend/app/routers/{structure,lessons}.py`, `backend/alembic.ini`, `backend/alembic/env.py`, first migration, `backend/requirements.txt`, `backend/tests/test_structure.py`, `backend/tests/test_lessons.py`, `frontend/package.json`, `frontend/src/{main,App}.tsx`, lesson list and detail components. No modified files except `.gitignore`.

## Owner decisions needed (defaults)

1. Backend and frontend stack: FastAPI + React (default yes).
2. PostgreSQL: which existing Coolify instance and database to use. Until then, a local Docker Postgres in development. No SQLite.
3. Access protection for the unauthenticated MVP: Coolify basic auth or IP allow-list.
4. A new GitHub repo remote is set to the URL you gave; first push needs your confirmation.
