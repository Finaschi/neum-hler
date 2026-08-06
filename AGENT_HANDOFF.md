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

Baked so far (20 lakes): `neumuehler`, `cramoner`, `duemmer`, `medeweg`,
`nedder`, `schwerin_aussen`, `schwerin_innen`, `cambs`, `pinnow`, `ziegelsee`,
`heidensee`, `ostorfer_ober`, `ostorfer_unter`, `fauler`, `lankow`, `rugen`,
`trebbow`, `kirchstueck`, `wendelstorf`, `grosseichsen` (all near Schwerin,
user-requested — this was explicitly "that's all for the foreseeable
future" per the user, so don't go looking for more to add unprompted). To
add another lake: confirm it has `see_verm=3` (fully surveyed) in the `sg`
layer first — about 1600 of the ~2459 MV lakes don't, and the user
explicitly wants those left out of the picker rather than shown with a
fabricated fallback shape — then run the bake script and add the lake to
the `LAKES` array in `index.html` (`~line 825`; each entry needs `lat`/`lon`
too now, the lake's own centroid — used by the nearest-lake GPS feature,
see below — computed via a simple shoelace-formula polygon centroid over
`shoreline`, not just averaging the points).

**One lake requested by name genuinely doesn't exist as a separately
surveyed water body**: "Ziegelinnensee" — checked both the `sg` layer (no
matching `see_gn`) and the `sg_tl` bands around Ziegelsee's own bbox (no
such name there either). Told the user rather than silently dropping it or
guessing at a substitute. If asked about it again, that finding still
holds unless the WFS service adds new data.

**Three gotchas hit adding the third batch of lakes — don't rediscover them:**

1. **The "pick whichever sg_tl name-group is biggest" fallback (from the
   second batch) is not safe in dense lake clusters** — it silently grabbed
   a *completely unrelated* neighboring lake's depth data for both Ostorfer
   See basins (confirmed by a sanity check: baked max depth 0.23m against
   an official 4.5m — nowhere close). `fetch_depth_bands()` now requires the
   target `outline` polygon and picks whichever candidate name-group's
   geometry actually overlaps *that specific outline*, refusing to proceed
   (hard error, not a silent bad bake) if the best overlap is under 50%.
   When you do get an ambiguous-name warning, also double check with a
   *union of the whole matched group*, not just its shallowest band — a
   group's shallowest depth level can itself be fragmented into several
   disconnected pieces, and comparing just one arbitrary fragment
   undercounts real overlap (this exact mistake produced a false "9%
   overlap, reject" on a pair that was actually a clean 100% match once
   fixed to union the whole group first).
2. Reused from the Pinnower See case: **MV has multiple lakes sharing a
   name** — "Ostorfer See" itself has two records (`22007`="Oberer",
   `22002`="Unterer"), and my first *geographic* guess at which was which
   (closer to Schwerin = "Unterer") was simply wrong — verified correctly
   only by directly comparing each `sg` record's exact bbox against the
   `sg_tl` layer's own "Oberer"/"Unterer Ostorfer See" band bboxes (exact
   match, not fuzzy). Don't guess ober/unter (or similar directional
   names) from general geography — check the actual band data's own
   labeled bbox against each candidate record's bbox.
3. Two more even smaller gotchas: `Rugensee` is one word officially (the
   user wrote "Rugen see"), and several requested names collided with
   unrelated same-named lakes elsewhere in MV that had to be filtered out
   by `see_verm` (unsurveyed) or by checking `stalu`/centroid was nowhere
   near Schwerin (e.g. 3 of 4 "Heidensee" candidates, 6 of 7 "Fauler See"
   candidates) — always check `--see-sp` candidates print for a lake name
   you haven't specifically single-matched already, even ones that don't
   *look* ambiguous from the user's phrasing.

1. **A lake can be stored as multiple disconnected polygon parts.**
   Schweriner See is really two basins (Innensee + Außensee) joined by a
   narrow channel, and the `sg`/`sg_tl` layers store it as one record with
   a 2-part MultiPolygon — not two separate lake records. `bake_lake.py`
   now supports `--part N` (0-indexed by area, largest first) to bake just
   one part, clipping depth bands to it via `.intersection()`, plus
   `--display-name` to give that part its own name in the app. Verified the
   split makes geographic sense before committing to it: part areas (35.9M
   m² vs 27.1M m²) and centroid latitudes (part 0 further north) matched
   the real Außensee/Innensee split; deep bands (45m+) intersect only part
   0, confirming the deepest hole is really in Außensee, not an artifact of
   arbitrary clipping. **When `--part` is used, per-lake stats (tmax excepted,
   which comes from the clipped grid either way) are recomputed from the
   clipped geometry/grid instead of trusting the `sg` layer's attrs** — those
   describe the *whole* original record (both basins combined), which would
   misrepresent a single basin if reported as its own stats.
2. **MV has multiple lakes sharing the same name in different regions** —
   there are two "Pinnower See", ~200km apart, and the wrong one (near
   Ueckermünde, nowhere near Schwerin) sorts *before* the right one in the
   WFS response's document order. `fetch_lake_record()`/`main()` now accept
   `--see-sp <id>` (the "Seeschlüssel Seeprojekt" field, a stable per-lake
   ID) to disambiguate — run once without it first, it'll print every
   candidate's `see_sp`/region/centroid to stderr if there's more than one
   name match, then re-run with the right `--see-sp`. Don't assume a name
   match is unique without checking.

**Also fixed while adding these**: `scene.fog`'s density used to be a fixed
constant (`0.00012`) calibrated for Neumühler See's ~5km extent. Schweriner
Außensee is ~14km across, and the same fixed fog density fogged out almost
the entire lake to black before it was even visible — looked like the
terrain had failed to load. Fog density is now computed from
`Math.max(worldW, worldD)` at scene-setup time (`0.6084 / dist`, where
0.6084 preserves Neumühler's exact prior look — verified pixel-identical
via screenshot diff). If you bake something even bigger than Schweriner
See, this should keep scaling correctly, but double check with a
screenshot anyway.

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

~~Pins are visual only~~ — **update, same day**: saved-marker pins
(`.map-pin`, not the GPS dot or measure pin) are now clickable
(`pointer-events:auto` + a click listener added in `buildMarkerMesh`,
closing over `m` directly rather than looking it up by id later) and open
a detail modal (`#markerDetailModal`) showing the type/subtype label,
description, and a formatted "Hinzugefügt am DD.MM.YYYY · HH:MM Uhr"
timestamp, plus a delete button — see `openMarkerDetail()`/
`closeMarkerDetail()`. This needed no backend/schema change: `created_at`
was already a column with `default now()`, already returned by the Edge
Function's `select("*")`, just never surfaced in the UI before. New
markers get a client-side `created_at` set immediately on creation
(optimistic), overwritten with the server's exact value once the POST
resolves — matters for marker created *before* this feature shipped: they
already have a real `created_at` in the database (the column's always been
there with a default), so their real original creation date shows up
correctly with no backfill needed.

Marker types and species/subtype coloring: species colors (`SPECIES_COLORS`
— pike/perch/both) are shared between `catch` ("Fang") and `territory`
("Revier") markers now, not territory-only — the subtype picker
(Hecht/Barsch/Beide) shows for both types (`typeNeedsSubtype()`), pin icon
shape (fish vs. flag) is what distinguishes marker type, color is what
distinguishes species. If you touch marker colors/labels again, keep
`markerColor()`/`markerLabel()`/`MARKER_LABELS` in sync — they intentionally
key off `type+'_'+subtype` when a subtype is present, falling back to the
bare `type`.

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

## Recurring gotcha: `element.hidden = true/false` vs. a CSS rule with unconditional `display:`

Hit **three times** across this project (`.marker-sub-row`, `button.ctrl.
photo-btn`, `.marker-detail-photo`) before it got a name. The HTML `hidden`
attribute and a class selector both have specificity (0,1,0) — a tie — but
origin wins over specificity: `[hidden]{display:none}` is a User-Agent
(browser default) rule, so ANY same-or-lower-specificity author rule with
an unconditional `display:` (flex/block/whatever) beats it regardless of
which one is declared later in the stylesheet. Net effect: toggling
`el.hidden = true` in JS does nothing visually if that element (or its
class) has its own `display:` rule anywhere in the stylesheet — the
element stays fully visible, `hidden` attribute correctly set on the DOM
node and all, completely invisible to a naive DOM inspection unless you
specifically check computed style.

**Standing rule for this codebase**: any CSS selector that also targets an
element toggled via `.hidden` in JS must scope its `display:` declaration
to `:not([hidden])` — e.g. `.foo:not([hidden]){ display:flex; }` — never
just `.foo{ display:flex; }`. Before adding any new `hidden`-toggled
element, grep the stylesheet for that element's id/class and check for a
bare `display:` rule; don't wait to notice it visually (all three
instances rendered "successfully" in the sense that nothing threw — they
just silently stayed on-screen when they shouldn't have, only caught by
actually looking at a screenshot, not by the automated pass/fail checks).

## Photos on markers, nearest-lake GPS suggestion, marker type filter — BUILT (2026-08-06)

Three independent features, no interaction between them:

- **Photos**: "Foto hinzufügen" in the marker-creation modal opens the
  device's file/camera picker (`<input type=file accept=image/*
  capture=environment>`), the image is resized client-side (canvas, longer
  side capped at 1280px, JPEG quality 0.72 — a 2000×1500 test photo came
  out ~8KB) via `compressImageFile()`, base64-encoded, and sent as a
  *follow-up* request after the marker itself is created (needs the
  confirmed server-assigned marker id first, not the optimistic temp id) to
  a new Edge Function route `POST /markers-api/<id>/photo`. That route
  base64-decodes, uploads to a Storage bucket named exactly `marker-photos`
  (must be created + set Public via the dashboard — not something doable
  from SQL alone in every Supabase setup, see `BACKEND_SETUP.md` §3c),
  updates the marker's new `photo_url` column, and returns the public URL.
  Shown in the marker detail modal (`#detailPhoto`) if present; not shown
  in the "Meine Marker" list (scope decision, not a bug — list stays
  compact). Photo upload failure is non-fatal — the marker itself still
  saves, only the photo silently fails with a status-line message. No
  automatic cleanup of a marker's photo in Storage when the marker itself
  is deleted (minor known gap, acceptable for now — a small storage-usage
  leak, not a correctness issue).
- **Nearest-lake GPS suggestion**: `LAKES` entries now carry `lat`/`lon`
  (each lake's polygon centroid, shoelace formula over `shoreline` — good
  enough for "which of 20 lakes is this probably," not precision
  positioning). When live GPS puts you outside the current lake's own
  extent, `checkNearestLake()` finds the closest lake by straight-line
  distance to centroid and offers a one-tap switch if within 6km,
  dismissible per-lake for the rest of the session (`dismissedNearestLakeId`
  — resets on reload, intentionally, not persisted).
- **Marker type filter**: icon-pill row (`#markerFilterRow`, reuses the
  same `pinIconFor()` glyphs as the map pins) in "Meine Marker" filters
  *both* the list and the 3D pins' visibility together
  (`updateMarkerPinVisibility()`, called from inside `renderMarkerList()`
  so every existing call site gets it for free) — deliberately not just a
  list-only filter, since leaving non-matching pins visible on the map
  while the list hides them would be a confusing mismatch.

## Current weather (temp + wind) — BUILT (2026-08-06)

User initially asked to source this from wetteronline.de — that has no
public API, and scraping it would be fragile/likely against its ToS, so
this uses **Open-Meteo** instead (`api.open-meteo.com`, free, no key,
CORS-open — verified with a direct `curl` including an `Origin` header,
`Access-Control-Allow-Origin: *`). Explained the substitution to the user
rather than silently swapping data sources. Current conditions only, no
forecast — matches what was actually asked for; fetched once on page load
via `loadWeather()`, not polled/refreshed on a timer.

Displayed inside the **expanded** title panel only (a new `.weather-row`
below the existing stats row), not in the collapsed chip — deliberate,
same reasoning as the lake picker earlier: avoid touching the collapsed-
chip layout that the overlap-regression test cares about. Uses each lake's
centroid `lat`/`lon` already sitting in the `LAKES` array (added for the
nearest-lake GPS feature) — no new per-lake data needed.

Wind direction shown both as text (16-point compass via `compass16()`,
e.g. "aus SW") and as a rotated arrow icon (`#weatherWindIcon`, CSS
`transform: rotate(<deg>deg)`, verified against a mocked 225° response —
arrow icon is drawn pointing north/up by default and rotated directly by
Open-Meteo's `wind_direction_10m`, which is already the standard
meteorological "direction the wind is coming FROM" convention, i.e. the
icon acts like a wind vane pointing into the wind — don't add another
180° "fix" here, that would make it backwards).

**Couldn't fully verify the live network call in this sandbox** — Playwright's
browser context here gets `net::ERR_CONNECTION_RESET` hitting
api.open-meteo.com directly (same class of restriction hit earlier this
session for CDN scripts, which needed local-package routing to test at
all), even though plain `curl` from the same sandbox reaches it fine. Verified
the actual app logic thoroughly via a mocked response instead (parsing,
rounding, compass conversion, icon rotation, show/hide all checked
against known values) and left it at that — a real browser with normal
internet access should reach it exactly like the app's existing Leaflet/
OSM map tiles already do in production. If weather ever silently doesn't
show for a real user, check the Network tab for that request specifically
before assuming the code is wrong.

## Marker editing + photo-library fix — BUILT (2026-08-06)

Two small, related fixes to the marker system:

- **Markers are now editable after the fact.** Tapping a marker's detail
  modal shows a new "Bearbeiten" button (`#markerDetailEdit`) that swaps
  the view-only fields for an edit form (description textarea + the same
  photo picker used at creation time, prefilled with the existing photo
  if any) and swaps the action row for Abbrechen/Speichern
  (`enterMarkerDetailEdit()`/`exitMarkerDetailEdit()`). Saving calls a new
  `PATCH /markers-api/<id>` Edge Function route (body `{description?,
  photo_url?}`, `photo_url: null` clears the photo) plus, if a new photo
  was picked, the existing `POST /markers-api/<id>/photo` route — same
  upload path as marker creation, just re-used for an edit. **Requires
  redeploying the Edge Function** (`supabase/functions/markers-api/
  index.ts`) — the PATCH route doesn't exist on an already-deployed
  function until you paste the updated code into the Supabase dashboard
  and redeploy; walked the user through this manually since there's no
  CLI/CI deploy pipeline for it in this setup.
- **Photo picker no longer forces the camera.** The file input had
  `capture="environment"`, which pushes some mobile browsers straight to
  the camera instead of also offering the photo library — removed from
  both the marker-creation and marker-edit inputs (`accept="image/*"`
  alone still lets the browser show its native "camera or library" sheet).
  Relevant since markers (especially catches) often get logged well after
  the fact, from an existing photo, not a fresh one.

Refactored `openMarkerDetail(m)` into a `renderDetailView(m)`
(populates the read-only fields) + `openMarkerDetail(m)` (calls
`renderDetailView` and resets to view mode) split, so both the initial
open and "save then flip back to view" paths share one render function
instead of duplicating the field-population logic.

## App renamed to "Fishing Deep" — BUILT (2026-08-06)

The app's own brand name (distinct from any individual **lake's** name,
e.g. "Neumühler See" — that's real per-lake data in `LAKES` and stays
untouched) is now **Fishing Deep**, replacing "Neumühler See" as the
app-level brand. That name stopped fitting once the app grew to 20 lakes;
the logo handoff doc used "SEEKARTE 3D" as an explicit placeholder pending
a real naming decision — this is that decision, made by the user.

Touched: `<title>` and `document.title` (still lake-name-first, e.g.
`Neumühler See — Fishing Deep`, so multiple open tabs on different lakes
stay distinguishable), `<meta name="description">` (also generalized from
singular "des Neumühler Sees" to plural "mecklenburgischer Seen" — it was
already stale post-multi-lake), `apple-mobile-web-app-title`,
`manifest.webmanifest` `name`/`short_name`/`description`, and
`icons/logo-lockup.svg`'s wordmark. The depth-readout label
(`#depthLabel`, "Neumühler See · Messpunkt") and the fog-density
calibration comment near `scene.fog` were **not** touched — both refer to
the lake, not the brand.

## Sheet redesign follow-up fixes (real-device feedback) — BUILT (2026-08-06)

The first cut of the sheet redesign (below) shipped with three real bugs,
caught from an actual iPhone screenshot rather than the sandbox's
Playwright viewport (which doesn't emulate `env(safe-area-inset-top)`, so
these weren't visible in testing):

1. **Status row sat too far down** — `top:calc(14px + env(safe-area-inset-top)
   + 30px)` was carrying over spacing calibrated for the *design mockup's*
   390×844 frame (which has no real notch/Dynamic Island to dodge), so on
   a real device it stacked an extra 30px+14px below the safe area for no
   reason, leaving a dead gap under the iOS status bar. Fixed to
   `calc(env(safe-area-inset-top) + 8px)` — `#hint` retuned to match
   (`+46px`, was `+76px`).
2. **Lake-code rail removed from the main sheet entirely** — redundant
   with the lake `<select>` already in the settings sheet, and the user
   found it added clutter for no benefit now that switching lives in
   Settings. Deleted `#lakeRail`/`.lake-pill` (CSS+HTML+JS) outright, not
   just hidden — one less thing fighting for vertical space in the header.
3. **`peek` detent redefined as a real "just the depth" state** — previously
   `peek` was 168px tall but still rendered the *full* header (which, with
   the lake rail, needed ~230px+), so content overflowed the sheet's own
   box. Diagnosed as a flex layout issue: `#sheetHeader{flex:none}` never
   shrinks to fit, so at a height smaller than its natural content size the
   excess simply overflowed downward past the sheet's rounded card — while
   separately, the absolutely-positioned primary button (`bottom:26px`)
   sat at a fixed offset from the sheet's bottom regardless, landing
   directly on top of the depth value text. Rather than patch around it,
   `peek` was redefined per the user's explicit ask ("completely hidable
   to the point where you really only see the depth"): `height:108px`
   (tightly fit to handle + depth readout, nothing else) plus
   `#sheet[data-detent="peek"] #sheetScroll, ...  #sheetPrimaryWrap, ...
   .fade-rule{ display:none; }` to hide the list/button/divider outright
   instead of letting them get clipped. `DETENTS.peek` in the JS updated
   to match (108, was 168) — it's the drag-clamp floor too.

**Lesson for next time**: request (or generate) a real-device screenshot
before considering a mobile layout change done — the Playwright viewport
tests in this sandbox cannot catch `env(safe-area-inset-*)` issues since
headless Chromium has no notch to report, and this class of bug (chrome
sitting in the wrong place, content overflowing a fixed-height container)
only showed up once real hardware was in the loop.

## UI redesign — bottom sheet + mono terrain ("Nocturne") — BUILT (2026-08-06)

Full chrome replacement, from a design handoff bundle (`Neumuehler Sheet
UI.dc.html` + `Lake App Redesign v2.dc.html`, high-fidelity — colours, type
sizes, spacing, radii were final, not up for reinterpretation). Two
independent decisions, both shipped together here:

1. **Chrome**: the five floating corner panels (`#title`, `#controls`,
   `#legend`, `#measurePanel`, `#markersPanel`) and their chip/accordion
   system (`IDS`, `closeOtherPanels()`, `data-toggle`) are gone. Replaced
   with a thin top **status row** (live GPS dot + `GPS AKTIV/AUS · <temp>°
   <wind> <dir>` text, settings gear) and a single **bottom sheet**
   (`#sheet`) holding the lake-code rail, depth readout, marker list, and
   the "Marker setzen" primary button. A second **settings sheet**
   (`#settingsSheet`, same visual component, opened via the gear button)
   holds what used to be the Controls + Legend panels: lake `<select>`,
   Überhöhung slider, the three toggles, GPS status text, nearest-lake
   suggestion, Draufsicht/Zurücksetzen/Auf-echter-Karte buttons, and the
   depth legend gradient.
2. **Terrain**: the rainbow depth ramp (`stops`), land colour, scene
   background/fog, lights, and water material all moved to a single-hue
   violet-on-charcoal palette ("Nocturne": `--color-bg #161826`,
   `--color-surface #232532`, `--color-accent #9184d9`). Exact numbers are
   in the design doc, ported verbatim into `stops`/`landColor()`/the light
   and water constructors — **do not re-tune these by eye**, they're
   final.

### Sheet mechanics

`#sheet` has three detents driven by a literal `height` (not `transform` —
see below), stored as `data-detent="peek|half|full"` and mapped to CSS
rules (`#sheet[data-detent="peek"]{height:168px}` etc.), animated via
`transition:height 380ms cubic-bezier(.32,.72,0,1)`. Persisted in
`localStorage` (`nms_sheet_detent_v1`).

Drag + tap-to-cycle is bound to **`#sheetHandle` only**, not the whole
`#sheetHeader` — the header also contains the lake-rail buttons and other
interactive content, and a header-wide click listener would intercept taps
meant for those (click bubbles from the button through the header before
reaching any ancestor listener). If you're tempted to make the whole
header draggable to match the design doc's "anywhere in the header" line
literally, you'll reintroduce that bug — scope it to the handle, or
explicitly exclude interactive descendants (`e.target.closest('.lake-pill')`
etc.) if you do widen it.

**Height vs. transform**: the design doc's interaction section says
"snap with `transition: transform`", but its own static mockup sizes the
sheet via a literal `height: 432px` on the div, and the primary button is
pinned via `bottom: 26px` relative to that box. A transform-based
implementation (tall fixed 92vh box, slid up/down) would need the button
repositioned by JS at every detent, since `bottom:26px` on a box that's
always 92vh tall stays anchored to the box's own (invariant) bottom edge,
not the *visible* bottom edge. Animating `height` directly sidesteps that
— the button's `position:absolute; bottom:26px` inside `#sheet` then
naturally tracks the real bottom regardless of detent. Visually identical
result; simpler and more robust. If you revisit this, know why it's not
literally what the doc's interaction bullet says.

Only the marker list scrolls (`#sheetScroll`) — the handle, lake rail, and
depth readout live in a separate non-scrolling `#sheetHeader` so they stay
put while browsing markers, matching the doc's explicit call-out.

### Depth readout

Single source of truth is `renderDepthValue(e)` (elevation in, writes
`#depthValue`/`#depthUnit`, `+`-prefixes and `.land`-tints land elevations
same as the old measure panel did). `lastMeasurePoint` (`{x,z,idx}`)
tracks whichever point is *currently shown* — manual tap always wins and
persists (`lastMeasureIdx >= 0` guard, unchanged from before), live GPS
position fills the readout only when no manual tap has happened yet. The
**"Marker setzen" primary button** opens the marker-creation modal at
`lastMeasurePoint` via a new `openMarkerModalAtPoint(x,z,idx)` (factored
out of the old click-to-raycast `openMarkerModal(clientX,clientY)`, which
now just raycasts then delegates to it) — if nothing's been tapped/GPS'd
yet, it flashes the hint pill with a nudge instead of silently doing
nothing.

### Marker list row depth

New: each row shows the marker's own depth (`markerDepthAt()`, reads
`EL[m.idx]` the same way the depth readout does) — not present in the old
list. Description text is **not** shown in the compact row (no room at
39px row height) — tap the row (or the pin) to open the full detail modal;
wired via a delegated click listener with `data-open="<id>"` alongside the
existing `data-del="<id>"` delete button.

### Marker/species colours

Re-tinted per the design doc: `SPECIES_COLORS` pike `#b5abfc` / perch
`#cfd3e5` / both `#9184d9`. The base `MARKER_COLORS` (used only when a
`catch`/`territory` marker somehow has no subtype, or for plain `poi`) had
no doc-given values — picked neutral-200 (`#e4e7f5`) for `poi` and
accent-400 (`#b5abfc`, same as pike) for `catch` as reasonable extensions
of the same palette, not from the doc. The measure-pin stays red
(`#ff5a5a`, unchanged) — it's a temporary probe marker, semantically
distinct, and the doc doesn't mention recolouring it.

### Filter control

The old 4-button icon-pill row (`#markerFilterRow`/`.mfilter-btn`, one
button per type with its own colour) is gone — the design doc shows a
single tappable label (`ALLE`/`POI`/`FNG`/`RVR`) that cycles. Same
underlying `markerFilter` state and `updateMarkerPinVisibility()` call
from inside `renderMarkerList()`, just a different control.

### `.hud`/chip system fully removed

If you're looking for `#title`/`#controls`/`#measurePanel`/`#legend`/
`#markersPanel`/`.chip`/`.hud`/`data-toggle` — they're gone, not hidden.
`#hint` survives (still a standalone centred-top pill, just repositioned
below the new status row) — it's reused by both the "tap to set a point
first" nudge and the existing one-time iOS install tip.

### Not done / deliberately out of scope

- Didn't touch `#markerModal`/`#pinModal`/`#markerDetailModal`/`#mapModal`
  beyond what the shared CSS custom properties cascade automatically —
  the design doc's fidelity claims only cover the main sheet screen, not
  these. They now pick up the Nocturne palette for free (same `--panel`/
  `--ink`/`--accent-teal` variable names, new values) but their own
  layout/spacing is untouched.
- Didn't add drag-resize to the settings sheet (it's a simple open/close
  overlay, `transform: translateY`, matching how it behaves in the doc —
  no detents there).
- `sw.js` cache bumped to `nms-shell-v4` so this ships promptly to
  existing installs (see the iOS PWA staleness fix above for why that
  matters) — bump it again on the next `index.html`-touching change too.

## Recurring gotcha, updated: the `[hidden]` rule now also covers the sheet

Same rule as above (`:not([hidden])` scoping) — `.marker-actions` needed
it retroactively when `#detailEditActions`/`#detailViewActions` started
toggling via `hidden` (already fixed, see the marker-edit section). Kept
in mind for every new `hidden`-toggled element added during this redesign
(`#markerListSection` empty states, `#nearestLakeSuggest`, etc.) — none of
them hit the bug this time because the rule was already known going in,
but keep checking on anything new.

## Style/scope notes specific to this project

- Keep German UI copy; rewording for clarity is fine, don't change stated
  facts (per-lake depth/length stats now come from the official survey data
  in `DATA.stats` — trust that over any other source).
- Don't touch `project/` — it's the frozen original design export, kept for
  reference only.
- The user prefers being asked before large builds, but wants direct,
  working code delivered as committed changes, not just instructions, for
  anything touching `index.html`.
