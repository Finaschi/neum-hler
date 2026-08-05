#!/usr/bin/env python3
"""
Bakes a lake's bathymetry into the per-lake JSON format the app fetches at
runtime (data/lakes/<slug>.json).

Source: LUNG MV's public WFS ("Gewässer MV", umweltkarten.lung-mv.de),
CC BY-SA, free to use. See AGENT_HANDOFF.md for how this was discovered.

Usage:
    python3 scripts/bake_lake.py "Neumühler See" neumuehler
    python3 scripts/bake_lake.py "Cramoner See" cramoner
    python3 scripts/bake_lake.py "Dümmersee" duemmer
    python3 scripts/bake_lake.py "Medeweger See" medeweg
    python3 scripts/bake_lake.py "Neddersee" nedder

What it does:
  1. Fetches the lake's outline + metadata from the `sg` WFS layer.
  2. Fetches the official 1m depth-band polygons from the `sg_tl` layer.
  3. Builds nested "depth >= k" isobath polygons for k = 0..floor(tmax), by
     unioning bands from the outside in. This gives clean nested contours to
     interpolate between, rather than raw (sometimes gappy) per-band shapes.
  4. Rasterizes a grid: inside the lake, depth is linearly interpolated
     between whichever pair of isobaths bracket each point, by relative
     distance to each (a standard contour-to-DEM method); outside the lake,
     elevation is a synthetic shore ramp (no terrestrial DEM exists in this
     data source, same situation the original hand-built dataset was in).
  5. Computes an *exact* local geo-transform (not fitted/approximate): grid
     row0 = north edge, increasing row = south (matches the orientation the
     app's existing geoToWorld/worldToGeo already assume — see
     AGENT_HANDOFF.md's georeferencing section for why). FIT_U/FIT_V come
     from sampling true geodesic azimuth+distance via pyproj's Geod, which
     captures the local UTM scale factor and meridian convergence exactly
     (sub-cm residual, vs. the ~29-45m median error of the old ICP fit).
"""
import sys
import json
import math
import urllib.request
import urllib.parse
import re

from pyproj import Transformer, Geod
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, Point
from shapely.ops import unary_union
from shapely import prepared

WFS_BASE = "https://umweltkarten.lung-mv.de/dienste/wg_gewaesser"
SRC_CRS = "EPSG:5650"
DST_CRS = "EPSG:4326"

TARGET_COLS = 220          # aim for ~this many grid columns across the wider extent
PAD_FRACTION = 0.10        # extra land margin around the lake bbox, as a fraction of bbox size
PAD_MIN_M = 80.0           # ... but never less than this many meters
LAND_MAX_ELEV = 8.0        # synthetic shore elevation cap, meters
LAND_RAMP_DIST = 130.0     # distance from shore at which land elevation reaches its cap


def wfs_get(params):
    url = WFS_BASE + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_gml_poslist(text):
    """Extract all posList coordinate strings -> list of [(x,y),...] rings."""
    rings = []
    for m in re.finditer(r"<(?:gml:)?posList[^>]*>([^<]*)</(?:gml:)?posList>", text):
        nums = [float(v) for v in m.group(1).split()]
        pts = list(zip(nums[0::2], nums[1::2]))
        rings.append(pts)
    return rings


def parse_multisurface_features(xml_text, tag):
    """Split a WFS GetFeature response into <qgs:tag> feature blocks."""
    blocks = re.findall(r"<qgs:%s\b.*?</qgs:%s>" % (tag, tag), xml_text, re.S)
    return blocks


def polygon_from_feature_block(block):
    """A feature's <geometry> may contain multiple surfaceMembers (MultiPolygon).
    Each surfaceMember's <Polygon> may have an exterior ring and interior rings."""
    polys = []
    for surf in re.findall(r"<surfaceMember\b.*?</surfaceMember>", block, re.S):
        ext_m = re.search(r"<exterior\b.*?</exterior>", surf, re.S)
        if not ext_m:
            continue
        ext_rings = parse_gml_poslist(ext_m.group(0))
        if not ext_rings:
            continue
        exterior = ext_rings[0]
        interiors = []
        for interior_block in re.findall(r"<interior\b.*?</interior>", surf, re.S):
            int_rings = parse_gml_poslist(interior_block)
            if int_rings:
                interiors.append(int_rings[0])
        if len(exterior) >= 4:
            try:
                polys.append(Polygon(exterior, interiors))
            except Exception:
                pass
    if not polys:
        return None
    if len(polys) == 1:
        return polys[0].buffer(0)
    return unary_union([p.buffer(0) for p in polys])


def fetch_lake_record(name):
    xml = wfs_get({
        "SERVICE": "WFS", "REQUEST": "GetFeature", "VERSION": "1.1.0",
        "TYPENAME": "sg",
    })
    for block in parse_multisurface_features(xml, "sg"):
        ng = re.search(r"<qgs:see_gn>([^<]*)</qgs:see_gn>", block)
        if ng and ng.group(1) == name:
            attrs = dict(re.findall(r"<qgs:(\w+)>([^<]*)</qgs:\1>", block))
            geom = polygon_from_feature_block(block)
            return attrs, geom
    raise SystemExit(f"Lake '{name}' not found in sg layer")


def fetch_depth_bands(name, bbox):
    lox, loy, hix, hiy = bbox
    xml = wfs_get({
        "SERVICE": "WFS", "REQUEST": "GetFeature", "VERSION": "1.1.0",
        "TYPENAME": "sg_tl",
        "BBOX": f"{lox},{loy},{hix},{hiy},{SRC_CRS}",
    })
    by_name = {}
    for block in parse_multisurface_features(xml, "sg_tl"):
        ng = re.search(r"<qgs:SEE_GN>([^<]*)</qgs:SEE_GN>", block)
        gname = ng.group(1) if ng else None
        von = re.search(r"<qgs:TIEFE_VON>([^<]*)</qgs:TIEFE_VON>", block)
        bis = re.search(r"<qgs:TIEFE_BIS>([^<]*)</qgs:TIEFE_BIS>", block)
        geom = polygon_from_feature_block(block)
        if von and bis and geom is not None and not geom.is_empty:
            by_name.setdefault(gname, []).append((float(von.group(1)), float(bis.group(1)), geom))

    if name in by_name:
        bands = by_name[name]
    elif len(by_name) == 1:
        (only_name, bands), = by_name.items()
        print(f"  (sg_tl uses name '{only_name}' for this lake, not '{name}' — using it, bbox is tight)")
    elif len(by_name) == 0:
        bands = []
    else:
        # multiple distinct names inside the padded bbox: pick the largest group
        only_name = max(by_name, key=lambda k: len(by_name[k]))
        bands = by_name[only_name]
        print(f"  WARNING: multiple lake names in bbox {list(by_name.keys())}, using '{only_name}'")

    bands.sort(key=lambda b: b[0])
    return bands


def build_isobaths(bands, outline):
    """poly_cumulative[k] = union of all bands with TIEFE_VON >= k => area where depth >= k."""
    max_k = int(round(max(b[1] for b in bands))) if bands else 0
    cumulative = {}
    for k in range(0, max_k + 1):
        parts = [g for (von, bis, g) in bands if von >= k - 1e-6]
        if parts:
            u = unary_union(parts)
        else:
            u = Polygon()
        cumulative[k] = u
    cumulative[0] = outline  # k=0 isobath IS the shoreline itself
    return cumulative, max_k


def depth_at_point(pt, cumulative, prepared_cumulative, max_k):
    # find deepest isobath containing pt
    k_in = 0
    for k in range(max_k, -1, -1):
        if prepared_cumulative[k].contains(pt):
            k_in = k
            break
    if k_in >= max_k:
        return float(max_k)
    outer = cumulative[k_in]
    inner = cumulative[k_in + 1]
    d_out = outer.boundary.distance(pt) if not outer.is_empty else 1.0
    d_in = inner.boundary.distance(pt) if not inner.is_empty else None
    if d_in is None or inner.is_empty:
        return float(k_in) + 0.5
    if d_out + d_in < 1e-9:
        return float(k_in)
    return k_in + d_out / (d_out + d_in)


def compute_geo_transform(e0, n0):
    to_wgs84 = Transformer.from_crs(SRC_CRS, DST_CRS, always_xy=True)
    geod = Geod(ellps="WGS84")
    lon0, lat0 = to_wgs84.transform(e0, n0)

    D = 500.0
    # sample point D meters "east" in grid frame (x=+D, z=0) -> (E0+D, N0)
    lon_e, lat_e = to_wgs84.transform(e0 + D, n0)
    az_e, _, dist_e = geod.inv(lon0, lat0, lon_e, lat_e)
    # sample point D meters "south" in grid frame (x=0, z=+D) -> grid z increases
    # southward (row0=north, see module docstring), i.e. UTM northing = N0 - D
    lon_s, lat_s = to_wgs84.transform(e0, n0 - D)
    az_s, _, dist_s = geod.inv(lon0, lat0, lon_s, lat_s)

    # az is degrees clockwise from true north; convert to true ENU offset
    def enu(dist, az_deg):
        r = math.radians(az_deg)
        return dist * math.sin(r), dist * math.cos(r)  # (east, north)

    e_x, n_x = enu(dist_e, az_e)   # true (e,n) for world (x=D, z=0)
    e_z, n_z = enu(dist_s, az_s)   # true (e,n) for world (x=0, z=D)

    fit_u = e_x / D
    fit_v = e_z / D
    # sanity: n should equal (fit_v*x - fit_u*z) form the app expects
    check_n_x = n_x / D   # expected: fit_v
    check_n_z = n_z / D   # expected: -fit_u
    resid = max(abs(check_n_x - fit_v), abs(check_n_z + fit_u))
    return lat0, lon0, fit_u, fit_v, resid


def build_grid(outline, bands, e0, n0, e_min, e_max, n_min, n_max, cell):
    gw = int(round((e_max - e_min) / cell)) + 1
    gh = int(round((n_max - n_min) / cell)) + 1
    cumulative, max_k = build_isobaths(bands, outline)
    prepared_cumulative = {k: prepared.prep(g) for k, g in cumulative.items()}
    prep_outline = prepared.prep(outline)

    elevation = np.zeros(gw * gh, dtype=np.float32)
    for row in range(gh):
        # row0 = north edge (n_max), increasing row -> south
        northing = n_max - row * cell
        for col in range(gw):
            easting = e_min + col * cell
            pt = Point(easting, northing)
            idx = row * gw + col
            if prep_outline.contains(pt):
                d = depth_at_point(pt, cumulative, prepared_cumulative, max_k)
                elevation[idx] = -d
            else:
                dist_out = outline.boundary.distance(pt)
                elevation[idx] = min(LAND_MAX_ELEV, LAND_MAX_ELEV * dist_out / LAND_RAMP_DIST)
    return gw, gh, elevation


def shoreline_latlon(outline):
    to_wgs84 = Transformer.from_crs(SRC_CRS, DST_CRS, always_xy=True)
    if isinstance(outline, MultiPolygon):
        outline = max(outline.geoms, key=lambda p: p.area)
    coords = list(outline.exterior.coords)
    result = []
    for x, y in coords:
        lon, lat = to_wgs84.transform(x, y)
        result.append([round(lat, 6), round(lon, 6)])
    return result


def main():
    if len(sys.argv) != 3:
        print("usage: bake_lake.py '<Seename>' <slug>", file=sys.stderr)
        sys.exit(1)
    name, slug = sys.argv[1], sys.argv[2]

    print(f"[{slug}] fetching lake record for '{name}'...")
    attrs, outline = fetch_lake_record(name)
    if outline is None or outline.is_empty:
        raise SystemExit("no outline geometry found")

    e_min0, n_min0, e_max0, n_max0 = outline.bounds
    span_e = e_max0 - e_min0
    span_n = n_max0 - n_min0
    pad = max(PAD_MIN_M, PAD_FRACTION * max(span_e, span_n))
    e_min, e_max = e_min0 - pad, e_max0 + pad
    n_min, n_max = n_min0 - pad, n_max0 + pad

    cell = max(span_e, span_n) / TARGET_COLS if max(span_e, span_n) > 0 else 10.0
    cell = round(cell, 3)

    e0 = (e_min + e_max) / 2.0
    n0 = (n_min + n_max) / 2.0

    print(f"[{slug}] fetching depth-band contours...")
    bbox_pad = pad + 50
    bands = fetch_depth_bands(name, (e_min0 - bbox_pad, n_min0 - bbox_pad, e_max0 + bbox_pad, n_max0 + bbox_pad))
    print(f"[{slug}] {len(bands)} depth bands found")

    print(f"[{slug}] computing exact geo-transform...")
    lat0, lon0, fit_u, fit_v, resid = compute_geo_transform(e0, n0)
    print(f"[{slug}] LAT_REF={lat0:.8f} LON_REF={lon0:.8f} FIT_U={fit_u:.10f} FIT_V={fit_v:.10f} (residual {resid:.2e})")

    print(f"[{slug}] rasterizing grid (cell={cell}m)...")
    gw, gh, elevation = build_grid(outline, bands, e0, n0, e_min, e_max, n_min, n_max, cell)
    print(f"[{slug}] grid {gw}x{gh} = {gw*gh} cells")

    max_depth_in_grid = -float(elevation.min())
    print(f"[{slug}] max depth in baked grid: {max_depth_in_grid:.2f}m (official tmax: {attrs.get('tmax')})")

    shoreline = shoreline_latlon(outline)

    out = {
        "id": slug,
        "name": name,
        "gw": gw, "gh": gh, "cellSize": cell,
        "elevation": [round(float(v), 3) for v in elevation],
        "latRef": lat0, "lonRef": lon0,
        "fitU": fit_u, "fitV": fit_v, "fitTx": 0.0, "fitTy": 0.0,
        "shoreline": shoreline,
        "stats": {
            "tmax": float(attrs.get("tmax", max_depth_in_grid)),
            "tmean": float(attrs["td"]) if attrs.get("td") else None,
            "volumeM3": int(float(attrs["vol"])) if attrs.get("vol") else None,
            "areaM2": float(attrs["flaeche"]) if attrs.get("flaeche") else None,
            "lengthKm": float(attrs["leff"]) if attrs.get("leff") else None,
            "widthKm": float(attrs["beff"]) if attrs.get("beff") else None,
            "shoreLengthKm": float(attrs["ul"]) if attrs.get("ul") else None,
            "surveyDate": attrs.get("verm_datum"),
            "source": "LUNG MV – Land Mecklenburg-Vorpommern, CC BY-SA (umweltkarten.lung-mv.de)",
        },
    }

    import os
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data", "lakes")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{slug}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    size_kb = os.path.getsize(out_path) / 1024
    print(f"[{slug}] wrote {out_path} ({size_kb:.0f} KB)")


if __name__ == "__main__":
    main()
