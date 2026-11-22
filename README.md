# BearingAI · Pulse Systems

BearingAI is an experimental bearing-signal classification application. It includes a Next.js interface, FastAPI inference API, a separate model-training worker, and preserved NBC/TIMKEN model artifacts. This repository is undergoing a staged migration from its local prototype to Vercel, Render, and Supabase.

> Research use only. Scores are not calibrated defect probabilities and this system is not validated for industrial acceptance. A fresh blind sample of physical bearings is required before safety-related use.

## Current local prototype

The existing local application remains the supported runnable path while the production data/auth adapters are being migrated.

1. Install Docker Desktop or Docker Engine with Compose.
2. Copy `.env.example` to `.env`; set strong random values for `BEARING_ADMIN_KEY`, `STUDIO_PASSWORD`, and `SESSION_SECRET`.
3. Run `docker compose up --build` from the repository root.
4. Open `http://localhost:3000`, predictions at `/analyze`, developer tools at `/studio`, and API docs at `http://localhost:9000/docs`.

The local stack uses SQLite and a shared local `storage/` volume. Do not split this configuration across cloud services. For individual processes see [deployment and local runbook](docs/DEPLOYMENT.md).

## Repository layout

- `frontend/` — Next.js 15 application and server-side API proxy.
- `backend/` — FastAPI inference API, feature extraction, and standalone training worker.
- `storage/models/` — local trained artifacts; kept out of this public repository and intended for private model storage.
- `storage/seed/` — local seed CSV corpus and frozen split manifest; kept out of this public repository.
- `supabase/migrations/` — versioned production database schema and RLS policies.
- `docs/` — architecture, API, dataset, model, migration audit, and deployment runbooks.
- `render.yaml` — Render service blueprint scaffold; do not deploy until the production-readiness checklist is complete.

## Current model behavior

- NBC defaults to Pulse Vision 1; TIMKEN defaults to Pulse Core 3.
- NBC Pulse Core 3, both Pulse Legacy 1 models, and all original model files remain in the registry/storage.
- BAD threshold is 0.80.
- Candidate training runs in `backend/app/worker.py`; it does not automatically promote a model.
- The local SQLite model loader reads trusted server artifacts and inference preserves the existing response shape documented in [API.md](docs/API.md).

## Production migration status

Read [the repository audit and migration plan](docs/MIGRATION_AUDIT.md) and [the deployment runbook](docs/DEPLOYMENT.md) before configuring cloud services. Supabase schema and private storage bucket policies are present, but the current FastAPI runtime still uses SQLite, local artifact paths, and the prototype static admin-key check. Separate Render deployments are therefore not production-ready yet. The Vercel frontend must not be pointed at a publicly exposed prototype API.

For the Supabase SQL Editor, run the migration and first-admin bootstrap steps in [SQL_EDITOR_SETUP.md](supabase/SQL_EDITOR_SETUP.md). The local `.env` file has blank Supabase credential slots; existing prototype secrets are preserved.

No cloud resources have been created and nothing has been deployed. The migration SQL must be reviewed and applied to a Supabase project by an authorized operator. Never expose `SUPABASE_SERVICE_ROLE_KEY`, database credentials, or backend secrets through `NEXT_PUBLIC_*` variables.
