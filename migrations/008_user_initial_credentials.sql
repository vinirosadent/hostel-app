-- ============================================================
-- Migration 008: User Initial Credentials tracking
--
-- Purpose: Track which users have temporary passwords still in use,
-- and when they were changed. Admin can see status (not the password
-- itself — bcrypt hashes in auth.users are one-way).
-- ============================================================

create table public.user_initial_credentials (
  id                 uuid primary key default uuid_generate_v4(),
  user_id            uuid not null unique references public.users(id) on delete cascade,
  initial_password_hint text,         -- e.g. "nome123 pattern" — never the actual password
  created_at         timestamptz not null default now(),
  created_by         uuid references public.users(id),
  password_changed   boolean not null default false,
  password_changed_at timestamptz,
  last_reset_at      timestamptz,     -- when admin last reset the password
  last_reset_by      uuid references public.users(id)
);
create index idx_uic_not_changed on public.user_initial_credentials(password_changed)
  where password_changed = false;

alter table public.user_initial_credentials enable row level security;

-- Master sees all. Users see their own row (to know if they still need to change).
create policy uic_read_master on public.user_initial_credentials
  for select using (public.is_master());

create policy uic_read_own on public.user_initial_credentials
  for select using (user_id = public.current_user_id());

create policy uic_master_write on public.user_initial_credentials
  for all using (public.is_master()) with check (public.is_master());

-- ------------------------------------------------------------
-- Trigger: when a user.must_change_password flips to false,
-- automatically mark their initial credentials row as changed.
-- ------------------------------------------------------------
create or replace function public.mark_initial_password_changed()
returns trigger language plpgsql security definer
set search_path = public
as $$
begin
  if old.must_change_password = true and new.must_change_password = false then
    update public.user_initial_credentials
       set password_changed = true,
           password_changed_at = now()
     where user_id = new.id
       and password_changed = false;
  end if;
  return new;
end; $$;

create trigger users_mark_pw_changed
  after update of must_change_password on public.users
  for each row execute function public.mark_initial_password_changed();

-- ============================================================
-- ROLLBACK
-- ============================================================
-- drop trigger if exists users_mark_pw_changed on public.users;
-- drop function if exists public.mark_initial_password_changed();
-- drop table if exists public.user_initial_credentials cascade;
