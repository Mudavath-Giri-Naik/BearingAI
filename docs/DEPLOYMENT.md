# Deployment and operations

## Status: cloud deployment is not ready

`render.yaml` is a service blueprint scaffold, not approval to provision services. The current FastAPI API and worker both use `storage/registry.sqlite3` and local `storage/models`, `storage/seed`, and `storage/uploads`. Independent Render instances do not share these paths. Current developer auth is a shared password plus a static `BEARING_ADMIN_KEY`; it is not Supabase Auth. Deploying this code to Vercel/Render before the runtime migration would split state and bypass the requested identity model.

Do not deploy this blueprint until the production-readiness checklist at the end is complete. No resources are created by this repository change.

## Local development

The supported local flow is root `docker-compose.yml`, which runs Next.js, API, and worker against a shared local `storage/` volume. Copy `.env.example` to `.env`, replace the three local prototype secrets, and run `docker compose up --build`. This local mode is intentionally retained during migration.

For direct processes:

- API: install `backend/requirements.txt`, set `BEARING_STORAGE` to the repository `storage` directory and a local `BEARING_ADMIN_KEY`, then run `uvicorn app.service:app --reload` from `backend/`.
- Worker: run `python -m app.worker` from `backend/` with the same `BEARING_STORAGE`.
- Frontend: install frontend dependencies and run `npm run dev` from `frontend/`; set server-side `API_INTERNAL_URL`, `BEARING_ADMIN_KEY`, `STUDIO_PASSWORD`, and `SESSION_SECRET`.

## Supabase setup (schema only at this stage)

1. Create a Supabase project in your own account and configure Auth providers and redirect URLs.
2. Review `supabase/migrations/202611230001_initial_registry.sql` and apply it through the Supabase CLI or SQL editor.
3. Bootstrap initial verified developer/admin profiles through a trusted administrative process. Do not let users update their own `role`, `status`, or `verified_at`.
4. Confirm both configured buckets are private and test RLS with ordinary and verified developer accounts.
5. Preserve the existing `storage/models` artifacts. Before importing them, calculate and review checksums, register their family/version/status, and upload to the private model bucket. Keep the original binaries unchanged.

The schema defines all requested logical entities, role-aware policies, immutable dataset file records, artifact checksums, and private buckets. The API/worker have not yet been switched to this schema or Storage; a successful SQL migration alone does not make the application production-ready.

## Vercel frontend instructions (OAuth flow is implemented; API runtime is still pending)

1. Import the monorepo into Vercel and set the project root to `frontend/`.
2. Use the Next.js framework preset and configure build command `npm run build`.
3. Set `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and `SUPABASE_URL` for the Next.js server. The public anon key is safe for browser use with RLS; never set the service-role key on Vercel.
4. Add `https://YOUR_VERCEL_HOST/api/auth/callback` and `http://localhost:3000/api/auth/callback` under Supabase Auth URL Configuration → Redirect URLs. Add the Vercel host as the Site URL for production.
5. Configure Google as an enabled Supabase Auth provider and ensure Google OAuth's authorized redirect URI points to `https://YOUR_PROJECT.supabase.co/auth/v1/callback` (Supabase displays the exact provider callback URL).
6. Set `NEXT_PUBLIC_BEARING_AUTH_MODE=supabase` to display Google sign-in. The OAuth callback exchanges the PKCE code and stores access/refresh tokens in HttpOnly cookies; the API proxy refreshes tokens as needed.
7. Set `API_INTERNAL_URL` to the API origin only after its Supabase/PostgreSQL production adapter is complete. Keep `BEARING_AUTH_MODE=local` until then; the current API startup guard rejects Supabase mode because persistence is still SQLite.
8. Check preview deployments do not have production service credentials.

When public Supabase mode is selected, the Studio UI uses Google OAuth. The API independently validates the access token and requires a verified developer/admin profile. The current API startup guard still prevents production mode until persistence and artifact storage are migrated.

## Render API and worker instructions (after runtime migration)

1. Use the root `render.yaml` as a starting point and review service plans, Docker context, and start commands in the Render dashboard.
2. Provision the API as a web service and training as an independent background worker. Configure secrets separately for each service.
3. Both services must connect to the same Supabase project and private Storage buckets. The API must verify Supabase access tokens and verified roles on protected routes. The worker must claim durable Postgres jobs with leases/idempotency and must not expose an HTTP admin surface.
4. Replace local model/seed/upload paths with verified private-object downloads and checksums. Keep inference model loading atomic: publish a deployment only after the approved artifact has downloaded, checksum-verified, and loaded successfully.
5. Configure health checks, logs, worker concurrency/timeouts, upload limits, backups, alerts, and secret rotation before accepting traffic.

## Environment variables

| Variable | Where | Purpose |
| --- | --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | Vercel browser bundle | Supabase project URL; public identifier |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Vercel browser bundle | Supabase publishable/anon key; RLS remains mandatory |
| `NEXT_PUBLIC_BEARING_AUTH_MODE` | Vercel build | `supabase` to show Google sign-in; leave local mode for prototype |
| `API_INTERNAL_URL` | Vercel server runtime | FastAPI origin for the server-side proxy |
| `SUPABASE_URL` | Render API and worker | Supabase project URL |
| `SUPABASE_ANON_KEY` | Render API | Auth verification / user-scoped requests |
| `SUPABASE_SERVICE_ROLE_KEY` | Render API and worker only | Server-only privileged data and Storage operations; never browser-side |
| `SUPABASE_DB_URL` | Render API and worker | Server-side PostgreSQL connection; prefer pooled URL where supported |
| `SUPABASE_DATASETS_BUCKET` | Render API and worker | Private dataset bucket (default `bearing-datasets`) |
| `SUPABASE_MODELS_BUCKET` | Render API and worker | Private artifact bucket (default `bearing-model-artifacts`) |
| `BEARING_AUTH_MODE` | Local / Render | `local` for prototype; production mode is not implemented yet |
| `BEARING_STORAGE` | Local only | Prototype local storage root |
| `BEARING_ADMIN_KEY` | Local only | Prototype studio API key; do not use as production identity |
| `STUDIO_PASSWORD` | Local only | Prototype shared password; remove after Supabase Auth migration |
| `SESSION_SECRET` | Local only | Prototype cookie signing secret; rotate and remove after auth migration |

Never prefix service-role, database, worker, or signing secrets with `NEXT_PUBLIC_`.

## Production readiness checklist

- [ ] Supabase-backed repository replaces SQLite in both FastAPI and worker; migrations have been tested against a disposable project.
- [ ] API validates Supabase JWTs and checks verified developer/admin profile status server-side for every studio operation; no static-key bypass remains in production.
- [ ] Frontend login and proxy use Supabase Auth, secure HTTP-only session handling where applicable, CSRF protections, and no client authorization as the trust boundary.
- [ ] Dataset uploads stream to private Storage with immutable dataset/file versions, checksum validation, path authorization, size limits, and malware scanning policy.
- [ ] Existing five model artifacts are checksum-registered and privately stored; inference only selects an active deployment and verifies/loads the full artifact before serving.
- [ ] Model promotion/rollback is transactional, audited, concurrency-safe, and never automatic. Active model cannot be archived/deleted.
- [ ] Worker uses durable PostgreSQL queue claiming, leases, retries, idempotency, bounded concurrency, and bearing-level split validation; it never trains on the protected test set.
- [ ] Existing API routes and response contracts pass compatibility tests; auth, uploads, persistence, registry lifecycle, and worker tests run against disposable infrastructure.
- [ ] Vercel and Render secrets, CORS/allowed origins, rate limits, backups, monitoring, retention, and incident/rollback procedures are reviewed.
- [ ] Human operator reviews cost/plan selection and explicitly approves provisioning before cloud resources are created.
