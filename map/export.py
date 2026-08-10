#!/usr/bin/env python3
"""Write the site's data files: GeoJSON for the chart, JSON for the photographs.

    python -m map.export --report

Everything the browser needs and nothing it has to work out for itself. Positions,
tiers, uncertainties and notes are all resolved by now; this step only serialises
them, rounds coordinates to something honest, and simplifies the coastline enough
that a phone can draw it.

**Zoom bands.** The land is 1,370 polygons and 117,850 vertices, and the shoals
are two buffers over the same geometry. Shipped raw that is the better part of
10 MB before the first pixel appears, on a page whose whole point is that the crew
opens it from a text message. So each band is simplified to about half a pixel at
the scale it serves, and at the coarsest band anything smaller than a pixel is
dropped rather than drawn as a speck nobody can see.

Coordinates are rounded to five decimal places — about 1 m at this latitude, well
under the uncertainty of anything on this chart, and roughly half the bytes of the
full float.
"""
import argparse
import collections
import json
import os
import xml.etree.ElementTree as ET

from shapely import set_precision
from shapely.geometry import box as shapely_box

from abaco_geo import COASTLINE_MAP, land_polygons
from trip import (AIRPORT, ANCHORAGES, DAYS, EXTENT, HOTEL, MAP_LAND_BBOX,
                  MARINA, PLACES, VIEW_BOUNDS, load_day, shoal, transfer_route)
from map import clock_fit as C
from map import place as P

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NS = "{http://www.topografix.com/GPX/1/1}"

# Web-mercator resolution at 26.5 N is 139,950 / 2^z m/px, so half a pixel is:
#   z=10  ~68 m    z=12  ~17 m    z=14  ~4 m
# One degree of latitude is ~111 km, which turns those into simplify tolerances.
# The coarse band also drops islets under a pixel: at z=10 that is ~19,000 m2.
# `near` clips a band to the area anyone will actually zoom into. The coarse band
# carries the whole region, because zoomed out is exactly when you want Little
# Abaco and Grand Bahama for context; the finer two would otherwise ship
# street-level detail for coastlines nobody can reach the far side of, and the
# fine band alone came to 2 MB of it.
BANDS = [
    dict(name="coarse", maxzoom=11, tol=0.00061, min_area_m2=19000.0, near=None),
    dict(name="medium", maxzoom=13, tol=0.00015, min_area_m2=1200.0, near=0.30),
    dict(name="fine", maxzoom=22, tol=0.00004, min_area_m2=0.0, near=0.30),
]
SHOALS = [(0.0060, "outer"), (0.0026, "inner")]
PRECISION = 5

# 1 deg^2 at 26.5 N, for the islet-area test without reprojecting anything.
_M_PER_DEG_LAT = 111320.0
_M_PER_DEG_LON = 99500.0


def _round(coords):
    return [[round(x, PRECISION), round(y, PRECISION)] for x, y in coords]


def _rings(geom, tol, min_area_m2):
    """Simplified exterior/interior rings of a (multi)polygon, small parts dropped.

    Simplified as one geometry, not part by part. `preserve_topology` only
    promises a part will not self-intersect; simplifying 1,370 islands
    independently let neighbours drift into each other, and the result was a
    MultiPolygon whose every part was valid and whose whole was not.
    """
    s = geom.simplify(tol, preserve_topology=True)
    # Snap to the output grid *before* serialising, and let shapely keep the
    # result valid while it does. Rounding coordinates on the way out is what
    # broke the two finer bands: at 5 decimals the grid is 1 m, the fine band's
    # tolerance is 4 m, and rounding quietly pushed neighbouring vertices onto
    # each other. set_precision(mode="valid_output") is the operation that was
    # actually wanted.
    s = set_precision(s, 10.0 ** -PRECISION, mode="valid_output")
    out = []
    for g in (list(s.geoms) if hasattr(s, "geoms") else [s]):
        if g.is_empty or not hasattr(g, "exterior"):
            continue
        if min_area_m2 and g.area * _M_PER_DEG_LAT * _M_PER_DEG_LON < min_area_m2:
            continue
        ring = [_round(g.exterior.coords)]
        ring += [_round(h.coords) for h in g.interiors]
        out.append(ring)
    return out


def _fc(features):
    return dict(type="FeatureCollection", features=features)


def _poly(rings, props):
    return dict(type="Feature", properties=props,
                geometry=dict(type="MultiPolygon", coordinates=rings))


def _near_chart(pad):
    """The chart extent grown by `pad` degrees — where zooming in is possible."""
    lon0, lon1, lat0, lat1 = EXTENT
    return shapely_box(lon0 - pad, lat0 - pad, lon1 + pad, lat1 + pad)


def chart_layers(land):
    """coast + shoals, one file per zoom band."""
    files = {}
    for band in BANDS:
        subject = land if band["near"] is None else \
            land.intersection(_near_chart(band["near"]))
        rings = _rings(subject, band["tol"], band["min_area_m2"])
        files[f"coast.{band['name']}.geojson"] = _fc([
            _poly(rings, dict(kind="land", maxzoom=band["maxzoom"]))])
        feats = []
        for buf, name in SHOALS:
            # Buffer the whole land, then clip: buffering a clipped coastline
            # would put a shoal halo along the clip line itself.
            ring_geom = shoal(land, buf)
            if band["near"] is not None:
                ring_geom = ring_geom.intersection(_near_chart(band["near"]))
            sr = _rings(ring_geom, band["tol"], band["min_area_m2"])
            if sr:
                feats.append(_poly(sr, dict(kind="shoal", ring=name,
                                            maxzoom=band["maxzoom"])))
        files[f"shoals.{band['name']}.geojson"] = _fc(feats)
    return files


def track_layer():
    """Seven days, drawn true. The poster's lateral offset is a print compromise
    and zoom solves the crowding properly, so nothing is nudged here."""
    feats = []
    for d in DAYS:
        t = load_day(d["file"], walk_split=d.get("walk_split"),
                     road_split=d.get("road_split"))
        segments = dict(t)
        # The poster draws no recorded track on the arrival day, because that
        # log is dead-reckoning noise inside an 870 m box, and substitutes the
        # road route instead. The map has to make the same choice or the two
        # artefacts disagree about how the crew reached the hotel.
        if d.get("ashore"):
            segments["afloat"] = []
        if d.get("transfer"):
            # transfer_route() yields (lon, lat) pairs, which is the order the
            # poster's plotter wants and the reverse of a track fix's.
            segments["transfer"] = [(None, lat, lon)
                                    for lon, lat in transfer_route()]
        for mode in ("afloat", "walk", "road", "transfer"):
            pts = segments.get(mode) or []
            if len(pts) < 2:
                continue
            feats.append(dict(
                type="Feature",
                properties=dict(day=d["label"], mode=mode, color=d["color"],
                                title=d["title"], route=d["route"],
                                n=d.get("n"), sail=bool(d.get("sail")),
                                nm=round(t["nm"], 1) if mode == "afloat" else None),
                geometry=dict(type="LineString",
                              coordinates=_round([(p[2], p[1]) for p in pts]))))
    return _fc(feats)


def places_layer():
    """The poster's own labels, so the two artefacts name the same places.

    minzoom staggers them: the big water and island legends belong at the scale
    you arrive at, the anchorages and the marina only once you are looking closely.
    """
    # These are set against the zoom the chart actually *opens* at, which differs
    # by device: the extent is portrait, so a landscape desktop fits it at about
    # z10.4 and a phone at about z9.9. Thresholds of 10 left the phone — the
    # stated primary target — with no names on it at all. Towns and cays now
    # appear on the first screen everywhere; anchorages still wait until someone
    # is looking closely at one.
    zoom = dict(big=8.5, water=8.5, town=9, isle=9.6)
    feats = []
    for lon, lat, text, kind, *_ in PLACES:
        feats.append(dict(type="Feature",
                          properties=dict(label=text, kind=kind,
                                          minzoom=zoom.get(kind, 11)),
                          geometry=dict(type="Point",
                                        coordinates=[round(lon, PRECISION),
                                                     round(lat, PRECISION)])))
    for lon, lat, text, *_ in ANCHORAGES:
        feats.append(dict(type="Feature",
                          properties=dict(label=text, kind="anchorage", minzoom=11.5),
                          geometry=dict(type="Point", coordinates=[round(lon, 5),
                                                                   round(lat, 5)])))
    for lon, lat, label, kind in ((AIRPORT[0], AIRPORT[1], AIRPORT[3], "airport"),
                                  (HOTEL[0], HOTEL[1], "Hotel", "hotel"),
                                  (MARINA[0], MARINA[1], "Marina", "marina")):
        feats.append(dict(type="Feature",
                          properties=dict(label=label, kind=kind, minzoom=12),
                          geometry=dict(type="Point", coordinates=[round(lon, 5),
                                                                   round(lat, 5)])))
    return _fc(feats)


def inreach_layer(path=None):
    """The tracker's positions — off by default, and the only evidence of where
    the boat sat overnight. Display only: nothing is placed from it, because
    measured, its usable brackets buy ten minutes the handheld does not already
    cover."""
    path = path or os.path.join(HERE, "geo", "inreach.gpx")
    if not os.path.exists(path):
        return None
    pts = []
    for tp in ET.parse(path).getroot().iter(NS + "trkpt"):
        t = tp.find(NS + "time")
        if t is None:
            continue
        pts.append((t.text, float(tp.get("lat")), float(tp.get("lon"))))
    pts.sort()
    return _fc([dict(
        type="Feature", properties=dict(kind="inreach", points=len(pts)),
        geometry=dict(type="LineString",
                      coordinates=_round([(lo, la) for _, la, lo in pts])))])


def public_camera(cam):
    """The camera as the site is allowed to name it.

    Serial numbers group a camera during the build, and only the Canon, the two
    GoPros and the drone have one — but "no serial numbers on anything published"
    is a rule about the whole artefact, not only about EXIF. Stripping the tags
    out of 2,505 JPEGs and then printing the serial under every one of them in
    the viewer would have honoured the letter of it and missed the point.
    """
    return cam.split("#")[0].strip() if cam else cam


def photos_json(placed):
    """Every photograph, with what is known about it and how well.

    Media paths follow from the id by convention. They do not exist until
    derive.py runs in milestone 5; the format is fixed now so the site can be
    built and checked against real positions before 900 MB is generated.
    """
    out = []
    for r in placed:
        rec = dict(id=r["id"], tier=r["tier"], camera=public_camera(r["camera"]),
                   utc=r["utc"], day=r["day"], note=r["note"],
                   thumb=f"media/thumb/{r['id']}.jpg",
                   view=f"media/view/{r['id']}.jpg")
        if r["lat"] is not None and r["tier"] != "travel":
            rec["lat"] = round(r["lat"], PRECISION)
            rec["lon"] = round(r["lon"], PRECISION)
            rec["uncertainty_m"] = r["uncertainty_m"]
        if r.get("day_provisional"):
            rec["day_provisional"] = True
        out.append(rec)
    # Time order, so the viewer's previous/next follows the day as it happened
    # rather than wandering by proximity. Photographs with no time go last.
    out.sort(key=lambda r: (r["utc"] is None, r["utc"] or "", r["id"]))
    return out


def export(dest, placed):
    os.makedirs(dest, exist_ok=True)
    # The map's own, wider coastline: the chart can be panned and zoomed past the
    # printed sheet's edge, and the poster's cache ends in a straight line at lon
    # -77.35 with nothing at all north of 26.83. Verified to classify land
    # identically inside EXTENT — 0.000 km2 of disagreement — so this is more
    # coastline, not different coastline.
    land = land_polygons(MAP_LAND_BBOX, source=COASTLINE_MAP)
    files = chart_layers(land)
    files["tracks.geojson"] = track_layer()
    files["places.geojson"] = places_layer()
    inr = inreach_layer()
    if inr:
        files["inreach.geojson"] = inr
    files["photos.json"] = photos_json(placed)
    files["meta.json"] = dict(
        extent=list(EXTENT), view_bounds=list(VIEW_BOUNDS),
        bands=[dict(name=b["name"], maxzoom=b["maxzoom"]) for b in BANDS],
        days=[dict(label=d["label"], color=d["color"], title=d["title"],
                   route=d["route"], n=d.get("n"), sail=bool(d.get("sail")))
              for d in DAYS],
        tiers=sorted({r["tier"] for r in placed}),
        counts=dict(collections.Counter(r["tier"] for r in placed)))

    written = {}
    for name, payload in files.items():
        path = os.path.join(dest, name)
        with open(path, "w") as fh:
            json.dump(payload, fh, separators=(",", ":"))
        written[name] = os.path.getsize(path)
    return written


def report(written, placed):
    print(f"\n{len(written)} files, {sum(written.values()) / 1024:.0f} KB total")
    for name, size in sorted(written.items(), key=lambda kv: -kv[1]):
        print(f"  {size / 1024:8.1f} KB  {name}")
    first = sum(v for k, v in written.items()
                if "coarse" in k or k in ("tracks.geojson", "places.geojson",
                                          "photos.json", "meta.json"))
    print(f"\n  what a phone fetches before the first pixel: "
          f"{first / 1024:.0f} KB (coarse band + tracks + places + photographs)")
    print(f"  the fine band adds "
          f"{sum(v for k, v in written.items() if 'fine' in k) / 1024:.0f} KB, "
          f"loaded only when zoomed in")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--index", default=os.path.join(HERE, "out", "photo_index.json"))
    ap.add_argument("--dest", default=os.path.join(HERE, "site_build", "data"))
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.index):
        raise SystemExit(f"no index at {a.index} — run python -m map.photo_index first")
    photos = json.load(open(a.index))
    per_photo, cameras, _ = C.fit(photos)
    placed = P.place(photos, per_photo, cameras)
    written = export(a.dest, placed)
    print(f"wrote {len(written)} files to {a.dest}")
    if a.report:
        report(written, placed)


if __name__ == "__main__":
    main()
