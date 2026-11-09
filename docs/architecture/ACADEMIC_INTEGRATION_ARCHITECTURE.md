# Academic Integration Architecture (proposed)

Repository: `aadiTechnology/acedemicvideocreation`. It owns the academic UI and API, and consumes the Video Engine (`aadiTechnology/ScriptToVideo`) only through `/api/v1`. No engine code is copied here, and no engine tables are queried.

```
Browser --HTTPS--> academic-web (static React) --> academic-api (FastAPI)
                                                       |  PostgreSQL (academic schema, own DB or schema)
                                                       |  storage (package originals, copied outputs)
                                                       +--(X-Engine-Key, private Docker network)--> engine-api
```

## Stack proposal (to be confirmed in Sprint 4)

Backend FastAPI + SQLAlchemy + Alembic (matches the engine's Python stack). Frontend React + Vite + TypeScript. Database: PostgreSQL. The existing Coolify PostgreSQL is used only after the owner confirms which instance and database, and no database is created silently. Local development uses SQLite or a Docker Postgres.

## Data model (Sprint 4)

`classes`, `subjects`, `chapters`, `topics`, `lessons`, `lesson_versions` (language en, hi or mr; review_status; package paths; normalized JSON), `video_jobs` (lesson_version_id, engine_job_id, idempotency_key, state, error_code, timestamps), `video_assets` (job id, kind, engine asset id, checksum, local copy path), `review_events`. UUID primary keys. `publication_status` is a nullable placeholder for a future student portal. `organization_id` is omitted unless the owner asks.

## Integration rules

- `engine_client.py` is the only module that talks to the engine. It reads `VIDEO_ENGINE_URL` and `VIDEO_ENGINE_API_KEY` from the environment, with timeouts and bounded retries, and sends `X-Correlation-Id`.
- Only `approved` language versions can be submitted. The idempotency key is derived from `lesson_version_id` plus a package hash, so double clicks and network retries do not duplicate renders. An explicit "re-render" creates a new key.
- The engine job id is stored against the lesson version and survives refresh and restart. The UI polls through the Academic API. The browser never sees the engine URL or key.
- On success the Academic API streams the MP4 and supporting assets from the engine to its own storage, so downloads do not depend on engine retention.
- For Colab jobs in `awaiting_audio`, the UI offers the narration batch download and an audio ZIP upload. Both are proxied to the engine.
- Errors shown to operators are mapped from engine error codes. No stack traces.

## Contract pinning

`contracts/video-engine.v1.json` holds the schema copied from a tagged engine release (for example `contract-v1.0.0`) and a `CONTRACT_VERSION` file. CI checks that the client's requests validate against the pinned schema. Upgrading means copying a newer tagged release and running the contract tests. A contract major mismatch is rejected by the engine.

## Environment variables (names only; values live in Coolify secrets or local `.env`, never in git)

| Variable | Purpose |
|---|---|
| `APP_ENV`, `APP_BASE_URL` | environment and public URL |
| `DATABASE_URL` | PostgreSQL connection |
| `VIDEO_ENGINE_URL` | internal engine URL, e.g. `http://engine-api:8000` |
| `VIDEO_ENGINE_API_KEY` | service-to-service secret |
| `VIDEO_ENGINE_TIMEOUT_SECONDS` | client timeout |
| `STORAGE_PROVIDER`, `STORAGE_LOCAL_DIR`, `B2_*` | asset storage; local disk first, Backblaze later |
| `ACCESS_RESTRICTION` | deployment-level protection for the unauthenticated MVP (see below) |

`.env.coolify` in this folder is not usable as is. It was copied from another application (project-tracker/SpendOS): it holds JWT, SMTP and Postgres secrets and a Coolify token for a different app, and lacks every engine variable above. It is git-ignored. A clean `.env.example` is added in Sprint 4. Rotate the credentials in that file because they have been exposed in this working session.

## Access protection

The MVP has no login. It must not be public. Recommended: Coolify basic auth or IP allow-list on the Academic domain. Owner to confirm the method before Sprint 8.

## Proposed tree

```
acedemicvideocreation/
  README.md  .env.example  .gitignore
  contracts/            pinned engine contract
  backend/app/{api,models,services,engine_client,importer}  backend/alembic  backend/tests
  frontend/src/...
  docs/{architecture,audits,deployment,implementation,runbooks,demos}
  Dockerfile.api  Dockerfile.web  docker-compose.coolify.yml
```

## Risks

Package validation complexity (Sprint 5). Colab manual step adds an operator action per video. PostgreSQL ownership unconfirmed. Slide visual quality is an engine-side risk that the POC will expose.
