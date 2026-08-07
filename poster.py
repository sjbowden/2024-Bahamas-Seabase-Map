#!/usr/bin/env python3
"""Frameable nautical-chart poster of the 2024 Bahamas Sea Base sailing tracks.

Renders a hero map of the Sea of Abaco with every day's GPS track, a strip of
per-day thumbnails, and a chart-style title block.

    python poster.py            # 200 dpi proof PNG
    python poster.py --final    # 300 dpi PNG + vector PDF
"""
import argparse
import csv
import glob
import math
import os
from datetime import datetime, timedelta, timezone

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Polygon as MplPolygon, FancyArrow
from matplotlib.path import Path
from matplotlib.patches import PathPatch

from abaco_geo import land_polygons
from roads import route as road_route


def transfer_route():
    """Friday's airport→hotel drive, routed over OSM roads. The recorded log
    for that day is unusable (all dead-reckoning), so this is a reconstruction,
    and the poster says so."""
    pts, _ = road_route((AIRPORT[1], AIRPORT[0]), (HOTEL[1], HOTEL[0]))
    return pts

HERE = os.path.dirname(os.path.abspath(__file__))
EDT = timezone(timedelta(hours=-4))
NM = 1852.0
LAT0 = 26.5
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

SERIF = FontProperties(family="P052")
SERIF_I = FontProperties(family="P052", style="italic")
SANS = FontProperties(family="Lato")
SANS_B = FontProperties(family="Lato", weight="bold")

# ------------------------------------------------------------------- days ---
DAYS = [
    dict(file="GPS_20240322_163426", label="Fri 22 Mar", n=None, color="#8A8073",
         sail=False, ashore=True, transfer=True, title="Arrival",
         route="Flew in · airport → hotel by road"),
    # the shakedown never leaves the harbour, so its badge has to be placed by
    # hand — every point on it is close to the marina
    dict(file="GPS_20240323_144533", label="Sat 23 Mar", n=1, color="#0B6E4F",
         sail=True, title="Shakedown", badge_at=(-77.0836, 26.5585), offset=0.0,
         walk_split="2024-03-23T14:57:23Z",
         route="Walked to the marina, then out into the harbour"),
    dict(file="GPS_20240324_105625", label="Sun 24 Mar", n=2, color="#C1272D", offset=-0.0015,
         sail=True, title="Man-O-War & Tahiti Beach",
         route="Marsh Harbour → Man-O-War Cay → Tahiti Beach → Tilloo Pond"),
    dict(file="GPS_20240325_111604", label="Mon 25 Mar", n=3, color="#D97706", offset=-0.0005,
         sail=True, title="Hope Town",
         route="Tilloo Pond → Hope Town Harbour → Lynyard Cay"),
    dict(file="GPS_20240326_114752", label="Tue 26 Mar", n=4, color="#1D4E89", offset=0.0005,
         sail=True, title="Little Harbour",
         route="Lynyard Cay → Little Harbour → north to Tilloo"),
    dict(file="GPS_20240327_122052", label="Wed 27 Mar", n=5, color="#8E2E8E", offset=0.0015,
         sail=True, title="Great Guana Cay",
         route="Tilloo → Great Guana Cay → Marsh Harbour"),
    # afloat until 09:52:40 EDT, when the van left for the airport
    dict(file="GPS_20240328_111720", label="Thu 28 Mar", n=None, color="#8A8073",
         sail=False, airport=True, title="Departure", sail_color="#35708E",
         road_split="2024-03-28T13:52:40Z", show_nm=True,
         route="Off the mooring to the dock, then MHH by road"),
]

# hand-placed chart labels: (lon, lat, text, kind, ha, va)
PLACES = [
    (-77.0640, 26.5310, "MARSH HARBOUR", "town", "right", "center"),
    (-76.9594, 26.5407, "HOPE TOWN", "town", "left", "center"),
    (-77.0002, 26.3242, "LITTLE HARBOUR", "town", "left", "center"),
    (-77.1310, 26.6790, "Great Guana Cay", "isle", "center", "bottom"),
    (-77.0030, 26.5930, "Man-O-War Cay", "isle", "left", "center"),
    (-76.9700, 26.4950, "Elbow Cay", "isle", "left", "center"),
    (-77.0270, 26.4700, "Lubbers\nQuarters", "isle", "right", "center"),
    (-76.9830, 26.4400, "Tilloo Cay", "isle", "left", "center"),
    (-77.1550, 26.4300, "G R E A T   A B A C O", "big", "center", "center"),
    (-77.0450, 26.6300, "S E A   O F   A B A C O", "water", "center", "center"),
    (-76.9430, 26.6250, "A T L A N T I C\nO C E A N", "water", "center", "center"),
]

# overnight anchorages worth marking: (lon, lat, text, ha)
AIRPORT = (-77.0782, 26.5135, "MHH", "Leonard M. Thompson Intl")
# hotel fixed from the EXIF of IMG_0496.JPG (14:43 EDT, 22 Mar, ±4.6 m); the
# marina is where Saturday's walk ends and the boat then sits for 90 minutes
HOTEL = (-77.048906, 26.545222)
MARINA = (-77.05192, 26.54688)

# (lon, lat, label, ha, va) — Lynyard sits below its marker to clear the rose
ANCHORAGES = [
    (-76.9907, 26.4488, "Tilloo Pond", "left", "center"),
    (-76.9849, 26.3568, "Lynyard Cay", "center", "top"),
]


# ------------------------------------------------------------------ tracks ---
def haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    h = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b_lon - a_lon) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


GOOD_QUALITY = (1, 2, 4, 5)     # GPS / DGPS / RTK; 6 is dead-reckoning guesswork
MIN_SATS = 4
MAX_HDOP = 4.0
MOVING_KN = 0.5                 # below this the boat is swinging on its hook


def _split_at(pts, iso):
    """Cut a day in two at a UTC instant: (before, after)."""
    cut = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return [p for p in pts if p[0] <= cut], [p for p in pts if p[0] > cut]


def _thin(pts, step=3):
    return [p for i, p in enumerate(pts) if i % step == 0 or i == len(pts) - 1]


def load_day(stem, min_step_m=22.0, max_kn=30.0, walk_split=None, road_split=None):
    """Read a day's fixes, discard low-quality ones, and thin anchor jitter.

    Distance only accumulates while the receiver reports real way on the boat,
    so hours of swinging at anchor don't quietly add miles to the day.
    """
    path = os.path.join(HERE, "tracks", stem + ".csv")
    raw, dropped = [], 0
    with open(path) as fh:
        for r in csv.DictReader(fh):
            lat, lon = float(r["lat"]), float(r["lon"])
            if lat >= 30.0:                         # Bahamas only, no PDX legs
                continue
            if (int(r["quality"]) not in GOOD_QUALITY
                    or int(r["sats"]) < MIN_SATS
                    or float(r["hdop"]) > MAX_HDOP):
                dropped += 1
                continue
            raw.append((datetime.strptime(r["utc"], "%Y-%m-%dT%H:%M:%SZ")
                        .replace(tzinfo=timezone.utc),
                        lat, lon, float(r["sog_kn"])))
    if len(raw) < 2:
        return dict(afloat=[], nm=0.0, max_kn=0.0, fixes=0, dropped=dropped,
                    walk=[], road=[])
    n_raw = len(raw)
    # Saturday begins on foot; Thursday ends in a van. Note the two splits keep
    # opposite halves, so an absent split must default the opposite way.
    walk_raw, raw = _split_at(raw, walk_split) if walk_split else ([], raw)
    raw, road_raw = _split_at(raw, road_split) if road_split else (raw, [])
    kept, dist, prev = [raw[0]], 0.0, raw[0]
    for p in raw[1:]:
        dt = (p[0] - prev[0]).total_seconds()
        step = haversine(prev[1], prev[2], p[1], p[2])
        if dt > 0 and step / dt * 1.94384 > max_kn and step > 60:
            continue                                # residual spike
        if p[3] > MOVING_KN:
            dist += step                            # measure against the last
        prev = p                                    # accepted fix, not the last
        if haversine(kept[-1][1], kept[-1][2],      # *plotted* one
                     p[1], p[2]) >= min_step_m:     # thin stationary jitter
            kept.append(p)
    speeds = [p[3] for p in raw if p[3] > 0.8]
    return dict(afloat=kept, nm=dist / NM, max_kn=(max(speeds) if speeds else 0.0),
                fixes=n_raw, dropped=dropped,
                walk=_thin(walk_raw), road=_thin(road_raw))


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


def draw_chart(ax, extent, land, days, tracks, *, detail=True, lw_scale=1.0,
               show_airport=False, spread=False):
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

    # shoal halo around the land, then land itself
    for buf, col in ((0.0060, C_SHOAL_1), (0.0026, C_SHOAL_2)):
        _fill(ax, _shoal(land, buf), col, None, 0)
    _fill(ax, land, C_LAND, C_LAND_EDGE, 0.5 * lw_scale)

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

    draw_airport(ax, lw_scale)

    # anchorages
    for lon, lat, text, ha, va in ANCHORAGES:
        ax.plot([lon], [lat], marker="o", ms=6 * lw_scale, mfc=C_PAPER,
                mec=C_INK, mew=1.3 * lw_scale, zorder=8)
        dx = {"left": 0.006, "right": -0.006}.get(ha, 0.0)
        dy = {"top": -0.005, "bottom": 0.005}.get(va, 0.0)
        ax.text(lon + dx, lat + dy, text, fontproperties=SANS_B,
                fontsize=9.5 * lw_scale, color=C_INK, ha=ha, va=va, zorder=8,
                path_effects=_halo(2.6 * lw_scale))

    # place names
    sizes = {"town": 10.5, "isle": 9.5, "big": 15.0, "water": 13.0}
    for lon, lat, text, kind, ha, va in PLACES:
        fp = SERIF_I if kind == "water" else SERIF
        col = "#5E7C8A" if kind == "water" else C_INK
        if kind == "big":
            col = "#7A6E58"
        pad = 0.004 if ha == "left" else (-0.004 if ha == "right" else 0)
        ax.text(lon + pad, lat, text, fontproperties=fp,
                fontsize=sizes[kind] * lw_scale, color=col, ha=ha, va=va,
                zorder=9, path_effects=_halo(3.0 * lw_scale))


_SHOAL_CACHE = {}


def _shoal(land, buf):
    """Buffered 'shallows' ring around the land — expensive, so memoize it."""
    if buf not in _SHOAL_CACHE:
        _SHOAL_CACHE[buf] = land.buffer(buf, join_style=1).buffer(
            -buf * 0.15, join_style=1)
    return _SHOAL_CACHE[buf]


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


def draw_airport(ax, lw_scale=1.0, label=True):
    lon, lat, code, name = AIRPORT
    ax.plot([lon], [lat], marker=PLANE, ms=15 * lw_scale, mfc=C_INK,
            mec=C_PAPER, mew=0.9 * lw_scale, zorder=10, clip_on=True,
            linestyle="none")
    text = f"{code}  {name}" if label else code
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


def chart_neatline(ax, extent, fig, lw_scale=1.0, label_every=5):
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

    def bands(lo, hi, horizontal):
        for m in range(math.floor(lo * 60), math.ceil(hi * 60)):
            a, b = max(m / 60.0, lo), min((m + 1) / 60.0, hi)
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


def scale_bar(ax, extent, y_frac=0.045, x_frac=0.06, nm_len=5, lw_scale=1.0):
    w, e, s, n = extent
    dlon = nm_len * NM / (111320.0 * math.cos(math.radians(LAT0)))
    x0 = w + (e - w) * x_frac
    y0 = s + (n - s) * y_frac
    h = (n - s) * 0.006
    for i in range(nm_len):
        ax.add_patch(plt.Rectangle((x0 + i * dlon / nm_len, y0), dlon / nm_len, h,
                                   facecolor=C_INK if i % 2 == 0 else C_PAPER,
                                   edgecolor=C_INK, lw=0.8 * lw_scale, zorder=10))
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


def _fleur_paths():
    """Fleur-de-lis pointing +y across y in [0,1], x in [-0.5,0.5] — the north
    point of a vintage rose. Pieces are filled separately."""
    C4, M, L, CP = Path.CURVE4, Path.MOVETO, Path.LINETO, Path.CLOSEPOLY
    # tall centre petal — cubic down the right flank, straight across the foot,
    # cubic back up the left. Codes must come in groups of three per CURVE4.
    centre = Path(
        [(0.0, 1.0),
         (0.050, 0.80), (0.100, 0.55), (0.115, 0.33),   # right flank
         (-0.115, 0.33),                                # foot
         (-0.100, 0.55), (-0.050, 0.80), (0.0, 1.0),    # left flank
         (0.0, 1.0)],
        [M, C4, C4, C4, L, C4, C4, C4, CP])
    # side petal: sweeps out and down from the band, then hooks up to a point
    # side petal: swells outward from a narrow base, then tapers to a cusp —
    # the two curves meet at the tip with no rounding, so it comes to a point
    right = Path(
        [(0.06, 0.30),
         (0.30, 0.25), (0.48, 0.35), (0.500, 0.625),    # outer edge to the tip,
         (0.38, 0.50), (0.24, 0.37), (0.06, 0.30),      # which is the outermost
         (0.06, 0.30)],                                 # point so it flares out
        [M, C4, C4, C4, C4, C4, C4, CP])
    left = Path([(-x, y) for x, y in right.vertices], right.codes)
    # the band that cinches the three petals together
    band = Path(
        [(-0.205, 0.195), (0.205, 0.195), (0.165, 0.315), (-0.165, 0.315),
         (-0.205, 0.195), (-0.205, 0.195)],
        [M, L, L, L, L, CP])
    return [centre, right, left, band]


def compass_rose(ax, lon, lat, R, lw_scale=1.0):
    """A vintage chart rose: 32-point faceted star, fleur-de-lis north, a
    graduated true ring and a magnetic ring turned by the local variation."""
    def P(bearing_deg, r):
        a = math.radians(bearing_deg)
        return (lon + r * ASPECT * math.sin(a), lat + r * math.cos(a))

    def ring(radius, rot, every, med, long_, numerals, color, fs, halo=False):
        # Draw the rings through P() as well. A plt.Circle in data coordinates
        # uses one radius for both axes, but a degree of latitude is 1.118x a
        # degree of longitude here, so it comes out an ellipse — narrowest
        # east–west, right where it used to slice through the numerals.
        a = np.linspace(0.0, 2.0 * math.pi, 721)
        for rr, wdt in ((radius, 0.9), (radius * 0.885, 0.6)):
            ax.plot(lon + rr * ASPECT * np.sin(a), lat + rr * np.cos(a),
                    color=color, lw=wdt * lw_scale, zorder=11,
                    solid_joinstyle="round")
        for deg in range(0, 360, every):
            if deg % long_ == 0:
                inner, wdt = radius * 0.885, 0.9
            elif deg % med == 0:
                inner, wdt = radius * 0.925, 0.65
            else:
                inner, wdt = radius * 0.950, 0.35
            a, b = P(deg + rot, inner), P(deg + rot, radius)
            ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=wdt * lw_scale,
                    zorder=11, solid_capstyle="butt")
        for deg in range(0, 360, numerals):
            x, y = P(deg + rot, radius * 0.805)
            ax.text(x, y, f"{deg:d}", fontproperties=SANS,
                    fontsize=fs * lw_scale, color=color, ha="center",
                    va="center", zorder=12, rotation=-(deg + rot),
                    rotation_mode="anchor",
                    path_effects=_halo(2.2 * lw_scale) if halo else None)

    ring(R, 0.0, 1, 5, 10, 30, C_ROSE, 6.0)
    ring(R * 0.79, VARIATION_DEG, 5, 15, 30, 30, C_ROSE_MAG, 5.4)

    # hairline rays at the 32-point bearings, under the star
    for k in range(32):
        if k % 4:
            a, b = P(k * 11.25, R * 0.10), P(k * 11.25, R * 0.30)
            ax.plot([a[0], b[0]], [a[1], b[1]], color=C_ROSE,
                    lw=0.35 * lw_scale, zorder=10)

    # Two overlaid 8-point stars give the classic 16-point rose. Each point is
    # split down its centreline into a lit and a shadowed half; the base
    # vertices sit a full half-sector away so the facets read as solids rather
    # than spokes.
    def star(bearings, r_tip, r_base, half=22.5, skip=()):
        for b in bearings:
            if b in skip:
                continue
            tip = P(b, r_tip)
            vl, vr = P(b - half, r_base), P(b + half, r_base)
            ax.add_patch(MplPolygon([(lon, lat), vl, tip], closed=True,
                                    facecolor=C_ROSE, edgecolor=C_ROSE,
                                    lw=0.3 * lw_scale, zorder=11))
            ax.add_patch(MplPolygon([(lon, lat), tip, vr], closed=True,
                                    facecolor=C_PAPER, edgecolor=C_ROSE,
                                    lw=0.3 * lw_scale, zorder=11))

    star([22.5 + 45 * k for k in range(8)], R * 0.32, R * 0.085)
    star([45 * k for k in range(8)], R * 0.58, R * 0.150, skip=(0,))
    star([0], R * 0.30, R * 0.150)          # stub for the fleur to stand on

    # fleur-de-lis rising from the north point
    fh = R * 0.52
    tr = (matplotlib.transforms.Affine2D()
          .scale(fh * ASPECT * 0.62, fh).translate(lon, lat + R * 0.20)
          + ax.transData)
    for p in _fleur_paths():
        ax.add_patch(PathPatch(p, transform=tr, facecolor=C_ROSE,
                               edgecolor=C_ROSE, lw=0.4 * lw_scale, zorder=13))

    # No cardinal letters and no variation caption: the fleur marks north, the
    # rings carry the bearings, and the inner ring's offset shows the variation
    # without spelling it out.


# ------------------------------------------------------------------ poster ---
def build(dpi, out_png, out_pdf=None, spread=True):
    tracks = {d["file"]: load_day(d["file"], walk_split=d.get("walk_split"),
                                  road_split=d.get("road_split"))
              for d in DAYS}
    walk_m = sum(haversine(w[a][1], w[a][2], w[a + 1][1], w[a + 1][2])
                 for d in DAYS for w in [tracks[d["file"]]["walk"]]
                 for a in range(len(w) - 1))
    total_nm = sum(tracks[d["file"]]["nm"] for d in DAYS if d["sail"])
    max_kn = max(tracks[d["file"]]["max_kn"] for d in DAYS if d["sail"])
    dropped = sum(tracks[d["file"]]["dropped"] for d in DAYS)

    extent = (-77.185, -76.912, 26.298, 26.712)
    land = land_polygons((-77.35, 26.15, -76.80, 26.85))

    fig = plt.figure(figsize=(18, 24), dpi=dpi)
    fig.patch.set_facecolor(C_PAPER)

    # ---- title block
    fig.text(0.065, 0.972, "1830 SEA BASE", fontproperties=SERIF, fontsize=62,
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
    draw_chart(ax, extent, land, DAYS, tracks, lw_scale=1.0, spread=spread)
    draw_badges(ax, DAYS, badge_positions(DAYS, tracks))
    compass_rose(ax, -76.9470, 26.3480, 0.0235)
    scale_bar(ax, extent)
    chart_neatline(ax, extent, fig)

    # ---- right-hand legend column
    x = 0.655
    y = 0.902
    fig.text(x, y, "THE PASSAGE, DAY BY DAY", fontproperties=SANS_B, fontsize=16,
             color=C_INK, ha="left", va="top")
    fig.lines.append(plt.Line2D([x, 0.935], [y - 0.014, y - 0.014],
                                transform=fig.transFigure, color=C_RULE, lw=1.0))
    y -= 0.042
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
        fig.text(x + 0.046, y + 0.014, d["label"].upper(), fontproperties=SANS_B,
                 fontsize=13.5, color=C_INK, ha="left", va="center")
        # only ever quote distances made on the water
        nm_txt = f"{nm:.1f} nm" if (d["sail"] or d.get("show_nm")) else ""
        fig.text(0.935, y + 0.014, nm_txt, fontproperties=SANS,
                 fontsize=13.5, color=C_INK_SOFT, ha="right", va="center")
        fig.text(x + 0.046, y - 0.008, d["title"], fontproperties=SERIF,
                 fontsize=16, color=C_INK, ha="left", va="center")
        fig.text(x + 0.046, y - 0.027, d["route"], fontproperties=SANS,
                 fontsize=10.5, color=C_INK_SOFT, ha="left", va="center")
        y -= 0.0660

    # ---- stats block
    y -= 0.004
    fig.lines.append(plt.Line2D([x, 0.935], [y + 0.020, y + 0.020],
                                transform=fig.transFigure, color=C_RULE, lw=1.0))
    stats = [(f"{total_nm:.0f}", "NAUTICAL MILES SAILED"),
             ("5", "DAYS UNDER SAIL"),
             (f"{max_kn:.1f}", "KNOTS, BEST SPEED"),
             (f"{sum(tracks[d['file']]['fixes'] for d in DAYS):,}", "GPS FIXES RECORDED")]
    for i, (big, cap) in enumerate(stats):
        yy = y - 0.050 * i
        fig.text(x, yy, big, fontproperties=SERIF, fontsize=40, color=C_INK,
                 ha="left", va="center")
        fig.text(x + 0.112, yy, cap, fontproperties=SANS, fontsize=11.5,
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


def compare(dpi=110):
    """Two proofs, identical but for the lateral offset, plus a zoom on the
    stretch that motivated it — so the distortion can be judged directly."""
    out = os.path.join(HERE, "out")
    build(dpi, os.path.join(out, "proof_true.png"), spread=False)
    build(dpi, os.path.join(out, "proof_offset.png"), spread=True)

    tracks = {d["file"]: load_day(d["file"], walk_split=d.get("walk_split"),
                                  road_split=d.get("road_split"))
              for d in DAYS}
    land = land_polygons((-77.35, 26.15, -76.80, 26.85))
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
    a = ap.parse_args()
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    if a.compare:
        compare()
    elif a.final:
        build(300, os.path.join(HERE, "out", "abaco_poster_18x24_300dpi.png"),
              os.path.join(HERE, "out", "abaco_poster_18x24.pdf"))
    else:
        build(100, os.path.join(HERE, "out", "proof.png"))
