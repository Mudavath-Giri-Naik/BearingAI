-- Safe follow-up for projects that already applied 202611230001 before the
-- Auth signup trigger was added. Existing profiles and assigned roles are kept.
create or replace function public.handle_new_auth_user()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.user_profiles(user_id, email, display_name)
  values (new.id, new.email, coalesce(new.raw_user_meta_data ->> 'name', new.raw_user_meta_data ->> 'full_name'))
  on conflict (user_id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_auth_user();

-- Backfill Auth users created before the signup trigger existed. These accounts
-- receive the table defaults (role=user, status=pending), never developer access.
insert into public.user_profiles(user_id, email, display_name)
select id, email, coalesce(raw_user_meta_data ->> 'name', raw_user_meta_data ->> 'full_name')
from auth.users
on conflict (user_id) do nothing;
