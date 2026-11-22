-- Run this in Supabase SQL Editor only after:
-- 1) the initial migration has been applied, and
-- 2) the intended administrator has created an account in Supabase Auth.
-- Replace the email below before running. This grants verified admin access.
do $$
declare
  target_email text := 'mudavathgirinaik444@gmail.com';
  target_user_id uuid;
begin
  if target_email = 'mudavathgirinaik444@gmail.com' then
    raise exception 'Set target_email to the administrator email first';
  end if;

  select id into target_user_id
  from auth.users
  where lower(email) = lower(target_email);

  if target_user_id is null then
    raise exception 'No Supabase Auth user found for %', target_email;
  end if;

  update public.user_profiles
  set role = 'admin', status = 'verified', verified_at = now(), updated_at = now()
  where user_id = target_user_id;

  if not found then
    raise exception 'Profile row missing for %. Confirm the auth user trigger ran.', target_email;
  end if;
end
$$;

-- Verify the result. This displays the selected admin's role and verification status.
select user_id, email, role, status, verified_at
from public.user_profiles
where lower(email) = lower('mudavathgirinaik444@gmail.com');
