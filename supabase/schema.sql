-- ROCmPorter Agent — Supabase schema
-- Run this in the Supabase dashboard: SQL Editor -> New query -> paste -> Run.

-- 1) Profiles: one row per user, holds their plan.
create table if not exists public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text,
  plan text not null default 'free',           -- 'free' | 'pro' | 'team'
  stripe_customer_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists "profiles are viewable by owner" on public.profiles;
create policy "profiles are viewable by owner"
  on public.profiles for select
  using (auth.uid() = id);

drop policy if exists "profiles are updatable by owner" on public.profiles;
create policy "profiles are updatable by owner"
  on public.profiles for update
  using (auth.uid() = id);

-- 2) Auto-create a profile row whenever a new auth user signs up.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- 3) Scans: history of repositories a user has scanned.
create table if not exists public.scans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  repo_url text not null,
  repo_name text,
  score int,
  risk_level text,
  findings_count int default 0,
  created_at timestamptz not null default now()
);

alter table public.scans enable row level security;

drop policy if exists "scans are viewable by owner" on public.scans;
create policy "scans are viewable by owner"
  on public.scans for select
  using (auth.uid() = user_id);

drop policy if exists "scans are insertable by owner" on public.scans;
create policy "scans are insertable by owner"
  on public.scans for insert
  with check (auth.uid() = user_id);

create index if not exists scans_user_id_created_at_idx
  on public.scans (user_id, created_at desc);

-- v2: store the full scan report so users can reopen past reports.
alter table public.scans add column if not exists report jsonb;

-- v3: Razorpay billing — plan expiry + payment history.
alter table public.profiles add column if not exists pro_until timestamptz;

create table if not exists public.payments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  provider text not null,
  amount int,
  currency text,
  payment_ref text,
  status text not null default 'paid',
  created_at timestamptz not null default now()
);
alter table public.payments enable row level security;
drop policy if exists "payments are viewable by owner" on public.payments;
create policy "payments are viewable by owner"
  on public.payments for select
  using (auth.uid() = user_id);
create index if not exists payments_user_id_created_at_idx
  on public.payments (user_id, created_at desc);
