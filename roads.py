#!/usr/bin/env python3
"""Road routing around Marsh Harbour.

Friday's arrival transfer was never usably recorded — that whole log is
dead-reckoning noise inside an 870 m box — so the airport-to-hotel leg is
reconstructed by routing over the OSM road network rather than invented.
"""
import json
import heapq
import math
import os
import pickle
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "geo")
BBOX = "26.495,-77.100,26.570,-77.030"          # S,W,N,E around Marsh Harbour

DRIVABLE = ("motorway", "trunk", "primary", "secondary", "tertiary",
            "unclassified", "residential", "service", "living_street",
            "motorway_link", "trunk_link", "primary_link", "secondary_link")
WALKABLE = DRIVABLE + ("footway", "path", "pedestrian", "track", "steps")

ENDPOINTS = ["https://overpass-api.de/api/interpreter",
             "https://overpass.kumi.systems/api/interpreter"]


def fetch_roads():
    dest = os.path.join(CACHE, "roads.json")
    if os.path.exists(dest):
        return json.load(open(dest))
    q = f'[out:json][timeout:120];(way["highway"]({BBOX}););out geom;'
    data = urllib.parse.urlencode({"data": q}).encode()
    last = None
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(url, data=data,
                                         headers={"User-Agent": "abaco-poster/1.0"})
            js = json.load(urllib.request.urlopen(req, timeout=180))
            os.makedirs(CACHE, exist_ok=True)
            json.dump(js, open(dest, "w"))
            return js
        except Exception as e:
            last = e
            print(f"  {url}: {e}")
    raise SystemExit(f"overpass failed: {last}")


def _key(lat, lon):
    return (round(lat, 6), round(lon, 6))


def metres(a, b):
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    h = (math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2)
         * math.sin(math.radians(b[1] - a[1]) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(h))


def build_graph(allowed):
    js = fetch_roads()
    g = {}
    for el in js.get("elements", []):
        if el.get("tags", {}).get("highway") not in allowed:
            continue
        geom = el.get("geometry") or []
        for a, b in zip(geom, geom[1:]):
            ka, kb = _key(a["lat"], a["lon"]), _key(b["lat"], b["lon"])
            if ka == kb:
                continue
            w = metres(ka, kb)
            g.setdefault(ka, []).append((kb, w))
            g.setdefault(kb, []).append((ka, w))   # treat all roads two-way
    return g


def nearest(g, lat, lon):
    return min(g, key=lambda n: metres(n, (lat, lon)))


def route(start, end, walking=False):
    """(lat,lon) -> (lat,lon) shortest path along roads; list of (lon,lat)."""
    cache = os.path.join(CACHE, "route_%s_%.5f_%.5f_%.5f_%.5f.pkl"
                         % ("w" if walking else "d", *start, *end))
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))

    g = build_graph(WALKABLE if walking else DRIVABLE)
    s, e = nearest(g, *start), nearest(g, *end)
    dist = {s: 0.0}
    prev = {}
    pq = [(0.0, s)]
    seen = set()
    while pq:
        d, n = heapq.heappop(pq)
        if n in seen:
            continue
        seen.add(n)
        if n == e:
            break
        for m, w in g.get(n, ()):
            nd = d + w
            if nd < dist.get(m, float("inf")):
                dist[m] = nd
                prev[m] = n
                heapq.heappush(pq, (nd, m))
    if e not in dist:
        raise SystemExit("no road route found")
    path, cur = [], e
    while cur != s:
        path.append(cur)
        cur = prev[cur]
    path.append(s)
    path.reverse()
    # snap the true endpoints onto the ends of the road path
    out = ([(start[1], start[0])] + [(lon, lat) for lat, lon in path]
           + [(end[1], end[0])])
    pickle.dump((out, dist[e]), open(cache, "wb"))
    return out, dist[e]


if __name__ == "__main__":
    AIRPORT = (26.5135, -77.0782)
    HOTEL = (26.545222, -77.048906)
    MARINA = (26.5470, -77.0517)
    p, d = route(AIRPORT, HOTEL)
    print(f"airport -> hotel : {len(p)} pts, {d/1000:.2f} km ({d/1852:.2f} nm)")
    p, d = route(HOTEL, MARINA, walking=True)
    print(f"hotel -> marina  : {len(p)} pts, {d:.0f} m")
