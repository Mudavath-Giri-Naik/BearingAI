-- BearingAI production registry. Apply with Supabase migrations after review.
create extension if not exists pgcrypto;

create type public.app_role as enum ('user', 'developer', 'admin');
create type public.profile_status as enum ('pending', 'verified', 'suspended');
create type public.dataset_status as enum ('uploading', 'ready', 'failed', 'archived');
create type public.training_job_status as enum ('queued', 'running', 'completed', 'failed', 'cancelled');
create type public.model_version_status as enum ('candidate', 'approved', 'archived');
create type public.model_deployment_status as enum ('active', 'rolled_back', 'retired');

create table public.user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text,
  display_name text,
  role public.app_role not null default 'user',
  status public.profile_status not null default 'pending',
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint verified_role_requires_timestamp check (status <> 'verified' or verified_at is not null)
);

create or replace function public.handle_new_auth_user()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.user_profiles(user_id, email, display_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data ->> 'name', new.raw_user_meta_data ->> 'full_name'))
  on conflict (user_id) do nothing;
  return new;
end;
$$;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_auth_user();

create table public.model_families (
  id uuid primary key default gen_random_uuid(),
  company text not null check (company in ('NBC', 'TIMKEN')),
  family_key text not null check (family_key in ('core', 'vision', 'legacy')),
  display_name text not null,
  created_at timestamptz not null default now(),
  unique(company, family_key)
);

create table public.datasets (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.user_profiles(user_id),
  company text not null check (company in ('NBC', 'TIMKEN')),
  name text not null check (length(trim(name)) between 1 and 200),
  version integer not null check (version > 0),
  status public.dataset_status not null default 'uploading',
  manifest_sha256 char(64),
  file_count integer not null default 0 check (file_count >= 0),
  stats jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(owner_id, company, name, version)
);

create table public.dataset_files (
  id uuid primary key default gen_random_uuid(),
  dataset_id uuid not null references public.datasets(id) on delete restrict,
  object_path text not null unique,
  original_path text not null,
  bearing_id text,
  label smallint not null check (label in (0, 1)),
  sha256 char(64) not null,
  byte_size bigint not null check (byte_size > 0),
  created_at timestamptz not null default now(),
  unique(dataset_id, sha256)
);

create table public.training_jobs (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.user_profiles(user_id),
  dataset_id uuid not null references public.datasets(id) on delete restrict,
  family_id uuid not null references public.model_families(id) on delete restrict,
  status public.training_job_status not null default 'queued',
  idempotency_key text unique,
  attempt integer not null default 0 check (attempt >= 0),
  lease_owner text,
  lease_expires_at timestamptz,
  logs text not null default '',
  candidate_version_id uuid,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz
);
create index training_jobs_claim_idx on public.training_jobs(status, created_at) where status = 'queued';

create table public.model_versions (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references public.model_families(id) on delete restrict,
  version text not null,
  display_name text not null,
  artifact_path text not null unique,
  artifact_sha256 char(64) not null,
  artifact_bytes bigint not null check (artifact_bytes > 0),
  status public.model_version_status not null default 'candidate',
  source text not null default 'training' check (source in ('seed', 'training', 'import')),
  training_job_id uuid references public.training_jobs(id) on delete restrict,
  dataset_id uuid references public.datasets(id) on delete restrict,
  threshold double precision not null default 0.8 check (threshold >= 0 and threshold <= 1),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  archived_at timestamptz,
  unique(family_id, version)
);
create index model_versions_select_idx on public.model_versions(family_id, status, created_at desc);

alter table public.training_jobs add constraint training_jobs_candidate_fk
  foreign key(candidate_version_id) references public.model_versions(id) on delete restrict;

create table public.model_evaluations (
  id uuid primary key default gen_random_uuid(),
  model_version_id uuid not null references public.model_versions(id) on delete restrict,
  dataset_id uuid references public.datasets(id) on delete restrict,
  evaluation_kind text not null check (evaluation_kind in ('development', 'blind', 'historical')),
  metrics jsonb not null,
  split_manifest_sha256 char(64),
  created_at timestamptz not null default now()
);

create table public.model_deployments (
  id uuid primary key default gen_random_uuid(),
  family_id uuid not null references public.model_families(id) on delete restrict,
  model_version_id uuid not null references public.model_versions(id) on delete restrict,
  status public.model_deployment_status not null,
  promoted_by uuid references public.user_profiles(user_id),
  previous_deployment_id uuid references public.model_deployments(id) on delete restrict,
  created_at timestamptz not null default now(),
  ended_at timestamptz
);
create unique index one_active_model_per_family on public.model_deployments(family_id) where status = 'active';

create table public.prediction_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.user_profiles(user_id) on delete set null,
  company text not null check (company in ('NBC', 'TIMKEN')),
  model_version_id uuid not null references public.model_versions(id) on delete restrict,
  input_sha256 char(64) not null,
  prediction text not null check (prediction in ('GOOD', 'BAD')),
  bad_score double precision not null check (bad_score >= 0 and bad_score <= 1),
  decision_threshold double precision not null default 0.8 check (decision_threshold >= 0 and decision_threshold <= 1),
  created_at timestamptz not null default now()
);

create table public.audit_logs (
  id bigint generated always as identity primary key,
  actor_id uuid references public.user_profiles(user_id) on delete set null,
  event text not null,
  entity_type text,
  entity_id text,
  detail jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index audit_logs_created_idx on public.audit_logs(created_at desc);

-- Approved status is not sufficient to serve: a deployment must point to it.
create or replace function public.is_verified_developer()
returns boolean language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.user_profiles p
    where p.user_id = (select auth.uid())
      and p.status = 'verified'
      and p.role in ('developer', 'admin')
  );
$$;
revoke all on function public.is_verified_developer() from public;
grant execute on function public.is_verified_developer() to authenticated;

alter table public.user_profiles enable row level security;
alter table public.datasets enable row level security;
alter table public.dataset_files enable row level security;
alter table public.training_jobs enable row level security;
alter table public.model_families enable row level security;
alter table public.model_versions enable row level security;
alter table public.model_evaluations enable row level security;
alter table public.model_deployments enable row level security;
alter table public.prediction_history enable row level security;
alter table public.audit_logs enable row level security;

create policy "read own profile" on public.user_profiles for select to authenticated using (user_id = (select auth.uid()));
create policy "verified developers read profiles" on public.user_profiles for select to authenticated using (public.is_verified_developer());
create policy "developers manage datasets" on public.datasets for all to authenticated using (public.is_verified_developer()) with check (public.is_verified_developer());
create policy "owners read datasets" on public.datasets for select to authenticated using (owner_id = (select auth.uid()));
create policy "developers manage dataset files" on public.dataset_files for all to authenticated using (public.is_verified_developer()) with check (public.is_verified_developer());
create policy "owners read dataset files" on public.dataset_files for select to authenticated using (exists (select 1 from public.datasets d where d.id = dataset_id and d.owner_id = (select auth.uid())));
create policy "developers manage training jobs" on public.training_jobs for all to authenticated using (public.is_verified_developer()) with check (public.is_verified_developer());
create policy "owners read training jobs" on public.training_jobs for select to authenticated using (owner_id = (select auth.uid()));
create policy "authenticated read model families" on public.model_families for select to authenticated using (true);
create policy "authenticated read approved models" on public.model_versions for select to authenticated using (status = 'approved' or public.is_verified_developer());
create policy "developers manage model versions" on public.model_versions for all to authenticated using (public.is_verified_developer()) with check (public.is_verified_developer());
create policy "authenticated read model evaluations" on public.model_evaluations for select to authenticated using (public.is_verified_developer());
create policy "developers manage evaluations" on public.model_evaluations for all to authenticated using (public.is_verified_developer()) with check (public.is_verified_developer());
create policy "authenticated read deployments" on public.model_deployments for select to authenticated using (status = 'active' or public.is_verified_developer());
create policy "developers manage deployments" on public.model_deployments for all to authenticated using (public.is_verified_developer()) with check (public.is_verified_developer());
create policy "read own prediction history" on public.prediction_history for select to authenticated using (user_id = (select auth.uid()));
create policy "developers read prediction history" on public.prediction_history for select to authenticated using (public.is_verified_developer());
create policy "insert own predictions" on public.prediction_history for insert to authenticated with check (user_id = (select auth.uid()));
create policy "developers read audit logs" on public.audit_logs for select to authenticated using (public.is_verified_developer());

-- Browser clients cannot grant roles, mutate audit history, or write model state.
revoke insert, update, delete on public.user_profiles from authenticated;
revoke insert, update, delete on public.model_families from authenticated;
revoke insert, update, delete on public.model_versions from authenticated;
revoke insert, update, delete on public.model_evaluations from authenticated;
revoke insert, update, delete on public.model_deployments from authenticated;
revoke update, delete on public.audit_logs from authenticated;

-- Private object buckets. Paths are rooted by owning user for uploaded datasets.
insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
values
  ('bearing-datasets', 'bearing-datasets', false, 62914560, array['application/zip','text/csv','application/octet-stream']),
  ('bearing-model-artifacts', 'bearing-model-artifacts', false, 536870912, array['application/octet-stream'])
on conflict (id) do nothing;

create policy "verified developers access dataset objects" on storage.objects for select to authenticated
using (bucket_id = 'bearing-datasets' and public.is_verified_developer());
create policy "verified developers upload dataset objects" on storage.objects for insert to authenticated
with check (bucket_id = 'bearing-datasets' and public.is_verified_developer());
create policy "verified developers access model artifacts" on storage.objects for select to authenticated
using (bucket_id = 'bearing-model-artifacts' and public.is_verified_developer());
create policy "verified developers upload model artifacts" on storage.objects for insert to authenticated
with check (bucket_id = 'bearing-model-artifacts' and public.is_verified_developer());

-- Freeze uploaded dataset contents and registered artifact identity. Lifecycle
-- status changes remain permitted; destructive object deletion is not exposed.
create or replace function public.reject_immutable_row_change()
returns trigger language plpgsql set search_path = '' as $$
begin
  raise exception 'This registry record is immutable';
end;
$$;
create trigger dataset_files_immutable before update or delete on public.dataset_files
for each row execute function public.reject_immutable_row_change();
create trigger audit_logs_append_only before update or delete on public.audit_logs
for each row execute function public.reject_immutable_row_change();

create or replace function public.guard_model_artifact_identity()
returns trigger language plpgsql set search_path = '' as $$
begin
  if new.artifact_path <> old.artifact_path
     or new.artifact_sha256 <> old.artifact_sha256
     or new.artifact_bytes <> old.artifact_bytes
     or new.family_id <> old.family_id
     or new.version <> old.version then
    raise exception 'Registered artifact identity is immutable';
  end if;
  return new;
end;
$$;
create trigger model_artifact_identity_immutable before update on public.model_versions
for each row execute function public.guard_model_artifact_identity();
