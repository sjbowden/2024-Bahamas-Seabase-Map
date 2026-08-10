#!/usr/bin/env python3
"""Work out what UTC instant each photograph was actually taken at.

    python -m map.clock_fit --report

Everything downstream needs one thing from a photograph's timestamp: the real
instant, in UTC, so it can be looked up against the boat's track. Getting there
takes three methods of decreasing strength, and the point of keeping them
separate is that each photograph carries the name of the one that placed it.

`gps_utc` — 490 photographs carry GPSDateStamp/GPSTimeStamp, which comes off the
satellites with the camera's clock playing no part. Nothing to fit.

`tz_tag` — 1,093 more carry OffsetTimeOriginal, so UTC is local minus that tag.
Measured against the photographs that have both, this is right to about a
second: the median of (local - tag - GPS UTC) is +0.017 min over 480 samples.
A camera's offset is therefore *not* a constant — the iPhone 15 Pro's tag reads
-07:00 in Portland, -04:00 all week in Abaco, and -07:00 again flying home. Any
model with one number per camera is wrong for the travel days.

`correlate` — 810 photographs come from three cameras with neither GPS nor a tz
tag: the Canon (547), the FinePix (149) and a GoPro (114). For these the whole
offset has to be fitted, and the design's original plan — score offsets by "what
fraction land near the track" — cannot work, because a camera with no GPS has no
position to measure. What these cameras do have is company: eleven cameras
photographed the same week and the crew all pointed them at the same things at
the same moments. So the statistic is a count of coincidences — how many of this
camera's frames land within 20 s of a frame whose UTC is already known — and the
offset that maximises it is the offset that makes the clock true. The null comes
free: the same count at every other candidate offset in the search. The Canon
reaches 176 of 547 against a null of 27.6 +/- 25.0, and a third of its frames
sitting within 20 s of somebody else's is not a coincidence about coincidences.

Two things the search needs, both learned the hard way:

The window is +/-12 h, because the crew's days look alike. Searched wider, an
offset a whole day out scores nearly as well as the truth, and the GoPro's best
peak across +/-26 h was -21.4 h — a lag no clock setting can produce.

The coverage floor is low, because photographs taken in the evenings ashore while
the receiver sat on its charger are real: hiding the iPhone 15 Pro's satellite
times and refitting recovers +240.03 min, right to two seconds, at a coverage of
0.844. A floor above that refuses a demonstrably correct answer. But it is a
floor and not a tiebreaker — 150 times scattered inside a single day score 30x
the chance rate with no rival at all, and coverage is the only thing that stops
them.

**One bar, not two.** There used to be a `calibrated` and an `inferred` grade
here, which read as though a well-fitted camera would be published differently
from a marginal one. It never was: place.py decides the published tier from the
*method* — satellites and timezone tags are `calibrated`, anything fitted is
`inferred` — so the grade affected nothing and only invited the reader to think a
distinction was being drawn. What actually distinguishes a good fit from a poor
one is `peak_width_s`, which place.py turns into metres per photograph against
the real track. The Canon's frames are `inferred` and mostly good to 8 m; the
GoPro's are `inferred` and run to 1.8 km. No grade could say that.

So there is one bar: accepted, or refused with a reason. `python -m map.tests` is
what keeps that honest, and the fits are sequential — each accepted camera joins
the reference the next one is measured against, largest and best-evidenced first.
"""
import argparse
import collections
import json
import os
from datetime import datetime, timedelta, timezone

import numpy as np

from trip import DAYS, read_fixes

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# How far a clock is allowed to be wrong. Timezones run UTC-12 to UTC+14, so a
# camera showing *some* real zone's wall time is inside this. Searching wider
# invites diurnal aliases: the crew's days look alike, so an offset 21 hours out
# scores nearly as well as the truth, and the GoPro's best peak across +/-26 h
# was -21.4 h — a lag no clock setting can produce.
SEARCH_H = 12.0
COARSE_S = 30.0                 # scan step; also the null distribution's grid
WINDOW_S = 20.0                 # "the same moment" — two crew shooting together
REFINE_S = 1.0
REFINE_SPAN_S = 120.0
SHOULDER_S = 1800.0             # within this of the winner is the same peak

# What the fit has to clear: one bar, three tests, and not a standard-deviation
# score among them. Calibrated against the fits that must pass (rate 5.6 to 10.0)
# and the inputs that must not (1.85).
#
#   rate      coincidences over what a random offset in the search finds. "This
#             offset lines up N times better than chance." Comparable between a
#             547-photograph camera and a 114-photograph one, which is exactly
#             what a z-score is not: z divides by the null's spread, the Canon's
#             spread is inflated to +/-25.0 by its own peak shoulder, and z
#             therefore ranked the Canon — 176 coincidences against 27.6
#             expected, peak sharp to under 30 s — *below* two weaker cameras.
#   coverage  a gate, not a tiebreaker, which took a degenerate input to settle:
#             150 times scattered inside a single day score rate 30 and an
#             unbounded margin, sailing through both other tests. Coverage 0.000
#             is the only thing that refuses them.
#   margin    the winner against the best genuinely different hypothesis, so a
#             rival offset that explains the data nearly as well is fatal.
#
# The coverage floor stays low on purpose. Photographs taken ashore in the
# evening, while the receiver sat on its charger, are real: hiding the iPhone 15
# Pro's satellite times and refitting recovers +240.03 min — right to two
# seconds — at a coverage of 0.844. A floor above that refuses a demonstrably
# correct answer, which is the opposite of the refusal rule's job.
ACCEPT = dict(rate=3.0, coverage=0.60, margin=1.10)

UTC = timezone.utc


def _local(s):
    return datetime.strptime(s, "%Y:%m:%d %H:%M:%S").replace(tzinfo=UTC)


def _utc(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _tz_minutes(s):
    """'-04:00' -> -240. Returns None for anything that isn't an offset."""
    try:
        sign = -1 if s[0] == "-" else 1
        h, m = s[1:].split(":")
        return sign * (int(h) * 60 + int(m))
    except (ValueError, IndexError, TypeError):
        return None


# --------------------------------------------------------------- coverage ---
def coverage(max_gap_s=120.0):
    """When the receiver was actually recording: a list of (start, end) UTC.

    Built from the full-cadence stream, not the plotted track, and broken at
    any gap longer than max_gap_s so the 28-minute hole on arrival day is a
    hole here too rather than being spanned by a straight line.
    """
    spans = []
    for d in DAYS:
        fixes, _ = read_fixes(d["file"])
        if not fixes:
            continue
        start = prev = fixes[0][0]
        for t, *_ in fixes[1:]:
            if (t - prev).total_seconds() > max_gap_s:
                spans.append((start, prev))
                start = t
            prev = t
        spans.append((start, prev))
    return sorted(spans)


def covered(t, spans):
    return any(a <= t <= b for a, b in spans)


# -------------------------------------------------------- direct methods ---
def direct_utc(photos):
    """UTC for every photograph that can say it without a fit.

    Returns {id: (utc, method)}. Also returns the per-camera clock error, the
    median of (local - tz tag - GPS UTC), which is the only thing a camera with
    both can tell us that the tag alone cannot.
    """
    err = collections.defaultdict(list)
    for p in photos:
        if p.get("gps_utc") and p.get("time_local") and p.get("tz_offset"):
            tz = _tz_minutes(p["tz_offset"])
            if tz is not None:
                delta = (_local(p["time_local"]) - timedelta(minutes=tz)
                         - _utc(p["gps_utc"])).total_seconds()
                err[p["camera"]].append(delta)
    clock_err = {}
    for cam, ds in err.items():
        ds.sort()
        clock_err[cam] = dict(median_s=round(ds[len(ds) // 2], 3), n=len(ds),
                              p90_abs_s=round(sorted(abs(d) for d in ds)[int(len(ds) * .9)], 3))

    out = {}
    for p in photos:
        if p.get("gps_utc"):
            out[p["id"]] = (_utc(p["gps_utc"]), "gps_utc")
            continue
        if p.get("time_local") and p.get("tz_offset"):
            tz = _tz_minutes(p["tz_offset"])
            if tz is not None:
                # Correct by the camera's measured clock error where we have one.
                # It is a second or so; carrying it costs nothing and means the
                # method is the same arithmetic for every camera.
                c = clock_err.get(p["camera"], {}).get("median_s", 0.0)
                out[p["id"]] = (_local(p["time_local"]) - timedelta(minutes=tz)
                                - timedelta(seconds=c), "tz_tag")
    return out, clock_err


# ------------------------------------------------------------ correlation ---
def _nearest_gap(shifted, ref):
    """For each shifted time, seconds to the closest reference instant."""
    i = np.clip(np.searchsorted(ref, shifted), 1, len(ref) - 1)
    return np.minimum(np.abs(shifted - ref[i - 1]),
                      np.abs(shifted - ref[np.minimum(i, len(ref) - 1)]))


def correlate_offset(local_times, reference_utc, spans, search_h=SEARCH_H):
    """Fit one camera's clock against the moments other cameras were shooting.

    Eleven cameras photographed one week and the crew pointed them at the same
    things, so the offset that makes this camera's frames coincide with everybody
    else's is the offset that makes its clock true. The statistic is a count of
    coincidences, and the null distribution comes free: the same count evaluated
    at every other candidate offset in the search.

    `offset_s` is what to add to this camera's local timestamps to get UTC.
    """
    if not local_times or len(reference_utc) < 20:
        return dict(accepted=False, reason="not enough to correlate")
    ref = np.array(sorted(t.timestamp() for t in reference_utc))
    cam = np.array([t.timestamp() for t in local_times])

    span = search_h * 3600.0
    grid = np.arange(-span, span + COARSE_S, COARSE_S)
    counts = np.array([int((_nearest_gap(cam + g, ref) < WINDOW_S).sum())
                       for g in grid])
    mu, sd = float(counts.mean()), float(counts.std()) or 1.0

    # Coverage matters as much as coincidence: an offset that scores well by
    # putting half the camera's photographs outside every window the receiver
    # was recording has not explained them, it has hidden them.
    def cov_frac(off):
        return sum(covered(datetime.fromtimestamp(t + off, UTC), spans)
                   for t in cam) / len(cam)

    order = np.argsort(counts)[::-1]
    best = int(order[0])
    coarse = float(grid[best])

    # Refine to the second. The coincidence count is a step function, so the
    # sub-window position comes from a smooth kernel over the same window.
    fine = np.arange(coarse - REFINE_SPAN_S, coarse + REFINE_SPAN_S + REFINE_S,
                     REFINE_S)
    kern = [float(np.exp(-(_nearest_gap(cam + g, ref) / WINDOW_S) ** 2).sum())
            for g in fine]
    offset = float(fine[int(np.argmax(kern))])

    hits = int((_nearest_gap(cam + offset, ref) < WINDOW_S).sum())
    coverage_frac = cov_frac(offset)

    # How well localised the winner is: the spread of nearby offsets scoring
    # within 10% of it. A broad peak is still a fit, but a photograph placed
    # from it is only as good as this number, and place.py should know.
    near = np.abs(grid - coarse) <= SHOULDER_S
    good = grid[near][counts[near] >= 0.9 * counts[best]]
    width = float(good.max() - good.min()) if good.size else 0.0
    rate = hits / mu if mu > 0 else float("inf")
    score = hits * coverage_frac

    # The best genuinely different hypothesis — not the winner's own shoulder,
    # which is broad because coincidence is.
    rival, rival_off = 0.0, None
    for i in order:
        if abs(float(grid[i]) - coarse) <= SHOULDER_S:
            continue
        rival, rival_off = float(counts[i]) * cov_frac(float(grid[i])), float(grid[i])
        break
    margin = score / rival if rival > 0 else float("inf")

    failed = []
    if rate < ACCEPT["rate"]:
        failed.append(f"rate {rate:.2f} < {ACCEPT['rate']}")
    if coverage_frac < ACCEPT["coverage"]:
        failed.append(f"coverage {coverage_frac:.2f} < {ACCEPT['coverage']}")
    if margin < ACCEPT["margin"]:
        failed.append(f"margin {margin:.2f} < {ACCEPT['margin']}")
    # No timezone on earth is more than 14 h from UTC, so an offset past that is
    # not a clock setting and will not be applied however well it scores.
    if abs(offset) > 12 * 3600.0:
        failed.append(f"offset {offset / 3600.0:+.1f} h is outside any timezone a "
                      f"clock could have been set to")
    accepted = not failed
    reason = None if accepted else "; ".join(failed)
    return dict(accepted=accepted, reason=reason,
                offset_s=offset, offset_min=round(offset / 60.0, 3),
                coincidences=hits, n=len(local_times),
                null_mean=round(mu, 1), null_sd=round(sd, 1),
                rate=(round(float(rate), 2) if rate != float("inf") else None),
                coverage=round(coverage_frac, 3), peak_width_s=round(width, 1),
                margin=(round(margin, 2) if margin != float("inf") else None),
                rival_min=(round(rival_off / 60.0, 2) if rival_off is not None else None))


# ------------------------------------------------------------- bracketing ---
def bracket_reach(photos, max_gap_s=120.0, max_span_m=200.0):
    """How many GPS-less photographs sit between two GPS ones of their own camera.

    This is the `bracket` tier's reach, and it is a measurement rather than a
    design choice — it depends entirely on which cameras happen to have partial
    GPS coverage. No clock offset is involved: a camera's own timestamps are
    self-consistent whatever they read.
    """
    from trip import haversine
    by_cam = collections.defaultdict(list)
    for p in photos:
        if p.get("time_local"):
            by_cam[p["camera"]].append(p)
    reach = collections.Counter()
    for cam, ps in by_cam.items():
        ps.sort(key=lambda p: p["time_local"])
        anchors = [(i, p) for i, p in enumerate(ps) if p.get("gps")]
        if len(anchors) < 2:
            continue
        for i, p in enumerate(ps):
            if p.get("gps"):
                continue
            before = [a for a in anchors if a[0] < i]
            after = [a for a in anchors if a[0] > i]
            if not before or not after:
                continue
            b, a = before[-1][1], after[0][1]
            tb, ta, tp = (_local(x["time_local"]) for x in (b, a, p))
            if (tp - tb).total_seconds() > max_gap_s or (ta - tp).total_seconds() > max_gap_s:
                continue
            if haversine(b["gps"][0], b["gps"][1], a["gps"][0], a["gps"][1]) > max_span_m:
                continue
            reach[cam] += 1
    return reach


# ------------------------------------------------------------------- main ---
def fit(photos):
    """Resolve UTC for every photograph. Returns (per_photo, cameras, spans)."""
    spans = coverage()
    direct, clock_err = direct_utc(photos)
    reference = [t for t, _ in direct.values()]

    by_cam = collections.defaultdict(list)
    for p in photos:
        by_cam[p["camera"]].append(p)

    cameras = {}
    for cam, ps in sorted(by_cam.items(), key=lambda kv: -len(kv[1])):
        known = [p for p in ps if p["id"] in direct]
        need = [p for p in ps if p["id"] not in direct and p.get("time_local")]
        rec = dict(photographs=len(ps), resolved_directly=len(known),
                   needing_fit=len(need), clock_error=clock_err.get(cam))
        if known:
            rec["method"] = "gps_utc" if any(p.get("gps_utc") for p in known) else "tz_tag"
        # A camera whose photographs all carry their own position needs no clock
        # to be placed — this is what the drone taught. Its time is still
        # unknown, which costs it only its slot in the viewer's ordering.
        if need and all(p.get("gps") for p in ps):
            rec["skipped_fit"] = "every photograph carries its own position"
            need = []
        # "unknown" is not a camera. It is 109 photographs with no make or model
        # — screenshots, re-saved messaging copies — from an unknown number of
        # devices, so one offset would be one answer to several questions.
        if need and cam == "unknown":
            rec["skipped_fit"] = "not one camera: no make or model to group by"
            need = []
        if need:
            # Reference excludes this camera: it has nothing to contribute, and
            # including a camera in its own reference would invite a false peak.
            ref = [t for pid, (t, _) in direct.items()
                   if pid not in {p["id"] for p in ps}]
            variants = {"as_indexed": [_local(p["time_local"]) for p in need]}
            if any(p.get("time_disagree") for p in need):
                # One camera's two archives disagree; fit both readings and let
                # the correlation say which copy had the corrected clock.
                def _other(p):
                    td = p.get("time_disagree") or {}
                    rival = [v for v in td.values() if v != p["time_local"]]
                    return _local(rival[0] if rival else p["time_local"])
                variants["other_archive"] = [_other(p) for p in need]
            # A wider search when there are rival readings, so a variant whose
            # optimum sits past +/-12 h is compared rather than truncated — then
            # refused on plausibility, which is the honest reason to reject it.
            wide = 20.0 if len(variants) > 1 else SEARCH_H
            fits = {k: correlate_offset(v, ref, spans, search_h=wide)
                    for k, v in variants.items()}
            best = max(fits, key=lambda k: (fits[k].get("accepted", False),
                                            fits[k].get("coincidences", 0)
                                            * fits[k].get("coverage", 0)))
            rec["fit"] = fits[best]
            rec["fit"]["variant"] = best
            if len(fits) > 1:
                rec["fit_variants"] = {
                    k: dict(rate=v.get("rate"), offset_min=v.get("offset_min"),
                            coincidences=v.get("coincidences"),
                            coverage=v.get("coverage"),
                            accepted=v.get("accepted"), reason=v.get("reason"))
                    for k, v in fits.items()}
            if fits[best].get("accepted"):
                rec["method"] = rec.get("method") or "correlate"
                off = timedelta(seconds=fits[best]["offset_s"])
                method = "correlate"
                for p in need:
                    direct[p["id"]] = (_local(p["time_local"]) + off, method)
        cameras[cam] = rec

    per_photo = {}
    for p in photos:
        t, method = direct.get(p["id"], (None, None))
        per_photo[p["id"]] = dict(
            utc=t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else None,
            method=method,
            in_coverage=bool(t and covered(t, spans)),
            has_gps=bool(p.get("gps")))
    return per_photo, cameras, spans


def report(photos, per_photo, cameras, spans):
    idx = {p["id"]: p for p in photos}
    print(f"\nreceiver coverage: {len(spans)} spans, "
          f"{sum((b - a).total_seconds() for a, b in spans) / 3600:.1f} h total")

    m = collections.Counter(v["method"] for v in per_photo.values())
    print("\nhow each photograph's UTC was resolved")
    for k, n in sorted(m.items(), key=lambda kv: (kv[0] is None, -kv[1])):
        print(f"  {str(k or 'unresolved'):22} {n:5}")
    print(f"  {'':22} {sum(m.values()):5}  total")

    print(f"\n{'camera':34} {'imgs':>5} {'direct':>6} {'fit':>5} {'method':>10} "
          f"{'offset':>11} {'coinc':>11} {'rate':>6} {'cov':>6} {'margin':>7}")
    for cam, r in sorted(cameras.items(), key=lambda kv: -kv[1]["photographs"]):
        f = r.get("fit") or {}
        off = f"{f['offset_min']:+.2f}m" if f.get("offset_min") is not None else "-"
        coinc = f"{f['coincidences']}/{f['n']}" if f.get("coincidences") is not None else "-"
        print(f"  {cam[:32]:32} {r['photographs']:5} {r['resolved_directly']:6} "
              f"{r['needing_fit']:5} {str(r.get('method') or '-'):>10} {off:>11} "
              f"{coinc:>11} {str(f.get('rate') or '-'):>6} "
              f"{str(f.get('coverage') or '-'):>6} {str(f.get('margin') or '-'):>7}")
        if r.get("skipped_fit"):
            print(f"  {'':32} no fit attempted: {r['skipped_fit']}")
        if f and not f.get("accepted"):
            print(f"  {'':32} REFUSED: {f.get('reason')}")
        elif f.get("accepted"):
            print(f"  {'':32} accepted: {f['coincidences']} of {f['n']} within "
                  f"{WINDOW_S:.0f}s of another camera's shot — {f['rate']}x what a "
                  f"random offset finds; best rival {f.get('rival_min')}m; peak "
                  f"localised to "
                  + (f"under {COARSE_S:.0f}s" if not f.get("peak_width_s")
                     else f"{f['peak_width_s'] / 60:.1f} min"))
        if r.get("fit_variants"):
            print(f"  {'':32} variants: {r['fit_variants']}")
        if r.get("clock_error"):
            c = r["clock_error"]
            print(f"  {'':32} clock error vs GPS UTC: median {c['median_s']:+.2f} s "
                  f"over {c['n']}, p90 |err| {c['p90_abs_s']:.2f} s")

    resolved = [v for v in per_photo.values() if v["utc"]]
    print(f"\n{len(resolved)} of {len(photos)} photographs have a UTC instant")
    print(f"  {sum(1 for v in resolved if v['in_coverage'])} land inside receiver coverage")
    print(f"  {sum(1 for v in resolved if not v['in_coverage'])} land outside it "
          f"(evenings ashore after the receiver died, and the travel days)")
    print(f"  {sum(1 for v in per_photo.values() if v['has_gps'])} carry their own "
          f"position and do not need the track at all")

    reach = bracket_reach(photos)
    print(f"\nbracket tier reach: {sum(reach.values())} photographs"
          + (f" — {dict(reach)}" if reach else ""))
    print("  (GPS-less photographs sitting between two GPS ones of their own camera,")
    print("   within 2 min and 200 m — the measurement milestone 2 owed the design)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--index", default=os.path.join(HERE, "out", "photo_index.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "out", "clock_fit.json"))
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()

    if not os.path.exists(a.index):
        raise SystemExit(f"no index at {a.index} — run python -m map.photo_index first")
    photos = json.load(open(a.index))
    per_photo, cameras, spans = fit(photos)
    with open(a.out, "w") as fh:
        json.dump(dict(photos=per_photo, cameras=cameras), fh, indent=1, default=str)
    print(f"wrote {a.out}")
    if a.report:
        report(photos, per_photo, cameras, spans)


if __name__ == "__main__":
    main()
