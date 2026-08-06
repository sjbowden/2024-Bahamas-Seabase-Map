#!/usr/bin/env python3
"""Fetch OSM coastline + reef geometry for the Sea of Abaco and stitch it into
land polygons, cached as GeoJSON so the poster renderer works offline."""
import json
import os
import sys
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "geo")

# generous bbox around the whole trip (S, W, N, E)
BBOX = (26.15, -77.35, 26.85, -76.80)

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

QUERIES = {
    "coastline": '(way["natural"="coastline"]({bbox});); out geom;',
    "reef": '(way["natural"="reef"]({bbox});rel["natural"="reef"]({bbox});); out geom;',
    "places": '(node["place"~"^(town|village|hamlet|island|islet)$"]({bbox});); out;',
}


def overpass(q):
    body = "[out:json][timeout:180];" + q.format(bbox=",".join(str(v) for v in BBOX))
    data = urllib.parse.urlencode({"data": body}).encode()
    last = None
    for url in ENDPOINTS:
        try:
            req = urllib.request.Request(url, data=data,
                                         headers={"User-Agent": "abaco-track-poster/1.0"})
            with urllib.request.urlopen(req, timeout=200) as r:
                return json.load(r)
        except Exception as e:  # try the mirror
            last = e
            print(f"  {url} failed: {e}", file=sys.stderr)
    raise SystemExit(f"all overpass endpoints failed: {last}")


def main():
    os.makedirs(CACHE, exist_ok=True)
    for name, q in QUERIES.items():
        dest = os.path.join(CACHE, name + ".json")
        if os.path.exists(dest):
            print(f"{name}: cached")
            continue
        print(f"{name}: fetching...")
        js = overpass(q)
        with open(dest, "w") as fh:
            json.dump(js, fh)
        print(f"{name}: {len(js.get('elements', []))} elements")


if __name__ == "__main__":
    main()
