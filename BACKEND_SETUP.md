# Backend & installable-app setup

Two things were added on top of the design: a Supabase backend so markers
survive reopening the app (and sync across devices), and PWA scaffolding so
the app can be "installed" from Safari on iPhone without the App Store.

Neither works until you complete the steps below — until then the app keeps
working exactly as before (markers just stay local to that one browser).

## 1. Create the Supabase project

1. Go to [supabase.com](https://supabase.com) → **New project**. Pick any
   name/region, set a database password (you won't need it day-to-day), and
   wait ~2 minutes for it to finish provisioning.
2. Open **SQL Editor** → **New query**, paste the contents of
   [`supabase/schema.sql`](supabase/schema.sql), and click **Run**. This
   creates the `markers` table with Row Level Security locked down (no
   public policies — see the comment in that file for why).

## 2. Deploy the markers-api function

The function lives at [`supabase/functions/markers-api/index.ts`](supabase/functions/markers-api/index.ts).

**Option A — Supabase CLI** (recommended if you're comfortable in a terminal):

```bash
npm install -g supabase
supabase login
supabase link --project-ref YOUR_PROJECT_REF   # find this in Project Settings -> General
supabase functions deploy markers-api
supabase secrets set MARKERS_PIN=choose-a-pin-here
```

**Option B — Dashboard only** (no CLI): open **Edge Functions** in the
Supabase dashboard, create a new function named `markers-api`, paste in the
contents of `index.ts`, deploy, then add `MARKERS_PIN` under
**Edge Functions → Secrets**.

Pick any PIN you like (digits, letters, whatever) — this is the single
shared passcode that gates every read/write. Anyone who knows it can see and
add markers; nobody else can (the database itself has zero public access,
see step 1).

## 3. Point the app at your project

Open `index.html`, search for `SUPABASE_CONFIG` (it's near the top of the
markers section of the script), and fill in the two values:

```js
var SUPABASE_CONFIG = {
  url: 'https://YOUR_PROJECT_REF.supabase.co/functions/v1/markers-api',
  anonKey: 'YOUR_ANON_PUBLIC_KEY'
};
```

Both values are on **Project Settings → API** in the Supabase dashboard
("Project URL" and "anon public" key — the anon key is meant to be public,
it's safe to ship in the HTML). Commit and push; GitHub Pages redeploys
automatically.

Once this is filled in, the first person to open the app (or tap the
"Marker" chip) is asked for the PIN once; after that it's remembered on that
device and markers load/save automatically in the background. A small
status line under "Meine Marker" shows sync state (synced / offline / wrong
PIN). If the connection drops, the last-synced marker list is still shown
from a local cache, but new markers can't be saved until it's back online.

## 3b. Multi-lake update — one-time steps if you already deployed the backend

The app now supports multiple lakes, and markers need to know which lake
they belong to. Two things need updating on your existing Supabase project
(both are safe to run even if you're not sure whether you've done them
before — they're written to be re-run without harm):

1. **Database**: open **SQL Editor → New query**, paste this, and run it:
   ```sql
   alter table public.markers add column if not exists lake_id text not null default 'neumuehler';
   create index if not exists markers_lake_id_idx on public.markers (lake_id);
   ```
   This adds the new column without touching your existing markers — they
   all get labelled `neumuehler` automatically, which is correct since that
   was the only lake before this update.

2. **Edge Function**: open **Edge Functions** in the dashboard, open your
   function (the one whose URL slug is `dynamic-task`, even though it's
   displayed as "markers-api"), and replace its code with the current
   contents of [`supabase/functions/markers-api/index.ts`](supabase/functions/markers-api/index.ts)
   in this repo, then deploy. The `MARKERS_PIN` secret and everything else
   stays as-is — only the code changes (it now filters/tags markers by
   `lake_id`).

If you skip step 2, the app still works, but markers from different lakes
will all mix together in the "Meine Marker" list instead of being scoped to
the lake you're currently viewing.

## 4. Installing it on an iPhone (no App Store)

Once the site is live at its GitHub Pages URL:

1. Open that URL in **Safari** on the iPhone (must be Safari, not Chrome —
   only Safari can install to the home screen on iOS).
2. Tap the **Share** icon → **Zum Home-Bildschirm** ("Add to Home Screen").
3. Launch it from the new home-screen icon. It now opens full-screen (no
   Safari address bar), has its own name/icon, and — this is the part that
   matters for GPS — iOS treats it as a distinct app in
   **Settings → [app name]**, including its own Location permission toggle.

The app shows a one-time tip about this the first time it's opened in
mobile Safari (before it's been installed). A basic service worker also
caches the app shell, so it still opens with a poor/no connection once it's
been loaded at least once — useful out on the water.

## What ships without any of this configured

If you skip all of the above, the app behaves exactly as it did before:
markers save to that one browser's local storage only, no PIN prompt ever
appears, and it's just a normal (if installable) website.
