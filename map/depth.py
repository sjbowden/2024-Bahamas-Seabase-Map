#!/usr/bin/env python3
"""Bathymetry for the chart: how shallow the water the crew sailed over actually was.

    python -m map.depth --fetch      # download and cache the grid (once)
    python -m map.depth --report     # what it says about each day

The shoal bands the chart drew until now were cartography, not measurement — two
buffers around the land, coloured to *suggest* shallows. This is the real thing,
from GMRT (the Global Multi-Resolution Topography synthesis), which serves a grid
subset over one HTTP request with no key and no account.

At 122 m cells over the whole chart region it resolves the Sea of Abaco's banks
plainly, and the answer it gives matches the crew's memory of scraping across:
Sunday and Tuesday both touch 1.0 m, and Wednesday spent 4,681 fixes in under
three metres of water.

Three things it is not, all of which shape how it is drawn rather than being
printed on the chart:

**Not soundings.** GMRT in shallow banks is largely satellite-derived and
interpolated. It says where the shallow water is, to a metre or so. It is not a
survey and nothing here should be navigated by.

**Not tide-corrected.** These are grid values against a nominal datum, not the
water level under the boat on the day, so they are not what the depth sounder
would have read.

**Blind to anything narrower than a cell.** A harbour entrance, a dredged
channel, a marina berth — all finer than 122 m, so the grid calls them land. The
day-by-day figures below therefore ignore fixes the grid thinks are ashore, which
is why Friday's airport drive and Thursday's mooring hop contribute nothing.
"""
import argparse
import math
import os
import urllib.parse
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(HERE, "geo", "depth_gmrt.npz")

# The region the chart can be looked at, which is what the shading has to cover:
# a depth layer stopping short of the view would put back the straight edge the
# coastline fetch was meant to remove. (S, W, N, E) to match fetch_coastline.
BBOX = (25.70, -78.30, 27.55, -75.55)
RESOLUTION = "high"          # 122 m cells here; "max" is 134 MB of ASCII
GRIDSERVER = "https://www.gmrt.org/services/GridServer"

# Depth bands, in metres. The chart convention the poster already follows is that
# deep water reads almost white and it gets bluer inshore, so this is that ramp
# continued rather than a new colour idea.
BANDS = [
    (0.0, 2.0, "#8BBBD8", "under 2 m"),
    (2.0, 4.0, "#A9CFE4", "2–4 m"),
    (4.0, 10.0, "#C6DEEC", "4–10 m"),
    (10.0, 20.0, "#DCEAF2", "10–20 m"),
    (20.0, 1e9, "#EDF4F8", "over 20 m"),
]

# Anything deeper than this is one band, so there is no reason to carry the
# abyssal plain at full precision: clipping lets the cache hold decimetres in an
# int16 and compress to a fraction of the 33 MB of ASCII it arrived as.
CLIP_DEEP_M = 400.0
CLIP_HIGH_M = -60.0          # land above this is just "land"


def fetch(force=False):
    """Download the grid and cache it compactly. Returns the cache path."""
    if os.path.exists(CACHE) and not force:
        return CACHE
    s, w, n, e = BBOX
    url = GRIDSERVER + "?" + urllib.parse.urlencode(dict(
        minlongitude=w, maxlongitude=e, minlatitude=s, maxlatitude=n,
        format="esriascii", resolution=RESOLUTION, layer="topo"))
    print(f"fetching GMRT {BBOX} at {RESOLUTION}...")
    with urllib.request.urlopen(url, timeout=300) as r:
        text = r.read().decode()
    hdr, rows = {}, []
    for line in text.splitlines():
        if not line.strip():
            continue
        first = line.split(None, 1)[0]
        if first.lower() in ("ncols", "nrows", "xllcorner", "yllcorner",
                             "cellsize", "nodata_value"):
            k, v = line.split()
            hdr[k.lower()] = float(v)
        else:
            rows.append(line)
    grid = np.array([[float(v) for v in r.split()] for r in rows], dtype=np.float64)
    # GMRT topo is elevation: negative is water. Store positive metres of water,
    # negative for land, clipped at both ends.
    depth = np.clip(-grid, CLIP_HIGH_M, CLIP_DEEP_M)
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    np.savez_compressed(
        CACHE, depth_dm=np.rint(depth * 10).astype(np.int16),
        x0=hdr["xllcorner"], y0=hdr["yllcorner"], cell=hdr["cellsize"],
        nrows=int(hdr["nrows"]), ncols=int(hdr["ncols"]))
    print(f"cached {CACHE} — {grid.shape[1]}x{grid.shape[0]} cells, "
          f"{hdr['cellsize'] * 111320:.0f} m, "
          f"{os.path.getsize(CACHE) / 2**20:.1f} MB")
    return CACHE


class Grid:
    """The cached depth grid, with a lookup by position."""

    def __init__(self, path=None):
        z = np.load(path or CACHE)
        self.depth = z["depth_dm"].astype(np.float32) / 10.0
        self.x0, self.y0 = float(z["x0"]), float(z["y0"])
        self.cell = float(z["cell"])
        self.nrows, self.ncols = int(z["nrows"]), int(z["ncols"])

    @property
    def bounds(self):
        return (self.x0, self.y0,
                self.x0 + self.ncols * self.cell,
                self.y0 + self.nrows * self.cell)

    def at(self, lat, lon):
        """Metres of water, negative on land, or None outside the grid."""
        col = int((lon - self.x0) / self.cell)
        row = int((self.y0 + self.nrows * self.cell - lat) / self.cell)
        if 0 <= row < self.nrows and 0 <= col < self.ncols:
            return float(self.depth[row, col])
        return None

    def axes(self):
        """Cell-centre coordinate vectors, north-up as the array is stored."""
        x = self.x0 + (np.arange(self.ncols) + 0.5) * self.cell
        y = self.y0 + (np.arange(self.nrows)[::-1] + 0.5) * self.cell
        return x, y

    def smoothed(self, passes=2):
        """A light box blur, so contours follow the seabed rather than the cells.

        Staircase contours cost vertices without adding information, and the
        underlying grid is interpolated anyway.
        """
        d = self.depth.astype(np.float32)
        for _ in range(passes):
            p = np.pad(d, 1, mode="edge")
            d = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]
                 + 4.0 * p[1:-1, 1:-1]) / 8.0
        return d


def along_track(grid, fixes):
    """Depths under a day's fixes, ignoring any the grid calls land.

    A harbour or a dredged cut is finer than a cell, so the grid puts the boat
    ashore there; those fixes say nothing about depth and are dropped rather than
    reported as a negative sounding.
    """
    out = []
    for t, lat, lon, *_ in fixes:
        d = grid.at(lat, lon)
        if d is not None and d > 0.0:
            out.append((t, d))
    return out


def day_summary(grid):
    """Per-day depth, for the chart's day popups. Shallowest first."""
    from trip import DAYS, read_fixes
    rows = {}
    for d in DAYS:
        fixes, _ = read_fixes(d["file"])
        ds = along_track(grid, fixes)
        if not ds:
            continue
        depths = sorted(x for _, x in ds)
        rows[d["label"]] = dict(
            shallowest_m=round(depths[0], 1),
            median_m=round(depths[len(depths) // 2], 1),
            fixes=len(depths),
            under_2m=sum(1 for x in depths if x < 2.0),
            under_3m=sum(1 for x in depths if x < 3.0))
    return rows


def _land_mask(land, w, h, x0, y0, x1, y1, merc_y):
    """True where the coastline says land, rasterised at the image's resolution.

    Needed because GMRT is a *bathymetry* synthesis: over low-lying land its
    elevations sit around zero, so testing `depth > 0` painted the pine forest and
    marsh in the middle of Great Abaco as shallow water. The coastline is the
    authority on what is sea, so it gets the final say here.
    """
    from PIL import Image, ImageDraw
    my0, my1 = merc_y(y0), merc_y(y1)

    def to_px(lon, lat):
        px = (lon - x0) / (x1 - x0) * w
        py = (my1 - merc_y(lat)) / (my1 - my0) * h
        return px, py

    mask = Image.new("1", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    parts = land.geoms if hasattr(land, "geoms") else [land]
    for g in parts:
        if g.is_empty or not hasattr(g, "exterior"):
            continue
        draw.polygon([to_px(x, y) for x, y in g.exterior.coords], fill=1)
        for hole in g.interiors:          # a lagoon is water again
            draw.polygon([to_px(x, y) for x, y in hole.coords], fill=0)
    return np.array(mask, dtype=bool)


# How crowded with land a neighbourhood may be before the grid is deemed to have
# nothing useful to say. 5 cells is about 600 m here.
FLATS_WINDOW = 5
FLATS_LAND_FRACTION = 0.25


def _box_mean(a, k):
    """Mean over a k x k window, via a summed-area table."""
    pad = k // 2
    p = np.pad(a, pad + 1, mode="edge")
    s = p.cumsum(0).cumsum(1)
    y0, x0 = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    y1, x1 = y0 + k, x0 + k
    total = s[y1, x1] - s[y0, x1] - s[y1, x0] + s[y0, x0]
    return total / float(k * k)


def _sea_only(water):
    """Water reachable from the edge of the image — the sea, and not the flats.

    The interior of Great Abaco is a lace of marsh and tidal flat that the
    coastline calls water and GMRT gives a metre or so, and shading it turned the
    island into a blue mosaic that swamped the chart. It is not holes in one island
    either, so filling holes did nothing: those are thousands of separate islets
    with real water between them. Only connectivity distinguishes the sea, so this
    is a span-based flood fill from the border — Pillow's own floodfill silently
    does nothing on a mode-L image in 12.3, and scipy is not a dependency here.
    """
    h, w = water.shape
    sea = np.zeros((h, w), dtype=bool)
    stack = []
    for x in range(w):
        if water[0, x]:
            stack.append((x, 0))
        if water[h - 1, x]:
            stack.append((x, h - 1))
    for y in range(h):
        if water[y, 0]:
            stack.append((0, y))
        if water[y, w - 1]:
            stack.append((w - 1, y))

    while stack:
        x, y = stack.pop()
        if sea[y, x] or not water[y, x]:
            continue
        lo = x
        while lo > 0 and water[y, lo - 1] and not sea[y, lo - 1]:
            lo -= 1
        hi = x
        while hi < w - 1 and water[y, hi + 1] and not sea[y, hi + 1]:
            hi += 1
        sea[y, lo:hi + 1] = True
        for ny in (y - 1, y + 1):
            if not (0 <= ny < h):
                continue
            run = water[ny, lo:hi + 1] & ~sea[ny, lo:hi + 1]
            idx = np.nonzero(run)[0]
            if idx.size:
                starts = np.concatenate(([0], np.nonzero(np.diff(idx) > 1)[0] + 1))
                for st in starts:
                    stack.append((lo + int(idx[st]), ny))
    return sea


def render_png(grid, path, max_px=2600, land=None):
    """Paint the depth bands into a paletted PNG, reprojected to web mercator.

    A raster, not vector bands. Bathymetry is a continuous field, and the first
    attempt here — contour it, polygonise the lines with the frame, classify each
    face by sampling — put only 6.7% of the wet area into a band and mis-assigned
    some of what it did catch, because contour lines that run off the grid edge do
    not close into faces. A picture of a grid is what a grid is.

    Reprojected on the way out because MapLibre maps an image's four corners onto
    a mercator quad: handing it rows that are linear in latitude would stretch
    them non-linearly and misregister the depths against the coastline by a few
    hundred metres in the middle of the image.
    """
    from PIL import Image

    x0, y0, x1, y1 = grid.bounds

    def merc_y(lat):
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    my0, my1 = merc_y(y0), merc_y(y1)
    h = min(max_px, grid.nrows)
    w = min(max_px, grid.ncols)
    # Output row -> mercator y -> latitude -> source row.
    out_lat = np.array([
        math.degrees(2 * math.atan(math.exp(my1 - (my1 - my0) * (r + 0.5) / h)) - math.pi / 2)
        for r in range(h)])
    src_row = np.clip(((y0 + grid.nrows * grid.cell - out_lat) / grid.cell).astype(int),
                      0, grid.nrows - 1)
    src_col = np.clip((np.linspace(0, grid.ncols - 1, w)).astype(int), 0, grid.ncols - 1)
    sampled = grid.depth[np.ix_(src_row, src_col)]

    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    dry = (_land_mask(land, w, h, x0, y0, x1, y1, merc_y)
           if land is not None else np.zeros((h, w), dtype=bool))
    # Only water that reaches the open sea gets shaded. The interior of Great
    # Abaco is a lace of marsh and tidal flat that the coastline correctly calls
    # water, and GMRT gives it a metre or so — but shading it turned the island
    # into a blue mosaic that swamped the chart. A flood fill from the edge of the
    # image keeps the sea and leaves the inland flats alone.
    # Shade open water only. Where the coastline is finer than the grid — the
    # marsh maze inside Great Abaco is thousands of islets tens of metres across —
    # a 122 m cell means nothing, and rasterising those islets into it produced a
    # blue mosaic that swamped the island. Connectivity does not separate them
    # (the flats are open to the sea) and neither does hole-filling (they are
    # separate islets, not holes), so the test is local: if a neighbourhood is
    # more than a quarter land, the grid is out of its depth and says nothing.
    crowded = _box_mean(dry.astype(np.float32), FLATS_WINDOW) > FLATS_LAND_FRACTION
    sampled = np.where(_sea_only(~dry) & ~crowded, sampled, -1.0)
    for lo, hi, colour, _ in BANDS:
        if hi > 1e8:
            continue                    # the water background paints the deepest
        m = (sampled > 0) & (sampled >= lo) & (sampled < hi)
        r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
        rgba[m] = (r, g, b, 255)
    img = Image.fromarray(rgba, "RGBA")
    # Quantising to the handful of colours actually used makes the file a fraction
    # of the size; RGBA is kept for the transparent land and deep water.
    img.save(path, "PNG", optimize=True)
    return dict(path=path, width=w, height=h,
                coordinates=[[x0, y1], [x1, y1], [x1, y0], [x0, y0]],
                covered=float((rgba[:, :, 3] > 0).mean()))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fetch", action="store_true", help="download the grid")
    ap.add_argument("--force", action="store_true", help="re-download it")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    if a.fetch or a.force or not os.path.exists(CACHE):
        fetch(force=a.force)
    grid = Grid()
    print(f"grid {grid.ncols}x{grid.nrows}, {grid.cell * 111320:.0f} m cells, "
          f"bounds {tuple(round(v, 2) for v in grid.bounds)}")
    if a.report:
        print(f"\n{'day':12} {'fixes':>6} {'shallowest':>11} {'median':>7} "
              f"{'<2 m':>6} {'<3 m':>6}")
        for label, r in day_summary(grid).items():
            print(f"{label:12} {r['fixes']:6} {r['shallowest_m']:10.1f} m "
                  f"{r['median_m']:6.1f} m {r['under_2m']:6} {r['under_3m']:6}")


if __name__ == "__main__":
    main()
