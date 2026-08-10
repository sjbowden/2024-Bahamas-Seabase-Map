#!/usr/bin/env python3
"""Bathymetry for the chart: how shallow the water the crew sailed over actually was.

    python -m map.depth --fetch      # download and cache the grid (once)
    python -m map.depth --report     # what it says about each day

The shoal bands the chart drew until now were cartography, not measurement — two
buffers around the land, coloured to *suggest* shallows. This is the real thing,
from GMRT (the Global Multi-Resolution Topography synthesis), which serves a grid
subset over one HTTP request with no key and no account.

At 61 m cells over the whole chart region it resolves the Sea of Abaco's banks
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
channel, a marina berth — all finer than 61 m, so the grid calls them land. The
day-by-day figures below therefore ignore fixes the grid thinks are ashore, which
is why Friday's airport drive and Thursday's mooring hop contribute nothing.
"""
import argparse
import math
import os
import urllib.parse
import urllib.request
import warnings

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GRIDSERVER = "https://www.gmrt.org/services/GridServer"

# Two grids are fetched and then merged into one by merged(); see there for why
# drawing them as two separate rasters could not be made to work.
#
# `wide` covers everywhere the chart can be looked at, because a depth layer
# stopping short of the view would put back the straight edge the coastline fetch
# was meant to remove. It has to be "high" rather than "max": the same box at max
# is 5008x3368 cells and 134 MB of ASCII.
#
# `fine` covers where the boat actually went, at 61 m — twice the detail, over the
# only area anyone zooms in far enough to see it. Its cell size sets the lattice
# the merged grid uses everywhere.
GRIDS = {
    "wide": dict(bbox=(25.70, -78.30, 27.55, -75.55), resolution="high",
                 cache="depth_gmrt.npz", minzoom=None),
    "fine": dict(bbox=(26.15, -77.35, 26.85, -76.80), resolution="max",
                 cache="depth_gmrt_fine.npz", minzoom=None),
}


def cache_path(which="wide"):
    return os.path.join(HERE, "geo", GRIDS[which]["cache"])


CACHE = cache_path("wide")

# Depth bands, in metres. The chart convention the poster already follows is that
# deep water reads almost white and it gets bluer inshore, so this is that ramp
# continued rather than a new colour idea.
# Spaced by how light they look. The first ramp's middle steps were nearly
# invisible: 4–10 m sat 25 luminance points from the "deep" background and 10–20 m
# only 11, so water of five to fifteen metres beside a beach read as open ocean —
# and the Bight of Old Robinson, 46% of which is those two bands, looked like empty
# water rather than the shallows it is. The top three steps are now the poster's
# own water colours with two darker ones added below, which keeps the chart on the
# sheet's palette while separating the bands by about 20 points each.
BANDS = [
    (0.0, 2.0, "#6FA6C9", "under 2 m"),
    (2.0, 4.0, "#8FBDD9", "2–4 m"),
    (4.0, 10.0, "#B2D3E6", "4–10 m"),
    (10.0, 20.0, "#CDE3EE", "10–20 m"),
    (20.0, 1e9, "#E7F1F5", "over 20 m"),
]

# Anything deeper than this is one band, so there is no reason to carry the
# abyssal plain at full precision: clipping lets the cache hold decimetres in an
# int16 and compress to a fraction of the 33 MB of ASCII it arrived as.
CLIP_DEEP_M = 400.0
CLIP_HIGH_M = -60.0          # land above this is just "land"


def fetch(which="wide", force=False):
    """Download one grid and cache it compactly. Returns the cache path."""
    spec = GRIDS[which]
    dest = cache_path(which)
    if os.path.exists(dest) and not force:
        return dest
    s, w, n, e = spec["bbox"]
    url = GRIDSERVER + "?" + urllib.parse.urlencode(dict(
        minlongitude=w, maxlongitude=e, minlatitude=s, maxlatitude=n,
        format="esriascii", resolution=spec["resolution"], layer="topo"))
    print(f"fetching GMRT {which} {spec['bbox']} at {spec['resolution']}...")
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
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    np.savez_compressed(
        dest, depth_dm=np.rint(depth * 10).astype(np.int16),
        x0=hdr["xllcorner"], y0=hdr["yllcorner"], cell=hdr["cellsize"],
        nrows=int(hdr["nrows"]), ncols=int(hdr["ncols"]))
    print(f"cached {dest} — {grid.shape[1]}x{grid.shape[0]} cells, "
          f"{hdr['cellsize'] * 111320:.0f} m, "
          f"{os.path.getsize(dest) / 2**20:.1f} MB")
    return dest


class Grid:
    """The cached depth grid, with a lookup by position."""

    def __init__(self, which="wide", path=None):
        z = np.load(path or cache_path(which))
        self.which = which
        self.minzoom = GRIDS[which]["minzoom"] if which in GRIDS else None
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


def merged():
    """One grid, at the fine cell size, covering everything the wide one does.

    Two rasters cannot be made to agree. Each ran its own land mask, its own
    neighbourhood context and its own plausibility tests at its own resolution, so
    cells near a band boundary landed on opposite sides of it — and swapping
    rasters at z11.5 made the colours jump. The fix is to stop having two: the wide
    grid is resampled onto the fine lattice and the fine grid pasted over where it
    reaches, then everything downstream runs once on the result.
    """
    wide, fine = Grid("wide"), Grid("fine")
    cell = fine.cell
    ncols = int(round(wide.ncols * wide.cell / cell))
    nrows = int(round(wide.nrows * wide.cell / cell))
    lon = wide.x0 + (np.arange(ncols) + 0.5) * cell
    lat = (wide.y0 + nrows * cell) - (np.arange(nrows) + 0.5) * cell

    wc = np.clip(((lon - wide.x0) / wide.cell).astype(int), 0, wide.ncols - 1)
    wr = np.clip(((wide.y0 + wide.nrows * wide.cell - lat) / wide.cell).astype(int),
                 0, wide.nrows - 1)
    depth = wide.depth[np.ix_(wr, wc)].copy()

    fc = ((lon - fine.x0) / fine.cell).astype(int)
    fr = ((fine.y0 + fine.nrows * fine.cell - lat) / fine.cell).astype(int)
    okc, okr = (fc >= 0) & (fc < fine.ncols), (fr >= 0) & (fr < fine.nrows)
    if okc.any() and okr.any():
        depth[np.ix_(okr, okc)] = fine.depth[np.ix_(fr[okr], fc[okc])]

    out = Grid("wide")
    out.depth, out.cell = depth, cell
    out.nrows, out.ncols = nrows, ncols
    out.which, out.minzoom = "merged", None
    return out


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


def day_summary(grid, finer=None):
    """Per-day depth, for the chart's day popups.

    Prefers the finer grid where it reaches, since the whole track is inside it and
    61 m resolves a shoal a 122 m cell averages away.
    """
    from trip import DAYS, read_fixes
    rows = {}
    for d in DAYS:
        fixes, _ = read_fixes(d["file"])
        ds = along_track(finer or grid, fixes) or along_track(grid, fixes)
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
# How far the fill reaches into the untrusted fringe. At 5 passes 5.8% of the
# shoreline was still bare — reading as deep water against a beach — and at 24 it
# is 0.4%, for a few more numpy passes over the grid. It also has the happy effect
# of smoothing the flats instead of leaving them a mosaic, because each pass
# averages the neighbours it grew from.
FRINGE_PASSES = 24
# How far the water colour is carried under the coastline, to keep the resampler
# from interpolating alpha at the shore. Only needs to cover a source pixel or two.
COAST_BLEED = 10

# A depth is rejected as implausible when it is more than this many times the mean
# of its wider neighbourhood, and over 6 m. GMRT has no soundings inside Great
# Abaco's tidal marsh and its interpolation there invents water 26 m deep, which is
# not a hole in a mangrove flat — it is an artefact, and it rendered as the undrawn
# deepest band, so it read as open ocean a few hundred metres from a beach.
#
# The test has to be local, because "deep" alone is not wrong: measured, this flags
# 5.8% of the marsh's water and 0.0% of both the open Sea of Abaco and the Atlantic
# off Elbow Cay, which keeps its real 30 m. Flagged cells are refilled from their
# neighbours like any other untrusted water.
SUSPECT_FACTOR = 2.0
SUSPECT_FLOOR_M = 6.0
SUSPECT_WINDOW = 25

# On the banks, depth is held inside the deepest band that gets drawn. The deepest
# band is the water background — nothing is painted for it — so a 25 m artefact a
# few hundred metres off a beach came out the same colour as the open Atlantic and
# read as ocean. Rejecting the artefacts one at a time only got half of them; this
# says the thing that is actually true, which is that the Sea of Abaco is not
# twenty metres deep anywhere, so anything claiming to be is not being believed.
#
# Ocean is told apart by its own surroundings over about six kilometres. Measured,
# that classes 0% of the marsh and the Marsh Harbour approaches as ocean and 85% of
# the water off Elbow Cay's Atlantic shore, which keeps its real depths.
# Bank water deeper than this is not believed, and is refilled from its
# neighbours rather than clamped. Clamping was the previous answer and it only
# moved the problem: an artefact held at 19.5 m lands in the *lightest* drawn
# band, so the marsh went from invisibly pale to visibly pale. Refilling gives it
# whatever its surroundings have, which is what the eye expects of a flat.
# Sub-samples per cell, per axis, when deciding a pixel's colour. 3 means each
# pixel is the average of 9 band lookups taken through the bilinearly interpolated
# seabed, which antialiases every band edge to about a third of a cell.
#
# Averaging the *depths* over a neighbourhood first was tried instead and was
# clearly worse: it pulled wide areas of the bank onto the 4 m boundary, where the
# least variation flips a cell, and the chart dithered into a mosaic. Bilinear
# interpolation cannot do that — it reproduces each cell centre exactly and moves
# monotonically between them.
SUBSAMPLES = 3

# No shore shelves from nothing to twenty metres inside one 61 m cell. Water is
# therefore not allowed to be deeper than this many metres per cell of distance
# from the drawn land — about a 1:20 slope, which is generous for sand (real
# beaches run 1:30 and flatter) and so only ever makes the chart shallower than
# GMRT claims, never deeper.
#
# This is the one rule here that constrains the *ocean* side too. Everything else
# exempts it, deliberately, so that the Atlantic drop-off along the cays stays
# deep — but that exemption also let the water read as near-white hard against the
# beach on Tilloo and Elbow, which is where this came from. It stops binding
# beyond about 7 cells, so the drop-off itself is untouched.
SHORE_SLOPE_M_PER_CELL = 3.0
SHORE_REACH_CELLS = 8

BANK_PLAUSIBLE_M = 12.0
OCEAN_CONTEXT_M = 40.0
OCEAN_WINDOW = 51

# How much shallower than its own surroundings a cell in open ocean may claim
# before it is treated as interpolation rather than seabed. A fifth catches the
# confetti and leaves the shelf break alone, where a genuinely shallower cell and
# the ocean around it both paint the deepest band anyway.
OCEAN_SPIKE_FRACTION = 0.2


def _box_mean(a, k):
    """Mean over a k x k window, via a summed-area table."""
    pad = k // 2
    p = np.pad(a, pad + 1, mode="edge")
    s = p.cumsum(0).cumsum(1)
    y0, x0 = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    y1, x1 = y0 + k, x0 + k
    total = s[y1, x1] - s[y0, x1] - s[y1, x0] + s[y0, x0]
    return total / float(k * k)


def _grow_into(values, region, trusted, passes=FRINGE_PASSES):
    """Spread depths from trusted water into the untrusted fringe beside it.

    The *shallowest* known neighbour rather than the average, because water shoals
    toward a shore: a third of the water cells touching the coastline have no depth
    in GMRT at all — it calls them land — so the fringe is invented, and where it
    *is* measured the distribution one cell offshore has a median of 2.0 m against
    a mean of 6.0 m, skewed by a scatter of deep cells. It stays honest on the
    Atlantic side, where the shallowest nearby value is itself part of a bottom
    dropping away.

    Worth recording that this was not what caused the light halo along the shore,
    though it looked like an obvious culprit: measured, it moved the shoreline ring
    from 82.1% to 83.4% in the two shallowest bands. The halo was the resampler
    interpolating alpha, and the fix for it is the bleed under the coastline below.
    """
    out = values.astype(np.float32).copy()
    known = trusted.copy()
    out[~known] = np.nan
    for _ in range(passes + 1):
        todo = region & ~known
        if not todo.any():
            break
        nb = np.stack([
            np.roll(out, 1, 0), np.roll(out, -1, 0),
            np.roll(out, 1, 1), np.roll(out, -1, 1),
        ])
        with warnings.catch_warnings():
            # A pixel with no known neighbour yet is expected, not exceptional.
            warnings.simplefilter("ignore", RuntimeWarning)
            near = np.nanmin(nb, axis=0)
        fill = todo & ~np.isnan(near)
        out[fill] = near[fill]
        known |= fill
    out[np.isnan(out)] = -1.0
    return out


def _box_mean_valid(values, valid, k):
    """Box mean over the valid cells only."""
    num = _box_mean(np.where(valid, values, 0.0).astype(np.float32), k)
    den = _box_mean(valid.astype(np.float32), k)
    return num / np.maximum(den, 1e-6)


def _implausible(depth, sea):
    """Cells far deeper than their surroundings — interpolation, not bathymetry."""
    ctx = _box_mean_valid(depth, sea & (depth > 0), SUSPECT_WINDOW)
    return sea & (depth > np.maximum(SUSPECT_FLOOR_M, SUSPECT_FACTOR * ctx))


def _is_ocean(depth, sea):
    """Open ocean, told apart by its surroundings over about six kilometres."""
    return _box_mean_valid(depth, sea & (depth > 0), OCEAN_WINDOW) > OCEAN_CONTEXT_M


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


def _cells_from(mask, reach):
    """How many cells each cell is from `mask`, out to `reach`; inf past that.

    Grown a ring at a time rather than by a proper distance transform: there is no
    scipy here, and the answer is only used out to eight cells.
    """
    dist = np.full(mask.shape, np.inf, dtype=np.float32)
    dist[mask] = 0.0
    cur = mask.copy()
    for k in range(1, reach + 1):
        g = cur.copy()
        g[1:] |= cur[:-1]
        g[:-1] |= cur[1:]
        g[:, 1:] |= cur[:, :-1]
        g[:, :-1] |= cur[:, 1:]
        dist[g & ~cur] = k
        cur = g
    return dist


def _between(a, sy, sx):
    """`a` resampled a fraction of a cell away, bilinearly, edges held.

    Rolling a padded copy wraps the outer ring around, which is why the ring is
    padded on and then cropped off again: the wrap only ever lands in the part
    thrown away.
    """
    p = np.pad(a, 1, mode="edge")
    for s, axis in ((sy, 0), (sx, 1)):
        if s:
            f = abs(s)
            p = (1.0 - f) * p + f * np.roll(p, -1 if s > 0 else 1, axis=axis)
    return p[1:-1, 1:-1]


def _banded(depth):
    """Band colours per pixel, antialiased; and where there is water at all.

    Each pixel is the mean of SUBSAMPLES² band lookups taken between the cell
    centres, so a band edge crossing a cell shows as a blend rather than as a step.
    Without this the bands drew as rectilinear staircases at 61 m, which is the
    scale of the survey and not of anything on the seabed. MapLibre's own resampling
    cannot fix that: given a hard edge on a coarse lattice it can only give back a
    staircase or a blur, and it was asked for both in turn.

    The deepest band is painted here rather than left transparent for the page
    background to show through, so that the 20 m edge antialiases like the others.
    Its colour is the background's, so nothing looks different where it is flat.
    """
    palette = np.array([[int(c[i:i + 2], 16) for i in (1, 3, 5)]
                        for _, _, c, _ in BANDS], dtype=np.uint8)
    edges = np.array([hi for _, hi, _, _ in BANDS[:-1]], dtype=np.float32)
    off = [(k + 0.5) / SUBSAMPLES - 0.5 for k in range(SUBSAMPLES)]

    acc = np.zeros(depth.shape + (3,), dtype=np.uint16)
    hits = np.zeros(depth.shape, dtype=np.uint8)
    for sy in off:
        for sx in off:
            v = _between(depth, sy, sx)
            wet = v > 0
            idx = np.digitize(v, edges).astype(np.uint8)
            for ch in range(3):
                acc[:, :, ch] += np.where(wet, palette[:, ch][idx], 0)
            hits += wet
    safe = np.maximum(hits, 1).astype(np.uint16)
    rgb = (acc // safe[:, :, None]).astype(np.uint8)
    return rgb, hits > 0


def cleaned(depth, dry):
    """Depths with the untrustworthy ones replaced; land and dry cells set to -1.

    Kept apart from the drawing so the raster and the vector bands cannot disagree
    about what the seabed is. They differed before, when each computed this for
    itself at its own resolution, and cells near a band boundary fell on opposite
    sides of it.

    Shade open water only. Where the coastline is finer than the grid — the marsh
    maze inside Great Abaco is thousands of islets tens of metres across — a 61 m
    cell means nothing, and rasterising those islets into it produced a blue mosaic
    that swamped the island. Connectivity does not separate them (the flats are
    open to the sea) and neither does hole-filling (they are separate islets, not
    holes), so the test is local: if a neighbourhood is more than a quarter land,
    the grid is out of its depth and says nothing.

    Suppressing that water outright left every shoreline with an unshaded band
    about 600 m wide, so the chart read as deep water right up to the beach — the
    opposite of the truth, and in the one place the shallows matter most. Instead
    the fringe is filled from the nearest water the grid *is* trusted on, which
    gets both sides right: shallow on the bank, and still deep along the Atlantic
    shore of the cays where the bottom drops away fast.

    Three ways a depth loses the benefit of the doubt, all refilled the same way:
    the coastline is finer than the grid there, the value is far deeper than its
    neighbourhood, or it claims more than twelve metres somewhere that is plainly
    a bank rather than ocean.
    """
    crowded = _box_mean(dry.astype(np.float32), FLATS_WINDOW) > FLATS_LAND_FRACTION
    sea = _sea_only(~dry)
    ocean = _is_ocean(depth, sea)
    doubted = (crowded
               | _implausible(depth, sea)
               | (~ocean & (depth > BANK_PLAUSIBLE_M)))
    out = _grow_into(depth, sea, trusted=sea & ~doubted & (depth > 0))

    # The mirror of _implausible, and it needs the opposite repair. A lone cell of
    # eight metres three kilometres out in water averaging two hundred is not a
    # pinnacle, it is the interpolation showing, and it drew as dark confetti
    # scattered across the open Atlantic. Refilling from the nearest trusted
    # neighbour is no use here — that takes the *shallowest* one, which is the wrong
    # direction — so these take the depth of the ocean around them instead.
    #
    # Restricted to water whose 3 km surroundings are plainly ocean, because on the
    # banks an isolated shallow patch is a coral head or a sand bore, and those are
    # the whole point of the layer.
    ctx = _box_mean_valid(out, sea & (out > 0), OCEAN_WINDOW)
    spike = sea & (ctx > OCEAN_CONTEXT_M) & (out < OCEAN_SPIKE_FRACTION * ctx)
    out = np.where(spike, ctx, out)

    # And nowhere close to shore may claim more depth than a beach could reach.
    reach = _cells_from(dry, SHORE_REACH_CELLS)
    out = np.minimum(out, SHORE_SLOPE_M_PER_CELL * reach)
    return np.where(sea, out, -1.0), sea


def render_png(grid, path, max_px=5200, land=None):
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
    sampled, sea = cleaned(sampled, dry)

    # Carry the water colour a little way *into* the land, which is not about
    # depth at all. The
    # image is magnified by ten or more when zoomed in, and MapLibre's linear
    # resampling interpolates the alpha channel as well as the colour — so a hard
    # water-to-transparent edge at the coast became a semi-transparent band a
    # source pixel wide, through which the pale background showed as a light halo
    # along every shore. Carrying the water colour a few pixels under the land
    # means the interpolation blends water into water; the coastline layer is drawn
    # on top, so nobody sees where it stops.
    sampled = _grow_into(sampled, np.ones_like(sea), passes=COAST_BLEED,
                         trusted=sampled > 0)
    rgba[:, :, :3], hit = _banded(sampled)
    rgba[:, :, 3] = np.where(hit, 255, 0)
    img = Image.fromarray(rgba, "RGBA")
    # Quantising to the handful of colours actually used makes the file a fraction
    # of the size; RGBA is kept for the transparent land and deep water.
    img.save(path, "PNG", optimize=True)
    return dict(path=path, width=w, height=h,
                coordinates=[[x0, y1], [x1, y1], [x1, y0], [x0, y0]],
                covered=float((rgba[:, :, 3] > 0).mean()))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fetch", action="store_true", help="download the grids")
    ap.add_argument("--force", action="store_true", help="re-download them")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    for which in GRIDS:
        if a.fetch or a.force or not os.path.exists(cache_path(which)):
            fetch(which, force=a.force)
    grid, fine = Grid("wide"), Grid("fine")
    for g in (grid, fine):
        print(f"{g.which:5} {g.ncols}x{g.nrows}, {g.cell * 111320:.0f} m cells, "
              f"bounds {tuple(round(v, 2) for v in g.bounds)}")
    if a.report:
        print(f"\n{'day':12} {'fixes':>6} {'shallowest':>11} {'median':>7} "
              f"{'<2 m':>6} {'<3 m':>6}")
        for label, r in day_summary(grid, fine).items():
            print(f"{label:12} {r['fixes']:6} {r['shallowest_m']:10.1f} m "
                  f"{r['median_m']:6.1f} m {r['under_2m']:6} {r['under_3m']:6}")


if __name__ == "__main__":
    main()
