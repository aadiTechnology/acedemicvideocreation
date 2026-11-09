# Handover: Academic Video Creation and Video Engine

Date: 2026-11-09. Everything below was built and checked in this working session. Items marked **not verified** were not run.

## 1. Architecture and service boundaries

```
Browser -> academics.aaditechnology.com (academic-web, nginx) -> academic-api -> PostgreSQL aadi_academic
                                                                      |-> Video Engine API (internal) -> worker -> PostgreSQL aadi_video_engine
Sign-in: Aadi Identity (id.aadiprojecttracker.aaditechnology.com), product "academics", client "academics-web"
```

- **Academic Video Creation** (`aadiTechnology/acedemicvideocreation`): lessons, language versions, import and validation, review, video requests, preview and download. Multitenant (tenant = Identity company), roles inside the product.
- **Video Engine** (`aadiTechnology/ScriptToVideo`): the original Python pipeline, preserved, plus `engine/` (API v1, PostgreSQL job store, worker). Domain-neutral; internal only.
- One PostgreSQL server (the Identity project's), separate databases and roles per service. No shared tables.
- The Academic app talks to the engine only through `/api/v1` (contract 1.1, `contracts/video-engine.v1.schema.json` in the engine repo).

## 2. Repositories and Git

| Repo | Branch | State |
|---|---|---|
| ScriptToVideo | `main` (pushed) | sprint branches `sprint-0-audit` ... `sprint-7-poc-fixes` merged by fast-forward |
| acedemicvideocreation | `main` (pushed) | sprint branches `sprint-4-foundation` ... `sprint-7-poc` merged |
| identity | `main` (pushed) | one change: postgres joins the `aadi-data` network (name configurable for the demo stack) |

## 3. Coolify

| Application | Status at handover | Public |
|---|---|---|
| `aadi-identity` (redeployed with the shared network) | running:healthy | id.aadiprojecttracker.aaditechnology.com |
| `aadi-identity-demo` (rehearsal, own network `aadi-data-demo`) | running:healthy | id-demo... |
| `aadi-video-engine` (API + worker) | running:healthy | none, internal only |
| `aadi-academic-video-creation` (web + API) | running:healthy | academics.aaditechnology.com |

Docs: `docs/deployment/COOLIFY_DEPLOYMENT.md` here and in the engine repo, `docs/runbooks/VIDEO_JOB_TROUBLESHOOTING.md` in the engine repo. Production database and roles were created through a one-off helper service (deleted afterwards); the reviewed SQL is `docs/deployment/POSTGRES_PROVISIONING.sql`.

**Secrets.** Generated passwords, the engine API key, the Identity client secret and the session secret are in Coolify's environment and in the git-ignored `Media\Academics\.env.db.local` on this machine. Nothing secret is committed. The old `Media\Academics\.env.coolify` (another app's secrets) was shown in this session: rotate those credentials.

## 4. Local setup

Academic: `README.md`. Engine: `README.md`, `.env.example`, `docker build` of the root `Dockerfile`. Tests need a local PostgreSQL (`docker run ... postgres:16-alpine`, port 15441).

## 5. Environment variables

Names and purpose only: `.env.example` in each repo; production values in Coolify.

## 6. API contract and sample

`ScriptToVideo/docs/architecture/VIDEO_ENGINE_API.md` (with the package convention) and `contracts/video-engine.v1.schema.json`. The live documentation page of a running engine is at `/docs`.

## 7. Deployment status and smoke test

| Check | Result |
|---|---|
| Engine healthy on Coolify, internal only, migrations ran with the migrator role | PASS |
| Academic healthy on Coolify; HTTPS valid; app loads; API returns 401 without a session; `/auth/login` redirects to Identity with the right client and redirect URI; Identity recognises the client (303 to its login page) | PASS (checked from outside) |
| **Sign in, create, approve, render, preview and download in production** | **NOT VERIFIED**: needs a person with an Aadi account in a company that has an `academics` subscription (owner step in Identity's admin page) |
| **Academic (production) calling the engine (production)** | **NOT VERIFIED** in production for the same reason; verified locally with the same images (see 8) |

## 8. POC results

`docs/poc/POC_REPORT.md`. Pipeline PASS for English, Hindi and Marathi (about 4 minutes each, 1920x1080, valid MP4, reproducible). **Hindi and Marathi narration NOT validated (BLOCKED)**: silent placeholder audio; the English voice is a free test voice. Scripts need expert review. The POC found and fixed two real problems (captions word by word; one-line slides).

## 9. Known limitations and variant readiness

- Slides are clean text (headline and bullets); no pictures, diagrams or animation unless images are supplied in the package.
- Colab narration is a manual step per language version; the notebook was never run; the model (AI4Bharat Indic Parler-TTS) and its licence are unvalidated.
- Latin letters inside Hindi/Marathi text have no glyph in Noto Sans Devanagari (mixed-script text needs a fallback font).
- Session is an 8-hour signed cookie: no refresh, no revocation check. No admin UI for roles (API only).
- Captions can overlap the slide footer title slightly.
- Coolify API token cannot read container logs (no `read:sensitive`).
- **Variants:** each engine job keeps `package.zip`, per-slide text layers (`NN.layers.json`), per-slide audio and the render config, so changing text, subtitles, voice or profile later is feasible without redesign (medium effort). No variant API exists yet.

## 10. Tests and builds

Engine: 45 engine tests pass (plus the older suite: 313 run earlier, 1 known failure that reads local project data). Academic: 85 backend tests pass on PostgreSQL; frontend `tsc` and build pass. Real end-to-end runs: UI to engine to worker to MP4, and the 3-language POC.

## 11. Videos and the tracker

User-guide videos (real screens, numbered click targets): `Media\Academics\docs\demos\` (`full-user-guide.mp4` is all four joined, 7.5 minutes) and engine guides in `Media\ScriptToVideo\docs\demos\`. They are git-ignored (large) and live on this machine. Written guide: `docs/user-guide/USER_GUIDE.md`. Consolidated sprint tracker: `docs/implementation/SPRINT_TRACKER.xlsx` (no secrets).

## 12. What the owner needs to do

1. Add an `academics` subscription for your company in Identity (platform admin), then sign in first so you become the company admin.
2. Run the production smoke test with the user guide.
3. Run the Colab notebook per language and listen; decide on the voice model.
4. Have the scripts reviewed; decide on visuals.
5. Rotate the credentials exposed in this session.
