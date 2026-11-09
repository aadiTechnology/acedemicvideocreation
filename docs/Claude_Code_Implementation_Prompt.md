# Claude Code Implementation Prompt — Aadi Academic Video Creation MVP

You are the senior software architect and implementation engineer for Aadi Technology. Implement the attached/adjacent PRD: `docs/PRD_AADI_ACADEMIC_VIDEO_CREATION_MVP.md`.

## Mission

Create a unified Academic Video Creation web application that consumes an independently deployable Video Engine API. The existing Python video-generation project belongs in a dedicated **Aadi Video Engine repository** and must be retained there. The Academic application belongs in a separate **Aadi Academic Video Creation repository** and consumes the engine through its versioned API. Never copy the engine source into the Academic repository.

The user must experience one application and one seamless workflow. Internally, Academic App and Video Engine are separate services. The Video Engine must be API-first and reusable by future applications.

**Do not start coding immediately. Phase 0 audit and proposal must be completed first, then wait for explicit owner approval.**

## Non-negotiable constraints

1. Read the entire PRD before acting.
2. Inspect the repository, Git state, current project files and existing video-generation code before proposing changes.
3. There are two separate repositories: Aadi Video Engine and Aadi Academic Video Creation. The original Python project is placed in the Video Engine repository by the owner. Identify its actual location; do not assume a folder name.
4. Preserve the original video project and its working behavior. No rewrite, deletion, destructive move or broad refactor just to fit a preferred structure.
5. Reuse current CSV format exactly:
   `Slide, Module, voice_text, subtitle_text, visual_instruction`
6. Keep supplementary metadata in `lesson_plan.json` or a documented equivalent.
7. Do not introduce paid AI APIs, mandatory paid TTS, mandatory GPU hosting, ChatGPT automation or browser scraping.
8. Azure Speech may remain an optional fallback if already implemented. Do not remove a working provider during MVP.
9. Google Colab, if used, is a manual optional execution path; it is not a production server or mandatory dependency.
10. No student portal, student login, LMS, student progress, payments, subscription billing, usage metering or digital marketing module in this MVP.
11. Do not build a customer-facing Video Engine UI. Academic UI is the only user-facing product. A minimal internal health/diagnostic endpoint is allowed.
12. Academic backend must call Video Engine via its versioned API. It must not import engine Python internals or query engine database tables directly.
13. Video Engine must be domain-neutral: no class/subject/student/campaign business logic.
14. Do not expose Video Engine publicly unless there is a documented technical need. Use internal Docker networking and service-to-service authentication.
15. Do not commit credentials, `.env`, private keys, access tokens, production URLs containing secrets or real student/personal data.
16. Do not guess GitHub repository, Coolify resource IDs, domains, DB credentials or secrets. Ask owner when required.
17. No destructive production deployment or database migration without explicit approval.
18. Follow governance: one micro-sprint at a time, max 20 new files and 10 modified files per sprint unless owner approves an exception. Green relevant tests required before proceeding.

## Phase 0 — Mandatory audit (no implementation changes)

### A. Separate repository and Git audit
- Confirm the local paths and Git remotes for both repositories:
  1. Aadi Video Engine repository (contains the original Python project).
  2. Aadi Academic Video Creation repository (new or existing Academic application).
- Inspect each repository root and project tree independently.
- Run `git status`, inspect current branch, remotes, recent commits, `.gitignore`, untracked files and large files in each repository.
- Identify the original video project location inside the Video Engine repository.
- Do not copy engine code into the Academic repository.
- Do not reset, clean, checkout destructively, rewrite history or change either remote.
- Check for secrets accidentally present; report paths without printing secret values.
- Identify how to preserve original project history and avoid committing generated media, virtual environments, caches and secrets.

### B. Existing video project audit
Trace and document:
- Entry points and current run command.
- CSV parsing and schema.
- Azure Speech/TTS integration.
- Audio generation, mixing and background music.
- Subtitle generation and burn-in.
- Slide/image/visual creation.
- FFmpeg invocation and output settings.
- Temporary and output folder structure.
- Error handling, retries, batch processing and cleanup.
- Storage and configuration.
- Dependencies, model weights, licence constraints and environment variables.
- Existing tests and representative sample inputs/outputs.
- Current language/voice support, especially English, Hindi and Marathi.
- Current limitations that affect the three-video POC.

Run a baseline generation using existing sample data if possible. Do not incur paid service charges without owner approval. If credentials or external services are unavailable, mark the test BLOCKED and explain.

### C. Architecture proposal
Propose the smallest safe implementation architecture:
- Academic frontend and backend.
- Video Engine API and asynchronous worker.
- Internal API communication and authentication.
- Persistent job tracking and idempotency.
- Input package and output asset contracts.
- Storage abstraction.
- Coolify/Docker deployment on the existing Contabo VPS.
- Future variant readiness: preserve scene/storyboard/source assets, narration, subtitles, text and render configuration separately where practical so later jobs can change text, remove subtitles, change voice/language or output format without rebuilding the entire product architecture.
- Future multi-client compatibility through caller application ID/external reference, without usage metering or billing now.

Do not over-engineer. A modular monolith inside each service is acceptable. Separate deployments do not require separate VPS instances.

### D. Phase 0 deliverables
Create/update only audit/design documentation, within sprint file limits. Place each document in the repository it governs:
**Video Engine repository**
1. `docs/audits/EXISTING_VIDEO_PROJECT_AUDIT.md`
2. `docs/architecture/VIDEO_ENGINE_API.md` (proposed canonical API contract)
3. `docs/architecture/VIDEO_ENGINE_ARCHITECTURE.md`
4. `docs/implementation/ENGINE_IMPLEMENTATION_PLAN.md`

**Academic repository**
5. `docs/architecture/ACADEMIC_INTEGRATION_ARCHITECTURE.md`
6. `docs/implementation/ACADEMIC_IMPLEMENTATION_PLAN.md`

Also provide a proposed tree for each repository and explain how the Academic repository pins/references the Video Engine API contract version.

Report:
- What can be reused unchanged.
- What needs a thin adapter.
- What needs modification and why.
- What must not be changed.
- Baseline test/generation result.
- Exact files expected to change in Sprint 1.
- Any owner decisions needed.

**Stop after Phase 0. Do not implement until the owner explicitly approves the plan.**

## Implementation phases — only after approval

### Sprint 1 — Minimal Video Engine service adapter (Video Engine repository only)
- Keep existing Python video pipeline intact.
- Add the smallest practical API adapter around it.
- Add versioned endpoints, request/response schemas and capability discovery.
- Submit a job and execute it asynchronously using a persistent job mechanism appropriate to the existing stack.
- Add idempotency to job submission.
- Persist job status across process restarts.
- Return status/progress and output asset metadata.
- Add retry for eligible failures and cancellation only if safely supported.
- Keep the engine's existing CLI/script workflow usable where practical.
- Add tests for schemas, validation, job lifecycle and error cases.
- Do not add academic concepts to the engine.

### Sprint 2 — Academic application foundation (Academic repository only)
- Create academic frontend and backend using existing repository conventions where possible.
- Implement class, subject, chapter, topic, lesson and language-version records.
- Use stable IDs.
- Store lesson source package and normalized metadata.
- Do not implement student/LMS functionality.

### Sprint 3 — Content import and academic review (Academic repository only)
- Import supported ZIP/CSV/JSON package.
- Preserve canonical CSV columns.
- Validate file structure, encoding, slide IDs, required fields and safe archive paths.
- Provide useful validation errors.
- Add review states Draft, In Review, Changes Required, Approved and Rejected.
- Separate academic approval from video completion.

### Sprint 4 — Seamless Academic-to-Engine integration (changes may be required in both repositories; keep each change in its owning repo)
- Build Academic-side Video Engine client.
- Submit only approved language versions.
- Map academic lesson version ID to engine job ID.
- Use internal service URL and secret from environment configuration.
- Do not expose service credentials to frontend.
- Show progress, errors, retry, preview and download within the Academic UI.
- Handle timeouts and duplicate clicks safely.
- Do not require user to upload/download files between the two services.

### Sprint 5 — POC validation
Generate three approximately five-minute Class 7 Science videos on Nutrition in Plants / Photosynthesis:
- English
- Hindi
- Marathi

Validate script correctness, language pronunciation, subtitle sync, visuals/animation quality, MP4 validity, duration, resolution and reproducibility. Do not claim success if a language's TTS or quality is not validated.

### Sprint 6 — Separate Coolify deployments and handover
- Create production Dockerfiles and Coolify-compatible deployment configuration in each repository.
- Deploy the Video Engine API and worker from the Video Engine repository as one independently managed Coolify application/resource group.
- Deploy Academic frontend and Academic API from the Academic repository as a separate Coolify application/resource group.
- Initially use same Contabo VPS and private Docker network.
- Configure persistent volumes and health checks.
- Use existing PostgreSQL only after confirming configuration and ownership. Avoid silently provisioning a new production database.
- Expose only Academic UI/API routes required by the product. Keep engine internal.
- Add `.env.example`; never commit real `.env`.
- Document Coolify setup, environment variables, volumes, domain, migrations, backups, health checks and rollback.
- Test deployment and smoke-test the complete create → approve → render → preview/download flow.

## Required service contract principles

The precise schema must be finalized in Phase 0, but it must support:
- `GET /api/v1/capabilities`
- `POST /api/v1/video-jobs`
- `GET /api/v1/video-jobs/{job_id}`
- `POST /api/v1/video-jobs/{job_id}/retry`
- `POST /api/v1/video-jobs/{job_id}/cancel` only if supported
- `GET /api/v1/video-jobs/{job_id}/assets`

A job should carry:
- schema/API version
- caller application identifier
- external reference (Academic lesson-version ID)
- idempotency key
- input package/asset references
- language
- voice/render configuration
- output profile
- optional source project/job reference for future variants

Do not force this illustrative list onto the existing engine if audit reveals a better compatible design. Document deviations.

## Future video variants — architecture only in MVP

The future service may reuse a generated video project to:
- Replace only on-screen text.
- Remove or replace subtitles.
- Change subtitle language.
- Change narration/voice.
- Change aspect ratio/resolution.

Do not implement those features now. Preserve editable source inputs and per-scene data where possible. Avoid a design that stores only a flattened MP4 and discards the source package. During audit, report which variants the current code can support with low, medium or high effort.

## Testing and quality gates

For every sprint:
- State scope, expected files, risks and acceptance tests before coding.
- Run focused tests and relevant existing regression tests.
- Run lint/type checks/build where applicable.
- Report PASS / FAIL / BLOCKED honestly.
- Never suppress or silently fix unrelated pre-existing failures.
- Do not proceed to the next sprint until owner reviews and approves.
- Provide a concise demo/verification record. For completed product sprints, provide a short walkthrough video where practical and maintain one consolidated Excel sprint reference. Never include real secrets or production credentials in the Excel.

## Git publishing rules — two repositories

- Treat the Video Engine and Academic application as two separate Git projects with independent history, branches, remotes and releases.
- First inspect existing remotes and repository history for both.
- The original Python video-generation project must remain in the Video Engine repository; never duplicate it into the Academic repository.
- Do not create either GitHub repository or push to a new remote until owner confirms both target GitHub repository URLs/owners and authorization.
- Do not force-push, rewrite history or overwrite existing branches.
- Use meaningful commits after each approved sprint.
- Before each repository push, show that repository's changed-file summary, test results, secret scan result and target branch/remote.
- Ask for approval before the first push to each repository if its destination is not already explicitly confirmed.
- If Git credentials are unavailable, provide exact commands and report BLOCKED; do not claim code was published.

## Coolify deployment rules — separate products

- Create separate Coolify application/resource deployments for the Video Engine repository and the Academic repository.
- The Video Engine deployment initially exposes only its private API and worker; no customer-facing Engine UI is required in MVP. Keep room to add its own UI later in the Video Engine repository.
- The Academic application is the user-facing product and communicates with the Engine through its configured private service URL.
- Both may run on the same Contabo VPS and private Docker network initially; separate deployments do not imply separate VPS purchases.
- Discover current Coolify deployment approach and existing Compose conventions.
- Do not assume resource IDs, domains, environment values or DB credentials.
- Prepare deployment artifacts and instructions first.
- Ask for missing configuration and explicit production deployment approval.
- Never expose internal Video Engine API through a public route by default.
- Verify health checks and the end-to-end workflow after deployment.
- If access is unavailable, provide a complete deployment handoff and report BLOCKED rather than claiming success.

## Final handover

At completion provide:
1. Final architecture and service boundaries.
2. Separate repository trees, Git commit/remote/branch details for both products.
3. Separate Coolify resource/deployment details for both products.
3. Local setup commands.
4. Environment-variable reference (names and purpose, no secret values).
5. API contract and sample request/response.
6. Coolify deployment steps and deployed service status.
7. POC video test results for all three languages.
8. Known limitations and future variant-readiness assessment.
9. Test/build results.
10. Sprint demo and consolidated Excel reference locations.

Begin with Phase 0 audit only. Wait for explicit approval before modifying implementation code.
