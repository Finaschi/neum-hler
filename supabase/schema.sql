-- Neumühler See — marker storage schema
-- Paste this into the Supabase SQL editor (Project → SQL Editor → New query) and run it once.

create extension if not exists pgcrypto;

create table if not exists public.markers (
  id uuid primary key default gen_random_uuid(),
  type text not null check (type in ('poi', 'catch', 'territory')),
  subtype text check (subtype is null or subtype in ('pike', 'perch', 'both')),
  x double precision not null,
  z double precision not null,
  idx integer not null,
  created_at timestamptz not null default now()
);

-- RLS is enabled with NO policies attached on purpose: the anon/public API
-- key therefore has zero direct access to this table. The only way in is
-- through the markers-api Edge Function, which authenticates with the
-- service-role key (which bypasses RLS) after checking the shared PIN.
alter table public.markers enable row level security;
