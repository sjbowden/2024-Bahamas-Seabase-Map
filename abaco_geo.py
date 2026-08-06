#!/usr/bin/env python3
"""Turn raw OSM coastline ways into clean land polygons.

OSM stores coastline as unordered, open-ended ways with the convention that
land lies to the LEFT of the way direction. We build the planar graph of
(coastline + bbox edge), polygonize it into faces, then classify each face as
land or water using that left-hand rule.
"""
import json
import math
import os
import pickle

from shapely.geometry import LineString, Point, box
from shapely.ops import polygonize, unary_union

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_ways(path):
    js = json.load(open(path))
    ways = []
    for e in js.get("elements", []):
        g = e.get("geometry")
        if not g or len(g) < 2:
            continue
        ways.append(LineString([(p["lon"], p["lat"]) for p in g]))
    return ways


def land_polygons(bbox, cache=True):
    """bbox = (west, south, east, north) in degrees -> unioned land geometry."""
    key = os.path.join(HERE, "geo", "land_%.4f_%.4f_%.4f_%.4f.pkl" % bbox)
    if cache and os.path.exists(key):
        with open(key, "rb") as fh:
            return pickle.load(fh)

    w, s, e, n = bbox
    frame = box(w, s, e, n)
    ways = _load_ways(os.path.join(HERE, "geo", "coastline.json"))

    # clip to frame, keeping direction
    segs = []
    for way in ways:
        clipped = way.intersection(frame)
        if clipped.is_empty:
            continue
        parts = getattr(clipped, "geoms", [clipped])
        for p in parts:
            if p.geom_type == "LineString" and len(p.coords) >= 2:
                segs.append(p)
    if not segs:
        raise SystemExit("no coastline inside bbox")

    # faces of the planar graph formed by coastline + frame boundary
    network = unary_union(segs + [frame.exterior])
    faces = [f for f in polygonize(network) if f.area > 0]

    # left-hand rule: for each face, find the nearest coastline segment to an
    # interior point and test which side that point falls on.
    coast = unary_union(segs)
    land = []
    for f in faces:
        pt = f.representative_point()
        best, bestd = None, float("inf")
        for sgn in segs:
            d = sgn.distance(pt)
            if d < bestd:
                bestd, best = d, sgn
        # locate the closest vertex pair on that way
        proj = best.project(pt)
        a = best.interpolate(max(proj - 1e-5, 0.0))
        b = best.interpolate(min(proj + 1e-5, best.length))
        cross = ((b.x - a.x) * (pt.y - a.y) - (b.y - a.y) * (pt.x - a.x))
        if cross > 0:                      # point lies left of travel = land
            land.append(f)

    result = unary_union(land) if land else None
    if cache:
        os.makedirs(os.path.join(HERE, "geo"), exist_ok=True)
        with open(key, "wb") as fh:
            pickle.dump(result, fh)
    return result


def polys(geom):
    """Yield exterior/interior ring coordinate lists for plotting."""
    if geom is None or geom.is_empty:
        return
    for g in getattr(geom, "geoms", [geom]):
        if g.geom_type != "Polygon":
            continue
        yield list(g.exterior.coords), [list(r.coords) for r in g.interiors]


if __name__ == "__main__":
    BB = (-77.35, 26.15, -76.80, 26.85)
    land = land_polygons(BB, cache=False)
    n = len(getattr(land, "geoms", [land]))
    print(f"{n} land polygons, total area {land.area:.5f} deg^2")
    big = sorted(getattr(land, "geoms", [land]), key=lambda g: -g.area)[:5]
    for g in big:
        c = g.centroid
        print(f"  area {g.area:.5f}  centroid {c.y:.3f},{c.x:.3f}")
