#!/usr/bin/env python3
"""Summarize each local sailing day: span, distance, moving speed, anchorages."""
import csv
import glob
import math
import os
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
EDT = timezone(timedelta(hours=-4))       # Bahamas, late March 2024
NM = 1852.0                                # metres per nautical mile


GOOD_QUALITY = (1, 2, 4, 5)     # GPS / DGPS / RTK; 6 is dead-reckoning guesswork
MIN_SATS = 4
MAX_HDOP = 4.0
MOVING_KN = 0.5                 # below this the boat is swinging on its hook


def load(path):
    """Fixes good enough to trust. Keep this filter in step with poster.py."""
    pts, dropped = [], 0
    with open(path) as fh:
        for r in csv.DictReader(fh):
            if (int(r["quality"]) not in GOOD_QUALITY
                    or int(r["sats"]) < MIN_SATS
                    or float(r["hdop"]) > MAX_HDOP):
                dropped += 1
                continue
            pts.append((
                datetime.strptime(r["utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc),
                float(r["lat"]), float(r["lon"]), float(r["sog_kn"]),
            ))
    return pts, dropped


def haversine(a_lat, a_lon, b_lat, b_lon):
    R = 6371000.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp = p2 - p1
    dl = math.radians(b_lon - a_lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def clean(pts, max_kn=30.0):    # the airport van legitimately hit 25.8 kn
    """Drop fixes implying an impossible speed over ground (GPS spikes)."""
    out = [pts[0]]
    for p in pts[1:]:
        dt = (p[0] - out[-1][0]).total_seconds()
        if dt <= 0:
            continue
        d = haversine(out[-1][1], out[-1][2], p[1], p[2])
        if d / dt * 1.94384 > max_kn and d > 60:
            continue
        out.append(p)
    return out


def stops(pts, radius_m=90, min_minutes=25):
    """Find stationary periods: a run of fixes staying inside `radius_m`."""
    res, i, n = [], 0, len(pts)
    while i < n:
        j = i + 1
        while j < n and haversine(pts[i][1], pts[i][2], pts[j][1], pts[j][2]) < radius_m:
            j += 1
        mins = (pts[j - 1][0] - pts[i][0]).total_seconds() / 60
        if mins >= min_minutes:
            lat = sum(p[1] for p in pts[i:j]) / (j - i)
            lon = sum(p[2] for p in pts[i:j]) / (j - i)
            res.append((pts[i][0], pts[j - 1][0], mins, lat, lon))
            i = j
        else:
            i += 1
    return res


def main():
    grand = 0.0
    for path in sorted(glob.glob(os.path.join(HERE, "tracks", "*.csv"))):
        pts, dropped = load(path)
        pts = clean(pts) if len(pts) >= 2 else pts
        if len(pts) < 2:
            continue
        local0 = pts[0][0].astimezone(EDT)
        bahamas = pts[0][1] < 30
        tz = EDT if bahamas else timezone(timedelta(hours=-7))
        a, b = pts[0][0].astimezone(tz), pts[-1][0].astimezone(tz)
        dist = sum(haversine(pts[k][1], pts[k][2], pts[k + 1][1], pts[k + 1][2])
                   for k in range(len(pts) - 1)
                   if pts[k + 1][3] > MOVING_KN)   # ignore drift at anchor
        moving = [p[3] for p in pts if p[3] > 0.8]
        print(f"\n{os.path.basename(path)}  [{'BAHAMAS' if bahamas else 'travel'}]"
              f"  ({dropped} low-quality fixes dropped)")
        print(f"  local {a:%a %b %d %H:%M} -> {b:%H:%M}  ({(b-a).total_seconds()/3600:.1f} h)")
        print(f"  track {dist/NM:8.1f} nm   max SOG {max(p[3] for p in pts):5.1f} kn"
              f"   avg moving {sum(moving)/len(moving) if moving else 0:4.1f} kn")
        if bahamas:
            grand += dist
            for s, e, mins, lat, lon in stops(pts):
                print(f"    stop {s.astimezone(tz):%H:%M}-{e.astimezone(tz):%H:%M} "
                      f"({mins:5.0f} min)  {lat:.4f},{lon:.4f}")
    print(f"\nTOTAL moved in the Bahamas: {grand/NM:.1f} nm "
          f"(includes the arrival and airport-transfer days)")


if __name__ == "__main__":
    main()
