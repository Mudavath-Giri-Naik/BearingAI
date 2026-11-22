# BearingAI architecture

## Local

```text
Browser (http://localhost:3000)
        |
        v
Next.js public site + private Studio
        |  server-side proxy and signed developer cookie
        v
FastAPI (:9000)  <---->  SQLite /storage/registry.sqlite3
        |                   |
        v                   v
Versioned model artifacts     Datasets and immutable split manifest
        ^                   |
        |                   v
Training worker <--------- queued jobs
```

- The browser never gets `BEARING_ADMIN_KEY`; only Next.js server forwards it for requests with verified signed studio sessions.
- Public pages only access GET models and POST predict; studio routes return 401/403 without developer credentials.
- New datasets must not overlap frozen test hashes or bearing IDs. They get versioned in `storage/uploads/{dataset_id}`.
- Models have `active`, `available`, `candidate` or `archived` lifecycle states. Active selection switches in one SQLite transaction. Prediction uses a snapshot of a model row.
- Worker trains from original **development** files plus the new dataset. It NEVER trains on frozen original test files. Candidate model selection uses one internal grouped development split.
- Retrospective 70-file benchmark is descriptive and exposed; a fresh blind bearing test is required to validate real-world performance.

## Production-scale upgrade

This package is designed to run as a **single-host prototype**, not an HA production cluster. To deploy to Railway/Render or multiple hosts:

1. Move SQLite state to PostgreSQL with a migration and explicit transactional lifecycle constraints.
2. Move `storage/models` and new dataset artifacts into S3-compatible object storage with signed checksums.
3. Separate worker resources; place training in an async queue and control concurrency, resource caps, cancellations and job timeouts.
4. Introduce real user identity, admin RBAC, invitation flow, abuse protection, antivirus, audit immutability and backups.
5. Keep model binaries private and load only verified trusted artifacts. PyTorch checkpoints use `weights_only=True`; joblib remains trusted-server-only.
6. Configure HTTPS, secure cookies, network ACLs, private API URLs, monitoring and rollback playbooks.

Never expose `BEARING_ADMIN_KEY` or `STUDIO_PASSWORD` in client-side environment variables (`NEXT_PUBLIC_*`).
