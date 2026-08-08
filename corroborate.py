#!/usr/bin/env python3
"""Cross-check the handheld GPS track against the other two record-keepers.

Three devices recorded this trip independently:

  * the handheld receiver  — GPSFILES/*.log, a fix every ~5 s while it had
    battery, which is roughly one 10–13 hour day per charge
  * an inReach satellite communicator — geo/inreach.gpx, a position report every
    10 minutes by day and every 4 hours overnight, and crucially still running
    while the handheld was on the charger
  * the crew's cameras — EXIF GPS, mostly iPhone

Agreement between them is what makes the chart trustworthy, and the inReach is
the only thing that can say what happened overnight.

    python corroborate.py [path/to/inreach.gpx] [path/to/photos.csv]
"""
import csv
import math
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from trip import (DAYS, EDT, LAT0, OFFSHORE_KM, haversine, load_day,
                  offshore_km)

NS = "{http://www.topografix.com/GPX/1/1}"
HERE = os.path.dirname(os.path.abspath(__file__))


def load_gpx(path):
    pts = []
    for tp in ET.parse(path).getroot().iter(NS + "trkpt"):
        t = tp.find(NS + "time")
        if t is None:
            continue
        pts.append((datetime.strptime(t.text, "%Y-%m-%dT%H:%M:%SZ")
                    .replace(tzinfo=timezone.utc),
                    float(tp.get("lat")), float(tp.get("lon"))))
    return sorted(pts)


def handheld_windows():
    """One (start, end, label) per log — i.e. per battery charge."""
    out = []
    for d in DAYS:
        t = load_day(d["file"], walk_split=d.get("walk_split"),
                     road_split=d.get("road_split"))
        pts = sorted(t["afloat"] + t["walk"] + t["road"], key=lambda p: p[0])
        if pts:
            out.append((pts[0][0], pts[-1][0], d["label"]))
    return sorted(out)


def all_fixes():
    fixes = []
    for d in DAYS:
        t = load_day(d["file"], walk_split=d.get("walk_split"),
                     road_split=d.get("road_split"))
        fixes += t["afloat"] + t["walk"] + t["road"]
    return sorted(fixes, key=lambda p: p[0])


def rule(title):
    print(f"\n{title}\n{'-' * len(title)}")


def main():
    gpx = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "geo", "inreach.gpx")
    photos = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "photos.csv")

    windows = handheld_windows()
    rule("Handheld runtime per charge")
    for s, e, label in windows:
        a, b = s.astimezone(EDT), e.astimezone(EDT)
        print(f"  {label:12s} {a:%H:%M}-{b:%H:%M}   {(b-a).total_seconds()/3600:5.1f} h")

    if not os.path.exists(gpx):
        print(f"\n(no inReach track at {gpx})")
        return

    inr = load_gpx(gpx)
    fixes = all_fixes()
    rule("inReach track")
    print(f"  {len(inr)} points, {inr[0][0]:%d %b %H:%M}Z .. {inr[-1][0]:%d %b %H:%M}Z")
    gaps = [(inr[i+1][0] - inr[i][0]).total_seconds() / 60 for i in range(len(inr) - 1)]
    print(f"  {sum(1 for g in gaps if 9.5 < g < 10.5)} of {len(gaps)} gaps are "
          f"10 min — a scheduled reporting interval, not a continuous logger")

    # (a) same place at the same moment?
    agree = []
    for t, la, lo in inr:
        n = min(fixes, key=lambda p: abs((p[0] - t).total_seconds()))
        if abs((n[0] - t).total_seconds()) <= 60:
            agree.append(haversine(la, lo, n[1], n[2]))
    agree.sort()
    if agree:
        print(f"  same moment, {len(agree)} coincident fixes: "
              f"median {agree[len(agree)//2]:.0f} m, "
              f"90th {agree[int(len(agree)*0.9)]:.0f} m, max {agree[-1]:.0f} m")

    # (b) same route? distance from each inReach point to the handheld's path,
    # ignoring time — this is what tells you the two tracks trace one voyage
    from shapely.geometry import LineString, Point
    k = math.cos(math.radians(LAT0))
    path_line = LineString([(p[2] * k, p[1]) for p in fixes])
    onpath = sorted(path_line.distance(Point(lo * k, la)) * 111000.0
                    for _, la, lo in inr)
    print(f"  same route, {len(inr)} points measured against the handheld path: "
          f"median {onpath[len(onpath)//2]:.0f} m, "
          f"90th {onpath[int(len(onpath)*0.9)]:.0f} m, max {onpath[-1]:.0f} m")
    print(f"  {sum(1 for d in onpath if d < 50)} of {len(onpath)} lie within 50 m "
          f"of the handheld's path")

    rule("Overnight, while the handheld was on the charger")
    for i in range(len(windows) - 1):
        s, e = windows[i][1], windows[i+1][0]
        pts = [p for p in inr if s < p[0] < e]
        hrs = (e - s).total_seconds() / 3600
        head = (f"  {s.astimezone(EDT):%a %d} {s.astimezone(EDT):%H:%M}"
                f"-{e.astimezone(EDT):%H:%M} ({hrs:4.1f} h, {len(pts)} fixes)")
        if not pts:
            print(f"{head}  no tracker coverage")
            continue
        path = sum(haversine(pts[j][1], pts[j][2], pts[j+1][1], pts[j+1][2])
                   for j in range(len(pts) - 1))
        net = haversine(pts[0][1], pts[0][2], pts[-1][1], pts[-1][2])
        bounds = [s] + [p[0] for p in pts] + [e]
        blind = max((bounds[j+1] - bounds[j]).total_seconds() / 3600
                    for j in range(len(bounds) - 1))
        print(f"{head}  path {path:5.0f} m  net {net:4.0f} m  "
              f"longest unwatched {blind:4.1f} h"
              f"{'   <-- MOVED' if net > 300 else ''}")

    rule("Outside the barrier cays")
    for d in DAYS:
        t = load_day(d["file"], walk_split=d.get("walk_split"),
                     road_split=d.get("road_split"))
        out = [p for p in t["afloat"] if offshore_km(p[2], p[1]) > OFFSHORE_KM]
        if not out:
            continue
        far = max(offshore_km(p[2], p[1]) for p in out)
        print(f"  {d['label']:12s} {out[0][0].astimezone(EDT):%H:%M}"
              f"-{out[-1][0].astimezone(EDT):%H:%M} EDT, "
              f"{(out[-1][0]-out[0][0]).total_seconds()/60:.0f} min, "
              f"out to {far:.2f} km beyond the chain")
        seen = [p for p in inr if out[0][0] <= p[0] <= out[-1][0]]
        print(f"  {'':12s} the inReach independently caught it: {len(seen)} fixes")

    if os.path.exists(photos):
        rule("Camera GPS")
        rows = [r for r in csv.DictReader(open(photos))
                if r.get("lat") and float(r["lat"]) < 30 and r.get("when")]
        ds = []
        for r in rows:
            t = datetime.strptime(r["when"], "%Y:%m:%d %H:%M:%S").replace(tzinfo=EDT)
            n = min(fixes, key=lambda p: abs((p[0] - t).total_seconds()))
            if abs((n[0] - t).total_seconds()) <= 90:
                ds.append(haversine(float(r["lat"]), float(r["lon"]), n[1], n[2]))
        ds.sort()
        if ds:
            print(f"  {len(rows)} located photos; {len(ds)} within 90 s of a fix: "
                  f"median {ds[len(ds)//2]:.0f} m, 90th {ds[int(len(ds)*0.9)]:.0f} m")
        off = [r for r in rows if offshore_km(float(r["lon"]), float(r["lat"])) > OFFSHORE_KM]
        print(f"  {len(off)} photo(s) taken beyond the barrier chain:")
        for r in sorted(off, key=lambda r: r["when"]):
            print(f"     {r['when']}  {r['name']}  "
                  f"{offshore_km(float(r['lon']), float(r['lat'])):.2f} km offshore")


if __name__ == "__main__":
    main()
