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
  lake_id text not null default 'neumuehler',
  description text,
  created_at timestamptz not null default now()
);

-- Multi-lake support: run this against an existing database that predates
-- the lake_id column (safe to re-run, only adds the column if missing).
-- All markers created before multi-lake support belong to Neumühler See,
-- hence the default.
alter table public.markers add column if not exists lake_id text not null default 'neumuehler';
create index if not exists markers_lake_id_idx on public.markers (lake_id);

-- Free-text marker notes: run this against an existing database that
-- predates the description column (safe to re-run).
alter table public.markers add column if not exists description text;

-- RLS is enabled with NO policies attached on purpose: the anon/public API
-- key therefore has zero direct access to this table. The only way in is
-- through the markers-api Edge Function, which authenticates with the
-- service-role key (which bypasses RLS) after checking the shared PIN.
alter table public.markers enable row level security;
