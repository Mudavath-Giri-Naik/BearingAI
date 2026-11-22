# BearingAI production migration audit

Audit date: 2026-11-23

## Repository baseline

- Existing top-level directories already match the requested `frontend/`, `backend/`, and `docs/` layout. SQL migration directory `supabase/migrations/` does not yet exist.
- The workspace contains no `.git` directory, so branch, commit history, and pre-existing tracked/untracked changes cannot be determined here.
- `storage/` contains 5 trained artifacts, a 701-file CSV seed set, and `storage/seed/split_manifest.csv`. Do not move or rewrite these artifacts as part of the initial migration.
- Backend automated tests currently comprise `backend/tests/test_service.py` and `backend/tests/test_training_flow.py`. Frontend has TypeScript type-check/build scripts, but no dedicated test suite or lockfile was identified.

## Existing application paths

- Next.js 15 app routes live in `frontend/app/`; `/analyze`, `/studio`, and API auth/proxy routes are present. `frontend/app/api/proxy/[...path]/route.ts` forwards to FastAPI.
- FastAPI routes, feature extraction, SQLite registry, prediction and dataset upload are in `backend/app/service.py`; feature parsing is in `backend/app/features.py`.
- `backend/app/worker.py` is a separate process that polls SQLite for queued jobs, trains CatBoost or the NBC CNN, writes candidates under `storage/models`, and leaves promotion manual.
- Compose runs API, worker, and Next.js while mounting one shared `./storage` directory.

## Model registry and inference

- `service.py:init_db()` seeds these records when their files exist: NBC Pulse Vision 1 (`nbc_cnn.pt`, active), NBC Pulse Core 3 (`nbc_core_v3.joblib`, available), TIMKEN Pulse Core 3 (`timken_core_v3.joblib`, active), NBC Pulse Legacy 1 (`nbc_legacy_v1.joblib`, available), and TIMKEN Pulse Legacy 1 (`timken_legacy_v1.joblib`, available).
- The artifacts are loaded on prediction, not held in a fully loaded approved-model cache. Candidate files are trusted server-side joblib/Torch artifacts. Promotion flips SQLite statuses; archive blocks active versions; physical deletion is absent.
- Predictions select by company and active status by default, allow explicit active/available IDs, and retain `THRESHOLD=0.8`. CNN loading uses `weights_only=True`.
- Candidate evaluation uses a `GroupShuffleSplit` on development rows and excludes manifest `test` rows from fitting. Upload grouping uses filename heuristics; a fresh blind bearing-level holdout remains required.

## Persistence, auth, and local dependencies

- SQLite tables are `models`, `datasets`, `jobs`, `audit`, and `predictions` in `storage/registry.sqlite3`.
- Dataset ZIP contents are written to `storage/uploads/{dataset_id}`; seed CSV and split manifest are read from `storage/seed`; model binaries are read/written under `storage/models`.
- Studio browser access uses `STUDIO_PASSWORD` and an HMAC signed HTTP-only cookie (`SESSION_SECRET`) in Next.js. FastAPI studio routes instead trust `BEARING_ADMIN_KEY`; the browser does not receive this key, but there are no user identities, Supabase Auth checks, or developer role claims.
- `.env.example` now documents prototype and production variable names. `.env` exists locally and was not read or printed. `.gitignore` previously lacked explicit `.env` protection; it now ignores `.env` and `.env.*` while allowing `.env.example`.
- There is a Dockerfile per service and root `docker-compose.yml`. No Render blueprint, Supabase migration, or Vercel deployment guide for the requested architecture exists yet.

## Migration plan

1. Preserve local behavior and artifact bytes; add deployment/security documentation and explicitly ignore local secrets.
2. Add versioned Supabase schema, constraints, indexes, and RLS policies for profiles, datasets/files, jobs, model families/versions/evaluations/deployments, predictions, and audit events. Keep migrations repeatable and reviewed before applying to a project.
3. Replace shared-password identity with Supabase Auth access tokens and backend-verified roles. Keep all service credentials server-only; make developer authorization a backend decision.
4. Add private Storage buckets and immutable object references/checksums for dataset versions and model artifacts; preserve local filesystem mode for Compose development.
5. Add a durable queue/worker path and registry lifecycle operations (register, compare, promote, rollback, archive); load and verify approved artifacts before serving predictions. Never auto-promote a candidate.
6. Add Render and Vercel configuration, local Compose support, environment examples, and operational/security runbooks.
7. Run the requested existing and new tests where credentials/dependencies permit; report exact commands and outcomes without claiming unrun checks.

## Progress after initial audit

- Supabase SQL Editor migration and first-admin bootstrap scripts have been provided. A new Auth signup creates a pending user profile; it does not grant developer access.
- Next.js now has a Google OAuth PKCE start/callback flow, HttpOnly access/refresh cookies, refresh handling in the API proxy, and revocation on logout. Local password sessions remain available in local mode.
- The FastAPI studio dependency now has a Supabase-mode path that verifies the bearer token against Supabase Auth and checks the caller's verified profile role through RLS.
- The API and worker still fail closed when `BEARING_AUTH_MODE=supabase`, because the runtime's database, queue, and artifact/data storage are still local SQLite/files. This guard must remain until those adapters are migrated.

## Migration risks to resolve in implementation

- Current endpoints synchronously use SQLite SQL and local paths; deploying the current code to separate Render services would split state and is unsafe. Supabase support must replace these production persistence paths rather than merely adding SQL tables.
- A Render worker and web service need durable queue claiming/leases, idempotency, and object storage; the existing SQLite polling loop is only safe with one shared local database.
- The API contract should remain stable while studio authentication changes. Existing front-end proxy and studio API must be migrated together.
- The included models are trusted local binaries; they must be checksum-registered before production deployment, and never silently retrained or overwritten.
