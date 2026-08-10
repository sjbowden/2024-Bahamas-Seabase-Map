#!/usr/bin/env python3
"""Tests for the map build. No pytest — this repo has no test dependency and
verification here has always been "run it and compare".

    python -m map.tests

The two that matter are the ones the design named. Both work by taking a camera
whose true UTC is known independently, throwing that knowledge away, and asking
the fitter to find it again:

  synthetic offset   inject a known clock error, confirm it comes back
  anchor starvation  hide a camera's GPS and timezone tag entirely, forcing it
                     down the correlation path, and check the offset it recovers
                     is the one its own satellites already agreed on

The second is the only test that exercises `correlate`, which is the method
shipping positions nobody can otherwise check.
"""
import collections
import json
import os
import sys
from datetime import datetime, timedelta

from shapely.validation import explain_validity

from abaco_geo import land_polygons
from trip import LAND_BBOX, haversine, in_chart
from map import clock_fit as C
from map import export as E
from map import place as P
from map.photo_index import _stamp, camera_key

INDEX = os.path.join(C.HERE, "out", "photo_index.json")

_pass, _fail, _skip = 0, [], 0


def check(name, ok, detail=""):
    global _pass
    if ok:
        _pass += 1
        print(f"  PASS  {name}" + (f"  ({detail})" if detail else ""))
    else:
        _fail.append(name)
        print(f"  FAIL  {name}  {detail}")


def near(name, got, want, tol, unit="s"):
    check(name, abs(got - want) <= tol,
          f"got {got:+.2f}{unit}, want {want:+.2f}{unit} +/-{tol}{unit}")


def section(t):
    print(f"\n{t}\n{'-' * len(t)}")


# ------------------------------------------------------------ unit, no data ---
def test_units():
    section("units")
    check("tz '-04:00' parses", C._tz_minutes("-04:00") == -240)
    check("tz '+05:30' parses", C._tz_minutes("+05:30") == 330)
    check("tz junk rejected", C._tz_minutes("Z") is None and C._tz_minutes(None) is None)
    check("unset clock rejected", _stamp("0000:00:00 00:00:00") is None)
    check("real stamp kept", _stamp("2024:03:25 17:46:47") == "2024:03:25 17:46:47")
    # Canon writes "Canon" into both Make and Model; the key says it once.
    check("camera key uses serial and de-stutters the make",
          camera_key(dict(make="Canon", model="Canon EOS REBEL T3i", serial="42"))
          == "Canon EOS REBEL T3i #42",
          camera_key(dict(make="Canon", model="Canon EOS REBEL T3i", serial="42")))
    check("camera key without serial",
          camera_key(dict(make="Apple", model="iPhone 15 Pro")) == "Apple iPhone 15 Pro")
    check("camera key with nothing", camera_key({}) == "unknown")


def test_coverage():
    section("receiver coverage")
    spans = C.coverage()
    check("spans are sorted and disjoint",
          all(spans[i][1] <= spans[i + 1][0] for i in range(len(spans) - 1)))
    check("every span is forward in time", all(a <= b for a, b in spans))
    hours = sum((b - a).total_seconds() for a, b in spans) / 3600.0
    check("total coverage is a plausible week of sailing", 50 < hours < 80,
          f"{hours:.1f} h across {len(spans)} spans")
    # The 28-minute hole on arrival day must be a hole, not a bridged line.
    day1 = [s for s in spans if s[0].strftime("%d") == "22"]
    check("arrival day is broken at its gap", len(day1) >= 2,
          f"{len(day1)} spans on 22 Mar")
    inside = C.covered(spans[0][0] + timedelta(seconds=1), spans)
    outside = C.covered(spans[0][0] - timedelta(hours=5), spans)
    check("covered() answers both ways", inside and not outside)
    return spans


# ------------------------------------------------------- the two real tests ---
def _known(photos):
    """{camera: [utc, ...]} for photographs whose UTC needs no fit."""
    direct, _ = C.direct_utc(photos)
    by_cam = collections.defaultdict(list)
    for p in photos:
        if p["id"] in direct:
            by_cam[p["camera"]].append(direct[p["id"]][0])
    return direct, by_cam


def test_synthetic(photos, spans):
    section("synthetic offsets — inject a known clock error, get it back")
    direct, by_cam = _known(photos)
    target = "Apple iPhone 14 Pro"          # 391, all by tz tag, none by GPS
    ids = {p["id"] for p in photos if p["camera"] == target}
    truth = sorted(by_cam[target])
    ref = [t for pid, (t, _) in direct.items() if pid not in ids]
    check(f"{target} has enough truth to test with", len(truth) > 100,
          f"{len(truth)} photographs")

    for shift_min in (-180.0, -7.0, 0.0, 23.5, 419.0):
        local = [t + timedelta(minutes=shift_min) for t in truth]
        fit = C.correlate_offset(local, ref, spans)
        # local = utc + shift, so the offset that recovers utc is -shift
        near(f"recovers {shift_min:+.1f} min", fit["offset_s"] / 60.0, -shift_min,
             0.5, "m")
        check(f"  and accepts it ({shift_min:+.1f})", fit["accepted"],
              f"tier={fit['tier']} z={fit['z']} cov={fit['coverage']}")


def test_anchor_starvation(photos, spans):
    section("anchor starvation — hide a camera's GPS and tz tag entirely")
    # The iPhone 15 Pro knows its own UTC from the satellites 480 times over.
    # Take that away and it has to be fitted like the Canon; the answer is
    # already known, which is the only reason this test can exist.
    target = "Apple iPhone 15 Pro"
    kept = [p for p in photos if p["camera"] == target
            and p.get("gps_utc") and p.get("tz_offset") == "-04:00"]
    check(f"{target} has Abaco-week photographs with satellite UTC", len(kept) > 200,
          f"{len(kept)} at -04:00")

    # Only the -04:00 photographs: this camera's tag moves with the journey, so
    # a single offset is only meaningful inside one leg of it.
    truth = [C._utc(p["gps_utc"]) for p in kept]
    local = [C._local(p["time_local"]) for p in kept]
    implied = sorted((l - t).total_seconds() / 60.0 for l, t in zip(local, truth))
    med = implied[len(implied) // 2]
    near("its own satellites say the clock reads EDT", med, -240.0, 1.0, "m")

    starved = [p for p in photos if p["camera"] != target]
    direct, _ = C.direct_utc(starved)
    ref = [t for t, _ in direct.values()]
    check("reference survives losing the target camera", len(ref) > 500,
          f"{len(ref)} known instants from other cameras")

    fit = C.correlate_offset(local, ref, spans)
    near("correlation recovers the same offset", fit["offset_s"] / 60.0, -med, 1.0, "m")
    check("and it clears the bar", fit["accepted"],
          f"tier={fit['tier']} z={fit['z']} coincidences={fit['coincidences']}/{fit['n']}")
    check("peak is tightly localised", fit["peak_width_s"] <= 300,
          f"{fit['peak_width_s']}s")


def test_refusal(photos, spans):
    section("the refusal rule — nonsense must be refused, not fitted")
    direct, by_cam = _known(photos)
    ref = [t for t, _ in direct.values()]
    # Times scattered at random through the week belong to no camera and must
    # not produce a confident offset.
    base = min(ref)
    scattered = [base + timedelta(seconds=(i * 7919) % (7 * 86400))
                 for i in range(200)]
    fit = C.correlate_offset(scattered, ref, spans)
    check("scattered times are refused", not fit["accepted"],
          f"tier={fit['tier']}, {fit.get('reason')}")
    thin = C.correlate_offset([base], ref[:5], spans)
    check("too little to correlate is refused", not thin["accepted"], thin.get("reason"))


def test_invariants(photos, spans):
    section("invariants")
    per_photo, cameras, _ = C.fit(photos)
    check("every photograph has exactly one verdict", len(per_photo) == len(photos),
          f"{len(per_photo)} verdicts for {len(photos)} photographs")
    methods = {v["method"] for v in per_photo.values()}
    allowed = {None, "gps_utc", "tz_tag", "correlate/calibrated", "correlate/inferred"}
    check("no unexpected method names", methods <= allowed, str(methods - allowed))
    bad = [k for k, v in per_photo.items() if v["utc"] and not v["method"]]
    check("a time always comes with the method that found it", not bad, str(bad[:3]))
    for k, v in per_photo.items():
        if v["utc"]:
            datetime.strptime(v["utc"], "%Y-%m-%dT%H:%M:%SZ")
    check("every resolved time parses as UTC", True)
    resolved = sum(1 for v in per_photo.values() if v["utc"])
    check("most photographs resolve", resolved > 0.9 * len(photos),
          f"{resolved}/{len(photos)}")
    # A camera is either resolved directly, fitted, or explicitly not attempted.
    for cam, r in cameras.items():
        if r["needing_fit"] and not r.get("skipped_fit"):
            check(f"{cam[:28]} records its fit", "fit" in r)
    gps_only = [c for c, r in cameras.items()
                if r.get("skipped_fit", "").startswith("every photograph")]
    check("a camera that never needs the track is not fitted", gps_only,
          f"{gps_only}")


def test_interpolation():
    section("track interpolation")
    fixes = P.track()
    times = [f[0] for f in fixes]
    check("the whole week is one sorted stream", times == sorted(times),
          f"{len(fixes)} fixes")

    # A midpoint between two adjacent fixes must land between them, not on one.
    i = next(j for j in range(1, len(fixes))
             if 1.0 <= (fixes[j][0] - fixes[j - 1][0]).total_seconds() <= 20.0
             and haversine(fixes[j - 1][1], fixes[j - 1][2],
                           fixes[j][1], fixes[j][2]) > 10.0)
    a, b = fixes[i - 1], fixes[i]
    mid = a[0] + (b[0] - a[0]) / 2
    got = P.at(fixes, times, mid)
    da = haversine(got[0], got[1], a[1], a[2])
    db = haversine(got[0], got[1], b[1], b[2])
    gap = haversine(a[1], a[2], b[1], b[2])
    check("a midpoint interpolates between the bracketing fixes",
          da > 0.5 and db > 0.5 and abs(da - db) < gap * 0.25,
          f"{da:.1f} m from one, {db:.1f} m from the other, {gap:.1f} m apart")

    # Overnight, there is nothing to interpolate and it must say so.
    biggest = max(range(1, len(fixes)),
                  key=lambda j: (fixes[j][0] - fixes[j - 1][0]).total_seconds())
    hole = fixes[biggest - 1][0] + (fixes[biggest][0] - fixes[biggest - 1][0]) / 2
    check("a time in a hole gets no position", P.at(fixes, times, hole) is None,
          f"{(fixes[biggest][0] - fixes[biggest - 1][0]).total_seconds() / 3600:.1f} h hole")
    check("before the first fix gets no position",
          P.at(fixes, times, times[0] - timedelta(hours=1)) is None)
    check("after the last fix gets no position",
          P.at(fixes, times, times[-1] + timedelta(hours=1)) is None)


def test_uncertainty():
    section("uncertainty is the boat's behaviour, not the clock's")
    fixes = P.track()
    times = [f[0] for f in fixes]
    # The same wide timing window costs almost nothing at anchor and real
    # distance under way. This is the whole argument for measuring it.
    anchored = [f for f in fixes if f[3] is not None and f[3] <= 0.2]
    moving = [f for f in fixes if f[3] is not None and f[3] >= 4.0]
    check("the week has both anchored and sailing moments", anchored and moving,
          f"{len(anchored)} anchored fixes, {len(moving)} at 4 kn or more")
    wide = 600.0
    at_anchor = [P.spread_m(fixes, times, f[0], wide) for f in anchored[::200]]
    at_sail = [P.spread_m(fixes, times, f[0], wide) for f in moving[::200]]
    at_anchor = [x for x in at_anchor if x is not None]
    at_sail = [x for x in at_sail if x is not None]
    ma = sorted(at_anchor)[len(at_anchor) // 2]
    ms = sorted(at_sail)[len(at_sail) // 2]
    check("a 10 min window costs little at anchor", ma < 200, f"median {ma:.0f} m")
    check("and a lot under way", ms > 500, f"median {ms:.0f} m")
    check("anchored is markedly better than sailing", ms > ma * 3,
          f"{ms:.0f} m against {ma:.0f} m")
    check("a zero window costs nothing",
          P.spread_m(fixes, times, moving[0][0], 0.0) == 0.0)


def test_placement(photos, spans):
    section("placement")
    per_photo, cameras, _ = C.fit(photos)
    placed = P.place(photos, per_photo, cameras)
    check("one record per photograph", len(placed) == len(photos))
    tiers = collections.Counter(r["tier"] for r in placed)
    known = {"gps", "calibrated", "inferred", "travel", "unplaced"}
    check("no tier outside the design's ladder", set(tiers) <= known,
          str(set(tiers) - known))
    check("the tiers partition the set", sum(tiers.values()) == len(placed))
    check("nothing is placed from the bracket tier any more",
          "bracket" not in tiers,
          "it reached six photographs, all in Portland; clock_fit still measures it")

    plotted = [r for r in placed
               if r["tier"] in ("gps", "calibrated", "inferred")]
    off = [r for r in plotted if r["lat"] is None or not in_chart(r["lat"], r["lon"])]
    check("everything plotted is on the Abaco chart", not off,
          f"{len(off)} off it, e.g. {off[0]['name'] if off else '-'} "
          f"{(off[0]['lat'], off[0]['lon']) if off else ''}")
    check("everything plotted has a position",
          all(r["lat"] is not None and r["lon"] is not None for r in plotted))
    check("everything plotted has a sailing day",
          all(r["day"] for r in plotted),
          f"{sum(1 for r in plotted if not r['day'])} without one")
    check("nothing off the chart keeps a position",
          all(r["lat"] is None or r["tier"] != "unplaced" for r in placed))
    check("every photograph has a note", all(r["note"] for r in placed))

    # A camera with a wider fit must not end up claiming more precision than one
    # with a narrow fit, taken across all its photographs.
    byc = collections.defaultdict(list)
    for r in plotted:
        if r["uncertainty_m"] is not None and r["tier"] in ("calibrated", "inferred"):
            byc[r["camera"]].append(r["uncertainty_m"])
    def p90(xs):
        xs = sorted(xs)
        return xs[int(len(xs) * 0.9)]
    gopro = next((c for c in byc if "HERO5" in c), None)
    phone = next((c for c in byc if "iPhone 14" in c), None)
    if gopro and phone:
        check("the GoPro's +/-20 min costs more than a phone's +/-2 s",
              p90(byc[gopro]) > p90(byc[phone]) * 10,
              f"90th: GoPro {p90(byc[gopro])} m, iPhone 14 Pro {p90(byc[phone])} m")
    return placed


def test_export(placed):
    section("export")
    from shapely.geometry import shape
    land = land_polygons(LAND_BBOX)
    for band in E.BANDS:
        rings = E._rings(land, band["tol"], band["min_area_m2"])
        geom = shape(dict(type="MultiPolygon", coordinates=rings))
        check(f"{band['name']} band is valid geometry", geom.is_valid,
              explain_validity(geom)[:70])
        check(f"{band['name']} band keeps the land's area",
              abs(geom.area - land.area) / land.area < 0.01,
              f"{geom.area / land.area * 100:.1f}% of source, "
              f"{len(geom.geoms)} of {len(land.geoms)} parts")
    coarse = shape(dict(type="MultiPolygon",
                        coordinates=E._rings(land, E.BANDS[0]["tol"],
                                             E.BANDS[0]["min_area_m2"])))
    fine = shape(dict(type="MultiPolygon",
                      coordinates=E._rings(land, E.BANDS[-1]["tol"],
                                           E.BANDS[-1]["min_area_m2"])))
    check("the coarse band is genuinely cheaper than the fine one",
          len(coarse.geoms) < len(fine.geoms) / 2,
          f"{len(coarse.geoms)} parts against {len(fine.geoms)}")

    pj = E.photos_json(placed)
    check("photos.json carries every photograph", len(pj) == len(placed))
    check("photos.json is in time order",
          [r["utc"] for r in pj if r["utc"]] == sorted(r["utc"] for r in pj if r["utc"]))
    check("no photograph off the chart carries coordinates",
          not [r for r in pj if r["tier"] in ("travel", "unplaced") and "lat" in r])
    check("coordinates are rounded to the output grid",
          all(len(str(r["lat"]).split(".")[-1]) <= E.PRECISION
              for r in pj if "lat" in r))
    check("every photograph names its media by convention",
          all(r["thumb"].endswith(".jpg") and r["id"] in r["thumb"] for r in pj))
    tracks = E.track_layer()
    check("tracks cover the sailing days",
          len({f["properties"]["day"] for f in tracks["features"]}) >= 6,
          f"{len(tracks['features'])} features")
    places = E.places_layer()
    check("places carry a label and a minzoom",
          all(f["properties"].get("label") and f["properties"].get("minzoom")
              for f in places["features"]),
          f"{len(places['features'])} places")


def test_nothing_published_carries_metadata(placed):
    section("what reaches the public folder")
    pj = E.photos_json(placed)
    leaks = [r for r in pj if "#" in (r.get("camera") or "")]
    check("no camera serial reaches photos.json", not leaks,
          f"{len(leaks)} records, e.g. {leaks[0]['camera'] if leaks else '-'}")
    check("serials do survive internally, for grouping",
          any("#" in (r["camera"] or "") for r in placed),
          "clock_fit still tells the Canon from a phone")
    fields = set().union(*(set(r) for r in pj))
    allowed = {"id", "tier", "camera", "utc", "day", "note", "thumb", "view",
               "lat", "lon", "uncertainty_m", "day_provisional"}
    check("photos.json carries no unexpected field", fields <= allowed,
          str(fields - allowed))

    # Derivatives, if they have been generated: EXIF must be gone and rotation
    # must have been baked in before it went.
    media = os.path.join(C.HERE, "site_build", "media")
    thumbs = os.path.join(media, "thumb")
    if not os.path.isdir(thumbs):
        print("  SKIP  derivatives not generated (python -m map.derive)")
        return
    from PIL import Image
    names = sorted(n for n in os.listdir(thumbs) if n.endswith(".jpg"))[:60]
    with_exif = []
    for n in names:
        im = Image.open(os.path.join(thumbs, n))
        if im.getexif() or im.info.get("icc_profile"):
            with_exif.append(n)
    check("no derivative carries EXIF or an ICC profile", not with_exif,
          f"checked {len(names)}, {len(with_exif)} carried metadata")
    portraits = 0
    for n in names:
        w, h = Image.open(os.path.join(thumbs, n)).size
        portraits += h > w
    check("portrait frames stayed portrait", portraits > 0,
          f"{portraits} of {len(names)} are taller than wide, so rotation was "
          f"baked in before the tags went")


def test_site_build():
    section("the built folder")
    out = os.path.join(C.HERE, "site_build")
    if not os.path.isdir(out):
        print("  SKIP  not built (python -m map.build)")
        return
    need = ["index.html", "app.js", "style.css", "robots.txt", "_headers",
            "vendor/maplibre-gl.js", "vendor/maplibre-gl.css",
            "data/meta.json", "data/photos.json", "data/tracks.geojson",
            "data/places.geojson"]
    missing = [n for n in need if not os.path.exists(os.path.join(out, n))]
    check("every file the page asks for is present", not missing, str(missing))

    app = open(os.path.join(out, "app.js")).read()
    meta = json.load(open(os.path.join(out, "data", "meta.json")))
    for band in meta["bands"]:
        check(f"app.js knows the {band['name']} band",
              f"'{band['name']}'" in app or f'"{band["name"]}"' in app)
        for kind in ("coast", "shoals"):
            f = os.path.join(out, "data", f"{kind}.{band['name']}.geojson")
            check(f"{kind}.{band['name']}.geojson exists", os.path.exists(f))
    html = open(os.path.join(out, "index.html")).read()
    check("the page tells robots to stay away", "noindex" in html)
    check("and so does the header file",
          "noindex" in open(os.path.join(out, "_headers")).read())
    check("nothing points at a CDN",
          "http://" not in app and "https://" not in app.replace(
              "https://github.com", "").replace("http://www.topografix.com", ""),
          "app.js must fetch only from this folder")


def main():
    test_units()
    spans = test_coverage()
    if not os.path.exists(INDEX):
        print(f"\nSKIP  the archive-backed tests: no {INDEX}")
        print("      run: python -m map.photo_index")
    else:
        photos = json.load(open(INDEX))
        test_synthetic(photos, spans)
        test_anchor_starvation(photos, spans)
        test_refusal(photos, spans)
        test_invariants(photos, spans)
        test_interpolation()
        test_uncertainty()
        placed = test_placement(photos, spans)
        test_export(placed)
        test_nothing_published_carries_metadata(placed)
    test_site_build()

    print(f"\n{_pass} passed, {len(_fail)} failed")
    if _fail:
        for f in _fail:
            print(f"  failed: {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
