# Run BearingAI SQL in Supabase SQL Editor

These scripts create schema/policies and bootstrap the first verified administrator. They do not create a Supabase project or deploy the application.

## 1. Apply the schema migration

1. Open the Supabase project dashboard and select **SQL Editor** → **New query**.
2. Open `migrations/202611230001_initial_registry.sql` in this repository.
3. Copy the entire file into the editor and run it once. It creates the registry tables, constraints, RLS policies, private storage buckets, and (in the current version) signup profile trigger.
4. Check the Results panel for errors. Do not proceed if the migration reports an error.

If you already ran the initial migration before the signup trigger was added, run `migrations/202611230002_auth_profile_trigger.sql` as a separate SQL Editor query now. It is safe to run again and backfills missing profiles as pending regular users; it preserves existing profile roles.

This migration file is the SQL script to run. Supabase SQL Editor does not read repository files directly; paste the file contents into a query. Keep the versioned file unchanged in the repo after applying it.

## 2. Create your Auth account

Enable the Auth provider you intend to use, then sign up the first administrator using the Supabase Auth flow. The migration's trigger creates a `user_profiles` row with role `user` and status `pending` by default.

## 3. Bootstrap the first administrator

1. Open `scripts/bootstrap_first_admin.sql`.
2. Replace both instances of `REPLACE_WITH_YOUR_AUTH_EMAIL` with the exact email used for the Auth account.
3. Paste the script into a new SQL Editor query and run it.
4. Confirm the final query shows `role = admin`, `status = verified`, and a non-null `verified_at`.

This bootstrap script must be run by a trusted project owner in SQL Editor. Ordinary users cannot grant themselves roles through the client policies. Keep the script's email targeted to the intended account.

## 4. Check schema and RLS

Run these read-only checks in SQL Editor:

```sql
select table_name
from information_schema.tables
where table_schema = 'public'
  and table_name in (
    'user_profiles', 'datasets', 'dataset_files', 'training_jobs',
    'model_families', 'model_versions', 'model_evaluations',
    'model_deployments', 'prediction_history', 'audit_logs'
  )
order by table_name;

select id, name, public
from storage.buckets
where id in ('bearing-datasets', 'bearing-model-artifacts')
order by id;

select schemaname, tablename, rowsecurity
from pg_tables
where schemaname = 'public'
  and tablename in (
    'user_profiles', 'datasets', 'dataset_files', 'training_jobs',
    'model_families', 'model_versions', 'model_evaluations',
    'model_deployments', 'prediction_history', 'audit_logs'
  )
order by tablename;
```

All listed tables should have `rowsecurity = true`, and both buckets should have `public = false`.

## Credentials to copy into `.env`

Use **Project Settings → API** for the project URL and publishable/anon key. Use **Project Settings → Database** for the connection string. The service-role key is privileged: put it only in trusted backend/worker secrets, never in a browser variable or Vercel `NEXT_PUBLIC_*` variable. The `.env` file has blank slots ready for these values; existing local prototype secrets were preserved.

The current app runtime is still on the local prototype adapter. Setting Supabase credentials does not yet switch the API/worker to Supabase; `BEARING_AUTH_MODE` should remain `local` until that runtime migration is implemented. The production-mode guard will refuse to start in `supabase` mode rather than silently using SQLite.
