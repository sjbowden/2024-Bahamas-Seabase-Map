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

from map import clock_fit as C
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

    print(f"\n{_pass} passed, {len(_fail)} failed")
    if _fail:
        for f in _fail:
            print(f"  failed: {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
