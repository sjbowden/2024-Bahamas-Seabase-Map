#!/usr/bin/env python3
"""Turn a UTC instant into a position on the chart, and say how sure we are.

    python -m map.place --report

Four ways a photograph gets a position, and every one of them is recorded on the
photograph so the viewer can make a different claim for each:

  gps        the camera wrote its own coordinates. Believe them over the track.
  bracket    no coordinates, but two of *this camera's* located photographs sit
             within two minutes either side and 200 m apart. Interpolate those.
  track      interpolate the boat's own fixes at the photograph's UTC. Tier
             `calibrated` when the UTC came from satellites or a timezone tag,
             `inferred` when it came from a fitted offset.
  unplaced   no UTC, or a UTC in a hole where the receiver was not recording.

Uncertainty is measured, not assumed. A photograph's timing is uncertain by its
camera's fit width — under 30 s for the Canon, +/-20.5 min for the GoPro — and
the honest way to turn that into metres is to ask where the boat actually was
across that window, rather than multiplying by an assumed speed. Which means a
GoPro frame taken while the boat lay at anchor is precise despite a twenty-minute
timing error, and one taken under sail is not. Same camera, same fit, different
answers, and the difference is real.
"""
import argparse
import bisect
import collections
import json
import os
from datetime import datetime, timedelta, timezone

from trip import (ANCHORAGES, DAYS, MOVING_KN, PLACES, haversine, in_chart,
                  read_fixes)
from map import clock_fit as C

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UTC = timezone.utc

# Bracketing fixes further apart than this are not a track, they are two facts
# with a hole between them. Matches the gap that breaks a coverage span.
MAX_GAP_S = 120.0

# The `bracket` tier's reach.
BRACKET_GAP_S = 120.0
BRACKET_SPAN_M = 200.0

# Sailing days. A photograph resolved to a UTC outside every receiver window is
# `unplaced` if it falls in this range — the receiver was merely off — and
# `travel` if it falls outside, because then the crew was not in Abaco at all.
SAIL_LO = datetime(2024, 3, 22, tzinfo=UTC)
SAIL_HI = datetime(2024, 3, 29, tzinfo=UTC)


def _day_by_date():
    """{date in EDT: day label} — the log stems carry the date they cover."""
    out = {}
    for d in DAYS:
        stem = d["file"].split("_")[1]                  # GPS_20240322_163426
        out[datetime.strptime(stem, "%Y%m%d").date()] = d["label"]
    return out


DAY_BY_DATE = _day_by_date()


def day_for(utc=None, local=None):
    """Which sailing day a photograph belongs to, and whether we are guessing.

    The receiver stopped each evening, so a photograph taken ashore at 21:00 has
    no track to name its day — but the calendar does, and grouping the tray by
    day is the reason the field exists. Where there is no trusted UTC either, the
    camera's own date is used and flagged, because a clock wrong by under 12 h
    still usually names the right day.
    """
    if utc is not None:
        return DAY_BY_DATE.get((utc - timedelta(hours=4)).date()), False
    if local is not None:
        return DAY_BY_DATE.get(local.date()), True
    return None, False


def track():
    """Every fix from every day, one time-ordered stream, at full cadence."""
    fixes = []
    for d in DAYS:
        day, _ = read_fixes(d["file"])
        fixes += [(t, lat, lon, sog, d["label"]) for t, lat, lon, sog in day]
    fixes.sort(key=lambda f: f[0])
    return fixes


def at(fixes, times, t):
    """Interpolate the track at one instant. Returns (lat, lon, sog, day) or None.

    Between the bracketing fixes, not the nearest one: at 5 kn the nearest fix is
    needlessly ~10 m out, and interpolation costs a subtraction.
    """
    i = bisect.bisect_left(times, t)
    if i == 0:
        return None if t < times[0] else (fixes[0][1], fixes[0][2], fixes[0][3], fixes[0][4])
    if i >= len(times):
        return None
    a, b = fixes[i - 1], fixes[i]
    span = (b[0] - a[0]).total_seconds()
    if span > MAX_GAP_S:
        return None
    f = 0.0 if span == 0 else (t - a[0]).total_seconds() / span
    return (a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f,
            a[3] + (b[3] - a[3]) * f, a[4])


def spread_m(fixes, times, t, half_window_s):
    """How far the boat moved across a photograph's timing uncertainty.

    This is the uncertainty, in metres, and it is a property of the boat's
    behaviour rather than of the clock: sample the track at t and at both ends of
    the window, and take the largest distance from the middle. Anchored, that is
    a few metres however wide the window; under sail it is the real cost.
    """
    mid = at(fixes, times, t)
    if mid is None:
        return None
    if half_window_s <= 0:
        return 0.0
    worst = 0.0
    for d in (-half_window_s, half_window_s):
        end = at(fixes, times, t + timedelta(seconds=d))
        if end is None:
            # The window runs off the end of the day's recording; the honest
            # reading is that we cannot bound it, so say so with the window.
            return None
        worst = max(worst, haversine(mid[0], mid[1], end[0], end[1]))
    return worst


def nearest_named(lat, lon, limit_m=4000.0):
    """The nearest anchorage or settlement worth naming, or None."""
    named = [(la, lo, txt) for lo, la, txt, *_ in ANCHORAGES] + \
            [(la, lo, txt.replace("\n", " ").strip())
             for lo, la, txt, kind, *_ in PLACES if kind in ("town", "isle")]
    best, best_d = None, limit_m
    for la, lo, txt in named:
        d = haversine(lat, lon, la, lo)
        if d < best_d:
            best, best_d = txt, d
    return (best, round(best_d)) if best else None


def place(photos, per_photo, cameras, fixes=None):
    """Give every photograph a tier, a position where it has one, and a note."""
    fixes = fixes or track()
    times = [f[0] for f in fixes]

    # Timing uncertainty per camera: half the fit's peak width, or a couple of
    # seconds where the UTC came from satellites or a tag.
    half = {}
    for cam, r in cameras.items():
        f = r.get("fit") or {}
        half[cam] = (f.get("peak_width_s", 0.0) or C.COARSE_S) / 2.0 \
            if f.get("accepted") else 2.0

    by_cam_anchors = collections.defaultdict(list)
    for p in photos:
        if p.get("gps") and p.get("time_local"):
            by_cam_anchors[p["camera"]].append(p)
    for v in by_cam_anchors.values():
        v.sort(key=lambda p: p["time_local"])

    out = []
    for p in photos:
        v = per_photo[p["id"]]
        rec = dict(id=p["id"], name=p["name"], camera=p["camera"],
                   utc=v["utc"], time_method=v["method"], tier=None,
                   lat=None, lon=None, uncertainty_m=None, day=None, note=None)

        # 1. its own coordinates, which beat the track by definition
        if p.get("gps"):
            lat, lon = p["gps"]
            rec.update(lat=lat, lon=lon, uncertainty_m=15,
                       tier="gps" if in_chart(lat, lon) else "travel")
            rec["note"] = ("the camera recorded this position"
                           if rec["tier"] == "gps"
                           else "taken away from Abaco — not on this chart")
            out.append(_finish(rec, p))
            continue

        # 2. between two of its own camera's located photographs
        b = _bracket(p, by_cam_anchors.get(p["camera"], []))
        if b:
            (lat, lon), gap_s, span_m = b
            # The same region guard the `gps` branch applies, and it matters:
            # every photograph this tier reaches in this dataset turns out to be
            # in Portland. Without the check they would plot on the Sea of Abaco
            # at latitude 45.
            rec.update(lat=lat, lon=lon,
                       tier="bracket" if in_chart(lat, lon) else "travel",
                       uncertainty_m=round(span_m / 2.0),
                       note=(f"between two of this camera's own located "
                             f"photographs, {gap_s:.0f} s apart"
                             if in_chart(lat, lon)
                             else "taken away from Abaco — not on this chart"))
            out.append(_finish(rec, p))
            continue

        # 3. the boat's track at this photograph's UTC
        if not v["utc"]:
            rec.update(tier="unplaced", note="no timestamp this build could trust")
            out.append(rec)
            continue
        t = C._utc(v["utc"])
        pos = at(fixes, times, t)
        if pos is None:
            travel = not (SAIL_LO <= t <= SAIL_HI)
            rec.update(tier="travel" if travel else "unplaced",
                       note=("taken away from Abaco — not on this chart" if travel
                             else "the receiver was not recording at this moment"))
            out.append(rec)
            continue
        lat, lon, sog, day = pos
        u = spread_m(fixes, times, t, half.get(p["camera"], 2.0))
        rec.update(lat=lat, lon=lon, day=day or day_for(t)[0],
                   tier="calibrated" if v["method"] in ("gps_utc", "tz_tag")
                   else "inferred",
                   uncertainty_m=None if u is None else round(u))
        rec["note"] = _track_note(t, sog, lat, lon, u)
        out.append(rec)
    return out


def _bracket(p, anchors):
    """(position, gap_s, span_m) if this photograph sits between two anchors."""
    if not p.get("time_local") or len(anchors) < 2:
        return None
    t = C._local(p["time_local"])
    ts = [C._local(a["time_local"]) for a in anchors]
    i = bisect.bisect_left(ts, t)
    if i == 0 or i >= len(ts):
        return None
    a, b = anchors[i - 1], anchors[i]
    ta, tb = ts[i - 1], ts[i]
    if (t - ta).total_seconds() > BRACKET_GAP_S or (tb - t).total_seconds() > BRACKET_GAP_S:
        return None
    span = haversine(a["gps"][0], a["gps"][1], b["gps"][0], b["gps"][1])
    if span > BRACKET_SPAN_M:
        return None
    total = (tb - ta).total_seconds()
    f = 0.0 if total == 0 else (t - ta).total_seconds() / total
    return ((a["gps"][0] + (b["gps"][0] - a["gps"][0]) * f,
             a["gps"][1] + (b["gps"][1] - a["gps"][1]) * f),
            (tb - ta).total_seconds(), span)


def _track_note(t, sog, lat, lon, u):
    """What the viewer says about a photograph placed from the boat."""
    local = (t - timedelta(hours=4)).strftime("%H:%M")
    anchored = sog is not None and sog <= MOVING_KN
    near = nearest_named(lat, lon)
    if anchored and near:
        where = f"at anchor off {near[0]}"
    elif anchored:
        where = "at anchor"
    else:
        where = "under way"
    note = f"placed from the boat's track at {local} EDT, {where}"
    if u is None:
        note += " — the timing cannot be bounded here"
    elif u > 400:
        note += f" — the boat was moving, so this is only good to ~{round(u / 100) * 100:.0f} m"
    else:
        note += " — may have been taken nearby ashore"
    return note


def _finish(rec, photo):
    """Attach the sailing day to a photograph placed without the track."""
    if not rec["day"]:
        local = C._local(photo["time_local"]) if photo.get("time_local") else None
        day, provisional = day_for(C._utc(rec["utc"]) if rec["utc"] else None,
                                  local)
        rec["day"] = day
        if provisional and day:
            rec["day_provisional"] = True
    return rec


# ------------------------------------------------------------------ report ---
def report(placed):
    print(f"\n{len(placed)} photographs placed")
    tiers = collections.Counter(r["tier"] for r in placed)
    for k, n in tiers.most_common():
        print(f"  {k:12} {n:5}")
    onchart = [r for r in placed if r["lat"] is not None and r["tier"] != "travel"]
    print(f"\n{len(onchart)} land on the Abaco chart")

    print("\nuncertainty, for those placed from the boat's track")
    fromtrack = [r for r in onchart if r["tier"] in ("calibrated", "inferred")]
    known = sorted(r["uncertainty_m"] for r in fromtrack if r["uncertainty_m"] is not None)
    if known:
        print(f"  median {known[len(known) // 2]} m, "
              f"90th {known[int(len(known) * 0.9)]} m, worst {known[-1]} m")
    print(f"  {sum(1 for r in fromtrack if r['uncertainty_m'] is None)} could not be bounded")

    print("\n  by camera — the same fit width costs different metres:")
    by = collections.defaultdict(list)
    for r in fromtrack:
        if r["uncertainty_m"] is not None:
            by[r["camera"]].append(r["uncertainty_m"])
    for cam, us in sorted(by.items(), key=lambda kv: -len(kv[1])):
        us.sort()
        print(f"    {cam[:30]:30} {len(us):5}  median {us[len(us) // 2]:5} m  "
              f"90th {us[int(len(us) * 0.9)]:6} m  worst {us[-1]:6} m")

    print("\n  by day:")
    for d in DAYS:
        n = sum(1 for r in onchart if r["day"] == d["label"])
        if n:
            print(f"    {d['label']:12} {n:5}")

    print("\nsample notes")
    seen = set()
    for r in placed:
        if r["tier"] in seen or not r["note"]:
            continue
        seen.add(r["tier"])
        print(f"  [{r['tier']}] {r['note']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--index", default=os.path.join(HERE, "out", "photo_index.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "out", "placed.json"))
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.index):
        raise SystemExit(f"no index at {a.index} — run python -m map.photo_index first")
    photos = json.load(open(a.index))
    per_photo, cameras, _ = C.fit(photos)
    placed = place(photos, per_photo, cameras)
    with open(a.out, "w") as fh:
        json.dump(placed, fh, indent=1)
    print(f"wrote {a.out} — {len(placed)} photographs")
    if a.report:
        report(placed)


if __name__ == "__main__":
    main()
