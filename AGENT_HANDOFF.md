# Agent handoff — Neumühler See 3D (multi-lake)

Read this before touching anything. It explains what exists, why it's built
the way it is, what's fragile, and what's mid-flight. Don't re-derive
decisions already explained here.

## What this is

A single-file (`index.html`) Three.js app: an interactive 3D bathymetry
(depth) model of lakes near Schwerin, Germany, built for mobile use by
anglers/boaters. German UI copy throughout. Originally a Claude-Design
export for a single lake (Neumühler See) — see `README.md`, `chats/`,
`project/` (a frozen archive of the original design handoff, **not**
actively maintained; all real work happens on the root `index.html`). As of
this doc, the app supports **five lakes** with a picker in the Controls
panel; see "Multi-lake architecture" below.

**The user is a first-time GitHub/Supabase user.** Assume zero familiarity —
every instruction to them needs to be literal, numbered, click-by-click.

## Git push

In this session (Claude Code on the web), `git push` to `origin`
(Finaschi/neum-hler) worked directly — no proxy issues. An earlier sandbox
session (a different environment, not this one) couldn't push at all and
worked around it by sending the file via `SendUserFile` and asking the user
to upload it manually through GitHub's web UI. If a future session finds
push blocked again, that's the fallback: edit locally, test, hand the file
to the user with exact click-by-click upload instructions, and don't claim
the live site is updated until they've confirmed the upload.

## Architecture

Single HTML file, three `<script>` blocks:

1. **Main app function** (`initApp(DATA)`, ~line 700 onward): Three.js
   scene, terrain, GPS, markers, the real-map (Leaflet) modal, depth
   readout. This used to be a synchronous IIFE that read an embedded JSON
   blob; it's now an ordinary function invoked once a `fetch()` for the
   current lake's JSON resolves (see "Multi-lake architecture"). Everything
   inside shares one closure — helper functions defined anywhere are
   hoisted and usable throughout (e.g. `loadMarkers()` is called from code
   above its own definition; that's fine, don't "fix" it).
2. **Mobile chip/panel toggle logic**: the collapsible HUD system (chips
   collapse to 44px pills on mobile, tap to expand). Has its own
   `IDS`/`closeOtherPanels()` accordion logic — on mobile, opening any panel
   closes all others. This is a separate closure from #1; it reaches into
   the DOM directly (`document.getElementById`), it does **not** share
   variables with the main app function.
3. **PWA bootstrap**: service worker registration + one-time iOS "add to
   home screen" tip (reuses the `#hint` pill element after its normal fade).

Each lake's elevation data now lives in its own file at
`data/lakes/<id>.json` (fetched at runtime, not embedded in the HTML — see
below). Don't try to read a whole one with a naive `Read` call on the
`elevation` array line; either grep for what you need or `node`/`python`
-parse it offline.

### Feature inventory (all shipped and working as of this doc)

- **Collapsible 4-corner + bottom-center HUD** (title/controls/legend/
  measure/markers), each a chip that expands to a panel. Accordion-closes
  siblings on mobile only; desktop keeps everything open. There's a
  Playwright-based overlap regression test for this (measures bounding
  rects of the visible chip/panel at several widths, asserts no pairwise
  overlap) — rebuild it before shipping any HUD/layout change. The lake
  picker was deliberately added *inside* the existing Controls panel (a
  `<select>`) rather than as a new HUD chip, specifically to avoid touching
  this overlap-sensitive layout.
- **Saveable markers** (POI / Fang / Revier-with-Hecht-Perch-Both), synced to
  a Supabase backend gated by a single shared PIN (not per-user auth — see
  `BACKEND_SETUP.md`). Optimistic UI with rollback on failure, localStorage
  cache (now per-lake, key `nms_markers_cache_v1_<lakeId>`) for offline
  viewing. The Supabase Edge Function is deployed under the URL slug
  `dynamic-task`, **not** `markers-api` — the dashboard let the user name
  the function "markers-api" for display but auto-picked a different URL
  slug. `SUPABASE_CONFIG` in `index.html` has real, working credentials
  filled in (not placeholders) — don't blank them out. Markers now carry a
  `lake_id` column; see "Multi-lake architecture" and `BACKEND_SETUP.md`
  §3b for the migration.
- **PWA**: `manifest.webmanifest`, `sw.js` (network-first, cache-fallback;
  never caches Supabase Edge Function calls — matched generically by
  `.supabase.co/functions/` in the URL, **not** by a specific function slug;
  an earlier version matched the literal string `markers-api`, which never
  actually matched the real deployed slug `dynamic-task` and was a live bug
  — fixed when multi-lake support was added, `CACHE` bumped to `v3`).
- **Real-map comparison** (`#mapModal`, "Auf echter Karte zeigen" button in
  Controls): a Leaflet + OpenStreetMap view showing our reconstructed
  shoreline (teal dots) against the lake's official shoreline (yellow line,
  `DATA.shoreline`, sourced from the same WFS survey as the depth data —
  see below). This used to be a single hand-traced-in-Google-Earth KML
  embedded as `REAL_SHORELINE`; that's gone, replaced by real per-lake
  survey data.
- **Live depth-at-position readout**: while GPS is on, the Messpunkt
  chip/panel shows depth at your *current* position, continuously, until you
  manually tap a point on the terrain (which then wins permanently for that
  session — see `updateGpsDepthReadout`/`resetGpsDepthReadout`).

## Multi-lake architecture — BUILT (5 lakes, 2026-08-05)

The app was originally Neumühler-See-only, with a hand-fitted (ICP)
georeferencing transform and a hand-digitized depth grid derived from a
scanned 1998 PDF. That's all been superseded by a much better data source
found and integrated in this session:

### The data source

`umweltkarten.lung-mv.de/dienste/wg_gewaesser` — a public WFS/WMS service
run by LUNG MV (Landesamt für Umwelt, Naturschutz und Geologie
Mecklenburg-Vorpommern), reachable via plain HTTP GET, CORS open
(`Access-Control-Allow-Origin: *`), CC BY-SA / no fees. Discovered by
checking a MV government water-portal URL the user provided — earlier
sessions had assumed this was network-blocked and, even if reachable,
probably didn't have bathymetry. Both assumptions were wrong: it's reachable
via plain `curl` (only `WebFetch`'s own fetcher got a 403; the network
itself is fine), and the `sg_tl` WFS layer ("Standgewässer: Seen:
Tiefenlinien") provides **official 1-meter depth-band contour polygons**
for ~852 fully-surveyed MV lakes (8,143 depth-band features total,
statewide). The `sg` layer gives each lake's outline polygon plus metadata
(`tmax`, `td` [mean depth], `vol`, `flaeche`, `verm_datum` [survey date],
`leff`/`beff` [effective length/width], and a direct link to the original
scanned depth-map PDF per lake via `tief_karte`).

Coordinates are in EPSG:5650 (a proper projected CRS, UTM-32N-like) — a real
geodetic reference, not something requiring approximate fitting.

### The bake pipeline (`scripts/bake_lake.py`)

Run once per lake (`python3 scripts/bake_lake.py "<Seename>" <slug>`,
requires `pyproj`, `shapely`, `numpy` — `pip install pyproj shapely numpy`),
writes `data/lakes/<slug>.json`. What it does:

1. Fetches the lake's outline + metadata from WFS layer `sg`.
2. Fetches official 1m depth-band polygons from WFS layer `sg_tl`. **Gotcha
   already hit and handled**: the `SEE_GN` (lake name) attribute is not
   always consistent between the `sg` and `sg_tl` layers for the same lake
   (e.g. `sg` has "Dümmersee", `sg_tl` has "Dümmer See" for the identical
   lake) — the script falls back to trusting a tight bbox query when the
   exact name isn't found in the bbox-filtered response, logging a warning.
   Also: **WFS `CQL_FILTER` on this server doesn't reliably filter
   server-side** — don't trust it; filter client-side after fetching, or use
   `BBOX` (which does work correctly) instead.
3. Builds nested "depth ≥ k" isobath polygons (k = 0..max, 1m steps) by
   unioning bands from the outside in, then rasterizes a grid: inside the
   lake, depth is linearly interpolated between whichever pair of isobaths
   bracket each point (a standard contour-to-DEM method — smooth, anchored
   exactly to the official contours, not blocky/stepped). Outside the lake,
   elevation is a synthetic shore ramp (there is no terrestrial DEM in this
   data source — same situation the original hand-built dataset was in, so
   this isn't a regression).
4. Computes an **exact** local geo-transform, not fitted/approximate: grid
   row0 = north edge, increasing row = south (this specific orientation is
   required — see the "why row0=north" derivation in the script's docstring
   and git history if you need to rederive it; it's not arbitrary, it's what
   makes the existing `FIT_U`/`FIT_V` formula in `index.html` — inherited
   unchanged from the old ICP-fit system — come out correct without
   modification). `FIT_U`/`FIT_V` come from sampling true geodesic
   azimuth+distance via `pyproj`'s `Geod` at the lake's own reference point,
   capturing the local UTM scale factor and meridian convergence exactly.
   Verified residual: sub-6m worst-case across the *entire* shoreline of
   Neumühler See, vs. the old ICP fit's RMS≈45m/median≈29m. `FIT_TX`/
   `FIT_TY` are always 0 by construction (grid origin = `LAT_REF`/`LON_REF`
   exactly).

Baked so far: `neumuehler`, `cramoner`, `duemmer`, `medeweg`, `nedder` (all
near Schwerin, user-requested). To add another lake: confirm it has
`see_verm=3` (fully surveyed) in the `sg` layer first — about 1600 of the
~2459 MV lakes don't, and the user explicitly wants those left out of the
picker rather than shown with a fabricated fallback shape — then run the
bake script and add the lake to the `LAKES` array in `index.html`
(`~line 690`, both places if you touch the picker UI).

### App-side integration

- `index.html`'s old single embedded `<script id="lake-data">` JSON blob is
  gone. On load, it does `fetch('data/lakes/' + getCurrentLakeId() +
  '.json')` then calls `initApp(DATA)` with the result — `initApp` is what
  used to be the top-level IIFE, essentially unchanged internally aside from
  reading `GW/GH/CELL/EL/LAT_REF/LON_REF/FIT_U/FIT_V` from `DATA` instead of
  a hardcoded/embedded source.
- **Lake switching is reload-based, not a hot in-place scene rebuild.** The
  picker (`<select id="lakeSelect">` inside the Controls panel) stores the
  chosen id in `localStorage['nms_lake_v1']` and calls `location.reload()`.
  This was a deliberate scope decision: a full teardown/rebuild of the
  entire Three.js scene graph (terrain, water, camera framing, markers, GPS
  state, measure state) in-place is a much bigger, higher-risk lift for
  marginal UX benefit over a ~1-2s reload with the existing loading screen.
  If a future request specifically asks for hot-swapping without reload,
  that's the next architectural step — it isn't built.
- Depth color ramp (`stops` in `initApp`) is scaled proportionally to each
  lake's own `DATA.stats.tmax` (reference calibration was 17.1m, Neumühler's
  depth) — without this, a 2.5m lake (Neddersee) would show almost no color
  variation and a 28m lake (Medeweger See) would clip. Same idea for the
  legend's scale labels and title-panel stats (`statMaxDepth`,
  `statLength`, `statMeanDepth`, `lakeChipMeta`) — all populated from
  `DATA.stats` at runtime now, not hardcoded HTML.
- Markers: `MARKERS_CACHE_KEY` is per-lake now; API calls pass
  `lake_id` (query param on GET, body field on POST). **The Supabase side
  needs a manual migration + Edge Function redeploy the agent cannot do
  itself** — see `BACKEND_SETUP.md` §3b. Until the user does that, GET
  requests with `?lake_id=` will just be ignored server-side (old function
  code doesn't read that param) and every lake will show every marker mixed
  together — not broken, just not scoped, until they redeploy.

## Apple-Maps-style pin markers — BUILT (2026-08-05)

Saved markers (POI/Fang/Revier), the GPS "you are here" dot, and the
tap-to-measure point all used to be literal 3D meshes (cone+sphere, ring,
cylinder) sitting in the terrain. They're now real DOM/CSS elements —
teardrop pins with an SVG icon, a pulsing blue GPS dot — kept in
screen-space sync with their 3D world position via Three.js's
`CSS2DRenderer`/`CSS2DObject` (r128's non-module build, loaded the same way
as `OrbitControls.js`: `examples/js/renderers/CSS2DRenderer.js`). This is
the standard way to get authentic 2D "always faces the camera" map-pin
styling that would be very awkward to fake with actual 3D geometry.

Two non-obvious gotchas hit and fixed while building this — don't
rediscover them:

1. **CSS2DObject visibility does not cascade from parent Group.visible.**
   Normal Three.js meshes inherit invisibility from an invisible ancestor
   (WebGLRenderer's traversal skips them). `CSS2DRenderer.renderObject()`
   does not do this — it checks each `CSS2DObject`'s *own* `.visible` only,
   and *unconditionally* recurses into every object's children regardless
   of that object's own visibility. Concretely: `measureMarker.visible =
   false` did **not** hide `mmPin` (a CSS2DObject child of that group) — the
   measure pin and GPS dot both stayed permanently on-screen from first
   load, invisible-parent or not. Fixed by overriding `.visible` on
   `measureMarker` and `gpsGroup` with `Object.defineProperty` (getter/
   setter) so setting the group's visibility explicitly cascades to the
   CSS2DObject child's `.visible` too. If you add another CSS2DObject that
   needs to be hidden/shown via a parent Group's visibility, it needs the
   same treatment — there is no free inheritance.
2. **CSS2DRenderer sets an explicit numeric `z-index` on every pin element**
   (for camera-distance sorting among pins themselves, `zOrder()` in the
   renderer source). If nothing establishes an isolated CSS stacking
   context around `#scene`, that explicit z-index escapes all the way to
   the page's root stacking context and beats the HUD panels' `z-index:
   auto` — regardless of DOM order — so a pin at the "wrong" screen depth
   would render **on top of** the Controls/Legend/etc. panels instead of
   being correctly hidden behind them, like the 3D terrain always was.
   Fixed with `#scene{ z-index:0; }` (isolates the scene subtree, containing
   CSS2DRenderer's internal z-index jockeying inside it) + `.hud{
   z-index:5; }` (so panels reliably paint above the whole scene). `#loading`
   (10) and the modals (30) were already above both. If you add more
   full-screen overlay layers, keep this ordering in mind.

Pins are visual only (`pointer-events:none` throughout, at the `#labelLayer`
level and per-element) — tapping a marker in 3D space does nothing;
removal is still only via the "Meine Marker" list, unchanged. If a future
request wants tap-to-select/tap-to-delete pins directly, that's new scope,
not built.

### Known, deliberately-reverted change (pre-dates multi-lake work)

A fix was built and verified working (disabling `controls.enabled` while
the map modal is open, because one-finger touches on the Leaflet map were
also rotating the 3D scene underneath). **The user asked to discard it** —
not because it didn't work, but because they deprioritized it. It's
reverted in the current file. If asked about "the map's touch controls feel
wrong" again, the fix is: toggle `controls.enabled = false` when `#mapModal`
opens, `= true` when it closes (in the `btnMap`/`mapModalClose`/
backdrop-click handlers).

## Testing (network is heavily sandboxed in some environments — work around it)

Most CDNs may be blocked in a given sandbox (`cdnjs.cloudflare.com`,
`unpkg.com`, `fonts.googleapis.com`, etc.), which is what the shipped app
depends on for Three.js/Leaflet/fonts. The npm registry and PyPI usually
work. The pattern that works:

```bash
npm install playwright-core three@0.128.0 leaflet@1.9.4 --no-save --silent
```
then use Playwright's `context.route()` (not `page.route()` — see gotcha
below) to intercept the CDN URLs and fulfill them with the
locally-installed copies.

**New gotcha found this session**: intercepting with `page.route()` and
`route.fulfill({path: ...})` without an explicit `cache-control: no-store`
response header can cause the *second* navigation in the same page/context
(e.g. testing a `location.reload()` after changing `localStorage`) to fail
silently — Chromium serves a broken/empty response for the intercepted
resource without erroring, and `typeof THREE` comes back `undefined` with
no console error explaining why. Fix: use `context.route()` instead of
`page.route()`, and add `headers: {'cache-control': 'no-store'}` to every
`route.fulfill()` call for a script/stylesheet that might be requested
again within the same test run. Cost a fair amount of confused debugging
before the cache was the obvious suspect — don't rediscover this.

Because the app's real functions live inside closures (not on `window`),
testing them directly requires either (a) driving the real UI via Playwright
clicks, or (b) for backend/logic-only testing, injecting a debug hook by
routing `index.html` through a string-replace that appends
`window.__test = {...}` right before the closing `}` of `initApp` — never do
this to the real shipped file, only within a test harness's in-memory route
handler.

Known test-harness gotchas already debugged (don't rediscover):
- The service worker will register during tests and then hijack subsequent
  page loads' network requests, bypassing your `route()` mocks entirely —
  either route `**/sw.js` to a 404, or unregister service workers before a
  `page.reload()`.
- The mobile accordion logic closes sibling panels automatically — e.g.
  opening the measure panel (or its auto-flash-open behavior after a GPS fix
  or tap) will close the Controls panel you had open. Tests that toggle GPS
  then immediately need to click something else in Controls must re-open
  Controls first.
- WebGL works in headless Chromium here (via swiftshader software
  rendering, on by default) — `page.mouse.click()` on the canvas genuinely
  raycasts and triggers real single-tap measurement. Double-tap-to-add-
  marker gesture simulation via synthetic events did *not* reliably
  reproduce (tried raw PointerEvents and `page.touchscreen.tap()`); presumed
  a synthetic-event fidelity limitation of the harness, not an app bug.

There's a standing overlap-regression check (measures bounding rects of the
visible chip/panel for title/controls/legend/measure/markers/hint at
360/375/414/720/1440px widths, asserts no pairwise overlap) — rebuild this
before shipping any HUD/layout change; it's caught real regressions
multiple times.

## Style/scope notes specific to this project

- Keep German UI copy; rewording for clarity is fine, don't change stated
  facts (per-lake depth/length stats now come from the official survey data
  in `DATA.stats` — trust that over any other source).
- Don't touch `project/` — it's the frozen original design export, kept for
  reference only.
- The user prefers being asked before large builds, but wants direct,
  working code delivered as committed changes, not just instructions, for
  anything touching `index.html`.
