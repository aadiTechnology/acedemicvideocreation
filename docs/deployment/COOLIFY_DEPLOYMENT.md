# Deploying Academic Video Creation on Coolify

Two services from `docker-compose.coolify.yml`, deployed as their own Coolify application (separate from the Video Engine and from Identity):

| Service | Image | Role |
|---|---|---|
| `academic-web` | nginx + the built React app | the only public service, `https://academics.aaditechnology.com`. Proxies `/api` and `/auth` to the API on the private network |
| `academic-api` | FastAPI | runs migrations (migrator role) at start, then serves with the runtime role. No public domain |

```
Browser --HTTPS--> academic-web --/api, /auth--> academic-api --aadi-postgres:5432--> database aadi_academic
                                                       |--aadi-engine-api:8000--> Video Engine (internal only)
                                                       |--> Identity (OIDC, public https)   |--> volume academic_storage (/data)
```

The API is not published under `academicsapi.aaditechnology.com`: the browser only needs the one origin, the session cookie is host-only, and fewer public endpoints is safer. The DNS record can stay for later use.

## Prerequisites (all done unless marked)

1. The Identity stack runs with the `aadi-data` network (done). The Video Engine app `aadi-video-engine` is deployed (done, internal only).
2. Database `aadi_academic` with roles `aadi_academic_app` (runtime) and `aadi_academic_migrator` exist (done, see `POSTGRES_PROVISIONING.sql`).
3. Product `academics` and client `academics-web` are registered in Identity with redirect `https://academics.aaditechnology.com/auth/callback` (done).
4. DNS for `academics.aaditechnology.com` points at the Coolify server (done by the owner).
5. **Owner step, not done:** in Identity's platform admin page, give the company a subscription to the product `academics`. Without it, sign-in is refused by Identity.

## Environment variables (Coolify secrets; names only)

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | runtime role: `postgresql://aadi_academic_app:<pw>@aadi-postgres:5432/aadi_academic` |
| `MIGRATION_DATABASE_URL` | migrator role, used only by `python -m app.migrate` at start |
| `SESSION_SECRET` | signs the session and sign-in cookies |
| `IDENTITY_CLIENT_SECRET` | the client secret registered in Identity |
| `VIDEO_ENGINE_API_KEY` | same value as the engine's `ENGINE_API_KEY` |
| `APP_BASE_URL`, `IDENTITY_ISSUER_URL`, `IDENTITY_CLIENT_ID`, `VIDEO_ENGINE_URL`, `VIDEO_ENGINE_TIMEOUT_SECONDS` | have defaults in the compose file |

`APP_ENV=production` and `AUTH_MODE=oidc` are fixed in the compose file; the API refuses to start in production with `AUTH_MODE=dev`.

## Verify after deploy

- Coolify shows both services healthy (`/health` on the API, `/` on the web).
- `https://academics.aaditechnology.com/` loads; opening a lesson page without signing in redirects to the Aadi sign-in page.
- Sign in with a person of a company that has the subscription. The first person of a company becomes its admin.
- Create a lesson, import the sample package from `docs/user-guide/sample/`, approve, generate a video (Colab voice), upload narration, watch the progress, download the MP4.

## Operations

- **Migrations** run at every API start and are repeatable. A failed migration stops the API from starting, so nothing runs against a half-migrated database.
- **Backups:** the `aadi_academic` database and the `academic_storage` volume (imported packages and finished videos). Both are needed to restore.
- **Rollback:** redeploy the previous commit. Migrations are additive; do not downgrade the database without a backup.
- **Uploads:** nginx allows 200 MB bodies (packages and narration ZIPs).
- **Rotating secrets:** `VIDEO_ENGINE_API_KEY` must be changed in both the engine and Academic apps, then both redeployed. Changing `SESSION_SECRET` signs everyone out.
- **Sessions:** an 8-hour signed cookie. People removed from Identity keep access to the app until the cookie expires (no revocation check yet).

## Known limits

- No refresh of the Identity token and no revocation check (see above).
- The Colab voice needs a manual notebook run per language version; Hindi and Marathi voice quality has not been validated (see the POC report).
