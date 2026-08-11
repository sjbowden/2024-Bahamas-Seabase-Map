#!/usr/bin/env python3
"""What a sailing day *is* — shared by everything that reads this trip.

The poster, the cross-check and the map build all need the same handful of
facts: which logs make up the week, how to throw away a bad fix, how far apart
two coordinates are, where the barrier cays run. Those lived in `poster.py`
until the map needed them, and importing `poster` costs a matplotlib import and
a font-registration pass — which a photo indexer has no business paying, and
which prints font warnings while it does. Hence this module: no matplotlib, no
numpy at import time, nothing that draws.

Two ways to read the track, and picking the wrong one is the subtle mistake this
module exists to prevent:

  read_fixes()  every usable fix, full cadence, one time-ordered stream.
                For *placing* things — photographs, cross-checks, anything that
                asks "where was the receiver at 14:32".
  load_day()    thinned to 22 m and split into afloat/walk/road.
                For *drawing*. It discards 88% of the fixes, and spatially, so
                an hour at anchor collapses to a point or two. Interpolating a
                position out of it is meaningless.
"""
import csv
import math
import os
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EDT = timezone(timedelta(hours=-4))
NM = 1852.0
LAT0 = 26.5                     # chart reference latitude, for lon/lat scaling


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


# ------------------------------------------------------------------ places ---
# The chart's own bounds, and the wider box the land is loaded over. The poster
# draws EXTENT; anything outside it is not on this chart, which is how a
# photograph taken in Portland is told apart from one taken in Abaco.
EXTENT = (-77.185, -76.912, 26.298, 26.712)     # lon0, lon1, lat0, lat1
LAND_BBOX = (-77.35, 26.15, -76.80, 26.85)      # lon0, lat0, lon1, lat1

# The chart can be panned and zoomed, so it needs coastline well past the sheet's
# edge — an ultrawide window reaches lon -78.31 before maxBounds stops it, and the
# poster's cache holds nothing north of 26.83, so Little Abaco, Coopers Town and
# Treasure Cay were simply absent and the land ended in a straight vertical line.
# This box reads geo/coastline_map.json. It is emphatically *not* LAND_BBOX:
# land_polygons() polygonises the coastline together with the bbox frame and
# classifies the resulting faces, so both are structural, and widening the
# poster's box moved 17% of its pixels.
MAP_LAND_BBOX = (-78.55, 25.45, -75.55, 27.55)  # lon0, lat0, lon1, lat1

# Where the chart may be looked at. No amount of fetching wins the race against a
# wide enough window, so the view is bounded by the data instead of the data being
# chased outward. Coastline is clipped where it meets the frame — measured, the
# west and south frames, not the north or east, where the land stops short of them
# — so this keeps a margin inside those two. app.js derives both the minimum zoom
# and the pan clamp from this box and the container size, which is what makes it
# hold at any window shape.
VIEW_BOUNDS = (-78.30, -75.55, 25.70, 27.55)    # lon0, lon1, lat0, lat1

# Hand-placed chart labels: (lon, lat, text, kind, ha, va). The alignment hints
# are the poster's, and the map ignores them — but the coordinates and the choice
# of what is worth naming are shared, so the two artefacts name the same places.
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
    (-76.9400, 26.4780, "A T L A N T I C\nO C E A N", "water", "center", "center"),
]

# Cays the map names and the printed sheet does not. The poster is one fixed
# frame at one scale and its labels are placed by hand against the whole
# composition; the map can afford more names because they only appear once
# somebody has zoomed in, and it costs nothing to hold a name in reserve. So this
# list is deliberately *not* imported by poster.py, and the sheet is unchanged.
#
# Every coordinate here is the centroid of the island as the coastline draws it,
# read off the geometry rather than estimated, so a label sits on its own cay.
# The names are the identifications I could defend; the smaller cays between
# Marsh Harbour and Little Harbour are left unnamed rather than guessed at.
# (lon, lat, text, minzoom). The zoom is per-cay because these labels have no
# collision detection — they are HTML markers, not a symbol layer — and Dickie's
# Cay sits 500 m from Man-O-War Cay's label, so it has to wait until the two are
# far enough apart on screen to read as two names.
MAP_CAYS = [
    (-77.07431, 26.64559, "Scotland Cay", 11.0),
    (-77.02866, 26.55015, "Matt Lowe's Cay", 11.0),
    (-77.00851, 26.59472, "Dickie's Cay", 13.5),
]
# Each coordinate is `representative_point()` of the island, which is guaranteed to
# fall inside it. Centroids were tried first and two of the four landed in open
# water, because the centroid of a crescent is not on the crescent.
#
# Two names came out again rather than be got wrong. Lynyard Cay is already named by
# ANCHORAGES, and adding it here put the same words on the chart twice four hundred
# metres apart. Pelican Cays is a group rather than one island, and the nearest
# thing to my guessed position was a rock of a fifth of a hectare — a group label
# wants someone who knows which cays it covers.

# Islands the coastline draws in the trip area that nothing names yet, largest
# first, with the size and length the geometry gives them. Left here because naming
# them is local knowledge rather than something to infer from a polygon:
#
#   26.50003 -76.99741  143 ha  2.7 km   (south of White Sound — Elbow Cay?)
#   26.43754 -77.05112   73 ha  2.6 km   (Lubbers Quarters Cay?)
#   26.40549 -77.04310   40 ha  1.5 km
#   26.29510 -77.05458   41 ha  1.1 km   (off Little Harbour)
#   26.42328 -77.04093   19 ha  1.7 km
#   26.35872 -77.02272   22 ha  0.9 km
#   26.33446 -77.02760   20 ha  1.5 km
#   26.56368 -77.01499   20 ha  1.0 km
#   26.41405 -76.99644   10 ha  0.9 km

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


def in_chart(lat, lon):
    """Is this position on the Abaco chart at all?"""
    lon0, lon1, lat0, lat1 = EXTENT
    return lon0 <= lon <= lon1 and lat0 <= lat <= lat1


def transfer_route():
    """Friday's airport→hotel drive, routed over OSM roads.

    The recorded log for that day is unusable — the whole thing is dead-reckoning
    noise inside an 870 m box — so this is a reconstruction, and both the poster
    and the map say so by drawing it dotted. It lives here rather than in
    poster.py because a day drawn one way on paper and another way on the chart
    is exactly the drift this module exists to prevent.
    """
    from roads import route as road_route
    pts, _ = road_route((AIRPORT[1], AIRPORT[0]), (HOTEL[1], HOTEL[0]))
    return pts


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


def read_fixes(stem):
    """Every usable fix from one log, in time order. Returns (fixes, dropped).

    A fix is `(utc, lat, lon, sog_kn)`. The quality filter and nothing else: no
    thinning, no walk/road split, because where the receiver was is where the
    receiver was whether it was under sail, on foot, or in a van to the airport.
    Those distinctions are cartographic and belong to load_day().

    `dropped` counts fixes the quality gate rejected. Fixes above 30° N — the
    Portland legs — are simply not this trip and are not counted as dropped.

    One filter deliberately left out: load_day() also rejects residual position
    spikes (a jump implying >30 kn over more than 60 m), which it can do because
    it walks the track in order, holding the last accepted fix. That guard is
    about coordinates being wrong rather than the receiver reporting them badly,
    so anything placing objects on this stream wants it too — see place.py.
    """
    path = os.path.join(HERE, "tracks", stem + ".csv")
    fixes, dropped = [], 0
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
            fixes.append((datetime.strptime(r["utc"], "%Y-%m-%dT%H:%M:%SZ")
                          .replace(tzinfo=timezone.utc),
                          lat, lon, float(r["sog_kn"])))
    # The logs are written sequentially and measure as monotonic, so this sorts
    # nothing today. It is here because bisecting for a bracketing pair is only
    # correct on a sorted stream, and that guarantee should be the reader's.
    fixes.sort(key=lambda p: p[0])
    return fixes, dropped


def _split_at(pts, iso):
    """Cut a day in two at a UTC instant: (before, after)."""
    cut = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return [p for p in pts if p[0] <= cut], [p for p in pts if p[0] > cut]


def _thin(pts, step=3):
    return [p for i, p in enumerate(pts) if i % step == 0 or i == len(pts) - 1]


def load_day(stem, min_step_m=22.0, max_kn=30.0, walk_split=None, road_split=None):
    """A day's track as the poster draws it: thinned, and split by how we moved.

    Distance only accumulates while the receiver reports real way on the boat,
    so hours of swinging at anchor don't quietly add miles to the day.

    Not for placement — see this module's docstring, and read_fixes().
    """
    raw, dropped = read_fixes(stem)
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


# ------------------------------------------------------------------ shoals ---
_SHOAL_CACHE = {}


def shoal(land, buf):
    """Buffered 'shallows' ring around the land — expensive, so memoize it.

    Keyed on the land as well as the distance. It used to key on the distance
    alone, which was safe only while one coastline existed: the poster buffers its
    own bbox at full resolution and the map buffers a wider one, so a process that
    drew both would have been handed whichever ring was built first.
    """
    key = (buf, round(land.area, 9), len(getattr(land, "geoms", [land])))
    if key not in _SHOAL_CACHE:
        _SHOAL_CACHE[key] = land.buffer(buf, join_style=1).buffer(
            -buf * 0.15, join_style=1)
    return _SHOAL_CACHE[key]


# ----------------------------------------------------------------- barrier ---
# The barrier chain, NW->SE: the outer cays dividing the Sea of Abaco from the
# Atlantic. Hand-drawn, so treat anything within ~0.5 km of it as "on the cays"
# rather than offshore.
BARRIER = [(-77.190, 26.720), (-77.145, 26.690), (-77.090, 26.652),
           (-77.045, 26.628), (-77.003, 26.596), (-76.972, 26.560),
           (-76.955, 26.535), (-76.968, 26.500), (-76.975, 26.455),
           (-76.978, 26.410), (-76.982, 26.365), (-76.995, 26.322),
           (-77.010, 26.280)]
OFFSHORE_KM = 0.5


def offshore_km(lon, lat):
    """Signed distance from the barrier chain; positive is the Atlantic side."""
    import numpy as np
    k = math.cos(math.radians(LAT0))
    b = np.array([(lo * k, la) for lo, la in BARRIER])
    p = np.array([lon * k, lat])
    seg = b[1:] - b[:-1]
    t = np.clip(((p - b[:-1]) * seg).sum(1) / (seg ** 2).sum(1), 0, 1)
    proj = b[:-1] + seg * t[:, None]
    i = int(np.argmin(((p - proj) ** 2).sum(1)))
    d = math.hypot(*(p - proj[i])) * 111.0
    s = seg[i]
    out = (s[0] * (p[1] - b[i][1]) - s[1] * (p[0] - b[i][0])) > 0
    return d if out else -d
