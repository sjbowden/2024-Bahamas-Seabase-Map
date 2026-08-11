#!/usr/bin/env python3
"""Frameable nautical-chart poster of the 2024 Bahamas Sea Base sailing tracks.

Renders a hero map of the Sea of Abaco with every day's GPS track, a strip of
per-day thumbnails, and a chart-style title block.

    python poster.py            # 200 dpi proof PNG
    python poster.py --final    # 300 dpi PNG + vector PDF
"""
import argparse
import glob
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Polygon as MplPolygon, FancyArrow
from matplotlib.path import Path
from matplotlib.patches import PathPatch

from abaco_geo import land_polygons
from trip import (AIRPORT, ANCHORAGES, DAYS, EXTENT, HOTEL, LAND_BBOX,
                  LAT0, MARINA, NM, PLACES, haversine, load_day, shoal,
                  transfer_route)


HERE = os.path.dirname(os.path.abspath(__file__))
ASPECT = 1.0 / math.cos(math.radians(LAT0))   # deg lon -> deg lat scaling

# ---------------------------------------------------------------- palette ---
# chart convention: deep water reads almost white, shoals get bluer inshore
C_WATER      = "#E7F1F5"
C_SHOAL_1    = "#CDE3EE"
C_SHOAL_2    = "#B2D3E6"
C_LAND       = "#F0E2C2"
C_LAND_EDGE  = "#8A7F6A"
C_INK        = "#2E3A42"
C_INK_SOFT   = "#5C6B75"
C_PAPER      = "#FBF6EA"
C_RULE       = "#B9AC91"

# ------------------------------------------------------------------- fonts ---
# The poster is set in P052 (a Palatino) and Lato. If matplotlib can't find
# them it doesn't complain — it quietly resolves *both* to DejaVu Sans, so the
# sheet loses its serif altogether and every string sets 7–29% wider. Register
# whatever is in fonts/ first, then say plainly whether it worked.
FONT_DIR = os.path.join(HERE, "fonts")
FONT_FAMILIES = ("P052", "Lato")


def _have_family(name):
    try:
        font_manager.findfont(FontProperties(family=name),
                              fallback_to_default=False)
        return True
    except ValueError:
        return False


def register_fonts(verbose=True):
    """Load font files kept beside the script. The directory is gitignored, so
    populate it from the system copies (see the README) or drop the files in."""
    loaded = 0
    if os.path.isdir(FONT_DIR):
        for fn in sorted(os.listdir(FONT_DIR)):
            if fn.lower().endswith((".otf", ".ttf")):
                try:
                    font_manager.fontManager.addfont(os.path.join(FONT_DIR, fn))
                    loaded += 1
                except Exception as exc:
                    print(f"  font {fn}: {exc}", file=sys.stderr)
    missing = [f for f in FONT_FAMILIES if not _have_family(f)]
    if missing and verbose:
        print(f"WARNING: {', '.join(missing)} not available — matplotlib will "
              f"substitute DejaVu Sans and the poster will not look right.\n"
              f"         Put the font files in {FONT_DIR}/ (see README).",
              file=sys.stderr)
    return loaded, missing


register_fonts()

SERIF = FontProperties(family="P052")
SERIF_I = FontProperties(family="P052", style="italic")
SANS = FontProperties(family="Lato")
SANS_B = FontProperties(family="Lato", weight="bold")

# DAYS, load_day() and the rest of "what a sailing day is" live in trip.py, so
# the map build can read them without importing matplotlib.

# PLACES, ANCHORAGES, AIRPORT, HOTEL and MARINA moved to trip.py alongside DAYS:
# the map names the same places, and one list means the two artefacts cannot
# drift apart about where Hope Town is.


# --------------------------------------------------------------- rendering ---
# The offset applies only along the Tilloo/Elbow run, where four days share one
# channel. Everywhere else the tracks are drawn exactly as recorded; the shift
# ramps in and out over FADE so there is no kink at the boundary.
# Just the channel along the west side of Elbow Cay: from Tilloo Cut north to
# short of Hope Town. That is where the days genuinely share one lane — three
# run within 250 m of each other from 26.485 to 26.525. South of Tilloo Cut the
# water opens onto Tilloo Bank and they separate on their own.
CORRIDOR_S, CORRIDOR_N, CORRIDOR_FADE = 26.470, 26.520, 0.010


def _corridor_gate(lat):
    """1 inside the crowded run, 0 outside, linear across the margins."""
    lo = np.clip((lat - (CORRIDOR_S - CORRIDOR_FADE)) / CORRIDOR_FADE, 0.0, 1.0)
    hi = np.clip(((CORRIDOR_N + CORRIDOR_FADE) - lat) / CORRIDOR_FADE, 0.0, 1.0)
    return np.minimum(lo, hi)


def offset_track(pts, d):
    """Shift a track sideways by `d` degrees of latitude, perpendicular to its
    own heading — but only through the Tilloo/Elbow run, where four days share
    one channel and would otherwise overplot. It is a deliberate cartographic
    lie of up to ~170 m, confined to the one stretch that needs it."""
    if not d or len(pts) < 3:
        return pts
    k = math.cos(math.radians(LAT0))
    P = np.array([(p[2] * k, p[1]) if len(p) > 2 else (p[0] * k, p[1])
                  for p in pts])
    S = P[1:] - P[:-1]
    Ls = np.hypot(S[:, 0], S[:, 1])
    keep = Ls > 0
    P = np.vstack([P[:-1][keep], P[-1]])
    S, Ls = S[keep], Ls[keep]
    if len(S) < 2:
        return pts
    U = S / Ls[:, None]                       # unit heading of each segment
    n = len(P)

    # Turn radius at each vertex. Offsetting a bend by more than its own radius
    # is what folds the line into a loop, so measure the radius and taper the
    # offset away wherever it would.
    ang = np.zeros(n)
    ang[1:-1] = np.arccos(np.clip((U[:-1] * U[1:]).sum(axis=1), -1.0, 1.0))
    span = np.zeros(n)
    span[1:-1] = (Ls[:-1] + Ls[1:]) / 2.0
    radius = np.where(ang > 1e-9, span / np.maximum(ang, 1e-9), np.inf)

    # a bend is only safe if the whole neighbourhood is gentle, so take the
    # tightest radius nearby, then ease the taper in and out
    w = 15
    pad = np.pad(radius, w // 2, mode="edge")
    tight = np.array([pad[i:i + w].min() for i in range(n)])
    scale = np.clip(tight / (2.0 * abs(d)), 0.0, 1.0)
    box = np.ones(w) / w
    scale = np.convolve(np.pad(scale, w // 2, mode="edge"), box, mode="valid")[:n]

    T = np.empty_like(P)
    T[0], T[-1] = U[0], U[-1]
    T[1:-1] = U[:-1] + U[1:]
    Lt = np.hypot(T[:, 0], T[:, 1])
    bad = Lt < 1e-12                          # a true reversal: heading is moot
    Lt[bad] = 1.0
    N = np.column_stack([-T[:, 1] / Lt, T[:, 0] / Lt])
    N[bad] = 0.0

    scale = scale * _corridor_gate(P[:, 1])   # true outside the crowded run
    Q = P + N * (d * scale)[:, None]
    # tapering prevents nearly all folds; trim whatever slips through, but only
    # where we actually moved the line
    trimmed = _trim_loops([tuple(q) for q in Q], tol=2.0 * abs(d),
                          active=scale > 1e-3)
    return [(x / k, y) for x, y in trimmed]


def _trim_loops(run, window=80, tol=None, active=None):
    """Cut the little loops an offset throws off wherever the track turns
    tighter than the offset distance.

    Walk the line; where it crosses itself a short way ahead, jump straight to
    the crossing point and drop the loop between. Taking the *farthest*
    crossing in the window removes a whole tangle in one step. Unlike GEOS's
    offset_curve this only ever deletes the spurious loop, never a stretch of
    real route.
    """
    if len(run) < 4:
        return run
    A = np.asarray(run, dtype=float)
    n = len(A)
    out = [A[0]]
    i = 0
    while i < n - 1:
        p, r = A[i], A[i + 1] - A[i]
        jump = None
        for j in range(min(i + window, n - 1) - 1, i + 1, -1):
            q, s = A[j], A[j + 1] - A[j]
            den = r[0] * s[1] - r[1] * s[0]
            if den == 0:
                continue
            dq = q - p
            t = (dq[0] * s[1] - dq[1] * s[0]) / den
            u = (dq[0] * r[1] - dq[1] * r[0]) / den
            if 0 < t < 1 and 0 < u < 1:
                x = p + t * r
                # Only snip a fold the offset itself created. A genuine loop —
                # the boat actually circling — is far wider than the offset, so
                # bail out rather than quietly straighten it away.
                if tol is not None and np.abs(A[i:j + 1] - x).max() > tol:
                    continue
                # never touch stretches drawn at their true position — a fold
                # can only be ours where the offset is actually applied
                if active is not None and not active[i:j + 1].all():
                    continue
                jump = (j, x)
                break
        if jump:
            out.append(jump[1])
            i = jump[0] + 1
        else:
            out.append(A[i + 1])
            i += 1
    return [tuple(v) for v in out]


def depth_bands(land):
    """Measured depth bands for the sheet, from GMRT, as (colour, geometry).

    The shoal halo this replaces was cartography: two buffers around the land,
    coloured to *suggest* shallows and knowing nothing about the seabed. The map's
    depth layer says the same thing from measurement, and the poster's own water
    colours are the top of that ramp — the two darker steps were added below them —
    so it drops onto the sheet without a new colour idea.

    Masked with the poster's *own* coastline, at full resolution, rather than the
    map's simplified one: the bands then stop exactly where this sheet draws the
    shore, and the land is filled over them afterwards, so any overrun is covered.
    """
    from map import depth as D

    grid = D.merged()
    bands = D.band_polygons(grid, land)
    # Deepest first. Each band is everything shallower than its upper edge, so they
    # nest, and in the order they arrive — shallowest first — every band buries the
    # one before it and the whole sheet comes out the colour of the deepest.
    return [(colour, geom)
            for hi, colour, _, geom in sorted(bands, key=lambda b: -b[0])]


def draw_chart(ax, extent, land, days, tracks, *, detail=True, lw_scale=1.0,
               show_airport=False, spread=False, depth=None,
               skip_labels=(), skip_anchorages=(), label_nudge=None, vessel=None,
               airport_text=None, airport_nudge=(0.0, 0.0)):
    w, e, s, n = extent
    ax.set_xlim(w, e)
    ax.set_ylim(s, n)
    ax.set_aspect(ASPECT)
    ax.set_facecolor(C_WATER)
    for spine in ax.spines.values():
        spine.set_color(C_INK)
        spine.set_linewidth(1.1 * lw_scale)
    ax.set_xticks([])
    ax.set_yticks([])

    # measured depths if they were passed in, otherwise the drawn shoal halo;
    # then the land itself over the top of either
    if depth:
        for colour, geom in depth:          # deepest first, shallowest on top
            _fill(ax, geom, colour, None, 0)
    else:
        for buf, col in ((0.0060, C_SHOAL_1), (0.0026, C_SHOAL_2)):
            _fill(ax, shoal(land, buf), col, None, 0)
    _fill(ax, land, C_LAND, C_LAND_EDGE, 0.5 * lw_scale)

    if detail:                       # the vessel belongs on the hero chart only
        # A square page puts its top edge much closer to the engraving than the
        # sheet's portrait frame does, so the caller can move and resize it.
        vlon, vlat, vwidth = vessel or (-76.9515, 26.6460, 0.0570)
        draw_vessel(ax, vlon, vlat, vwidth)

    # tracks — a pale casing under each line keeps crossings readable where
    # five days share the same channel
    def line(pts, color, lw, dash=None, case=3.2):
        if len(pts) < 2:
            return
        xy = np.array([(p[2], p[1]) if len(p) > 2 else p for p in pts])
        ax.plot(xy[:, 0], xy[:, 1], lw=case * lw_scale, color=C_PAPER,
                alpha=0.88, zorder=5, solid_capstyle="round",
                solid_joinstyle="round")
        ax.plot(xy[:, 0], xy[:, 1], lw=lw * lw_scale, color=color, zorder=6,
                ls=dash or "-", solid_capstyle="round",
                solid_joinstyle="round", dash_capstyle="round")

    for d in days:
        t = tracks[d["file"]]
        if not d.get("ashore"):
            # everything afloat gets the day's colour, even Thursday's 270 m
            # hop off the mooring — it was still time on the water
            afloat = (offset_track(t["afloat"], d.get("offset", 0.0))
                      if spread else t["afloat"])
            line(afloat, d.get("sail_color", d["color"]),
                 2.0 if d["sail"] else 1.8, case=4.4 if d["sail"] else 3.6)
        if d.get("transfer"):
            line(transfer_route(), d["color"], 1.4, (0, (1, 2.2)), case=3.0)
        line(t["walk"], d.get("sail_color", d["color"]), 1.6, (0, (1, 2.0)), 3.0)
        line(t["road"], d["color"], 1.3, (0, (4, 3)), 3.2)

    if not detail:
        if show_airport:                          # only where it's meaningful
            draw_airport(ax, lw_scale, label=False)
        return

    draw_airport(ax, lw_scale, text=airport_text, nudge=airport_nudge)

    # Labels a caller may drop or shift. The two artefacts frame the same water at
    # different shapes and scales, so a name that sits clear on the sheet can land
    # on a track on a square page. Defaults are empty: the sheet is unaffected.
    nudge = label_nudge or {}
    skip = set(skip_labels)

    # anchorages
    for lon, lat, text, ha, va in ANCHORAGES:
        # skip_labels drops the name and keeps the ring; skip_anchorages drops both,
        # for a page where an unnamed ring would be a mark with nothing to say.
        if text in set(skip_anchorages):
            continue
        if text in skip:
            continue
        # The ring stays on the anchorage — that is a measured position, and moving
        # it would say the boat lay somewhere it did not. Only the name shifts.
        ax.plot([lon], [lat], marker="o", ms=6 * lw_scale, mfc=C_PAPER,
                mec=C_INK, mew=1.3 * lw_scale, zorder=8)
        lon, lat = (lon + nudge.get(text, (0, 0))[0],
                    lat + nudge.get(text, (0, 0))[1])
        dx = {"left": 0.006, "right": -0.006}.get(ha, 0.0)
        dy = {"top": -0.005, "bottom": 0.005}.get(va, 0.0)
        ax.text(lon + dx, lat + dy, text, fontproperties=SANS_B,
                fontsize=9.5 * lw_scale, color=C_INK, ha=ha, va=va, zorder=8,
                path_effects=_halo(2.6 * lw_scale))

    # place names
    sizes = {"town": 10.5, "isle": 9.5, "big": 15.0, "water": 13.0}
    for lon, lat, text, kind, ha, va in PLACES:
        if text in skip:
            continue
        lon, lat = (lon + nudge.get(text, (0, 0))[0],
                    lat + nudge.get(text, (0, 0))[1])
        fp = SERIF_I if kind == "water" else SERIF
        col = "#5E7C8A" if kind == "water" else C_INK
        if kind == "big":
            col = "#7A6E58"
        pad = 0.004 if ha == "left" else (-0.004 if ha == "right" else 0)
        ax.text(lon + pad, lat, text, fontproperties=fp,
                fontsize=sizes[kind] * lw_scale, color=col, ha=ha, va=va,
                zorder=9, path_effects=_halo(3.0 * lw_scale))


def badge_positions(days, tracks):
    """Pick where to stamp each day's number: the point on that day's track
    that sits farthest from every other day's track, so the badge lands on the
    stretch of water unique to that day rather than in the shared channel."""
    def arr(d, step):
        pts = tracks[d["file"]]["afloat"][::step]
        return np.array([(p[2] * math.cos(math.radians(p[1])), p[1]) for p in pts])

    # keep badges off the labelled features too, not just off other tracks
    avoid = [(lon, lat) for lon, lat, *_ in ANCHORAGES]
    avoid.append((AIRPORT[0], AIRPORT[1]))
    avoid += [(lon, lat) for lon, lat, _t, kind, *_ in PLACES if kind != "water"]
    avoid_xy = np.array([(lon * math.cos(math.radians(lat)), lat)
                         for lon, lat in avoid])

    sailing = [d for d in days if d["sail"]]
    out = {}
    for d in sailing:
        if d.get("badge_at"):
            out[d["file"]] = d["badge_at"]
            continue
        mine = arr(d, 3)
        others = [arr(o, 2) for o in sailing if o is not d]
        if not len(mine) or not others:
            continue
        other = np.vstack(others + [avoid_xy])
        best, bestd = None, -1.0
        for i in range(0, len(mine), max(1, len(mine) // 400)):
            dd = np.min(np.hypot(other[:, 0] - mine[i, 0], other[:, 1] - mine[i, 1]))
            if dd > bestd:
                bestd, best = dd, i
        raw = tracks[d["file"]]["afloat"][::3][best]
        out[d["file"]] = (raw[2], raw[1])
    return out


def draw_badges(ax, days, badges, lw_scale=1.0):
    for d in days:
        if d.get("n") is None or d["file"] not in badges:
            continue
        lon, lat = badges[d["file"]]
        ax.plot([lon], [lat], marker="o", ms=15 * lw_scale, mfc=d["color"],
                mec=C_PAPER, mew=1.8 * lw_scale, zorder=11)
        ax.text(lon, lat, str(d["n"]), fontproperties=SANS_B,
                fontsize=10.5 * lw_scale, color=C_PAPER, ha="center",
                va="center_baseline", zorder=12)


def _plane_marker(rotate_deg=45.0):
    """Top-down airliner silhouette, as a matplotlib marker path."""
    v = [(0.00, 1.00), (0.11, 0.60), (0.11, 0.30), (1.00, -0.06), (1.00, -0.26),
         (0.11, -0.16), (0.09, -0.62), (0.40, -0.86), (0.40, -1.00),
         (0.00, -0.88), (-0.40, -1.00), (-0.40, -0.86), (-0.09, -0.62),
         (-0.11, -0.16), (-1.00, -0.26), (-1.00, -0.06), (-0.11, 0.30),
         (-0.11, 0.60)]
    a = math.radians(rotate_deg)
    ca, sa = math.cos(a), math.sin(a)
    v = [(x * ca - y * sa, x * sa + y * ca) for x, y in v]
    codes = [Path.MOVETO] + [Path.LINETO] * (len(v) - 1) + [Path.CLOSEPOLY]
    return Path(v + [v[0]], codes)


PLANE = _plane_marker()


VESSEL_ART = os.path.join(HERE, "catamaran.png")
_VESSEL_CACHE = {}


def vessel_rgba(margin=12):
    """The catamaran, keyed to a real alpha channel and cropped to its ink.

    The supplied PNG carries an alpha channel but is fully opaque — a flattened
    export. The paper is neutral (saturation ~3) while the ink is sepia
    (~25), so key on chroma plus lightness and take opacity from darkness.
    That also lets the chart show through between the strokes, which is what
    makes it sit *on* the chart rather than on an opaque plate.
    """
    if "img" not in _VESSEL_CACHE:
        from PIL import Image
        src = np.asarray(Image.open(VESSEL_ART).convert("RGB"), dtype=float)
        sat = src.max(axis=2) - src.min(axis=2)
        lum = src.mean(axis=2)
        alpha = np.clip((255.0 - lum) / 255.0 * 1.9, 0, 1)
        alpha[(sat <= 8) & (lum > 170)] = 0.0
        ys, xs = np.nonzero(alpha > 0.02)          # trim the empty margin so
        y0 = max(ys.min() - margin, 0)             # placement is predictable
        y1 = min(ys.max() + margin + 1, alpha.shape[0])
        x0 = max(xs.min() - margin, 0)
        x1 = min(xs.max() + margin + 1, alpha.shape[1])
        _VESSEL_CACHE["img"] = np.dstack([src / 255.0, alpha])[y0:y1, x0:x1]
    return _VESSEL_CACHE["img"]


def draw_vessel(ax, lon, lat, width_deg, alpha=1.0, zorder=4):
    """Drop the engraving into open water, sized so it keeps its own aspect
    once the map's longitude stretch is accounted for."""
    img = vessel_rgba()
    h, w = img.shape[:2]
    height_deg = width_deg * (h / w) / ASPECT
    ax.imshow(img, extent=(lon - width_deg / 2, lon + width_deg / 2,
                           lat - height_deg / 2, lat + height_deg / 2),
              aspect="auto", zorder=zorder, alpha=alpha, interpolation="bilinear")


def draw_airport(ax, lw_scale=1.0, label=True, text=None, nudge=(0.0, 0.0)):
    lon, lat, code, name = AIRPORT
    ax.plot([lon], [lat], marker=PLANE, ms=15 * lw_scale, mfc=C_INK,
            mec=C_PAPER, mew=0.9 * lw_scale, zorder=10, clip_on=True,
            linestyle="none")
    text = text or (f"{code}  {name}" if label else code)
    # The marker stays on the runway; only the name may move.
    lon, lat = lon + nudge[0], lat + nudge[1]
    ax.text(lon, lat - 0.0075 * lw_scale, text, fontproperties=SANS,
            fontsize=8.5 * lw_scale, color=C_INK, ha="center", va="top",
            zorder=10, clip_on=True,      # text is unclipped by default and
            path_effects=_halo(2.6 * lw_scale))   # leaks outside the panel


def _fill(ax, geom, face, edge, lw):
    if geom is None or geom.is_empty:
        return
    verts, codes = [], []
    for g in getattr(geom, "geoms", [geom]):
        if g.geom_type != "Polygon":
            continue
        for ring in [g.exterior] + list(g.interiors):
            c = list(ring.coords)
            verts.extend(c)
            codes.extend([Path.MOVETO] + [Path.LINETO] * (len(c) - 2) + [Path.CLOSEPOLY])
    if not verts:
        return
    patch = PathPatch(Path(verts, codes), facecolor=face,
                      edgecolor=edge or "none", lw=lw, zorder=2,
                      antialiased=True)
    ax.add_patch(patch)


def _halo(lw):
    import matplotlib.patheffects as pe
    return [pe.withStroke(linewidth=lw, foreground=C_PAPER, alpha=0.85)]


def _dm(value, pos, neg):
    """26.3667 -> 26°22′N"""
    hemi = pos if value >= 0 else neg
    v = abs(value)
    d = int(v)
    m = int(round((v - d) * 60))
    if m == 60:
        d, m = d + 1, 0
    return f"{d}°{m:02d}′{hemi}"


def chart_neatline(ax, extent, fig, lw_scale=1.0, label_every=5,
                   corner_clip=True):
    """The graduated border of a paper chart: a band ticked off in whole
    minutes of arc, alternating light and dark, labelled every 5'."""
    w, e, s, n = extent
    pos = ax.get_position()
    fw, fh = fig.get_size_inches()
    band_in = 0.105
    tx = band_in / (pos.width * fw) * (e - w)
    ty = band_in / (pos.height * fh) * (n - s)

    # blank the border area so map content doesn't run under the graduations
    outer = [(w, s), (e, s), (e, n), (w, n), (w, s)]
    inner = [(w + tx, s + ty), (w + tx, n - ty), (e - tx, n - ty),
             (e - tx, s + ty), (w + tx, s + ty)]
    codes = ([Path.MOVETO] + [Path.LINETO] * 3 + [Path.CLOSEPOLY]) * 2
    ax.add_patch(PathPatch(Path(outer + inner, codes), facecolor=C_PAPER,
                           edgecolor="none", zorder=14))

    def bands(lo, hi, horizontal, clip=None):
        for m in range(math.floor(lo * 60), math.ceil(hi * 60)):
            a, b = max(m / 60.0, lo), min((m + 1) / 60.0, hi)
            if clip is not None:
                a, b = max(a, clip[0]), min(b, clip[1])
            if b <= a or m % 2:
                continue
            if horizontal:
                for y0 in (s, n - ty):
                    ax.add_patch(plt.Rectangle((a, y0), b - a, ty,
                                               facecolor=C_INK, edgecolor="none",
                                               zorder=15))
            else:
                for x0 in (w, e - tx):
                    ax.add_patch(plt.Rectangle((x0, a), tx, b - a,
                                               facecolor=C_INK, edgecolor="none",
                                               zorder=15))

    # The top and bottom bands are graduated in longitude and the sides in latitude,
    # and drawn corner to corner they overlap in the corners — where a dark cell of
    # one runs into a light cell of the other, so the top edge's rhythm appeared to
    # break. Clipping each edge to the span between the other two keeps every edge
    # graduated in its own units, and leaves the four corners as plain squares.
    if corner_clip:
        bands(w, e, True, clip=(w + tx, e - tx))
        bands(s, n, False, clip=(s + ty, n - ty))
    else:
        bands(w, e, True)
        bands(s, n, False)

    for rect in ((w, s, e - w, n - s), (w + tx, s + ty, e - w - 2 * tx, n - s - 2 * ty)):
        ax.add_patch(plt.Rectangle(rect[:2], rect[2], rect[3], fill=False,
                                   edgecolor=C_INK, lw=1.0 * lw_scale, zorder=16))

    # labels outside the neatline, skipping anything crowding a corner
    for m in range(math.ceil(w * 60), math.floor(e * 60) + 1):
        x = m / 60.0
        if m % label_every or x - w < 0.012 or e - x < 0.012:
            continue
        ax.text(x, s - (n - s) * 0.008, _dm(x, "E", "W"), fontproperties=SANS,
                fontsize=7.4 * lw_scale, color=C_INK, ha="center", va="top",
                zorder=16, clip_on=False)
    for m in range(math.ceil(s * 60), math.floor(n * 60) + 1):
        y = m / 60.0
        if m % label_every or y - s < 0.012 or n - y < 0.012:
            continue
        ax.text(w - (e - w) * 0.008, y, _dm(y, "N", "S"), fontproperties=SANS,
                fontsize=7.4 * lw_scale, color=C_INK, ha="center", va="bottom",
                rotation=90, zorder=16, clip_on=False)


def scale_bar(ax, extent, y_frac=0.045, x_frac=0.06, nm_len=5, lw_scale=1.0,
              caption_top=False):
    """A graduated scale bar.

    `caption_top` follows the usual convention for a map legend — the units named
    above the bar and the numbers beneath its ends — rather than the sheet's, which
    hangs "0" and "5 nautical miles" together under the two ends.
    """
    w, e, s, n = extent
    dlon = nm_len * NM / (111320.0 * math.cos(math.radians(LAT0)))
    x0 = w + (e - w) * x_frac
    y0 = s + (n - s) * y_frac
    h = (n - s) * 0.006
    for i in range(nm_len):
        ax.add_patch(plt.Rectangle((x0 + i * dlon / nm_len, y0), dlon / nm_len, h,
                                   facecolor=C_INK if i % 2 == 0 else C_PAPER,
                                   edgecolor=C_INK, lw=0.8 * lw_scale, zorder=10))
    if caption_top:
        ax.text(x0 + dlon / 2, y0 + h * 2.4, "nautical miles", fontproperties=SANS,
                fontsize=8 * lw_scale, ha="center", va="bottom", color=C_INK,
                zorder=10)
        for i in (0, nm_len):
            ax.text(x0 + i * dlon / nm_len, y0 - h * 1.2, f"{i:d}",
                    fontproperties=SANS, fontsize=8 * lw_scale, ha="center",
                    va="top", color=C_INK, zorder=10)
    else:
        ax.text(x0, y0 - h * 2.2, "0", fontproperties=SANS, fontsize=8 * lw_scale,
                ha="center", va="top", color=C_INK, zorder=10)
        ax.text(x0 + dlon, y0 - h * 2.2, f"{nm_len} nautical miles",
                fontproperties=SANS, fontsize=8 * lw_scale, ha="center", va="top",
                color=C_INK, zorder=10)


# magnetic variation at 26°30'N 77°03'W for March 2024, from the WMM 2020
# coefficients (cross-checks to -9.12° against WMM 2025 at epoch 2025.0)
VARIATION_DEG = -9.081
VARIATION_TEXT = "VAR  9°05′ W  (2024)"
VARIATION_RATE = "ANNUAL INCREASE  4′"


C_ROSE = "#43362B"          # sepia engraving ink
C_ROSE_MAG = "#8C4A32"      # faded red for the magnetic ring


def draw_fleur(ax, cx, cy, height, color, lw_scale=1.0, zorder=13):
    """A heraldic fleur-de-lis, drawn about (cx, cy) with the given height.

    Built as four pieces because that is how the emblem is actually composed:
    a tall centre petal, two side petals that sweep out and curl *downward*
    into a scroll, a banded waist, and a flared foot beneath it. Earlier
    versions had the side petals pointing up like horns and no foot at all,
    which is what made it read as a trident.

    Unit space runs y 0..1 with the tip at the top; x is scaled by the map
    aspect so the emblem stays upright and unsquashed.
    """
    C4, M, L = Path.CURVE4, Path.MOVETO, Path.LINETO

    def bez(pts, t):
        p0, p1, p2, p3 = (np.asarray(p, float) for p in pts)
        t = t[:, None]
        return ((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1
                + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)

    def ribbon(segments, w_start, w_end):
        """A tapering band of constant-ish width following a curved spine.

        The side petal is a ribbon that curls down and under, not a lobe — so
        sweep a width along a spine rather than trying to guess the outline's
        control points directly.
        """
        spine = np.vstack([bez(sg, np.linspace(0, 1, 60)) for sg in segments])
        d = np.gradient(spine, axis=0)
        d /= np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)[:, None]
        nrm = np.column_stack([-d[:, 1], d[:, 0]])
        w = np.linspace(w_start, w_end, len(spine))[:, None] / 2.0
        return np.vstack([spine + nrm * w, (spine - nrm * w)[::-1]])

    def mirror(p):
        return Path(np.column_stack([-p.vertices[:, 0], p.vertices[:, 1]]),
                    p.codes)

    # centre petal: a slender leaf, flanks slightly concave below the tip
    centre = Path(
        [(0, 1.00),
         (0.030, 0.82), (0.080, 0.66), (0.098, 0.50),
         (0.108, 0.46), (0.108, 0.42), (0.098, 0.360),
         (-0.098, 0.360),
         (-0.108, 0.42), (-0.108, 0.46), (-0.098, 0.50),
         (-0.080, 0.66), (-0.030, 0.82), (0, 1.00)],
        [M, C4, C4, C4, C4, C4, C4, L, C4, C4, C4, C4, C4, C4])
    # outer petal: the big scroll, out over the top and hooked back under
    outer = Path(ribbon([[(0.055, 0.420), (0.092, 0.588), (0.192, 0.642), (0.310, 0.592)],
                         [(0.310, 0.592), (0.402, 0.552), (0.430, 0.452), (0.352, 0.410)]],
                        0.145, 0.006))
    # inner tendril: the second, smaller curl that rises beside the centre
    # petal and hooks outward — the reference has two curls a side, not one
    inner = Path(ribbon([[(0.068, 0.380), (0.100, 0.545), (0.145, 0.665), (0.212, 0.722)],
                         [(0.212, 0.722), (0.268, 0.768), (0.312, 0.706), (0.268, 0.664)]],
                        0.052, 0.005))
    # foot: a stem between two scrolls that curl outward and back up
    stem = Path(
        [(-0.058, 0.320),
         (-0.052, 0.240), (-0.048, 0.150), (-0.052, 0.070),
         (-0.030, 0.030), (0.030, 0.030), (0.052, 0.070),
         (0.048, 0.150), (0.052, 0.240), (0.058, 0.320)],
        [M, C4, C4, C4, C4, C4, C4, C4, C4, C4])
    curl = Path(ribbon([[(0.030, 0.220), (0.100, 0.160), (0.175, 0.098), (0.240, 0.130)],
                        [(0.240, 0.130), (0.302, 0.161), (0.284, 0.248), (0.212, 0.244)]],
                       0.066, 0.006))

    # a dark core inside the centre petal — the engraving is an outline
    # drawing with the parchment showing through, not a silhouette, but the
    # centre petal keeps a filled heart
    core = Path([(x * 0.42, 0.40 + (y - 0.40) * 0.88) for x, y in centre.vertices],
                centre.codes)

    tr = (matplotlib.transforms.Affine2D()
          .scale(height * ASPECT, height).translate(cx, cy - height * 0.5)
          + ax.transData)
    # All outline with the paper showing through — filling the side petals
    # solid was tried and reads as heavy horns; the engraving's value is much
    # lighter than it first appears, carried by line rather than mass.
    for p in (outer, mirror(outer), inner, mirror(inner),
              stem, curl, mirror(curl), centre):
        ax.add_patch(PathPatch(p, transform=tr, facecolor=C_PAPER,
                               edgecolor=color, lw=0.55 * lw_scale,
                               zorder=zorder, joinstyle="round"))
    ax.add_patch(PathPatch(core, transform=tr, facecolor=color,
                           edgecolor=color, lw=0.3 * lw_scale,
                           zorder=zorder + 1))
    # the banded waist: a light capsule with a dark edge, drawn as a dark line
    # cased by a slightly thinner light one
    y = cy - height * 0.5 + height * 0.330
    x0 = cx - height * ASPECT * 0.175
    x1 = cx + height * ASPECT * 0.175
    ax.plot([x0, x1], [y, y], color=color, lw=2.6 * lw_scale,
            zorder=zorder + 2, solid_capstyle="round")
    ax.plot([x0, x1], [y, y], color=C_PAPER, lw=1.5 * lw_scale,
            zorder=zorder + 3, solid_capstyle="round")


def compass_rose(ax, lon, lat, R, lw_scale=1.0, *, magnetic=True,
                 numerals=True, ring=1.00, eyelets=True, letter_r=1.26,
                 fleur_r=1.68):
    """An engraved chart rose.

    Star, rhumb fan and cardinal spears follow the hand-drawn roses of period
    charts: narrow points shaded with strokes running along their own axis, and
    cardinals that break clean through the ring to a spearhead outside it. The
    two graduated rings are the modern part and carry the actual information —
    true bearings on the outer, magnetic within, offset by the local variation.
    Numerals are dropped at the four cardinals to give the spears somewhere to
    go, and the letters take their place.

    All geometry is built in unit space (1.0 == R, x already stretched by the
    map aspect) so circles stay circular and hatch spacing stays even.
    """
    def XY(xu, yu):
        return (lon + xu * R * ASPECT, lat + yu * R)

    def axes_for(bearing):
        a = math.radians(bearing)
        return (np.array([math.sin(a), math.cos(a)]),      # along
                np.array([math.cos(a), -math.sin(a)]))     # across

    def upoly(pts, face, edge, lw, z=11):
        ax.add_patch(MplPolygon([XY(*p) for p in pts], closed=True,
                                facecolor=face, edgecolor=edge,
                                lw=lw * lw_scale, zorder=z, joinstyle="miter"))

    def graduated(radius, rot, every, med, long_, every_num, color, fs, skip=()):
        a = np.linspace(0.0, 2.0 * math.pi, 721)
        for rr, wdt in ((radius, 0.9), (radius * 0.885, 0.6)):
            ax.plot(lon + rr * R * ASPECT * np.sin(a), lat + rr * R * np.cos(a),
                    color=color, lw=wdt * lw_scale, zorder=11)
        for deg in range(0, 360, every):
            if deg % long_ == 0:
                inner, wdt = radius * 0.885, 0.9
            elif deg % med == 0:
                inner, wdt = radius * 0.925, 0.65
            else:
                inner, wdt = radius * 0.950, 0.35
            al, _ = axes_for(deg + rot)
            p, q = XY(*(al * inner)), XY(*(al * radius))
            ax.plot([p[0], q[0]], [p[1], q[1]], color=color, lw=wdt * lw_scale,
                    zorder=11, solid_capstyle="butt")
        for deg in ([] if not every_num else range(0, 360, every_num)):
            if deg in skip:
                continue
            al, _ = axes_for(deg + rot)
            x, y = XY(*(al * radius * 0.805))
            ax.text(x, y, f"{deg:d}", fontproperties=SANS,
                    fontsize=fs * lw_scale, color=color, ha="center",
                    va="center", zorder=12, rotation=-(deg + rot),
                    rotation_mode="anchor")

    # The graduated rings are the informative part, and a small rose cannot carry
    # them: at photobook size the two rings and two sets of numerals became a grey
    # smudge, so the caller can ask for the true ring alone, tighter and unnumbered.
    graduated(ring, 0.0, 1, 5, 10, 30 if numerals else 0, C_ROSE, 6.0,
              skip=(0, 90, 180, 270))
    if magnetic:
        graduated(0.79, VARIATION_DEG, 5, 15, 30, 30 if numerals else 0,
                  C_ROSE_MAG, 5.4, skip=(0, 90, 180, 270))

    # The star. A cardinal point and its spear are one continuous shape, not a
    # bar laid over the star — drawing them separately reads as a heavy cross
    # sitting on top. Facets are solid rather than hatched: the engraved roses
    # shade theirs with fine strokes, but at a two-inch printed rose those can
    # never resolve, and they come out looking like stray drafting lines.
    CARDINAL, INTER, MINOR = 1.16, 0.56, 0.28
    points = ([(b, CARDINAL, 0.150) for b in (0, 90, 180, 270)]
              + [(b, INTER, 0.150) for b in (45, 135, 225, 315)]
              + [(22.5 + 45 * k, MINOR, 0.070) for k in range(8)])
    for b, r_tip, r_valley in sorted(points, key=lambda p: p[1]):
        al, _ = axes_for(b)
        vl, _ = axes_for(b - 22.5)
        vr, _ = axes_for(b + 22.5)
        tip = al * r_tip
        upoly([(0.0, 0.0), tuple(vl * r_valley), tuple(tip)],
              C_ROSE, C_ROSE, 0.4, z=12)
        upoly([(0.0, 0.0), tuple(tip), tuple(vr * r_valley)],
              C_PAPER, C_ROSE, 0.4, z=12)

    # spearhead and eyelet where the cardinals break out past the ring
    for b in (0, 90, 180, 270):
        al, ac = axes_for(b)
        upoly([tuple(al * CARDINAL), tuple(al * 1.055 + ac * 0.050),
               tuple(al * 1.015), tuple(al * 1.055 - ac * 0.050)],
              C_ROSE, C_ROSE, 0.4, z=13)
        if eyelets:
            cx, cy = XY(*(al * 0.985))
            ax.plot([cx], [cy], marker="o", ms=3.6 * lw_scale, mfc=C_PAPER,
                    mec=C_ROSE, mew=0.8 * lw_scale, zorder=13)

    for b, ch in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
        al, _ = axes_for(b)
        # letter_r may be one radius or one per cardinal: the four have different
        # room around them, since the fleur crowds N and the ring's own graduations
        # sit closer to E and W than to N and S.
        r = letter_r.get(ch, 1.26) if isinstance(letter_r, dict) else letter_r
        x, y = XY(*(al * r))
        ax.text(x, y, ch, fontproperties=SERIF_I, fontsize=12 * lw_scale,
                color=C_ROSE, ha="center", va="center", zorder=13,
                path_effects=_halo(3.0 * lw_scale))

    # fleur-de-lis riding above the north spear
    draw_fleur(ax, lon, lat + R * fleur_r, R * 0.42, C_ROSE, lw_scale, zorder=13)


def text_width(fig, txt, fp, size):
    """Rendered width of a string, as a fraction of figure width."""
    probe = fig.text(0, 0, txt, fontproperties=fp, fontsize=size)
    w = (probe.get_window_extent(renderer=fig.canvas.get_renderer())
         .transformed(fig.transFigure.inverted()).width)
    probe.remove()
    return w


def fit_fontsize(fig, txt, fp, size, avail, floor=8.5, step=0.25, pad=0.006):
    """Largest size at or below `size` whose text fits `avail` figure widths.

    The longest route line runs to within 0.02 in of the margin at 10.5 pt, so
    one more character would overflow — and on a machine without Lato the
    DejaVu fallback overflows outright. Measure instead of trusting the number.

    `pad` reserves a visible sliver of margin. It also keeps the answer stable
    between the 100 dpi proof and the 300 dpi final: font metrics round
    differently at each, and without it the two picked different sizes.
    """
    while size > floor:
        if text_width(fig, txt, fp, size) <= avail - pad:
            break
        size -= step
    return size


def build(dpi, out_png, out_pdf=None, spread=True, depth=False):
    tracks = {d["file"]: load_day(d["file"], walk_split=d.get("walk_split"),
                                  road_split=d.get("road_split"))
              for d in DAYS}
    walk_m = sum(haversine(w[a][1], w[a][2], w[a + 1][1], w[a + 1][2])
                 for d in DAYS for w in [tracks[d["file"]]["walk"]]
                 for a in range(len(w) - 1))
    total_nm = sum(tracks[d["file"]]["nm"] for d in DAYS if d["sail"])
    max_kn = max(tracks[d["file"]]["max_kn"] for d in DAYS if d["sail"])
    dropped = sum(tracks[d["file"]]["dropped"] for d in DAYS)

    extent = EXTENT
    land = land_polygons(LAND_BBOX)
    # Worked out once and handed to both charts on the sheet; it takes about half a
    # minute and neither of them should pay for it twice.
    bands = depth_bands(land) if depth else None

    fig = plt.figure(figsize=(18, 24), dpi=dpi)
    fig.patch.set_facecolor(C_PAPER)

    # ---- title block
    fig.text(0.065, 0.972, "SEA BASE 1830", fontproperties=SERIF, fontsize=62,
             color=C_INK, ha="left", va="top")
    fig.text(0.0675, 0.9345, "ABACO · THE BAHAMAS", fontproperties=SANS,
             fontsize=17, color=C_INK_SOFT, ha="left", va="top")
    fig.text(0.935, 0.9695, "SEA OF ABACO", fontproperties=SANS_B,
             fontsize=17, color=C_INK, ha="right", va="top")
    fig.text(0.935, 0.9495, "22–28 MARCH 2024", fontproperties=SANS,
             fontsize=15, color=C_INK_SOFT, ha="right", va="top")
    fig.lines.append(plt.Line2D([0.065, 0.935], [0.9235, 0.9235],
                                transform=fig.transFigure, color=C_RULE, lw=1.4))

    # ---- hero map
    ax = fig.add_axes([0.065, 0.225, 0.545, 0.685])
    # Lynyard Cay's name is left where it is, though it sits only 89 m off the
    # track. The square page moves it 1.2 km east, which clears by 502 m — but this
    # sheet has the compass rose at 26.352, and the rose's W reaches to lon -76.971,
    # so any step east big enough to clear the track lands on the rose. West clears
    # the track only at 2 km, which detaches the name from the cay it labels. So the
    # choice here is the rose's position or the overlap, and the overlap is quieter.
    draw_chart(ax, extent, land, DAYS, tracks, lw_scale=1.0, spread=spread,
               depth=bands)
    # And Saturday's badge sat on the junction where its track meets Sunday's, which
    # is the part worth seeing. This is the marina end of Saturday's own leg, 3.3 km
    # from the junction and 296 m from any other track.
    badges = badge_positions(DAYS, tracks)
    badges[[d for d in DAYS if d.get("n") == 1][0]["file"]] = (-77.0517, 26.5469)
    draw_badges(ax, DAYS, badges)
    compass_rose(ax, -76.9450, 26.3520, 0.0160)
    scale_bar(ax, extent)
    chart_neatline(ax, extent, fig)

    # ---- right-hand legend column
    #
    # Every size here is measured up to the point where the line would wrap,
    # rather than picked by eye. The route line is the one that can't grow —
    # it's the longest string in the narrowest slot — so it stays small and the
    # day title carries the weight. The label/nm pair is deliberately held
    # below the title so the serif stays the dominant thing in each row.
    x = 0.655
    ind = x + 0.046
    wide, narrow = 0.935 - x, 0.935 - ind
    hdr_size = fit_fontsize(fig, "THE PASSAGE, DAY BY DAY", SANS_B, 26, wide)
    ttl_size = min(fit_fontsize(fig, d["title"], SERIF, 26, narrow) for d in DAYS)
    rte_size = min(fit_fontsize(fig, d["route"], SANS, 14, narrow) for d in DAYS)
    lab_size = min(18.0, ttl_size)
    line_h = lambda s: 1.15 * s / 1728.0          # 24 in tall = 1728 pt
    intra = 0.005                                 # between lines within a row
    min_row = (line_h(lab_size) + line_h(ttl_size) + line_h(rte_size)
               + 2 * intra + 0.010)
    # Stats: dropping the fix count removes the one wide numeral, which frees
    # the number column and lets the captions grow from 11.5 pt to ~24, so the
    # pair reads as a unit instead of a big number beside a small label.
    stats = [(f"{total_nm:.0f}", "NAUTICAL MILES SAILED"),
             ("5", "DAYS UNDER SAIL"),
             (f"{max_kn:.1f}", "KNOTS, BEST SPEED")]
    num_size = 40
    cap_x = x + max(text_width(fig, n, SERIF, num_size) for n, _ in stats) + 0.022
    cap_size = min(fit_fontsize(fig, c, SANS, 26, 0.935 - cap_x) for _, c in stats)
    stat_gap = 1.45 * line_h(num_size)            # snug, not the old fixed 0.05
    stats_span = stat_gap * (len(stats) - 1)

    y = 0.902
    fig.text(x, y, "THE PASSAGE, DAY BY DAY", fontproperties=SANS_B,
             fontsize=hdr_size, color=C_INK, ha="left", va="top")
    rule_y = y - line_h(hdr_size) - 0.006
    fig.lines.append(plt.Line2D([x, 0.935], [rule_y, rule_y],
                                transform=fig.transFigure, color=C_RULE, lw=1.0))
    # Spread the seven rows so the column reaches the stats block instead of
    # stopping short — but never tighter than the type itself needs.
    STAT_FLOOR = 0.212
    top = rule_y - 0.012
    fill = (top - 0.030 - stats_span - STAT_FLOOR) / 7
    row_h = max(min_row, min(fill, 1.35 * min_row))   # fill, but stay readable
    off_lab = row_h / 2 - 0.006 - line_h(lab_size) / 2
    off_ttl = off_lab - line_h(lab_size) / 2 - intra - line_h(ttl_size) / 2
    off_rte = off_ttl - line_h(ttl_size) / 2 - intra - line_h(rte_size) / 2
    y = top - row_h / 2
    for d in DAYS:
        nm = tracks[d["file"]]["nm"]
        if d.get("n") is not None:                  # numbered badge, keyed to
            fig.text(x + 0.011, y + 0.006, str(d["n"]),  # the same one on the map
                     fontproperties=SANS_B, fontsize=15, color=C_PAPER,
                     ha="center", va="center", zorder=4,
                     bbox=dict(boxstyle="circle,pad=0.42", facecolor=d["color"],
                               edgecolor="none"))
        elif d.get("sail_color"):        # part afloat, part by road
            fig.lines.append(plt.Line2D([x + 0.001, x + 0.009], [y + 0.005, y + 0.005],
                                        transform=fig.transFigure,
                                        color=d["sail_color"], lw=3.0,
                                        solid_capstyle="round"))
            fig.lines.append(plt.Line2D([x + 0.013, x + 0.022], [y + 0.005, y + 0.005],
                                        transform=fig.transFigure, color=d["color"],
                                        lw=1.8, ls=(0, (3, 2))))
        else:
            fig.lines.append(plt.Line2D([x + 0.001, x + 0.021], [y + 0.005, y + 0.005],
                                        transform=fig.transFigure, color=d["color"],
                                        lw=1.8, ls=(0, (3, 2))))
        fig.text(ind, y + off_lab, d["label"].upper(), fontproperties=SANS_B,
                 fontsize=lab_size, color=C_INK, ha="left", va="center")
        # only ever quote distances made on the water
        nm_txt = f"{nm:.1f} nm" if (d["sail"] or d.get("show_nm")) else ""
        fig.text(0.935, y + off_lab, nm_txt, fontproperties=SANS,
                 fontsize=lab_size, color=C_INK_SOFT, ha="right", va="center")
        fig.text(ind, y + off_ttl, d["title"], fontproperties=SERIF,
                 fontsize=ttl_size, color=C_INK, ha="left", va="center")
        fig.text(ind, y + off_rte, d["route"], fontproperties=SANS,
                 fontsize=rte_size, color=C_INK_SOFT, ha="left", va="center")
        y -= row_h

    # ---- stats block
    y += row_h / 2 - 0.030
    fig.lines.append(plt.Line2D([x, 0.935], [y + 0.020, y + 0.020],
                                transform=fig.transFigure, color=C_RULE, lw=1.0))
    for i, (big, cap) in enumerate(stats):
        yy = y - stat_gap * i
        fig.text(x, yy, big, fontproperties=SERIF, fontsize=num_size,
                 color=C_INK, ha="left", va="center")
        fig.text(cap_x, yy, cap, fontproperties=SANS, fontsize=cap_size,
                 color=C_INK_SOFT, ha="left", va="center")

    # ---- bottom strip of per-day thumbnails
    strip_y, strip_h = 0.058, 0.134
    left, right, gap = 0.065, 0.935, 0.010
    wid = (right - left - gap * (len(DAYS) - 1)) / len(DAYS)
    for i, d in enumerate(DAYS):
        t = tracks[d["file"]]
        pts = t["afloat"] + t["walk"] + t["road"]
        axd = fig.add_axes([left + i * (wid + gap), strip_y, wid, strip_h])
        if len(pts) >= 2:
            lons = [p[2] for p in pts]
            lats = [p[1] for p in pts]
            cx, cy = (min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2
            if d.get("ashore"):        # no passage; frame airport→hotel→marina
                cx, cy = -77.0618, 26.5305
                need_w, need_h = 0.047, 0.047
            else:
                need_w = max(max(lons) - min(lons), 0.012) * 1.35
                need_h = max(max(lats) - min(lats), 0.012) * 1.35
            box_ratio = (strip_h * 24) / (wid * 18)     # inches h/w
            if need_h / (need_w / ASPECT) < box_ratio:
                need_h = need_w / ASPECT * box_ratio
            else:
                need_w = need_h / box_ratio * ASPECT
            sub = (cx - need_w / 2, cx + need_w / 2, cy - need_h / 2, cy + need_h / 2)
        else:
            sub = extent
        # The arrival panel doubles as the harbour inset, so it carries
        # Saturday's walk — but marking that day ashore here keeps its sailing
        # track out of a day on which nobody sailed.
        shown = [d] + [dict(o, ashore=True)
                       for o in DAYS if d.get("ashore") and o.get("walk_split")]
        draw_chart(axd, sub, land, shown, tracks, detail=False, lw_scale=0.62,
                   depth=bands,
                   show_airport=bool(d.get("transfer") or d.get("airport")))
        # the arrival panel doubles as the Marsh Harbour detail inset; the
        # departure panel needs the marina too, since that's where it starts
        # Friday ends at the hotel; the marina only enters the story on
        # Saturday, when the crew walks to it and boards
        marks = []
        if d.get("ashore"):
            marks = [(HOTEL, "Hotel", 0.0016, 0.0012, "left", "bottom")]
        elif d.get("walk_split"):
            # the sail track comes in from the west and the hotel sits hard
            # against the panel edge, so the marina reads up and to the right
            marks = [(HOTEL, "Hotel", -0.0012, -0.0010, "right", "top"),
                     (MARINA, "Marina", 0.0009, 0.0008, "left", "bottom")]
        elif d.get("airport"):
            # the marina is near the right edge here; label it underneath,
            # inboard of the road heading off to the airport
            marks = [(MARINA, "Marina", 0.0, -0.0009, "center", "top")]
        for (lon, lat), name, dx, dy, ha, va in marks:
            axd.plot([lon], [lat], marker="o", ms=6.5, mfc=C_PAPER,
                     mec=C_INK, mew=1.3, zorder=9)
            axd.text(lon + dx, lat + dy, name, fontproperties=SANS_B,
                     fontsize=8, color=C_INK, ha=ha, va=va, zorder=9,
                     path_effects=_halo(2.2))
        if d.get("n") is not None:
            axd.text(0.10, 0.895, str(d["n"]), transform=axd.transAxes,
                     fontproperties=SANS_B, fontsize=11, color=C_PAPER,
                     ha="center", va="center", zorder=10,
                     bbox=dict(boxstyle="circle,pad=0.40", facecolor=d["color"],
                               edgecolor="none"))
        head = (f"   ·   {tracks[d['file']]['nm']:.1f} nm"
                if (d["sail"] or d.get("show_nm")) else "")
        axd.set_title(f"{d['label'].upper()}{head}",
                      fontproperties=SANS_B, fontsize=10, color=C_INK, pad=6)
        axd.text(0.5, -0.075, d["title"], transform=axd.transAxes,
                 fontproperties=SERIF, fontsize=10.5, color=C_INK_SOFT,
                 ha="center", va="top")

    # This hangs on a wall, so the footer is a credit line, not a methods
    # section — the data caveats all live in the README instead.
    fig.text(0.5, 0.016,
             "Recorded on a handheld GPS receiver  ·  Dotted lines are ashore"
             "  ·  Coastline © OpenStreetMap contributors",
             fontproperties=SANS, fontsize=9, color=C_INK_SOFT, ha="center", va="bottom")

    fig.savefig(out_png, dpi=dpi, facecolor=C_PAPER)
    print("wrote", out_png)
    if out_pdf:
        fig.savefig(out_pdf, facecolor=C_PAPER)
        print("wrote", out_pdf)
    plt.close(fig)


def photobook_extent(tracks, margin=0.11):
    """A square frame around the path, in degrees.

    The chart axes render degrees true — one degree of latitude is ASPECT times the
    display size of one degree of longitude — so a square *page* needs a longitude
    span ASPECT times the latitude span, not an equal one. The path itself is 37 km
    north to south and 17 km across, so the square is set by its height and the
    extra width is the Sea of Abaco and the Atlantic either side.
    """
    lats, lons = [], []
    for d in DAYS:
        t = tracks[d["file"]]
        for mode in ("afloat", "walk", "road"):
            for p in (t.get(mode) or []):
                lats.append(p[1]); lons.append(p[2])
    for lon, lat in transfer_route():
        lats.append(lat); lons.append(lon)
    # The labels have to fit as well as the path. Fitted to the track alone, Great
    # Guana Cay's name fell outside the neatline entirely — its cay is north of
    # anywhere the boat went — and Little Harbour's landed under the scale bar.
    for lon, lat, *_ in list(PLACES) + list(ANCHORAGES):
        lats.append(lat); lons.append(lon)
    # The margin is generous because a label is a box, not the point it hangs off:
    # fitted tight to the coordinates, Great Guana Cay's name and Little Harbour's
    # both ended up lying along the neatline.
    clat, clon = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
    span = max(max(lats) - min(lats), (max(lons) - min(lons)) / ASPECT) * (1 + margin)
    return (clon - span * ASPECT / 2, clon + span * ASPECT / 2,
            clat - span / 2, clat + span / 2)


def photobook(dpi, out_png, depth=False, title=True):
    """One square page of chart, for an 8 x 8 in photobook.

    The sheet is 18 x 24 and its hero chart is portrait, so this is not a crop of it:
    the frame is recomputed square around the path and everything is drawn at the
    scale that suits 8 inches. Same drawing code as the poster, so the two agree
    about coastline, colour, tracks and type.

    At 300 dpi this is 2400 px square, which is what a photobook printer asks for;
    600 gives 4800 px for a printer that wants more.
    """
    tracks = {d["file"]: load_day(d["file"], walk_split=d.get("walk_split"),
                                 road_split=d.get("road_split"))
              for d in DAYS}
    land = land_polygons(LAND_BBOX)
    bands = depth_bands(land) if depth else None
    extent = photobook_extent(tracks)

    fig = plt.figure(figsize=(8, 8), dpi=dpi)
    fig.patch.set_facecolor(C_PAPER)
    # Room at the top for a title, and a hair all round for the neatline.
    ax = fig.add_axes([0.055, 0.052, 0.890, 0.858 if title else 0.896])
    # 0.8 rather than 1.0: this frame is about half the poster's scale, so the same
    # line weights would read as heavier here than they do on the sheet.
    #
    # Two names move and one goes. Sea of Abaco sat above Wednesday's track and now
    # sits between it and Sunday's, which is the water it names — and west as well,
    # because dropping it to that latitude ran its letter-spaced type into
    # Man-O-War Cay. Lynyard Cay's label lay along the track, so it steps east onto
    # open water and up, leaving its anchorage ring where the boat actually lay.
    # Man-O-War Cay's name moves to the north end of the island it names. Lubbers Quarters is
    # dropped: the square page carries the same names at half the scale, and that one
    # had nowhere to go that was not a track or another label.
    draw_chart(ax, extent, land, DAYS, tracks, detail=True, lw_scale=0.80,
               spread=True, depth=bands,
               # Lynyard Cay's name is dropped here and redrawn below in the
               # cays' own serif, because it is a cay on this page and not only
               # somewhere the boat lay. Its anchorage ring stays regardless.
               skip_labels=("Lubbers\nQuarters", "Lynyard Cay"),
               # Tilloo Pond goes entirely, ring and name. It was the last label in
               # the anchorages' bold sans once Lynyard Cay moved to the cays' serif,
               # so the style marked a category of one — and with the name gone the
               # ring would mark a spot with nothing to say about it.
               skip_anchorages=("Tilloo Pond",),
               label_nudge={"S E A   O F   A B A C O": (-0.0300, -0.0245),
                            "Great Guana Cay": (0.0330, 0.0),
                            # East is limited to about +0.048 before the letter-
                            # spaced type runs off the coast; the drop puts the whole
                            # line 545 m inside the coastline. Sampling the label as
                            # a box on a 15 x 5 grid rather than along its centreline
                            # matters here: a coarser sample called -0.004 clear when
                            # it is not.
                            "G R E A T   A B A C O": (0.0345, -0.0180),
                            "A T L A N T I C\nO C E A N": (0.0300, 0.0),
                            "MARSH HARBOUR": (0.0, 0.0058),
                            "Man-O-War Cay": (-0.0140, 0.0204),
                            "Elbow Cay": (-0.0095, 0.0),
                            # Up into the space Tilloo Pond's name has left, at
                            # the same latitude but east of it: the tracks run
                            # through the pond itself, so the old spot is 26 m off
                            # them and this one is 522 m.
                            "Tilloo Cay": (-0.0020, 0.0088)},
               airport_nudge=(-0.0115, 0.0),
               # The full name, over two lines, since a photobook page is read
               # closer than a wall.
               airport_text="Leonard M. Thompson\nInternational Airport (MHH)",
               # Lower and a shade smaller: on a square page the sheet's position
               # ran the topmast through the neatline.
               vessel=(-76.8950, 26.6100, 0.0620))
    # Saturday's badge kept landing on the junction where its track meets Sunday's,
    # which is the part worth seeing. Searching for the point "clearest of
    # everything" put it 465 m away and still on top of the junction, because that
    # measure counts distance to five tracks equally and the junction is only one of
    # them. Measuring distance from the junction itself, subject to staying 130 m off
    # the other tracks and labels, moves it to the marina end of Saturday's own leg,
    # 3.3 km away — and then off the line rather than on it. On the leg itself there
    # is nowhere good: the badge covered the start at the marina end, the far west end
    # covers the junction, and the middle runs alongside Sunday's track with 7 to 39 m
    # to spare, so a badge there hides Sunday instead. This sits 1.3 km west of the
    # start and 400 m north of Saturday's own line, in open water, 446 m from any
    # other track — near enough to read as Saturday's, over nothing at all.
    badges = badge_positions(DAYS, tracks)
    badges[[d for d in DAYS if d.get("n") == 1][0]["file"]] = (-77.0630, 26.5530)
    draw_badges(ax, DAYS, badges, lw_scale=0.80)
    # Bigger than the sheet's rose in map degrees, because this frame is half the
    # scale: at 0.0135 the cardinals and the fleur were on top of each other. The
    # magnetic ring and both sets of numerals come off — at this size they read as a
    # grey smudge rather than as information — and the true ring draws tighter.
    compass_rose(ax, -76.8850, 26.3700, 0.0235,
                 magnetic=False, numerals=False, ring=0.72, eyelets=False,
                 # The cardinals break out to 1.055 and the letters sat at 1.26,
                 # close enough that S touched the south spear once the ring was
                 # drawn tighter and stopped separating them.
                 # Pushing the letters out to clear the spears walked N into the
                 # fleur, which sits at 1.68 and is 0.42 tall, so the fleur goes up
                 # with them. One overlap traded for another otherwise.
                 letter_r={"N": 1.30, "E": 1.34, "S": 1.40, "W": 1.40},
                 fleur_r=1.86)
    # Over Great Abaco rather than out in the water: ink on the land tone reads
    # better than ink on pale blue, and that corner of the island is empty.
    scale_bar(ax, extent, y_frac=0.052, x_frac=0.185, nm_len=5, lw_scale=0.80,
              caption_top=True)
    chart_neatline(ax, extent, fig, lw_scale=0.80, label_every=5)

    # Lynyard Cay, in the same serif as Tilloo and Elbow, north of its anchorage.
    ax.text(-76.9775, 26.3720, "Lynyard Cay", fontproperties=SERIF,
            fontsize=9.5 * 0.80, color=C_INK, ha="left", va="center", zorder=9,
            path_effects=_halo(3.0 * 0.80))

    if title:
        fig.text(0.5, 0.952, "SEA BASE 1830", fontproperties=SERIF, fontsize=25,
                 color=C_INK, ha="center", va="center")
        fig.text(0.5, 0.924, "SEA OF ABACO  ·  22–28 MARCH 2024",
                 fontproperties=SANS, fontsize=9.5, color=C_INK_SOFT,
                 ha="center", va="center", linespacing=1.4)
    fig.savefig(out_png, dpi=dpi, facecolor=C_PAPER)
    print("wrote", out_png)
    plt.close(fig)


def compare(dpi=110):
    """Two proofs, identical but for the lateral offset, plus a zoom on the
    stretch that motivated it — so the distortion can be judged directly."""
    out = os.path.join(HERE, "out")
    build(dpi, os.path.join(out, "proof_true.png"), spread=False)
    build(dpi, os.path.join(out, "proof_offset.png"), spread=True)

    tracks = {d["file"]: load_day(d["file"], walk_split=d.get("walk_split"),
                                  road_split=d.get("road_split"))
              for d in DAYS}
    land = land_polygons(LAND_BBOX)
    zoom = (-77.030, -76.958, 26.330, 26.560)     # the Tilloo/Elbow run

    fig = plt.figure(figsize=(13, 17), dpi=dpi)
    fig.patch.set_facecolor(C_PAPER)
    for i, (spread, title) in enumerate(((False, "TRUE TRACKS"),
                                         (True, "OFFSET FOR LEGIBILITY"))):
        ax = fig.add_axes([0.035 + i * 0.485, 0.045, 0.455, 0.885])
        draw_chart(ax, zoom, land, DAYS, tracks, detail=False, lw_scale=1.25,
                   spread=spread)
        ax.set_title(title, fontproperties=SANS_B, fontsize=15, color=C_INK,
                     pad=10)
    fig.text(0.5, 0.965, "Sea of Abaco · Tilloo Cut to Lynyard Cay",
             fontproperties=SERIF, fontsize=25, color=C_INK, ha="center")
    fig.text(0.5, 0.017,
             "Same data both sides. On the right the days are nudged apart only along "
             "this run; everywhere else on the chart the tracks are drawn exactly as "
             "recorded.",
             fontproperties=SANS, fontsize=11, color=C_INK_SOFT, ha="center")
    dest = os.path.join(out, "compare_offset.png")
    fig.savefig(dest, dpi=dpi, facecolor=C_PAPER)
    plt.close(fig)
    print("wrote", dest)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--final", action="store_true", help="300 dpi PNG + PDF")
    ap.add_argument("--compare", action="store_true",
                    help="proofs with and without the lateral offset")
    ap.add_argument("--depth", action="store_true",
                    help="measured GMRT depth bands instead of the drawn shoal halo")
    ap.add_argument("--photobook", action="store_true",
                    help="one square 8 x 8 in page of chart")
    ap.add_argument("--dpi", type=int, default=300,
                    help="dots per inch for --photobook (default 300)")
    ap.add_argument("--no-title", action="store_true",
                    help="leave the title off --photobook")
    a = ap.parse_args()
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    suffix = "_depth" if a.depth else ""
    if a.photobook:
        photobook(a.dpi, os.path.join(
            HERE, "out", f"photobook{suffix}_8x8_{a.dpi}dpi.png"),
            depth=a.depth, title=not a.no_title)
    elif a.compare:
        compare()
    elif a.final:
        build(300, os.path.join(HERE, "out",
                                f"abaco_poster{suffix}_18x24_300dpi.png"),
              os.path.join(HERE, "out", f"abaco_poster{suffix}_18x24.pdf"),
              depth=a.depth)
    else:
        build(100, os.path.join(HERE, "out", f"proof{suffix}.png"), depth=a.depth)
