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
# Cells per side to coarsen the grid by before drawing the bands, and how far to
# round their corners afterwards. 4 cells is about 244 m, and 240 m of rounding is
# roughly one coarse cell — together, about the generalisation the poster's drawn
# shoal halos had.
#
# Averaging the depths over a neighbourhood *before* banding was tried instead,
# while this was still a raster, and was clearly worse: it pulled wide areas of the
# bank onto the 4 m boundary, where the least variation flips a cell, and the chart
# dithered into a mosaic. Coarsening by whole cells and rounding the outline cannot
# do that.
COARSEN = 2
# Corner-cutting passes over each ring, and a small outward nudge afterwards.
#
# The corners were rounded by morphology first — dilate, erode twice, dilate — and
# that was a bad mistake: closing followed by opening deletes anything thinner than
# the radius, and the shallow bands are thin ribbons along the coast. It ate them
# off the shoreline and left a 240 m strip of bare background hugging every beach,
# which is the exact opposite of a shoal chart. Corner cutting moves vertices
# instead of adding and removing area, so a one-cell ribbon survives it.
#
# The nudge outward is what keeps the bands *touching* the shore: cutting a corner
# moves it inward a little, and the land is drawn on top, so erring outward costs
# nothing and erring inward shows as a pale gap.
# What to call water the coastline knows about and the grid does not. The tidal
# flats inside Great Abaco are the case that matters, and 1.0 m is the median of
# GMRT's own readings where it does report them there.
FLAT_DEPTH_M = 1.0
# Coarse cells per side to average the depths over before banding them, and the
# smallest piece of a band worth drawing. 10 cells is about 1.2 km, and 60,000 m2
# is four coarse cells.
#
# About 2 km, which is where smoothing stops being free. Rendered against the
# poster's drawn shoal halo at four settings, the band areas hold at roughly 1.0x
# the grid's own figures up to here and then start losing shallow water: 0.91x of
# the under-2 m band at 2.9 km and 0.85x at 3.9 km. Under-reporting shallows is the
# wrong direction for a chart about them, so this is the last setting that is only
# a cosmetic change.
#
# It will not reach the cleanliness of the halo it replaced, and no smoothing
# setting can. That halo left the water near-white with a thin rim, and 37.6% of
# the water inside the poster's frame is under four metres — it looked clean partly
# by being wrong. What remains between the two is tone, not geometry.
#
# The per-day figures are unaffected by any of this — they come from the 61 m grid.
COARSE_SMOOTH = 16
MIN_PART_M2 = 60000.0
# Depths are clipped to this before they are averaged. Nothing below the deepest
# band edge changes which band a cell is in, and without the clip the averaging
# reached across the shelf edge and mixed the grid's 400 m values into water of
# twelve to sixteen metres — which pushed 120 km2 of it out of the "under 20 m"
# band altogether, so the page background showed through as the deepest colour.
BAND_CLAMP_M = 22.0
# Coarse cells per side for the majority vote that cleans up each band's mask, and
# how close to land a cell must be to be exempt from it.
#
# Over the bank southwest of Great Guana the depths sit right on the 4 m edge —
# median 3.5 m, tenth to ninetieth 2.6 to 4.8 — so the mask there fragments into
# slivers, and since a run of cells along a row becomes one rectangle, each sliver
# came out as a horizontal lens. A vote over the neighbourhood cannot leave a
# one-cell sliver standing.
#
# The exemption matters more than the vote: a majority filter erodes thin ribbons,
# and the bands *are* thin ribbons along the shore. Eroding those is how the chart
# ended up with a strip of bare background against every beach once before.
MASK_MAJORITY = 7
MASK_SHORE_EXEMPT = 2
CHAIKIN_PASSES = 4
GRIP_M = 60.0
# How much of the smoothed outline to keep. This is what governs how smooth the
# bands actually look, more than the number of corner-cutting passes: at 45 m the
# 244 m staircase was still plainly a staircase, because simplifying threw away the
# curve that had just been cut into it. At 20 m the steps read as gentle scallops.
#
# Measured against the alternatives rather than guessed. A fourth cutting pass at
# 12 m (2.1 MB) is hard to tell from this (1.5 MB), and the residual waviness is
# not corner sharpness at all — it is the amplitude of the 244 m step itself, which
# corner cutting cannot remove. Coarsening less to shrink that step was the other
# way and is worse: 183 m cells cost 2.0 MB and bring back the isolated specks that
# coarsening exists to merge.
SIMPLIFY_M = 20.0

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


def _chaikin(pts, passes):
    """Corner cutting on a closed ring: each corner becomes two, a quarter in."""
    p = np.asarray(pts, dtype=np.float64)
    if len(p) > 1 and np.array_equal(p[0], p[-1]):
        p = p[:-1]
    if len(p) < 3:
        return pts
    for _ in range(passes):
        nxt = np.roll(p, -1, axis=0)
        q = np.empty((len(p) * 2, 2))
        q[0::2] = 0.75 * p + 0.25 * nxt
        q[1::2] = 0.25 * p + 0.75 * nxt
        p = q
    return np.vstack([p, p[:1]])


def _despeckle(geom, min_deg2):
    """Drop parts and holes below one coarse cell, so smoothing cannot fray.

    Smoothing the depths puts a wide area of the bank close to a band edge, and
    without this the edge frays into specks there instead of running as a line —
    which is how averaging depths failed the first time it was tried.
    """
    from shapely.geometry import Polygon
    from shapely import unary_union

    keep = []
    for g in (list(geom.geoms) if hasattr(geom, "geoms") else [geom]):
        if g.is_empty or not hasattr(g, "exterior") or g.area < min_deg2:
            continue
        holes = [h for h in g.interiors if Polygon(h).area >= min_deg2]
        keep.append(Polygon(g.exterior.coords, [h.coords for h in holes]))
    return unary_union(keep) if keep else geom


def _rounded(geom):
    """The staircase of coarse cells, smoothed, and never pulled off the shore."""
    from shapely.geometry import Polygon
    from shapely import make_valid, unary_union

    geom = _despeckle(geom, MIN_PART_M2 / (111320.0 * 99500.0))
    parts = []
    for g in (list(geom.geoms) if hasattr(geom, "geoms") else [geom]):
        if g.is_empty or not hasattr(g, "exterior"):
            continue
        p = Polygon(_chaikin(g.exterior.coords, CHAIKIN_PASSES),
                    [_chaikin(h.coords, CHAIKIN_PASSES) for h in g.interiors])
        if not p.is_valid:
            p = make_valid(p)
        parts.append(p)
    out = unary_union(parts)
    out = out.buffer(GRIP_M / 111320.0, join_style=1)
    return out.simplify(SIMPLIFY_M / 111320.0, preserve_topology=True)


def band_polygons(grid, land):
    """The depth bands as polygons: (hi, colour, label, geometry), deepest first.

    Built from the cells rather than by contouring them. Contouring was tried three
    times and lost 40-60% of the two shallow bands' area every time, differently
    each time — those bands are ribbons hugging the coast, which is where every
    assumption about ring winding and nesting broke. Here each run of band cells in
    a row becomes a rectangle and GEOS unions them, so holes and nesting are
    computed rather than inferred, and the area is exact at the coarsened cell size
    before rounding. Measured after rounding it comes to 1.01-1.07x the grid's own
    figure, always over rather than under, which is the safe direction for a chart
    about shoals.

    Polygons rather than a raster because a raster of a coarse grid can only be a
    staircase or a blur, and both were tried and both looked it. These are also
    smaller: 367 KB against 692 KB for the PNG they replace.
    """
    from shapely import unary_union
    from shapely.geometry import box

    x0, y0, x1, y1 = grid.bounds
    dry = _land_mask(land, grid.ncols, grid.nrows, x0, y0, x1, y1, lambda lat: lat)
    depth, sea = cleaned(grid.depth, dry)

    # Water the coastline knows about but the grid could not answer for — the tidal
    # flats inside Great Abaco, cut off from the flood fill or suppressed for sitting
    # in a neighbourhood that is mostly land — is flat, not deep. Left out it showed
    # as bare page background, which is the palest thing on the chart, so the marsh
    # read as the deepest water in the region while the open bank beside it read as
    # shoal. This is not a guess: where GMRT does report a depth in that maze the
    # median is 1.0 m, so this carries the grid's own answer into the cells it could
    # not resolve.
    flats = ~dry & ~(sea & (depth > 0))
    depth = np.where(flats, FLAT_DEPTH_M, depth)
    wet = ~dry & (depth > 0)

    # Coarsen to about 122 m. It was 244 m — closer to the generalisation the
    # poster's drawn halos had — but on the Atlantic wall off Elbow Cay the bands
    # crowd into a couple of hundred metres, so at 244 m each was narrower than a
    # cell and drew as a staircase rather than as a ribbon. Corner cutting cannot
    # help there: there is nothing to cut a corner off. What makes this affordable is
    # that the depths are averaged below, which suppresses the isolated specks that
    # finer cells used to bring back.
    k = COARSEN
    nr, nc = (grid.nrows // k) * k, (grid.ncols // k) * k
    dsum = np.where(wet, depth, 0.0)[:nr, :nc].reshape(nr // k, k, nc // k, k)
    wsum = wet[:nr, :nc].reshape(nr // k, k, nc // k, k)
    n = wsum.sum((1, 3))
    coarse = np.where(n > 0, dsum.sum((1, 3)) / np.maximum(n, 1), -1.0)
    # Any water in the block at all makes it water. Requiring most of the block to
    # be wet left the marsh lace — thousands of islets tens of metres across, so
    # every block there is mostly land — as unpainted holes. Blocks that straddle a
    # shore now reach a little way over it, which nobody sees: the land is drawn on
    # top, and erring that way is what keeps the bands against the beach.
    cwet = n > 0
    # Average the coarse depths a little before sorting them into bands. Where the
    # bottom shelves steadily — the Atlantic side of the cays — the contours really
    # are close to parallel with the shore, and without this each band's edge
    # wobbled by a cell or so on its own, so corner cutting rounded the wobble off
    # rather than removing it and the bands came out lumpy instead of running
    # together.
    #
    # This is the operation that failed at 61 m per-pixel, where it dithered the
    # bank into a mosaic. It is safe here because it runs on 244 m blocks and
    # _despeckle drops anything smaller than one of them, so a fraying edge cannot
    # survive as confetti.
    if COARSE_SMOOTH > 1:
        clamped = np.minimum(coarse, BAND_CLAMP_M)
        num = _box_mean(np.where(cwet, clamped, 0.0).astype(np.float32), COARSE_SMOOTH)
        den = _box_mean(cwet.astype(np.float32), COARSE_SMOOTH)
        coarse = np.where(cwet, num / np.maximum(den, 1e-6), coarse)

    # Blocks close to the shore keep their own value through the vote below.
    cshore = _cells_from(~cwet, MASK_SHORE_EXEMPT)
    near_shore = cwet & np.isfinite(cshore)

    cell = grid.cell * k
    top = y0 + grid.nrows * grid.cell
    out = []
    for lo, hi, colour, label in BANDS:
        if hi > 1e8:
            continue                  # the water background paints the deepest
        mask = cwet & (coarse > 0) & (coarse < hi)
        # A neighbourhood vote, so a band cannot be one cell thick, except where it
        # is against the shore and being thin is the truth.
        vote = _box_mean(mask.astype(np.float32), MASK_MAJORITY) > 0.5
        mask = (cwet & vote) | (mask & near_shore)
        pad = np.zeros((mask.shape[0], mask.shape[1] + 2), bool)
        pad[:, 1:-1] = mask
        boxes = []
        for r in range(mask.shape[0]):
            row = pad[r]
            edges = np.flatnonzero(row[1:] != row[:-1])
            hi_lat, lo_lat = top - r * cell, top - (r + 1) * cell
            boxes += [box(x0 + a * cell, lo_lat, x0 + b * cell, hi_lat)
                      for a, b in zip(edges[0::2], edges[1::2])]
        g = _rounded(unary_union(boxes))
        out.append((hi, colour, label, g))
    return out


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
