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

# The interactive chart can be panned and zoomed, so it runs out of coastline
# where the poster simply stops at its neatline. An ultrawide window can reach
# lon -78.31 to -75.79, and the poster's cache holds nothing north of 26.83 — so
# Little Abaco, Coopers Town and Treasure Cay were missing entirely and the land
# ended in a straight vertical line. This wider box is fetched to its own file:
# land_polygons() builds a planar graph from the coastline *and the bbox frame*
# and classifies faces by the left-hand rule, so the frame is structural and the
# poster's geometry must not be disturbed by the map's needs.
MAP_BBOX = (25.40, -78.60, 27.60, -75.50)

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

QUERIES = {
    "coastline": '(way["natural"="coastline"]({bbox});); out geom;',
    "reef": '(way["natural"="reef"]({bbox});rel["natural"="reef"]({bbox});); out geom;',
    "places": '(node["place"~"^(town|village|hamlet|island|islet)$"]({bbox});); out;',
}


def overpass(q, bbox=BBOX):
    body = "[out:json][timeout:300];" + q.format(bbox=",".join(str(v) for v in bbox))
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
    wide = "--map" in sys.argv
    jobs = ([("coastline_map", QUERIES["coastline"], MAP_BBOX)] if wide
            else [(n, q, BBOX) for n, q in QUERIES.items()])
    for name, q, bbox in jobs:
        dest = os.path.join(CACHE, name + ".json")
        if os.path.exists(dest) and "--force" not in sys.argv:
            print(f"{name}: cached")
            continue
        print(f"{name}: fetching {bbox}...")
        js = overpass(q, bbox)
        with open(dest, "w") as fh:
            json.dump(js, fh)
        print(f"{name}: {len(js.get('elements', []))} elements")


if __name__ == "__main__":
    main()
