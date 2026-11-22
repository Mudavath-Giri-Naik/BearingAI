# BearingAI API

## GET `/health`
Returns service health.

## GET `/api/v1/models?company=NBC`
Returns user-selectable active/available model versions. Does not return hidden candidate or archived models.

## POST `/api/v1/predict`
Content-Type `multipart/form-data`:

- `company`: `NBC` or `TIMKEN`
- `model`: an ID from `GET /api/v1/models` (optional; defaults to active model)
- `file`: 450-bin CSV with increasing frequency and nonnegative magnitude

Example:

```sh
curl -X POST http://localhost:9000/api/v1/predict \
  -F company=NBC -F model=nbc-vision-1 -F file=@sample.csv
```

Response includes prediction `GOOD`/`BAD`, `bad_score`, `decision_threshold=0.8`, model identity, evidence and warning. Bad scores are not calibrated defect probabilities. HTTP 422 for invalid input.

## Studio APIs

Local prototype requests use `x-admin-key` from the Next.js server-side proxy. When the backend is configured for Supabase mode, requests instead require a Bearer access token issued by Supabase Auth; FastAPI verifies the user with Supabase Auth and checks that `user_profiles.status='verified'` and role is `developer` or `admin`. The frontend role or UI state is not authorization.

- `GET /api/v1/studio/summary`
- `GET /api/v1/studio/models`
- `GET /api/v1/studio/datasets`
- `POST /api/v1/studio/datasets` (multipart: `company`,`name`,`file` ZIP containing GOOD/ and BAD/ folders)
- `GET /api/v1/studio/jobs`
- `POST /api/v1/studio/jobs` JSON `{"company":"NBC","family":"core","dataset_id":"..."}`
- `POST /api/v1/studio/models/promote` JSON `{"model_id":"..."}`
- `POST /api/v1/studio/models/archive` JSON `{"model_id":"..."}`
- `GET /api/v1/studio/audit`

## Web BFF proxy

Next.js provides `/api/proxy/api/v1/...` routes. Studio Google login starts with POST `/api/auth/login` and completes at `/api/auth/callback` using PKCE; access and refresh tokens are stored in HTTP-only cookies. The server-side proxy refreshes access tokens and sends the bearer token to FastAPI. Logout revokes the Supabase session when possible and clears the cookies. Local mode retains its signed cookie and static admin-key behavior.

The API still refuses Supabase startup until its SQLite registry and local model/data paths are replaced by the production PostgreSQL and Storage adapters. The OAuth integration alone does not make the complete cloud deployment ready.

## Model promotion rules

Developer must review validation metrics before promotion. The system does not automatically claim performance improvement. Moving back to a previous `available` version is a rollback. Active versions may not be archived. Artifact physical deletion is intentionally absent to preserve traceability.
