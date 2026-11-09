# Aadi Academic Video Creation — MVP PRD

**Version:** 1.0  
**Date:** 9 November 2026  
**Owner:** Aadi Technology  
**Status:** Development baseline — subject to existing-code audit

## 1. Executive summary

Aadi Academic Video Creation is a single user-facing web application for preparing, reviewing and producing academic teaching videos. It consumes video-generation capabilities from an independently hosted Aadi Video Engine.

The existing Python video-generation project will be retained under the same Git repository in a dedicated folder and treated as the starting implementation of the Video Engine. The first task is to audit it, document its current capabilities and dependencies, and expose its reusable functionality through a stable internal API. Do not rewrite the engine merely to achieve a preferred folder structure.

The Academic application owns academic concepts and workflow. The Video Engine owns video-production execution. The user experiences one application, one workflow and one interface; the service boundary is internal and invisible to the user.

## 2. Product goals

### 2.1 MVP goals

1. Create academic lesson records organised by class, subject, chapter and topic.
2. Support lesson versions in English, Hindi and Marathi.
3. Import structured lesson content produced through a human-operated ChatGPT Free workflow.
4. Preserve the existing canonical CSV columns:
   - `Slide`
   - `Module`
   - `voice_text`
   - `subtitle_text`
   - `visual_instruction`
5. Keep supplementary lesson metadata in a separate `lesson_plan.json` (or equivalent documented JSON schema).
6. Review and approve academic content before requesting video production.
7. Submit approved lesson packages to the Video Engine through an internal, versioned API.
8. Show job status, progress, failure details suitable for operators, retry action and generated video preview inside the Academic application.
9. Generate and download final MP4 and available supporting assets.
10. Validate the complete workflow with three approximately five-minute videos on the same Class 7 Science topic, one each in English, Hindi and Marathi.

### 2.2 Explicit non-goals

Do not implement in this MVP:
- Student login, student portal, LMS, enrolment or student progress.
- Teacher/student identity and full RBAC, unless a minimal existing authentication facility is already present and can be reused safely without expanding scope.
- Payments, subscriptions, billing or usage metering.
- Digital marketing workflows or social-media publishing.
- Public customer-facing Video Engine UI.
- AI API automation, browser automation or scraping of ChatGPT.
- Mandatory GPU infrastructure or a paid AI/TTS API.
- A new video editor or a rewrite of the existing video-generation project.

The unauthenticated MVP must be protected from public access through an appropriate deployment/network restriction. Do not expose an unrestricted production admin application to the public internet.

## 3. Product architecture and ownership boundaries

### 3.1 User experience

The Academic application is the only customer/operator-facing application. Users must not see a separate Video Engine dashboard, login, domain, API or manual file-transfer process.

### 3.2 Logical services

**Academic application**
- Academic structure and lesson records.
- Language versions and lesson package import.
- Academic review and approval.
- Production request initiation and status display.
- Video preview, download and lesson-to-output association.

**Video Engine**
- Existing Python video-generation code and its dependencies.
- Input package validation.
- TTS provider integration and audio generation.
- Slide/scene rendering and animation as supported by the existing code.
- Subtitle processing.
- Audio mixing and FFmpeg rendering.
- Asynchronous job execution, job status, retry and output asset references.
- Technical logs and render validation.

The Video Engine must not own academic class, subject, chapter, student or lesson-authoring workflows. It receives a domain-neutral production package and returns production results.

### 3.3 Deployment boundary

Deploy Academic frontend/backend and Video Engine API/worker as independently deployable services. They may initially run on the same Contabo VPS using Coolify and Docker. Use an internal Docker network for service-to-service calls. Do not require a second VPS or a second customer-facing domain for MVP.

### 3.4 Separate repository boundary

The Video Engine and Academic application must be maintained in **two separate Git repositories** from the beginning.

**Repository A — Aadi Video Engine**
- Owns the existing Python video-generation project.
- The original project must be retained inside this repository, under its existing folder structure wherever practical.
- Owns the engine API, job processing/worker, rendering adapters, engine tests, engine documentation and engine deployment files.
- Starts as an API-only service for this MVP. Do not build its customer-facing UI now.
- Its architecture must allow a dedicated Video Engine UI/admin product to be added later without changing the API contract or requiring the Academic application to be embedded in it.

**Repository B — Aadi Academic Video Creation**
- Owns the academic frontend, academic backend, academic database migrations, lesson/content workflows, review/approval and the Video Engine API client.
- Must consume the Video Engine only through its documented, versioned API.
- Must not copy the Video Engine source code into the Academic repository or import its Python modules.

**Shared integration contract**
- Maintain the versioned API contract and example manifests in both repositories or in a separately agreed shared contract location. The canonical contract owner is the Video Engine repository; the Academic repository may pin/reference a released contract version.
- Use environment configuration for the Video Engine base URL and service credentials.
- Do not share databases or directly query the other service's tables.

The owner will provide or confirm the two Git repository URLs. Do not create, rename, push or change Git remotes without confirmation.


## 4. Users and MVP operating model

The MVP is for a small internal content-production team.

- **Content operator:** creates lessons, imports packages and requests video generation.
- **Academic reviewer:** reviews and approves lesson content.
- **Production operator:** monitors rendering and handles failures.

These are workflow responsibilities, not a requirement to build a complete user/role administration module now. If there is no safe existing login, use deployment-level access restrictions for the MVP. Do not invent default passwords or commit secrets.

## 5. Core user workflow

1. Operator creates a lesson with class, subject, chapter, topic and target duration.
2. Operator selects a language version: English, Hindi or Marathi.
3. Application provides a structured prompt/package specification for manual use with ChatGPT Free.
4. Operator imports a ZIP or the supported structured files. The app does not automate ChatGPT.
5. Application validates required CSV columns, metadata, slide identifiers and required content.
6. Operator/reviewer checks narration, subtitles, visual instructions, learning objectives and assessment content.
7. Reviewer marks the language version approved for production.
8. Operator selects supported voice/render settings and requests video generation.
9. Academic API submits the package to the Video Engine internally.
10. Engine creates a persistent job and processes it asynchronously.
11. Academic app displays job status/progress and refreshes it automatically or through a user action.
12. On completion, the output is attached to the correct lesson and language version.
13. Operator previews, approves and downloads the MP4 and supporting assets.

## 6. Functional requirements

### 6.1 Academic structure and lesson management

- Manage classes, subjects, chapters and topics.
- Create a lesson linked to the academic structure.
- Store title, description, learning objectives, target audience/class, expected duration and source references.
- Support multiple language versions under one logical lesson.
- Each language version has its own narration, subtitles, storyboard, review status and video output.
- Use stable UUIDs or equivalent non-reusable identifiers.
- Do not hard-code only the POC topic into the application.

### 6.2 Content package import and validation

Support a documented package format containing, at minimum:

```text
lesson-package/
  lesson_plan.json
  lesson.csv
  academic_review.json       # optional until review workflow is completed
  assets/
    ...
```

- Preserve the canonical five CSV columns exactly.
- Do not silently rename, reorder destructively or drop user data.
- Validate file type, size, encoding, required columns, non-empty slide IDs, duplicate slide IDs and required narration/visual fields.
- Show actionable validation errors before submission.
- Keep source references and page references where supplied.
- Reject unsafe archive paths and disallow archive path traversal.
- Store imported original package and a normalized internal representation where practical.

### 6.3 Academic review

- Review script, subtitle text, visual instructions, objectives, source references and quiz questions.
- Support Draft, In Review, Changes Required, Approved and Rejected statuses.
- Keep approval separate from render completion.
- Record reviewer note and timestamp; do not require a complex audit framework in MVP.
- Prevent production submission unless the language version is approved, except where a clearly labelled administrator override is explicitly approved in the product design.

### 6.4 Video Engine integration

The Academic application must use the Video Engine API; it must not import or directly call the engine's internal Python modules.

Minimum versioned internal endpoints (final names may be adjusted after audit):

- `GET /api/v1/capabilities` — supported formats, languages, voice providers, voices and templates.
- `POST /api/v1/video-jobs` — submit a production package and configuration.
- `GET /api/v1/video-jobs/{job_id}` — status and progress.
- `POST /api/v1/video-jobs/{job_id}/retry` — retry eligible failed jobs.
- `POST /api/v1/video-jobs/{job_id}/cancel` — cancel where supported.
- `GET /api/v1/video-jobs/{job_id}/assets` — output asset metadata and retrieval references.

Requirements:
- Use versioned JSON schemas and document them in `contracts/`.
- Use service-to-service authentication and private networking.
- Do not expose engine secrets to the browser.
- Persist job ID mapping to academic lesson version ID.
- Make job submission idempotent using an idempotency key so repeated clicks/network retries do not create duplicate renders.
- Handle timeout, unavailable engine, invalid input, worker failure and partial completion.
- Use asynchronous workers; never render inside a synchronous web request.
- Store status transitions and useful failure codes.
- Do not couple the two applications through direct cross-database queries.

### 6.5 Existing Video Engine reuse

Audit the existing Python project before implementation.

Inventory:
- Current folder structure and entry points.
- CSV parser and current schema.
- Azure Speech/TTS integration.
- Audio generation and mixing.
- Subtitle generation/burning.
- Slide/image/visual generation.
- FFmpeg commands and output settings.
- Existing batch/CLI workflows.
- Dependencies, licences and environment variables.
- Existing test coverage and sample inputs/outputs.
- Storage paths, temporary files and cleanup behaviour.

Preserve working functionality. Azure Speech must remain available as an optional fallback if it already works; do not remove it while evaluating local TTS. Local TTS and Colab support should be implemented only to the extent supported by the existing project and approved scope. Colab is a manual optional execution path, not a permanent production server and not a required dependency for the first integration if it delays the POC.

If the existing engine is currently a script/CLI, expose it through a thin API/job adapter. Avoid rewriting rendering internals. Keep a documented CLI path for local diagnosis where practical.

### 6.6 Video output and assets

- Preserve the existing output capability unless the audit proves a change is required.
- Support MP4 output and return metadata such as duration, resolution, frame rate, file size and checksum where practical.
- Keep generated video/audio/subtitle assets associated with the engine job and academic language version.
- Use a storage abstraction so local disk can be used for initial testing and an S3-compatible/Backblaze-compatible object store can be configured later.
- Do not make public permanent URLs the only asset-access mechanism.
- Do not introduce CDN or paid storage dependency for the POC unless needed.
- Avoid deleting source or intermediate assets until the job is complete and retention behaviour is defined.

### 6.7 Production UI

Within the Academic application provide:
- Lesson list with class, subject, topic, languages and status.
- Lesson detail and language-version tabs.
- Import/validation experience.
- Academic review experience.
- Generate video action.
- Production status and progress.
- Retry action for eligible failures.
- Video preview and download.
- Clear operator-facing errors and a link/reference to diagnostic job information.

No separate engine UI is required for customers. A minimal internal health/diagnostic endpoint or admin-only operational page is acceptable if necessary, but avoid building a second product UI.

## 7. Future compatibility requirements — foundations only

The MVP must avoid decisions that would force a major redesign later, but must not implement future modules now.

### 7.1 Multiple client applications

Keep the Video Engine API domain-neutral. It must accept a production manifest rather than academic-specific database objects. Include a caller/application identifier and external reference in the job metadata for correlation, but do not implement usage metering or billing.

### 7.2 Future video variations

A future Aadi Video Service may need to take an existing video/project and create variants, such as:
- Same visuals and narration, but different on-screen text.
- Same video with subtitles removed.
- Same content with a different subtitle language.
- Same project with a different voice/narration.
- Different aspect ratio or output resolution.

Do not implement these variant features in MVP unless already supported. However:
- Preserve source lesson package, scene/slide data and render configuration alongside outputs.
- Keep text, narration, subtitles, visual assets and render settings as separate data/assets where the current engine permits.
- Do not flatten all content into a single irrecoverable video file.
- Record the source job/project reference and render configuration for each output.
- Design the manifest with optional versioned fields and stable asset IDs so future variant jobs can reference an earlier project/output.
- Audit whether the existing engine can regenerate from saved source assets. Document gaps and the least expensive future extension path.

### 7.3 Future student portal

- Keep academic lesson, language version, video asset and assessment data separately addressable.
- Include publication-ready status fields, but do not implement student access.
- Keep organization ownership as a future-compatible nullable field only if it does not complicate the current schema.
- Do not implement tenant isolation, student progress, enrolment or payments now.

## 8. Non-functional requirements

- Maintainable modular code with clear service boundaries.
- Versioned and documented API contracts.
- Secure upload handling and archive extraction.
- Secrets only through environment variables/Coolify secrets; never commit `.env` files or credentials.
- Structured logs with correlation IDs across Academic API and Video Engine jobs.
- Health/readiness endpoints for deployed services.
- Persistent job state so a process restart does not lose submitted jobs.
- Graceful handling of worker restart and interrupted rendering.
- Database migrations must be repeatable and documented.
- Basic automated tests for package validation, API contracts, job submission/status and end-to-end sample generation.
- No hard-coded hostnames, tokens or local absolute paths.
- User-facing errors must not expose stack traces or secrets.

## 9. Deployment and Git requirements

### 9.1 Git repository

- Maintain two separate repositories: Aadi Video Engine and Aadi Academic Video Creation.
- Inspect Git status, branches, remotes, ignored files and history independently in each repository.
- Keep the original Python video-generation project in the Video Engine repository. Do not copy it into the Academic repository.
- Do not overwrite or delete the original project.
- Do not commit secrets, generated large media, temporary files, caches, virtual environments or local databases.
- Add suitable `.gitignore`, `.env.example`, README and architecture documentation to each repository.
- Do not create either GitHub repository, change remotes, push code or publish secrets without confirming each target repository/remote and obtaining the user's explicit approval if credentials or permissions are needed.
- If either repository already exists, inspect and preserve its history and current work.

### 9.2 Coolify deployment

Target: existing Contabo VPS managed by Coolify.

- The two products must have separate Git repositories and separate Coolify application/resource deployments.
- Video Engine API and worker are deployed from the Video Engine repository.
- Academic frontend and backend are deployed from the Academic repository.
- The Video Engine starts API-only; its own UI can be added to its repository and deployment later.
- Both deployments may share the same VPS and private Docker network initially.

- Provide Dockerfiles and a production Compose configuration compatible with Coolify.
- Deploy Academic frontend, Academic API, Video Engine API and Video Engine worker as separate services.
- Initially use one VPS and internal Docker networking.
- Configure persistent volumes for required data and temporary render work.
- Use existing PostgreSQL infrastructure if suitable; do not silently create or assume a production database.
- Configure engine API base URL through environment variables.
- Provide health checks, restart policies, resource notes and deployment/runbook documentation.
- Expose only required public application routes. Keep Video Engine internal.
- Provide a staging/local verification procedure before production deployment.
- Do not run destructive database operations or overwrite a live deployment.
- Do not claim deployment succeeded until the actual Coolify deployment and smoke tests confirm it.

### 9.3 Configuration placeholders

Use documented placeholders for values not known to the developer:
- Git repository URL/owner.
- Coolify project/resource identifiers.
- Public application domain.
- PostgreSQL connection details.
- Object storage credentials/bucket.
- Service-to-service secret.
- TTS provider configuration.

Ask the owner for missing values at the point they are required. Never guess credentials, domains or repository names.

## 10. MVP acceptance criteria

1. Existing video project is preserved and its current baseline operation is documented.
2. Academic application can create a lesson and three language versions.
3. Import validator accepts a valid package with the canonical CSV columns.
4. Invalid or incomplete packages show clear errors.
5. Reviewer can approve a language version.
6. Approved package can be submitted to the Video Engine through the API.
7. Job remains visible after page refresh and service restart.
8. Duplicate submission does not create duplicate jobs when the same idempotency key is used.
9. User can monitor progress and retrieve the resulting MP4 from the Academic UI.
10. Engine failure is shown clearly and eligible jobs can be retried.
11. Three five-minute POC videos (English, Hindi, Marathi) can be generated using one shared topic.
12. Academic app has no direct dependency on Video Engine internal Python imports or database tables.
13. Both applications can be deployed as separate services on the same Coolify-managed VPS.
14. Video Engine endpoints are not publicly exposed unnecessarily.
15. Repository includes setup, configuration, deployment, API contract and troubleshooting documentation.

## 11. Proof-of-concept content

Initial validation topic: **Class 7 Science — Nutrition in Plants / Photosynthesis**.

Produce three language versions:
- English
- Hindi
- Marathi

Target duration: approximately five minutes each.

The POC must evaluate:
- Academic correctness and reviewer approval.
- Language quality and pronunciation.
- Narration and subtitle alignment.
- Visual clarity and animation quality supported by the current engine.
- Video rendering reliability and repeatability.
- End-to-end integration without manual file copying between applications.

## 12. Delivery phases and governance

### Phase 0 — Audit and architecture proposal
- Audit existing video project and repository.
- Run current baseline workflow.
- Identify reusable components, gaps and risks.
- Propose repository layout, service boundary, API contract and deployment approach.
- Produce a file-change plan and estimate.
- Stop for owner approval before implementation.

### Phase 1 — Video Engine service adapter
- Preserve existing engine.
- Add minimal API/job adapter and worker execution.
- Add contract tests and local run instructions.

### Phase 2 — Academic MVP
- Academic structure, lesson/language versions, package import and validation.
- Review and approval workflow.

### Phase 3 — Integration and production workflow
- Job submission/status/retry/output integration.
- Unified UI and error handling.

### Phase 4 — POC, deployment and handover
- Generate the three target videos.
- Deploy through Coolify after approval.
- Run smoke tests and document handover.

### Governance
- Work one micro-sprint at a time.
- Maximum 20 new files and 10 modified files per micro-sprint unless owner explicitly approves an exception.
- Before each sprint, state scope, files expected to change, risks and tests.
- Do not start the next sprint until the current sprint is reviewed and approved.
- Preserve working functionality and run relevant regression tests.
- Every sprint must have a concise demo/verification record. For completed product sprints, provide a short walkthrough video where practical and maintain one consolidated Excel reference containing sprint, feature, test evidence, demo location, test credentials only if safe/non-secret, and known issues. Never place real secrets in the Excel.
- Report PASS, FAIL or BLOCKED honestly. Do not hide pre-existing failures.

## 13. Required project documentation

Maintain:
- `README.md` — setup and project overview.
- `docs/architecture/SYSTEM_ARCHITECTURE.md`
- `docs/architecture/VIDEO_ENGINE_API.md`
- `docs/audits/EXISTING_VIDEO_PROJECT_AUDIT.md`
- `docs/deployment/COOLIFY_DEPLOYMENT.md`
- `docs/runbooks/VIDEO_JOB_TROUBLESHOOTING.md`
- `docs/implementation/SPRINT_TRACKER.xlsx` (create when implementation starts, not as a substitute for the PRD).

## 14. Open decisions to confirm during audit

Do not guess these:
- Actual existing video project folder name and entry point.
- Whether existing code currently runs as CLI, script, web app or a combination.
- Current database and job persistence approach.
- Current TTS providers and supported language/voice quality.
- Current output dimensions and rendering profiles.
- Existing storage location and whether object storage is already configured.
- Target Git remote/repository.
- Coolify project/resource, domain and production database settings.
- Whether a minimal login already exists and can safely be reused.

The audit should recommend defaults and list only decisions that genuinely require owner input.
