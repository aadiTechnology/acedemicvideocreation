# Academic Integration Architecture (proposed)

Repository: `aadiTechnology/acedemicvideocreation`. It owns the academic UI and API, and consumes the Video Engine (`aadiTechnology/ScriptToVideo`) only through `/api/v1`. No engine code is copied here, and no engine tables are queried.

```
Browser --HTTPS--> academic-web (static React) --> academic-api (FastAPI)
                                                       |  PostgreSQL (academic schema, own DB or schema)
                                                       |  storage (package originals, copied outputs)
                                                       +--(X-Engine-Key, private Docker network)--> engine-api
```

## Stack proposal (to be confirmed in Sprint 4)

Backend FastAPI + SQLAlchemy + Alembic (matches the engine's Python stack). Frontend React + Vite + TypeScript. Database: PostgreSQL, on the same server as Aadi Identity and Project Tracker (see "Shared platform"). No SQLite.

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
| `DATABASE_URL` | PostgreSQL connection (Academic database on the shared server, runtime role) |
| `MIGRATION_DATABASE_URL` | migrator role, used only by the migration command |
| `IDENTITY_ISSUER_URL`, `IDENTITY_CLIENT_ID`, `IDENTITY_CLIENT_SECRET` | OIDC sign-in through Aadi Identity |
| `IDENTITY_PRODUCT_KEY` | `academics` |
| `VIDEO_ENGINE_URL` | internal engine URL, e.g. `http://engine-api:8000` |
| `VIDEO_ENGINE_API_KEY` | service-to-service secret |
| `VIDEO_ENGINE_TIMEOUT_SECONDS` | client timeout |
| `STORAGE_PROVIDER`, `STORAGE_LOCAL_DIR`, `B2_*` | asset storage; local disk first, Backblaze later |
| `ACCESS_RESTRICTION` | deployment-level protection for the unauthenticated MVP (see below) |

`.env.coolify` in this folder is not usable as is. It was copied from another application (project-tracker/SpendOS): it holds JWT, SMTP and Postgres secrets and a Coolify token for a different app, and lacks every engine variable above. It is git-ignored. A clean `.env.example` is added in Sprint 4. Rotate the credentials in that file because they have been exposed in this working session.

## Shared platform: Aadi Identity and one PostgreSQL server

Academic Video Creation is a second product on the multitenant platform (`aadiTechnology/identity`, OIDC, currently serving Project Tracker). It does not get its own login.

- **Sign-in:** OIDC authorization code with PKCE against Identity. Register product key `academics` and client `academics-web` (`register-product`, `register-client` CLI) with the Academic redirect and logout URIs. Identity's redirect rule, product hub and switcher then work for Academic like any other product.
- **Tenancy:** every Academic table carries `tenant_id` (the Identity company UUID, claim `tid`). Every query and every engine submission is scoped by the tenant of the signed-in user. Identity user ids (`sub`) are stored as `created_by`/`reviewed_by`. Tenants buy Academic through an Identity subscription for product `academics`; no subscription means no access.
- **Roles:** Identity answers who you are and which products you may open. Roles stay inside each product (decision D3), so Academic keeps a small role set (content operator, reviewer, production operator) mapped from its own tables. This is a deliberate change to the PRD's "no login, no RBAC" non-goal, and it is allowed because the PRD permits reusing an existing authentication facility. It also removes the need for the IP or basic-auth restriction on the Academic UI.
- **Engine stays service-to-service.** The Video Engine never sees end users and never talks to Identity. Academic passes `caller.tenant_ref` (opaque, the tenant UUID) in the manifest so jobs and assets can be correlated per tenant. No metering or billing.
- **One PostgreSQL server, separate databases (owner decision).** The server is the PostgreSQL that Coolify hosts for Aadi Identity (`postgres:16`, today a container private to the Identity compose stack). Identity, Project Tracker, Academic and the Video Engine each use their own database on it (`aadi_academic`, `aadi_video_engine`), with their own roles: a runtime role without DDL rights and a migrator role, as in `dev-environment/`. Products never read each other's tables; they link only through Identity UUIDs stored in their own columns.
  - **Guardrails:** Academic and engine roles get `CONNECT` on their own database only, and `CONNECT` on the `identity` database is revoked from `PUBLIC` and from those roles. The server is never published on a public port. Take a backup before any change, and add Academic and engine databases to the backup scope.
  - **Reachability (needs owner approval, touches production Identity):** the Identity postgres service must also join a shared internal Docker network (for example `aadi-data`) that the Academic API and the engine containers join. That is a small change to `identity/docker-compose.coolify.yml` plus a redeploy of Identity, and I will not make it without explicit approval. Fallback if the owner prefers not to touch Identity: a standalone Coolify PostgreSQL resource for the other products.
  - **Provisioning:** database and role creation is a reviewed SQL script run by the owner (or by me on approval), not an application side effect. The Academic and engine passwords are generated into Coolify secrets and never committed.
- **Local development:** extend `dev-environment/bootstrap.ps1` (it already creates databases and roles) with `aadi_academic_dev` and `aadi_video_engine_dev`, instead of a separate setup.

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

Package validation complexity (Sprint 5). Colab manual step adds an operator action per video. Identity registration needs a platform admin, and the shared PostgreSQL server details are unconfirmed. Slide visual quality is an engine-side risk that the POC will expose.
