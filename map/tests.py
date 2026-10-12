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
import re
import sys
from datetime import datetime, timedelta

from shapely.validation import explain_validity

from abaco_geo import land_polygons
from trip import DAYS, MAP_LAND_BBOX, haversine, in_chart, read_fixes
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

    # at(): a fix is a recorded position at its own instant, wherever it sits in
    # the stream. The first fix after the receiver came back on used to be
    # refused, because the gap behind it was checked before the match.
    t0 = datetime(2024, 3, 25, 12, 0, tzinfo=C.UTC)
    two = [(t0, 26.50, -77.00, 0.0, "Mon 25 Mar"),
           (t0 + timedelta(hours=4), 26.60, -77.10, 0.0, "Mon 25 Mar")]
    when = [f[0] for f in two]
    hit = P.at(two, when, two[1][0])
    check("a fix answers for its own instant, even the first after a gap",
          hit is not None and abs(hit[0] - 26.60) < 1e-9, str(hit))
    check("but a moment inside the gap is still unknown",
          P.at(two, when, t0 + timedelta(hours=2)) is None)

    from map import photo_index as PI
    ok, dropped = PI.readable([dict(id="a"), dict(id="b", unreadable=True),
                               dict(id="c", unreadable=False)])
    check("an unreadable photograph is left off, and counted",
          [p["id"] for p in ok] == ["a", "c"] and dropped == 1)


def test_fit_uses_the_reading_that_won():
    """Two archives disagree about a camera's clock; the offset fitted to one
    reading must be added to that reading. It was being added to the indexed one
    whichever won. No camera in the real archives takes this branch, so the
    correlation is stubbed to make it win."""
    section("clock fit, alternate reading")
    photos = [dict(id=f"x{i:02d}", name=f"x{i}.jpg", camera="Test Cam",
                   time_local=f"2024:03:25 02:{i:02d}:00",
                   time_disagree=dict(mine=f"2024:03:25 02:{i:02d}:00",
                                      crew=f"2024:03:25 12:{i:02d}:00"))
              for i in range(3)]
    real = C.correlate_offset

    def stub(local_times, reference_utc, spans, search_h=C.SEARCH_H):
        won = local_times[0].hour == 12
        return dict(accepted=won, offset_s=4 * 3600.0, offset_min=240.0,
                    coincidences=10 if won else 1, coverage=1.0, rate=9.0,
                    peak_width_s=60.0, reason=None if won else "stubbed out")
    C.correlate_offset = stub
    try:
        per_photo, cameras, _ = C.fit(photos)
    finally:
        C.correlate_offset = real
    check("the other archive's reading wins the stubbed fit",
          cameras["Test Cam"]["fit"]["variant"] == "other_archive",
          str(cameras["Test Cam"].get("fit")))
    got = [per_photo[p["id"]]["utc"] for p in photos]
    check("and each UTC is that reading plus the offset",
          got == [f"2024-03-25T16:{i:02d}:00Z" for i in range(3)], str(got))


def test_honest_uncertainty():
    """Four ways a position or a fit was claimed more firmly than the evidence."""
    section("uncertainty that matches the evidence")
    import numpy as np
    from map import depth as DP

    # The rival a fit is measured against is the strongest by the fit's own score.
    far = C.SHOULDER_S * 10
    grid = np.array([0.0, far, 2 * far])
    counts = np.array([100.0, 90.0, 80.0])
    cover = {0.0: 0.60, far: 0.60, 2 * far: 1.00}
    score, off = C.strongest_rival([0, 1, 2], counts, grid, 0.0, lambda o: cover[o])
    check("a lower-count rival with full coverage is the one that counts",
          score == 80.0 and off == 2 * far, f"{score} at {off}")
    check("which turns an apparent margin of 1.11 into 0.75",
          round(60.0 / 54.0, 2) == 1.11 and round(60.0 / score, 2) == 0.75)

    # A ring has to hold everywhere the boat was inside the timing window.
    t0 = datetime(2024, 3, 25, 12, 0, tzinfo=C.UTC)
    out_and_back = []
    for k in range(-24, 25):                    # a fix every 5 s, 2 min either side
        away = 0.009 * (1 - abs(abs(k) - 6) / 6) if abs(k) <= 12 else 0.0
        out_and_back.append((t0 + timedelta(seconds=5 * k), 26.50 + away, -77.00,
                             5.0, "Mon 25 Mar"))
    when = [f[0] for f in out_and_back]
    ends = max(haversine(26.50, -77.00, f[1], f[2])
               for f in (out_and_back[12], out_and_back[36]))
    ring = P.spread_m(out_and_back, when, t0, 60)
    check("an out-and-back inside the window is inside the ring",
          ends < 1 and ring is not None and ring > 900,
          f"ends {ends:.0f} m from the middle, ring {ring}")
    holed = [f for f in out_and_back if not (0 < (f[0] - t0).total_seconds() < 300)]
    check("a hole in the recording inside the window leaves the ring unbounded",
          P.spread_m(holed, [f[0] for f in holed], t0, 600) is None)

    # In a gap, two still reports either side of the nominal time are not enough
    # when the clock is only known to twenty minutes.
    gap = [(t0 - timedelta(minutes=15), 26.510, -77.00, "handheld"),
           (t0 - timedelta(minutes=5), 26.500, -77.00, "handheld"),
           (t0 + timedelta(minutes=5), 26.500, -77.00, "handheld"),
           (t0 + timedelta(minutes=15), 26.510, -77.00, "handheld")]
    gt = [f[0] for f in gap]
    sure = P.moored_through(gap, gt, t0, 2.0)
    check("a photograph timed to the second, between two still reports, is placed",
          sure is not None and sure[2] < 1, str(sure))
    check("the same photograph timed to twenty minutes is not",
          P.moored_through(gap, gt, t0, 20 * 60) is None)
    drift = [(f[0], 26.5000 + 0.0001 * i, f[2], f[3]) for i, f in enumerate(gap)]
    got = P.moored_through(drift, gt, t0, 12 * 60)
    check("and where the boat lay still throughout, the ring is how far she swung",
          got is not None and 15 < got[2] < 25, str(got))

    # Depth: just outside the grid is outside it.
    g = DP.merged()
    top = g.y0 + g.nrows * g.cell
    check("a point half a cell north-west of the depth grid has no depth",
          g.at(top + g.cell / 2, g.x0 - g.cell / 2) is None
          and g.at(top - g.cell / 2, g.x0 - g.cell / 2) is None
          and g.at(top + g.cell / 2, g.x0 + g.cell / 2) is None)
    check("and one half a cell inside it does",
          g.at(top - g.cell / 2, g.x0 + g.cell / 2) is not None)


def test_receiver_windows():
    """When the handheld was running, from what it recorded rather than what was
    drawn. The drawn track is thinned, so an evening at anchor is not in it."""
    section("receiver windows")
    import corroborate as K
    from trip import EDT, load_day, overnight_bridges, read_inreach, recorded_fixes
    late = []
    for d in DAYS:
        rec = recorded_fixes(d["file"])
        drawn = load_day(d["file"], walk_split=d.get("walk_split"),
                         road_split=d.get("road_split"))
        pts = sorted(drawn["afloat"] + drawn["walk"] + drawn["road"], key=lambda p: p[0])
        if rec and pts:
            late.append((d["label"], (rec[-1][0] - pts[-1][0]).total_seconds()))
    check("the record never ends before the drawing does",
          all(s >= 0 for _, s in late), str(late))
    sun = dict(late).get("Sun 24 Mar", 0)
    check("Sunday's record runs two hours past its last drawn point", sun > 7200,
          f"{sun:.0f} s")
    wins = {label: (s, e) for s, e, label in K.handheld_windows()}
    check("the runtime windows end at the last recorded fix",
          all(wins[d["label"]][1] == recorded_fixes(d["file"])[-1][0]
              for d in DAYS if d["label"] in wins))
    end = wins["Sun 24 Mar"][1].astimezone(EDT)
    check("so Sunday's ends at 21:02, not 18:46", (end.hour, end.minute) == (21, 2),
          f"{end:%H:%M}")
    # No inReach report the handheld was awake for may be drawn as a night bridge.
    inr = read_inreach()
    awake = [(s, e) for s, e in wins.values()]
    middles = set()
    for _, _, _, line in overnight_bridges():
        middles.update(line[1:-1])
    stolen = [p for p in inr if (p[1], p[2]) in middles
              and any(s <= p[0] <= e for s, e in awake)]
    check("no bridge borrows a report from while the handheld was recording",
          not stolen, f"{len(stolen)} such")


def test_track_notes():
    """What the viewer says about a photograph placed from the track. The note
    once offered "may have been taken nearby ashore" under way in mid-sound, and
    called Friday's walk through Marsh Harbour the boat's track."""
    section("track notes")
    t = datetime(2024, 3, 25, 16, 0)
    mid = P._track_note(t, 5.0, 26.4700, -77.0200, 50)       # under way, mid-sound
    check("under way, nothing is said about being ashore",
          "under way" in mid and "ashore" not in mid, mid)
    far = P.shore_m(26.4700, -77.0200)
    check("and that spot really is out of reach of land", far > P.SHORE_M, f"{far:.0f} m")
    still = P._track_note(t, 0.1, 26.4700, -77.0200, 50)     # stopped out there
    check("stopped out of reach of land, the same", "ashore" not in still, still)
    moor = P._track_note(t, 0.1, 26.5385, -76.9600, 50)      # Hope Town harbour
    check("stopped within reach of land, ashore is offered with the distance",
          "at anchor" in moor and "or ashore nearby" in moor and "m away" in moor, moor)
    hotel = P._track_note(t, 0.1, P.HOTEL[1], P.HOTEL[0], 50)
    check("a fix on land is ashore, not at anchor",
          "ashore at the hotel" in hotel and "boat" not in hotel, hotel)
    fri = P._track_note(t, 5.0, 26.4700, -77.0200, 50, day=DAYS[0]["label"])
    check("and so is any fix before the crew had boarded",
          "ashore" in fri and "boat" not in fri and "under way" not in fri, fri)
    # A stop took the nearest of eight labels, so the afternoon at the Pelican
    # Cays was captioned "off Tilloo Cay" and the snorkel at Sandy Cay had no
    # name at all.
    for what, lat, lon, want in (
            ("the Pelican Cays", 26.42169, -76.98400, "the Pelican Cays"),
            ("Sandy Cay", 26.4000, -76.9925, "Sandy Cay"),
            ("Tilloo Pond", 26.4488, -76.9900, "Tilloo Pond"),
            ("Hope Town's harbour", 26.5385, -76.9600, "Hope Town"),
            ("Tahiti Beach", 26.50169, -76.98744, "Tahiti Beach"),
            ("the first night's anchorage", 26.55462, -77.08319, "Outer Point Cay"),
            ("Fishers Bay", 26.6600, -77.1150, "Great Guana Cay")):
        got = P.nearest_named(lat, lon)
        check(f"a stop at {what} is named for it", bool(got) and got[0] == want, str(got))
    check("a stop in open water is given no name",
          P.nearest_named(26.5700, -77.1000) is None)


def test_journal():
    """The journal as published. It is the one part of a private notebook that
    is public, so the test that matters is what must not be in it."""
    section("journal page")
    from map import journal as J
    text = open(J.SOURCE, encoding="utf-8").read()
    page = J.render()
    # Passages cut on purpose before publishing: health and a few family asides.
    # A later edit that pastes from the full transcript would bring them back
    # without anyone deciding to.
    private = ["Dramamine", "Bonine", "got sick", "thrown up", "threw up", "threw that up", "seasickness medicine",
               "panicked", "freaked", "pre-calc", "agonized", "blamed each other",
               "Legoland", "use the bathroom"]
    leaked = [w for w in private if w.lower() in text.lower()]
    check("nothing cut from the journal has come back", not leaked, str(leaked))
    # Surnames were cut too, and a list of them here would publish them. It is
    # kept with the transcript, outside the repository, so this runs only where
    # that folder is.
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    terms = os.path.join(os.path.dirname(repo), "bahamas-journal", "private-terms.txt")
    if os.path.exists(terms):
        names = [l.strip() for l in open(terms, encoding="utf-8")
                 if l.strip() and not l.startswith("#")]
        named = [n for n in names if re.search(rf"\b{re.escape(n)}", text, re.I)]
        check("no surname is published", not named, f"{len(named)} found")
    else:
        print("  SKIP  no surname is published (the private list is not on this machine)")
    check("no transcription scaffolding is published",
          "<!--" not in text and "IMG_" not in text and "left page" not in text)
    title, intro, days = J.parse(text)
    heads = [h for h, _ in days]
    check("the journal runs from the Thursday out to the Thursday home",
          len(heads) == 8 and heads[0].startswith("Thursday 21")
          and heads[-1].startswith("Thursday 28"), str(heads))
    labels = [J.chart_label(h) for h in heads]
    on_chart = [d["label"] for d in DAYS]
    check("every day on the chart has a day in the journal",
          set(on_chart) <= set(labels), str(set(on_chart) - set(labels)))
    check("each has an anchor the chart can link to",
          all(f'id="{J.slug(l)}"' in page for l in on_chart))
    check("and a link back to that day on the chart",
          all(f'index.html?day={l.replace(" ", "%20")}' in page for l in on_chart))
    check("the travel day with no track has no chart link",
          'day=Thu%2021%20Mar' not in page and 'id="thu-21-mar"' in page)
    check("later additions are set apart from the notebook's own words",
          page.count("<aside>") == text.count("\n> ") >= 6)
    check("text is escaped and a URL is a link",
          J._inline("a < b & https://example.org/x.") ==
          'a &lt; b &amp; <a href="https://example.org/x" rel="noopener">https://example.org/x</a>.')
    check("the page tells robots to stay away", "noindex" in page)


def test_land_cache_follows_its_source():
    """Refreshing a coastline has to refresh the land built from it."""
    section("land cache")
    import glob
    import tempfile
    import abaco_geo as G

    def coast(path, side):
        # One square island, anticlockwise, so the land is on the left.
        ring = [(0, 0), (side, 0), (side, side), (0, side), (0, 0)]
        with open(path, "w") as fh:
            json.dump(dict(elements=[dict(type="way", geometry=[
                dict(lon=x, lat=y) for x, y in ring])]), fh)

    tmp = tempfile.mkdtemp(prefix="coast-test-")
    src = os.path.join(tmp, f"cachetest{os.getpid()}.json")
    bbox = (-1.0, -1.0, 4.0, 4.0)
    stem = os.path.join(G.HERE, "geo", "land_" + os.path.basename(src).split(".")[0])
    try:
        coast(src, 1)
        small = G.land_polygons(bbox, source=src).area
        again = G.land_polygons(bbox, source=src).area
        made = glob.glob(stem + "_*.pkl")
        check("land is cached once for one source", len(made) == 1 and again == small,
              f"{len(made)} files")
        coast(src, 2)
        big = G.land_polygons(bbox, source=src).area
        check("a changed coastline gives changed land, not the cached one",
              abs(small - 1.0) < 1e-9 and abs(big - 4.0) < 1e-9,
              f"area {small:g} then {big:g}")
        check("and the superseded cache is cleared away",
              len(glob.glob(stem + "_*.pkl")) == 1)
    finally:
        for f in glob.glob(stem + "_*.pkl"):
            os.remove(f)
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


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
              f"rate={fit['rate']}x cov={fit['coverage']}")


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
          f"rate={fit['rate']}x margin={fit['margin']} "
          f"coincidences={fit['coincidences']}/{fit['n']}")
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
    check("scattered times are refused", not fit["accepted"], fit.get("reason"))

    # This one is why coverage is a gate and not a tiebreaker: pseudo-random times
    # packed into a single day score 30x the chance rate with no rival offset at
    # all, so rate and margin both wave it through. Only coverage stops it.
    packed = [base + timedelta(seconds=(i * 104729) % 86400) for i in range(150)]
    dud = C.correlate_offset(packed, ref, spans)
    check("times packed into one day are refused", not dud["accepted"],
          dud.get("reason"))
    check("  and only coverage catches them",
          dud["rate"] is None or dud["rate"] >= C.ACCEPT["rate"],
          f"rate {dud['rate']}x, margin {dud['margin']}, coverage {dud['coverage']}")
    thin = C.correlate_offset([base], ref[:5], spans)
    check("too little to correlate is refused", not thin["accepted"], thin.get("reason"))


def test_invariants(photos, spans):
    section("invariants")
    per_photo, cameras, _ = C.fit(photos)
    check("every photograph has exactly one verdict", len(per_photo) == len(photos),
          f"{len(per_photo)} verdicts for {len(photos)} photographs")
    methods = {v["method"] for v in per_photo.values()}
    allowed = {None, "gps_utc", "tz_tag", "correlate"}
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
    # "screenshot" joined the ladder when 28 phone screenshots stopped being
    # counted as photographs the build had failed to place.
    known = {"gps", "calibrated", "inferred", "travel", "unplaced", "screenshot"}
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
    # A photograph the track cannot place still happened on a day. 101 of them
    # were going out with a trusted UTC on a trip day and no day at all, because
    # the branch that gives up on a position also skipped naming the day -- so
    # the tray filed them under "Undated" and no day box could hide them.
    lost = [r["id"] for r in placed
            if r["utc"] and not r["day"] and P.day_for(C._utc(r["utc"]))[0]]
    check("a known trip day survives a failed placement", not lost,
          f"{len(lost)} have a UTC on a trip day and no day, e.g. {lost[:3]}")
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
    from abaco_geo import COASTLINE_MAP
    land = land_polygons(MAP_LAND_BBOX, source=COASTLINE_MAP)
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

    # Where the depth mask calls something land but the drawn band calls it water,
    # the raster is blank and the pale page background shows through beside a
    # beach, reading as the deepest water. Using the coarse band as the mask was
    # supposed to prevent that, on the reasoning that finer bands are supersets of
    # it — 31.5 km2 of coastline said otherwise.
    mask = E.mask_land(land)
    worst = 0.0
    for band in E.BANDS:
        drawn = shape(dict(type="MultiPolygon",
                           coordinates=E._rings(land, band["tol"],
                                                band["min_area_m2"])))
        worst = max(worst, mask.difference(drawn).area * E._M_PER_DEG_LAT * E._M_PER_DEG_LON)
    check("no drawn water is left unpainted by the depth mask", worst < 1000.0,
          f"worst band leaves {worst:.0f} m2")
    check("the depth mask is a real mask, not everything",
          0.5 < mask.area / land.area < 1.0,
          f"{mask.area / land.area * 100:.1f}% of the coastline's area")

    # The handheld runs one battery charge a day, so the drawn track breaks at every
    # handover — 207 m of it between Tuesday and Wednesday, which reads as two lines
    # that do not meet. The inReach was recording through all of them.
    from trip import DAYS as _DAYS, load_day as _load_day
    tracks = E.track_layer()
    bridges = {f["properties"]["day"]: f
               for f in tracks["features"] if f["properties"]["mode"] == "moored"}
    firsts, lasts = {}, {}
    for d in _DAYS:
        t = _load_day(d["file"], walk_split=d.get("walk_split"),
                      road_split=d.get("road_split"))
        pts = sorted((t.get("afloat") or []) + (t.get("walk") or [])
                     + (t.get("road") or []), key=lambda p: p[0])
        if pts:
            firsts[d["label"]], lasts[d["label"]] = pts[0], pts[-1]
    order = [d["label"] for d in _DAYS if d["label"] in firsts]
    check("every night between two days is bridged",
          all(b in bridges for b in order[1:]),
          f"{len(bridges)} bridges for {len(order) - 1} handovers")
    worst = 0.0
    for prev, day in zip(order, order[1:]):
        if day not in bridges:
            continue        # already FAILed one check up; keep the suite running
        c = bridges[day]["geometry"]["coordinates"]
        worst = max(worst,
                    haversine(c[0][1], c[0][0], lasts[prev][1], lasts[prev][2]),
                    haversine(c[-1][1], c[-1][0], firsts[day][1], firsts[day][2]))
    check("each bridge touches both tracks it joins", worst < 5.0,
          f"worst end is {worst:.1f} m out; coordinates round to about 1 m")

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


def test_gaps(photos, placed):
    """The three things that rescued 97 photographs, and the one that must not."""
    section("what the gaps gave back")
    byid = {p["id"]: p for p in photos}
    moored = [r for r in placed
              if (r.get("note") or "").startswith(("placed from the satellite",
                                                   "placed at "))]
    check("the second receiver places the evenings the handheld missed",
          len(moored) > 50, f"{len(moored)} placed across a gap")

    exact = [r["id"] for r in placed if r["tier"] in ("calibrated", "inferred")
             and r["uncertainty_m"] is not None and r["uncertainty_m"] < P.RECEIVER_M]
    check("no photograph placed from a receiver claims to beat the receiver",
          not exact, f"{len(exact)} under {P.RECEIVER_M:.0f} m, e.g. {exact[:3]}")
    # The note's figure is the ring's figure, written the way the viewer writes it.
    odd = [r["id"] for r in placed if "only good to ~" in (r.get("note") or "")
           and P._good_to(r["uncertainty_m"]) not in r["note"]]
    late = [r["id"] for r in placed if r["tier"] in ("calibrated", "inferred")
            and (r["uncertainty_m"] or 0) > 400 and "placed from the" in (r.get("note") or "")
            and "only good to" not in r["note"]]
    check("a note that gives a distance gives the one on the ring",
          not odd and not late and P._good_to(765) == "770 m"
          and P._good_to(1878) == "1.9 km" and P._good_to(84) == "84 m",
          f"{odd[:3]} {late[:3]} {P._good_to(765)}")
    # "The receiver was off" is a claim about a day of the trip. The evening of
    # 21 March EDT is already the 22nd in UTC, and the crew was over Texas.
    lost = [r["id"] for r in placed if r["tier"] == "unplaced" and r.get("utc")
            and not r.get("day")]
    check("a photograph the receiver missed was taken on a day of the trip",
          not lost, f"{len(lost)} with no day, e.g. {lost[:3]}")

    # Every one of them must be bounded by the rule that justified it: the fixes
    # either side are close enough that the gap's length does not matter.
    fixes = P.both_receivers()
    ts = [f[0] for f in fixes]
    loose, silent = [], []
    for r in moored:
        got = P.moored_at(fixes, ts, C._utc(r["utc"]))
        if got is None:
            silent.append(r["id"])
            continue
        if got[2] > P.MOORED_M:
            loose.append((r["id"], round(got[2])))
    check("each was moored, by the rule that allowed it", not loose and not silent,
          f"{len(loose)} over {P.MOORED_M:.0f} m, {len(silent)} no longer bracketed")
    worst = max((r["uncertainty_m"] for r in moored), default=0)
    check("none claims to be tighter than the gap allows",
          worst <= P.MOORED_M + P.INREACH_M,
          f"worst {worst} m, ceiling {P.MOORED_M + P.INREACH_M:.0f} m")
    # Friday's are at the hotel, before the crew had a boat. Saying "the boat
    # moved" about those was wrong once and should not come back.
    boats = [r["id"] for r in moored if "the boat" in r["note"]]
    check("none of them talks about a boat", not boats, f"{len(boats)} do")

    # A screenshot is the shape of a screen. Ten PNGs in this archive are 2250 px
    # on the short edge -- photographs somebody saved as PNG -- and calling those
    # screenshots would silently take real pictures off the chart.
    shots = [r for r in placed if r["tier"] == "screenshot"]
    # A count, not just properties: the tier turning itself off (px missing from
    # the index, say) would otherwise pass every check below over empty lists.
    check("the screenshots are all found", len(shots) > 20, f"{len(shots)}")
    wrong = [r["id"] for r in shots
             if byid[r["id"]]["ext"] != ".png"
             or min(byid[r["id"]]["px"]) > P.SCREEN_PX]
    check("every screenshot is a PNG the size of a screen", not wrong, str(wrong[:4]))
    big_png = [p for p in photos
               if p["ext"] == ".png" and p.get("px") and min(p["px"]) > P.SCREEN_PX]
    tiers = {r["id"]: r["tier"] for r in placed}
    check("a photograph saved as PNG is not called a screenshot",
          all(tiers[p["id"]] != "screenshot" for p in big_png),
          f"{len(big_png)} such photographs")
    check("no screenshot is given a position",
          not [r for r in shots if r.get("lat") is not None])

    # WhatsApp kept the date and dropped the time, so it may name a day and must
    # never place anything.
    wa = [r for r in placed if P.WHATSAPP.match(r["name"])]
    check("the WhatsApp files are all found", len(wa) > 30, f"{len(wa)}")
    check("each gets its day from the filename", all(r.get("day") for r in wa),
          f"{sum(1 for r in wa if not r.get('day'))} without a day")
    check("each says the day is a guess",
          all(r.get("day_provisional") for r in wa))
    check("none of them is given a position",
          not [r for r in wa if r.get("lat") is not None],
          "a date is not a time, and the boat moved during the day")


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
    from map import derive as D

    # Completeness first, over the whole set: the page asks for exactly the paths
    # in photos.json, so a single missing or empty file is a broken photograph.
    # This is stat-only, so checking all 5,010 costs nothing.
    want = {r["id"] for r in pj}
    for kind in ("thumb", "view"):
        d = os.path.join(media, kind)
        have = {n[:-4] for n in os.listdir(d) if n.endswith(".jpg")}
        empty = [i for i in sorted(want & have)
                 if os.path.getsize(os.path.join(d, f"{i}.jpg")) == 0]
        check(f"every photograph has a {kind}", want <= have,
              f"{len(want - have)} missing of {len(want)}")
        check(f"no {kind} is an empty file", not empty, str(empty[:4]))
        # Orphans are stale, not broken -- but they are how a renamed id hides.
        check(f"no {kind} is left over from an older index", not (have - want),
              f"{len(have - want)} orphaned")

    # Both sizes now, not just thumbnails: the viewing copies are the ones that
    # would carry a camera's GPS onto the internet, and they were never checked.
    for kind, edge in (("thumb", D.THUMB["px"]), ("view", D.VIEW["px"])):
        d = os.path.join(media, kind)
        names = sorted(n for n in os.listdir(d) if n.endswith(".jpg"))[::37][:60]
        meta, big = [], []
        for n in names:
            im = Image.open(os.path.join(d, n))
            if im.getexif() or im.info.get("icc_profile") or im.info.get("comment"):
                meta.append(n)
            if max(im.size) > edge:
                big.append((n, im.size))
        check(f"no {kind} carries EXIF or an ICC profile", not meta,
              f"checked {len(names)}, {len(meta)} carried metadata")
        check(f"no {kind} exceeds its {edge} px long edge", not big, str(big[:3]))

    names = sorted(n for n in os.listdir(thumbs) if n.endswith(".jpg"))[:60]
    portraits = 0
    for n in names:
        w, h = Image.open(os.path.join(thumbs, n)).size
        portraits += h > w
    check("portrait frames stayed portrait", portraits > 0,
          f"{portraits} of {len(names)} are taller than wide, so rotation was "
          f"baked in before the tags went")

    # And the failure the other checks cannot see: the wrong picture at an id.
    # derive now fingerprints each derivative's source and renders again when it
    # changes, so this should not happen -- but every check above would still
    # pass if it did, the file being present, sized right and metadata-free. So
    # rebuild a few from the index we ship now and insist on the same bytes. A
    # mismatch here with the fingerprints intact means the renderer itself
    # changed (a Pillow upgrade, or prepare/render edited without bumping
    # derive.RENDER_VERSION), not that ids moved.
    # placed records have had src stripped, so the archive and member come from
    # the index -- which is the point: it is this index the derivatives must match.
    stale, rebuilt = [], 0
    origins = [p for p in json.load(open(INDEX)) if p.get("src")]
    for r in origins[::900][:3]:
        archive = os.path.join(C.HERE, "photos",
                               os.path.basename(D._archive_path(r)))
        if not os.path.exists(archive):
            continue        # no zips here; say so below rather than pass quietly
        rebuilt += 1
        # Through derive's own prepare/render, not a hand copy of its steps: a
        # copy drifts, and a drifted copy flags every derivative stale -- or
        # blesses ones a real run would no longer produce.
        with D._zip(archive).open(r["src"]["member"]) as fh:
            im = D.prepare(fh.read())
        for spec in (D.THUMB, D.VIEW):
            path = os.path.join(media, spec["name"], f"{r['id']}.jpg")
            if not os.path.exists(path):
                # The interrupted-run state this test exists for: report it,
                # don't crash on it.
                stale.append(f"{r['id']}/{spec['name']} (missing)")
            elif D.render(im, spec) != open(path, "rb").read():
                stale.append(f"{r['id']}/{spec['name']}")
    if not rebuilt:
        print("  SKIP  cannot re-derive: no zips in photos/")
    else:
        check("the derivatives on disk are the ones this index asks for", not stale,
              f"{stale} differ from a fresh build" if stale
              else f"rebuilt {rebuilt}, bytes match")


# ------------------------------------------------------ derivative cache ---
def test_derive_cache():
    """derive against a throwaway archive: does it notice the source changing?

    Ids are positions in the time-sorted index, so one photograph added to the
    archives renumbers everything after it. A cache keyed on the id alone then
    keeps p00000.jpg and shows it at whatever is p00000 now. No archive of real
    photographs is needed to ask the question, so this runs everywhere.
    """
    section("derivative cache")
    import io
    import shutil
    import tempfile
    import zipfile
    from PIL import Image
    from map import derive as D

    def archive(folder, colour, member="a.jpg"):
        buf = io.BytesIO()
        Image.new("RGB", (64, 48), colour).save(buf, "JPEG", quality=90)
        with zipfile.ZipFile(os.path.join(folder, "Seabase 2024.zip"), "w") as zf:
            zf.writestr(member, buf.getvalue())
            info = zf.getinfo(member)
        return dict(id="p00000", unreadable=False,
                    src=dict(archive="mine", member=member,
                             crc=info.CRC, size=info.file_size))

    def colour_of(dest):
        with Image.open(os.path.join(dest, "view", "p00000.jpg")) as im:
            r, g, b = im.convert("RGB").getpixel((5, 5))
        return "red" if r > b else "blue"

    tmp = tempfile.mkdtemp(prefix="derive-test-")
    try:
        dest = os.path.join(tmp, "media")
        record = os.path.join(tmp, "derived.json")
        run = lambda ps: D.run(ps if isinstance(ps, list) else [ps], dest, workers=1,
                               progress=False, archive_dir=tmp, manifest_path=record)
        red = archive(tmp, (220, 20, 20))
        first = run(red)
        check("a first run makes both derivatives",
              first["errors"] == 0 and first["files"] == 2 and colour_of(dest) == "red",
              str(first))
        again = run(red)
        check("an unchanged source is not rendered twice", again["files"] == 0,
              str(again))
        blue = archive(tmp, (20, 20, 220))
        changed = run(blue)
        check("the same id from a different source is rendered again",
              changed["files"] == 2 and colour_of(dest) == "blue",
              f"{changed}, viewing copy is {colour_of(dest)}")
        # A build that does not render must still notice that it should have.
        nothing = D.stale([blue], os.path.join(tmp, "no-media"), manifest_path=record)
        check("no media folder is not stale media", nothing is None, str(nothing))
        check("media made from this index is current",
              D.stale([blue], dest, manifest_path=record) == [])
        moved = dict(red, id="p00000")
        check("media made from another source is reported, without rendering",
              D.stale([moved], dest, manifest_path=record) == ["p00000"]
              and colour_of(dest) == "blue")
        check("the record of what came from where is not in the published folder",
              os.path.exists(record)
              and not any(n.endswith(".json") for n in os.listdir(dest)),
              str(os.listdir(dest)))

        # One size's settings change: only that size is made again.
        keep = D.THUMB
        D.THUMB = dict(keep, quality=keep["quality"] - 10)
        try:
            thumb_only = run(blue)
        finally:
            D.THUMB = keep
        check("changing the thumbnail settings leaves the viewing copies alone",
              thumb_only["files"] == 1, str(thumb_only))
        run(blue)                       # back to the real settings

        # Debris from a killed run, and a photograph that has left the index.
        open(os.path.join(dest, "view", "p00007.jpg.part"), "wb").write(b"half")
        other = dict(blue, id="p00001")
        both = run([blue, other])
        swept = not os.path.exists(os.path.join(dest, "view", "p00007.jpg.part"))
        check("half-written files from a killed run are swept up", swept)
        only_second = run(other)
        left = sorted(os.listdir(os.path.join(dest, "view")))
        check("a photograph dropped from the index takes its derivatives with it",
              left == ["p00001.jpg"] and only_second["removed"] == 2,
              f"{left}, {only_second}")
        sample = D.run([blue], dest, workers=1, progress=False, archive_dir=tmp,
                       manifest_path=record, only=1)
        check("a sample run removes nothing",
              sample["removed"] == 0
              and os.path.exists(os.path.join(dest, "view", "p00001.jpg")),
              str(sample))

        missing = dict(blue, src=dict(blue["src"], member="not-there.jpg", crc=1))
        broken = run(missing)
        check("a photograph that cannot be read is counted as an error",
              broken["errors"] == 1, str(broken))
        # The file from before is still on disk under that id. It must not be
        # trusted again just because a later run asks for the old source.
        healed = run(blue)
        check("and what is on disk after a failure is not vouched for",
              healed["files"] == 2, str(healed))
        try:
            D.fail_on_errors(broken)
            raised = False
        except SystemExit as e:
            raised = bool(e.code)
        check("an error fails the build rather than finishing it", raised)
        try:
            D.fail_on_errors(changed)
            clean = True
        except SystemExit:
            clean = False
        check("a clean run does not", clean)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- stories ---
def test_stories():
    """The journal's stories, as the chart places them.

    These are typed by hand, coordinates included, so the checks are the ones a
    typo would trip: a day the trip did not have, a time that is not a time, and
    above all a position on the wrong island. A story may be ashore -- the
    lighthouse is 700 m from where the boat lay -- but none is further from its
    own day's track than a crew could walk or row from it.
    """
    section("stories")
    from map.stories import STORIES
    check("there are stories to tell", len(STORIES) > 0, f"{len(STORIES)}")
    by_label = {d["label"]: d for d in DAYS}
    order = [d["label"] for d in DAYS]
    bad_day = [s["title"] for s in STORIES if s["day"] not in by_label]
    check("every story names a day of the trip", not bad_day, str(bad_day))
    blank = [s.get("title") for s in STORIES
             if not s.get("title", "").strip() or not s.get("text", "").strip()]
    check("every story has a title and something to say", not blank, str(blank))
    bad_time = [s["title"] for s in STORIES
                if s.get("time") is not None
                and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", s["time"])]
    check("a time, where given, is HH:MM", not bad_time, str(bad_time))
    keys = [(order.index(s["day"]), s.get("time") or "99:99")
            for s in STORIES if s["day"] in by_label]
    check("the stories run in the order the trip did", keys == sorted(keys))
    long = [(s["title"], len(s["text"])) for s in STORIES if len(s["text"]) > 700]
    check("each fits a bubble", not long, str(long))

    fixes = {}
    far = []
    for s in STORIES:
        if s["day"] not in by_label:
            continue
        stem = by_label[s["day"]]["file"]
        if stem not in fixes:
            fixes[stem] = read_fixes(stem)[0][::6]
        d = min(haversine(s["lat"], s["lon"], f[1], f[2]) for f in fixes[stem])
        if d > 1500:
            far.append((s["title"], round(d)))
        if not in_chart(s["lat"], s["lon"]):
            far.append((s["title"], "off the chart"))
    check("every story is within 1.5 km of its own day's track", not far, str(far))

    fc = E.stories_layer()
    check("the export carries every story", len(fc["features"]) == len(STORIES))
    ns = [f["properties"]["n"] for f in fc["features"]]
    check("numbered 1..n in trip order", ns == list(range(1, len(STORIES) + 1)))
    wrong = [f["properties"]["title"] for f in fc["features"]
             if f["properties"]["color"] != by_label[f["properties"]["day"]]["color"]]
    check("each in its own day's colour", not wrong, str(wrong))


def test_site_build():
    section("the built folder")
    out = os.path.join(C.HERE, "site_build")
    if not os.path.isdir(out):
        print("  SKIP  not built (python -m map.build)")
        return
    need = ["index.html", "app.js", "style.css", "robots.txt", "_headers",
            "data/depth.geojson", "data/shoals.geojson",
            "vendor/maplibre-gl.js", "vendor/maplibre-gl.css",
            "data/meta.json", "data/photos.json", "data/tracks.geojson",
            "data/places.geojson", "data/stories.geojson",
            "journal.html", "journal.css"]
    missing = [n for n in need if not os.path.exists(os.path.join(out, n))]
    # Everything below, and the browser after it, reads this folder. If it was
    # built from an older source, a pass is a pass for yesterday's page.
    src = os.path.join(C.HERE, "map", "site")
    old = [n for n in ("index.html", "app.js", "style.css", "journal.css")
           if os.path.exists(os.path.join(out, n))
           and open(os.path.join(src, n), "rb").read() != open(os.path.join(out, n), "rb").read()]
    check("the built folder is built from this source", not old,
          f"{', '.join(old)} differ from map/site: run python -m map.build")
    page0 = open(os.path.join(out, "index.html")).read()
    check("the panel says whose position the ring is", "the boat's\n       position" in page0
          or "the boat's position" in page0)
    check("every file the page asks for is present", not missing, str(missing))

    app = open(os.path.join(out, "app.js")).read()
    # A nudge is a distance on the ground: 2 km is a finger's width at the opening
    # view and four screens away at z15. Lubbers Quarters was there to be read at
    # z10 and nowhere to be found by anyone who had zoomed in on the island.
    from shapely.geometry import Point
    from abaco_geo import COASTLINE_MAP, land_polygons
    from trip import MAP_LABEL_ANCHOR, MAP_LAND_BBOX
    land = land_polygons(MAP_LAND_BBOX, source=COASTLINE_MAP)
    places = json.load(open(os.path.join(out, "data", "places.geojson")))["features"]
    adrift = [f["properties"]["label"] for f in places
              if f["properties"]["kind"] == "isle"
              and land.distance(Point(f["geometry"]["coordinates"])) * 1e5 > 50]
    check("every island's name is on the island, or ends at its shore",
          not adrift, str(adrift))
    sided = {f["properties"]["label"]: f["properties"]["anchor"]
             for f in places if "anchor" in f["properties"]}
    check("a name set beside its island ends at the shore rather than straddling it",
          sided == MAP_LABEL_ANCHOR and "p.anchor || 'center'" in app, str(sided))
    meta = json.load(open(os.path.join(out, "data", "meta.json")))
    for band in meta["bands"]:
        check(f"app.js knows the {band['name']} band",
              f"'{band['name']}'" in app or f'"{band["name"]}"' in app)
        f = os.path.join(out, "data", f"coast.{band['name']}.geojson")
        check(f"coast.{band['name']}.geojson exists", os.path.exists(f))
        gone = os.path.join(out, "data", f"shoals.{band['name']}.geojson")
        check(f"the drawn shoal halo is gone ({band['name']})",
              not os.path.exists(gone), "depth.png says it from measurement now")
    # Every tier the build emits has to be somewhere a viewer can reach. A tier
    # that is neither on the chart nor in the tray's loop is counted in the tray's
    # total and then never drawn -- which is what happened when screenshots were
    # added, and no test noticed because nothing here read app.js's own lists.
    pj = json.load(open(os.path.join(out, "data", "photos.json")))
    emitted = {r["tier"] for r in pj}
    on_chart = set(re.findall(r"'([a-z]+)'",
                              re.search(r"ON_CHART\s*=\s*\[([^\]]*)\]", app).group(1)))
    in_tray = set(re.findall(r"'([a-z]+)'",
                             re.search(r"for \(const tier of \[([^\]]*)\]", app).group(1)))
    # Unticking a day takes its photographs with it, and that has to happen by
    # giving the clustered source less data. A layer filter would hide the dots
    # and leave the cluster still reporting how many it had, so a day switched
    # off would leave "610" floating over empty water.
    days_body = re.search(r"function applyDays\(\)\s*\{(.*?)\n\}", app, re.S)
    check("unticking a day refreshes the photographs too",
          bool(days_body) and "refreshPhotos()" in days_body.group(1))
    # Scoped to refreshPhotos itself, not the whole file: getSource('photos')
    # also appears in the cluster-expansion click, so a file-wide match would
    # stay green through the exact regression this exists to catch.
    photos_body = re.search(r"function refreshPhotos\(\)\s*\{(.*?)\n\}", app, re.S)
    check("and by reloading the source, not filtering the layer",
          bool(photos_body) and "setData(photoFC(" in photos_body.group(1)
          and "setFilter" not in photos_body.group(1))

    check("app.js draws every tier the build emits somewhere",
          emitted <= on_chart | in_tray,
          f"unreachable: {sorted(emitted - on_chart - in_tray)}")
    # The day checkboxes are now the only way a chart photograph is shown, so a
    # placed photograph whose day is missing or unlisted (place.py can emit
    # day=None when day_for cannot name one) would be invisible everywhere with
    # every box ticked and nothing on the page looking wrong.
    day_labels = {d["label"] for d in meta["days"]}
    unlisted = [r["id"] for r in pj
                if r["tier"] in on_chart and r.get("lat") is not None
                and r.get("day") not in day_labels]
    check("every photograph on the chart names a day the panel lists",
          not unlisted,
          f"{len(unlisted)} no checkbox can show, e.g. {unlisted[:5]}")
    # export.py ships day_provisional and test_gaps proves it; the flag is worth
    # nothing unless the page reads it where a person sees the day claimed.
    check("the viewer hedges a day guessed from a filename",
          "day_provisional" in app)
    # Safari and Firefox fetch when src is set; a lazy flag set after is too late.
    tray = app[app.index("function buildTray"):]
    check("a tray thumbnail is marked lazy before it is given its address",
          0 < tray.find("img.loading = 'lazy'") < tray.find("img.src = "))
    tracks = json.load(open(os.path.join(out, "data", "tracks.geojson")))["features"]
    wet = [f["properties"]["mode"] for f in tracks if "shallowest_m" in f["properties"]]
    check("only a track afloat carries a depth of water",
          wet and set(wet) == {"afloat"}, str(sorted(set(wet))))
    # Asked of the server itself, and of the build only that it uses that server.
    from map import serve
    srv = serve.server(out, 0)
    host = srv.server_address[0]
    srv.server_close()
    build_src = open(os.path.join(C.HERE, "map", "build.py")).read()
    check("a preview is served to this machine only, and the build's is that one",
          host == "127.0.0.1" and "serve.run(" in build_src
          and "HTTPServer" not in build_src, host)
    # Place names are HTML and always paint above the canvas, so the bubble is
    # HTML too: drawn in #clusters, which stacks above the names, it covers what
    # it covers -- names never hide, and never show through a bubble either.
    # (An earlier fix hid any name a bubble touched, which cost the opening
    # view HOPE TOWN entirely; covering beats vanishing.)
    # The arrows walk every photograph in time order, so the one after the last
    # at an anchorage is somewhere else and nothing said so.
    page = open(os.path.join(out, "index.html")).read()
    check("the viewer says when a step lands at a different spot",
          'id="viewer-moved"' in page and 'id="viewer-spot"' in page
          and "function announceMove" in app and "announceMove(from, i)" in app)
    # The photographs taken at a story's spot cluster on the story's own dot. The
    # bubble covered the dot, and the dot underneath still took the click.
    check("a story's dot moves out from under a photograph count",
          "function seatStories" in app and "s.marker.setOffset" in app
          and "seatStories(bubbles)" in app)
    check("the cluster bubble is HTML above the names, not canvas below them",
          "'circle-opacity': 0" in app and "occludePlaces" not in app)
    check("and the tray explains each tier it lists",
          all(f"{t}:" in app for t in in_tray & emitted),
          f"no note for {[t for t in in_tray & emitted if f'{t}:' not in app]}")

    # A build without --media must still refuse an index the media on disk does
    # not belong to, and unreadable photographs must be dropped before anything
    # lists them. Both live in build.py's main, which no test can call cheaply.
    build_src = open(os.path.join(C.HERE, "map", "build.py")).read()
    check("a build that skips rendering still checks the media it has",
          "derive.stale(" in build_src)
    check("and unreadable photographs are dropped before placement",
          build_src.index("PI.readable(") < build_src.index("C.fit(photos)"))
    # One optional fetch failing must not stop the panel being built.
    start_body = re.search(r"async function start\(\)\s*\{(.*?)\n\}", app, re.S).group(1)
    check("a failed optional load does not stop the panel being built",
          "catch" in start_body and "addStories" in start_body
          and start_body.index("catch") < start_body.index("buildPanel("))
    tray_body = re.search(r"function buildTray\(\)\s*\{(.*?)\n\}", app, re.S).group(1)
    check("tray photographs are buttons, so a keyboard can open them",
          "createElement('button')" in tray_body and "aria-label" in tray_body)
    check("the viewer takes focus, holds it, and gives it back",
          ".inert = true" in app and "$('#viewer-close').focus()" in app
          and "viewerReturn" in app and "back.focus()" in app)

    html = open(os.path.join(out, "index.html")).read()
    # The chart opens as a chart. Photographs and stories are a tick away, and a
    # box that starts unticked has to start with its layer hidden, which is the
    # page's job: every layer is added visible before the panel exists.
    boxes = dict(re.findall(r'data-layer="(\w+)"( checked)?', html))
    check("photographs and stories start off; depth and names start on",
          boxes.get("photos") == "" and boxes.get("stories") == ""
          and boxes.get("depth") and boxes.get("places"), str(boxes))
    wire = re.search(r"function wirePanel\(\)\s*\{(.*?)\n\}", app, re.S).group(1)
    check("and each layer is put in its box's state when the panel is wired",
          wire.count("applyLayer(cb.dataset.layer, cb.checked)") == 2)
    check("photographs taken in one spot stay a count, and a click opens them",
          "clusterMaxZoom: 19" in app and "getClusterLeaves" in app
          and "openStack" in app)
    check("the key to the photograph dots is shown only with the photographs",
          re.search(r'id="photo-key" hidden>\s*<h2>How each one was placed', html)
          and "$('#photo-key').hidden = !on" in app)
    # The poster: offered only if it is there, and there if it is offered.
    offered = meta.get("poster", [])
    gone = [f["href"] for f in offered if not os.path.exists(os.path.join(out, f["href"]))]
    check("every poster file the page offers is in the build", not gone, str(gone))
    check("and the page knows how to offer them",
          'id="poster-links"' in html and "meta.poster" in app)
    check("the chart links to the journal, and a story to its day in it",
          'href="journal.html"' in html and "journal.html#" in app)
    from map import journal as J
    check("the chart and the journal agree how a day's anchor is spelled",
          "replace(/[^a-z0-9]+/g, '-')" in app and J.slug("Sun 24 Mar") == "sun-24-mar")
    # Stories are HTML markers, so nothing but the page's own code hides them:
    # the panel needs a box for them, and a day switched off has to take its
    # stories with it the way it takes its photographs.
    check("the panel has a box for the stories", 'data-layer="stories"' in html)
    check("unticking a day hides its stories too",
          bool(days_body) and "refreshStories" in days_body.group(1))
    check("the page tells robots to stay away", "noindex" in html)
    check("and so does the header file",
          "noindex" in open(os.path.join(out, "_headers")).read())
    check("nothing points at a CDN",
          "http://" not in app and "https://" not in app.replace(
              "https://github.com", "").replace("http://www.topografix.com", ""),
          "app.js must fetch only from this folder")


BROWSER_TIMEOUT_S = 300


def test_browser():
    """What only a click can show, in a real browser. See map/browser_check.js."""
    import functools
    import http.server
    import shutil
    import subprocess
    import threading
    from map import serve
    section("in a browser")
    out = os.path.join(C.HERE, "site_build")
    script = os.path.join(C.HERE, "map", "browser_check.js")
    if not os.path.isdir(out):
        print("  SKIP  not built (python -m map.build)")
        return
    if not shutil.which("node") or subprocess.run(
            ["node", "-e", "require.resolve('playwright-core')"], cwd=C.HERE,
            capture_output=True).returncode:
        print("  SKIP  no browser driver (npm install --no-save playwright-core@1.64.0)")
        return
    class Quiet(serve.Handler):
        def log_message(self, *args):
            pass
    httpd = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(Quiet, directory=out))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        run = subprocess.run(
            ["node", script, f"http://127.0.0.1:{httpd.server_address[1]}/"],
            cwd=C.HERE, capture_output=True, text=True, timeout=BROWSER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        # One failed check, and the rest of the suite still reports.
        check("the browser check ran to the end", False,
              f"no answer in {BROWSER_TIMEOUT_S} s")
        return
    finally:
        httpd.shutdown()
        httpd.server_close()
    lines = [json.loads(l) for l in run.stdout.splitlines() if l.startswith("{")]
    skipped = [r["skip"] for r in lines if "skip" in r]
    if skipped:
        print(f"  SKIP  no browser to drive ({skipped[0]})")
        return
    for r in lines:
        check(r["name"], r["ok"], r["detail"])
    check("the browser check ran to the end", run.returncode == 0 and len(lines) >= 10,
          run.stderr.strip()[-300:])


def test_edges():
    """Inputs this trip's data does not contain, each of which once went wrong."""
    import contextlib
    import io
    import random
    import tempfile
    import zipfile
    from datetime import timezone
    from PIL import Image
    from shapely.geometry import box
    import parse_nmea
    from trip import shoal
    from map import derive as D
    from map.photo_index import _merge, by_camera
    from trip import recorded_fixes
    section("edges the data does not reach")

    b = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(b, "JPEG", comment=b"GPS 26.5,-77.0")
    out = Image.open(io.BytesIO(D.render(D.prepare(b.getvalue()), D.THUMB)))
    check("a JPEG comment does not survive rendering", not out.info.get("comment"),
          str(out.info.get("comment")))

    with tempfile.TemporaryDirectory() as t:
        dest, man = os.path.join(t, "media"), os.path.join(t, "derived.json")
        ph = [dict(id=f"p{i:05d}", src=dict(archive="mine", member=f"{i}.jpg",
                                            crc=i, size=i)) for i in range(2)]
        for s in (D.THUMB, D.VIEW):
            os.makedirs(os.path.join(dest, s["name"]))
            for p in ph:
                with open(os.path.join(dest, s["name"], p["id"] + ".jpg"), "wb") as fh:
                    fh.write(b"x")
        D._save_manifest(man, dest, {p["id"]: {s["name"]: D.fingerprint(p, s)
                                               for s in (D.THUMB, D.VIEW)} for p in ph})
        check("media that matches its index is not stale", D.stale(ph, dest, man) == [])
        check("a photograph dropped from the end of the index leaves stale media",
              D.stale(ph[:1], dest, man) == ["p00001"], str(D.stale(ph[:1], dest, man)))
        with open(os.path.join(dest, "view", "p00000.jpg.part"), "wb") as fh:
            fh.write(b"x")
        check("and so does a half-written file",
              D.stale(ph, dest, man) == ["p00000.jpg.part"])

        def nmea(body):
            ck = 0
            for ch in body:
                ck ^= ord(ch)
            return f"${body}*{ck:02X}\n"
        log = os.path.join(t, "GPS_x.log")
        with open(log, "w") as fh:
            for i, lat in enumerate(("xxxx", "9930.000", "2699.000", "2630.000", "2630")):
                fh.write(nmea(f"GPRMC,12000{i}.00,A,{lat},N,07700.000,W,"
                              "1.0,0.0,250324,,,A"))
        rows = parse_nmea.parse_file(log)
        check("a malformed or impossible coordinate costs one fix, not the log",
              [(r[1], r[2]) for r in rows] == [(26.5, -77.0)] * 2, str(rows))
        check("and minutes are read the same with no decimal point",
              parse_nmea.dm_to_deg("2630", "N") == 26.5)

    far = shoal(box(10, 0, 11, 1), 0.1)
    shoal(box(0, 0, 1, 1), 0.1)
    check("two coastlines of the same area get their own shoals",
          shoal(box(10, 0, 11, 1), 0.1) is far and far.bounds[0] > 9, str(far.bounds))

    # 100 coincidences at -4 h that the receiver never saw, 80 at +4 h that it did.
    r, t0 = random.Random(442), datetime(2024, 3, 23, tzinfo=timezone.utc)
    cam = sorted(t0 + timedelta(seconds=r.uniform(0, 6 * 86400)) for _ in range(100))
    h4, m1 = timedelta(hours=4), timedelta(seconds=60)
    f = C.correlate_offset(cam, [c - h4 for c in cam] + [c + h4 for c in cam[:80]],
                           sorted((c + h4 - m1, c + h4 + m1) for c in cam))
    check("the fit takes the offset the receiver supports, not the bigger raw peak",
          f["accepted"] and f["offset_min"] == 240.0, str(f))

    def copy(arch, size, **tags):
        return dict(archive=arch, member=arch, size=size, crc=1, ext=".jpg", tags=tags)
    when = "2024:03:24 10:00:00"
    m = _merge("a.jpg", "cam", [
        copy("mine", 9, time_local=when, px=[1, 1]),
        copy("crew", 5, time_local=when, gps=[26.5, -77.0], tz_offset="-04:00",
             gps_utc="2024-03-24T14:00:00Z")], collections.Counter())
    check("a smaller copy lends its position and GPS time, and not its timezone",
          (m["gps"], m["gps_utc"], m["tz_offset"])
          == ([26.5, -77.0], "2024-03-24T14:00:00Z", None), str(m))
    m = _merge("a.jpg", "cam", [copy("mine", 9, error="bad"),
                                copy("crew", 5, px=[1, 1])], collections.Counter())
    check("a copy that will not decode is not the one the pixels come from",
          m["src"]["archive"] == "crew" and not m["unreadable"], str(m["src"]))

    # Two crew with the same phone share a name and a model; the time is what
    # tells their photographs apart.
    m = _merge("a.jpg", "cam", [
        copy("mine", 9, time_local=when, px=[1, 1]),
        copy("crew", 5, time_local="2024:03:25 16:30:00", gps=[26.4, -77.1],
             gps_utc="2024-03-25T20:30:00Z")], collections.Counter())
    check("a copy taken at another time lends nothing",
          (m["gps"], m["gps_utc"]) == (None, None), str(m))
    m = _merge("a.jpg", "cam", [
        copy("mine", 9, time_local=when, px=[1, 1]),
        copy("crew", 5, time_local=when, gps=[26.5, -77.0]),
        copy("crew", 4, time_local=when, gps=[26.6, -77.2],
             gps_utc="2024-03-24T14:00:00Z")], collections.Counter())
    check("position and GPS time come from one lender, not one from each",
          (m["gps"], m["gps_utc"]) == ([26.5, -77.0], None), str(m))
    g = by_camera([copy("mine", 9, error="bad"),
                   copy("crew", 5, make="Apple", model="iPhone 14", px=[1, 1])])
    check("a copy that will not decode goes with its readable twin",
          list(g) == ["Apple iPhone 14"] and len(g["Apple iPhone 14"]) == 2, str(list(g)))
    g = by_camera([copy("mine", 9, error="bad"),
                   copy("crew", 5, make="Apple", model="iPhone 14"),
                   copy("crew", 6, make="Google", model="Pixel 7a")])
    check("but not when two cameras could each be its twin",
          sorted(len(v) for v in g.values()) == [1, 1, 1], str(list(g)))

    # The spike rule is for a boat. Thursday ends in a van at up to 46 kn, and
    # every one of those fixes is where the receiver was.
    raw = sum(len(read_fixes(d["file"])[0]) for d in DAYS)
    lost = sum(len(read_fixes(d["file"])[0]) - len(recorded_fixes(d["file"]))
               for d in DAYS)
    check("placement keeps every fix from the road to the airport",
          len(P.track()) == raw and lost > 0,
          f"{raw - len(P.track())} dropped; {lost} would be without the road split")

    # Three places where the arithmetic drew something the data did not say.
    import numpy as np
    import poster
    from map import depth as DP
    loop = [(0, 0), (4, 0), (4, 2), (2, 2), (2, -2), (6, -2)]
    cut = poster._trim_loops(loop)
    check("trimming a fold keeps the corner after the crossing",
          cut == [(0.0, 0.0), (2.0, 0.0), (2.0, -2.0), (6.0, -2.0)], str(cut))
    flat = DP._box_mean(np.full((1500, 1500), 2500.0, dtype=np.float32), 25)
    check("a box mean over a deep grid is the depth, to the centimetre",
          float(np.abs(flat - 2500.0).max()) < 0.01,
          f"off by up to {float(np.abs(flat - 2500.0).max()):.1f} m")
    vals = np.full((5, 3), 400.0, dtype=np.float32)
    trusted = np.zeros((5, 3), bool)
    trusted[0] = True
    region = np.zeros((5, 3), bool)
    region[4] = True
    grown = DP._grow_into(vals, region, trusted)
    check("the grid's north edge is not a neighbour of its south edge",
          (grown[4] == -1.0).all(), str(grown[4]))

    # A tag that is trusted becomes a UTC nothing else checks.
    check("a malformed timezone tag is not an offset",
          [C._tz_minutes(s) for s in ("x04:00", "+99:99", "-04:60", "-4:00", None,
                                      "+14:45", "-14:30", "-04:00\n")]
          == [None] * 8 and C._tz_minutes("-04:00") == -240
          and C._tz_minutes("+05:30") == 330 and C._tz_minutes("+14:00") == 840)

    with tempfile.TemporaryDirectory() as t:
        os.makedirs(os.path.join(t, "view"))
        os.makedirs(os.path.join(t, "thumb"))
        check("an empty media folder has nothing to be wrong",
              D.stale([], t, os.path.join(t, "m.json")) is None)
        with open(os.path.join(t, "view", "p00001.jpg.part"), "wb") as fh:
            fh.write(b"x")
        check("but one holding only a half-written file does",
              D.stale([], t, os.path.join(t, "m.json")) == ["p00001.jpg.part"])
    # A folder rendered before comments were stripped: the same sources and
    # settings, recorded under the render version of the time.
    with tempfile.TemporaryDirectory() as t:
        dest, man = os.path.join(t, "media"), os.path.join(t, "derived.json")
        ph = [dict(id="p00000", src=dict(archive="mine", member="0.jpg", crc=0, size=0))]
        now, D.RENDER_VERSION = D.RENDER_VERSION, 1
        try:
            old = {"p00000": {s["name"]: D.fingerprint(ph[0], s) for s in (D.THUMB, D.VIEW)}}
        finally:
            D.RENDER_VERSION = now
        for s in (D.THUMB, D.VIEW):
            os.makedirs(os.path.join(dest, s["name"]))
            with open(os.path.join(dest, s["name"], "p00000.jpg"), "wb") as fh:
                fh.write(b"x")
        D._save_manifest(man, dest, old)
        check("derivatives from before comments were stripped are not current",
              D.stale(ph, dest, man) == ["p00000"], str(D.stale(ph, dest, man)))

    # No fixes at all is no position, and a day spent wholly ashore is a day.
    noon = datetime(2024, 3, 25, 16, tzinfo=timezone.utc)
    check("an empty track places nothing and raises nothing",
          P.at([], [], noon) is None)
    import trip
    real_read = trip.read_fixes
    trip.read_fixes = lambda stem: ([(noon, 26.5, -77.0, 0.0),
                                     (noon + timedelta(seconds=30), 26.5001, -77.0, 2.0)], 0)
    try:
        ashore = trip.load_day("x", walk_split="2024-03-25T17:00:00Z")
        driven = trip.load_day("x", road_split="2024-03-25T15:00:00Z")
    finally:
        trip.read_fixes = real_read
    check("a day whose every fix is on foot or on the road still loads",
          (ashore["afloat"], len(ashore["walk"]), driven["afloat"], len(driven["road"]))
          == ([], 2, [], 2), f"{ashore} {driven}")

    # One camera, one photograph timed by satellite, on a boat doing 2 m/s. Its
    # uncertainty is the two seconds either side and the receiver's own error,
    # whether or not the camera's other photographs needed a fit 20 minutes wide.
    run = [(noon + timedelta(seconds=10 * k), 26.5 + k * 0.00018, -77.0, 3.9, "Mon 25 Mar")
           for k in range(400)]
    still = [(f[0], 26.5, -77.0, 0.0, f[4]) for f in run]
    shot = [dict(id="p1", name="a.jpg", camera="cam", ext=".jpg", gps=None, px=[4, 3])]
    when = {"p1": dict(utc="2024-03-25T16:30:00Z", method="gps_utc")}
    wide = {"cam": dict(fit=dict(accepted=True, peak_width_s=1200.0))}
    plain = P.place(shot, when, {"cam": {}}, fixes=run)[0]["uncertainty_m"]
    fit = P.place(shot, when, wide, fixes=run)[0]["uncertainty_m"]
    check("a photograph timed by satellite keeps its own two-second window",
          plain == fit and plain < 30, f"{plain} m alone, {fit} m beside a fit")
    # A timezone tag says which zone the clock was set to, not that it was right.
    tagged = {"p1": dict(utc="2024-03-25T16:30:00Z", method="tz_tag")}
    tag = P.place(shot, tagged, wide, fixes=run)[0]["uncertainty_m"]
    check("a photograph timed by a zone tag takes its camera's fitted window",
          tag > 10 * plain, f"{tag} m against {plain} m by satellite")
    late = [dict(shot[0], id="p2")]
    p2 = P.place(late, {"p2": dict(utc="2024-03-29T04:00:00Z", method="gps_utc")},
                 {"cam": {}}, fixes=run)[0]
    check("the first instant after the trip's last day is not a day of the trip",
          (p2["tier"], p2["day"]) == ("travel", None), str(p2))
    moored = P.place(shot, when, {"cam": {}}, fixes=still)[0]["uncertainty_m"]
    check("a boat that never moved is still only known to the receiver's error",
          moored == P.RECEIVER_M, f"{moored} m")

    # The chart is drawn with degrees true, and the vessel does not undo it.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=poster.SHEET_IN, dpi=50)
    ax = fig.add_axes(poster.HERO_RECT)
    w, e, s, n = poster.true_extent(trip.EXTENT, poster.HERO_RECT, poster.SHEET_IN)
    ax.set_xlim(w, e)
    ax.set_ylim(s, n)
    ax.set_aspect(poster.ASPECT)
    poster.draw_vessel(ax, (w + e) / 2, (s + n) / 2, 0.03)
    fig.canvas.draw()
    o, east, north = ax.transData.transform(
        [(w, s), (w + 0.01 * poster.ASPECT, s), (w, s + 0.01)])
    ratio = (east[0] - o[0]) / (north[1] - o[1])
    box = ax.get_position()
    plt.close(fig)
    check("a hundredth of a degree north is as long as its equal east, vessel and all",
          abs(ratio - 1) < 1e-3 and abs(box.width - poster.HERO_RECT[2]) < 1e-4,
          f"ratio {ratio:.5f}, frame width {box.width:.5f}")

    # ---- the second whole-repository review, 12 October
    # A fit's window runs as far each way as its near-peak offsets do.
    check("a fitted window is the peak's own ends, not half its width either side",
          P.fit_window(dict(peak_width_s=600.0, peak_lo_s=-498.0, peak_hi_s=102.0))
          == (498.0, 102.0)
          and P.fit_window(dict(peak_width_s=600.0)) == (300.0, 300.0)
          and P.fit_window(dict(peak_width_s=0.0, peak_lo_s=0.0, peak_hi_s=7.0))
          == (C.COARSE_S / 2, C.COARSE_S / 2)
          and {"peak_lo_s", "peak_hi_s"} <= set(f) and f["peak_lo_s"] <= 0 <= f["peak_hi_s"],
          str({k: f.get(k) for k in ("peak_width_s", "peak_lo_s", "peak_hi_s")}))
    skew = {"cam": dict(fit=dict(accepted=True, peak_width_s=600.0,
                                 peak_lo_s=-590.0, peak_hi_s=10.0))}
    even = {"cam": dict(fit=dict(accepted=True, peak_width_s=600.0))}
    fitted = {"p1": dict(utc="2024-03-25T16:30:00Z", method="correlate")}
    lop = P.place(shot, fitted, skew, fixes=run)[0]["uncertainty_m"]
    mid = P.place(shot, fitted, even, fixes=run)[0]["uncertainty_m"]
    check("and a peak lying to one side of its winner makes the longer ring",
          lop > 1.8 * mid, f"{lop} m against {mid} m centred")

    # A drive reconstructed from the map is one the map allows.
    import roads
    check("a van does not go against a one-way street or down a private road",
          [roads.directions(t) for t in ({"oneway": "yes"}, {"oneway": "-1"},
                                         {"access": "private"}, {},
                                         {"junction": "roundabout"})]
          == [(True, False), (False, True), (False, False), (True, True), (True, False)]
          and roads.directions({"oneway": "yes"}, walking=True) == (True, True))
    legal = set()
    for el in roads.fetch_roads().get("elements", []):
        tags = el.get("tags", {})
        if tags.get("highway") not in roads.DRIVABLE:
            continue
        fwd, back = roads.directions(tags)
        geom = [roads._key(g["lat"], g["lon"]) for g in el.get("geometry") or []]
        for a, b in zip(geom, geom[1:]):
            if fwd:
                legal.add((a, b))
            if back:
                legal.add((b, a))
    drive, dist = roads.route((trip.AIRPORT[1], trip.AIRPORT[0]),
                              (trip.HOTEL[1], trip.HOTEL[0]))
    steps = [roads._key(lat, lon) for lon, lat in drive[1:-1]]
    wrong = [(a, b) for a, b in zip(steps, steps[1:]) if (a, b) not in legal]
    check("the airport drive runs the way every street on it runs",
          not wrong and 6000 < dist < 6400, f"{len(wrong)} steps against, {dist:.0f} m")
    was, roads.ROUTE_VERSION = roads.ROUTE_VERSION, roads.ROUTE_VERSION + 1
    try:
        bumped = roads._source_digest(roads.DRIVABLE)
    finally:
        roads.ROUTE_VERSION = was
    check("a cached route is keyed on the roads and the router that made it",
          bumped != roads._source_digest(roads.DRIVABLE)
          and roads._source_digest(roads.DRIVABLE) != roads._source_digest(roads.WALKABLE))

    # A fix thrown out as a spike sets no speed record.
    jump = [(noon, 26.5, -77.0, 5.0),
            (noon + timedelta(seconds=5), 26.6, -77.0, 70.0),
            (noon + timedelta(seconds=10), 26.50005, -77.0, 6.0)]
    trip.read_fixes = lambda stem: (jump, 0)
    try:
        best = trip.load_day("x")["max_kn"]
    finally:
        trip.read_fixes = real_read
    check("the best speed is the best of the fixes that were kept", best == 6.0, str(best))
    import corroborate
    check("the cross-check reads the same road fixes placement does",
          len(corroborate.all_fixes()) == len(P.track()),
          f"{len(corroborate.all_fixes())} against {len(P.track())}")

    # Two more things a build that renders nothing must not publish beside.
    with tempfile.TemporaryDirectory() as t:
        for s in (D.THUMB, D.VIEW):
            os.makedirs(os.path.join(t, s["name"]))
        with open(os.path.join(t, D.LEGACY_MANIFEST), "w") as fh:
            fh.write("{}")
        check("a manifest left inside the media folder is not publishable",
              D.stale([], t, os.path.join(t, "m.json")) == [D.LEGACY_MANIFEST])
        zpath = os.path.join(t, "a.zip")
        b = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(b, "JPEG")
        with zipfile.ZipFile(zpath, "w") as zf:
            zf.writestr("x.jpg", b.getvalue())
        info = zipfile.ZipFile(zpath).getinfo("x.jpg")
        right = D.one(("p0", zpath, "x.jpg", t, (), info.CRC, info.file_size))
        other = D.one(("p1", zpath, "x.jpg", t, (), info.CRC + 1, info.file_size))
        check("a photograph is rendered only from the bytes that were indexed",
              right[3] is None and right[2] == 2 and other[2] == 0
              and "not the file" in (other[3] or ""), f"{right} {other}")

    # float() takes "nan" for a number, and a hemisphere is one of four letters.
    from map.photo_index import _dms
    with tempfile.TemporaryDirectory() as t:
        log = os.path.join(t, "GPS_y.log")
        with open(log, "w") as fh:
            fh.write(nmea("GPRMC,120000.00,A,2630.000,N,07700.000,W,nan,0.0,250324,,,A"))
            fh.write(nmea("GPRMC,120001.00,A,2630.000,?,07700.000,W,1.0,0.0,250324,,,A"))
            fh.write(nmea("GPGGA,120002.00,2630.000,N,07700.000,W,1,08,nan,1.0,M,,M,,"))
            fh.write(nmea("GPRMC,120002.00,A,2630.000,N,07700.000,W,1.0,0.0,250324,,,A"))
        rows = parse_nmea.parse_file(log)
    check("a speed that is not a number and a hemisphere that is not one cost a fix",
          len(rows) == 1 and rows[0][3] == 1.0 and rows[0][7] == 99.0, str(rows))
    check("a camera position needs a real hemisphere and real minutes",
          [_dms((26, 30, 0), r) for r in ("N", "S", None, "?")] == [26.5, -26.5, None, None]
          and _dms((26, 75, 0), "N") is None and _dms((26, float("nan"), 0), "N") is None)

    # Two files of one name in one archive are two photographs; one in each
    # archive is one photograph twice, even with the clock corrected in one.
    from map.photo_index import same_photograph

    def member(arch, path, crc, when):
        return dict(archive=arch, member=path, size=crc, crc=crc, ext=".jpg",
                    tags=dict(time_local=when, make="Apple", model="iPhone 14"))
    two = same_photograph([member("crew", "a/IMG_1.JPG", 1, "2024:03:24 10:00:00"),
                           member("crew", "b/IMG_1.JPG", 2, "2024:03:25 16:00:00"),
                           member("mine", "IMG_1.JPG", 3, "2024:03:25 16:00:00")])
    fuji = same_photograph([member("crew", "DSCF1.JPG", 1, "2024:03:24 10:00:00"),
                            member("mine", "DSCF1.JPG", 2, "2024:03:25 02:15:00")])
    dupe = same_photograph([member("crew", "a/IMG_1.JPG", 1, "2024:03:24 10:00:00"),
                            member("crew", "b/IMG_1.JPG", 1, "2024:03:24 10:00:00")])
    check("two files of one name in one archive are kept as two photographs",
          [sorted(c["member"] for c in part) for part in two]
          == [["a/IMG_1.JPG"], ["IMG_1.JPG", "b/IMG_1.JPG"]], str(two))
    check("one in each archive is one photograph, whatever their clocks say",
          len(fuji) == 1 and len(fuji[0]) == 2 and len(dupe) == 1)

    # A cell the depth service has nothing for is not 400 m of water.
    import numpy as np
    real_open, real_path = DP.urllib.request.urlopen, DP.cache_path

    class Reply(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False
    ascii_grid = ("ncols 2\nnrows 2\nxllcorner -77.0\nyllcorner 26.0\ncellsize 0.5\n"
                  "NODATA_value -9999\n-2 -9999\n-4 1\n")
    with tempfile.TemporaryDirectory() as t:
        DP.urllib.request.urlopen = lambda *a, **k: Reply(ascii_grid.encode())
        DP.cache_path = lambda which="wide": os.path.join(t, "g.npz")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                DP.fetch("wide", force=True)
            g = DP.Grid("wide", path=os.path.join(t, "g.npz"))
        finally:
            DP.urllib.request.urlopen, DP.cache_path = real_open, real_path
    check("a depth cell with no data is kept as unknown, not as deep water",
          g.depth.tolist() == [[2.0, DP.NO_DEPTH_M], [4.0, -1.0]] and g.missing == 1,
          f"{g.depth.tolist()} {g.missing}")

    # A fix takes the quality reported in its own burst, not whichever GGA last
    # carried the same time of day. A log two days long has two noons.
    def burst(hms, date, q):
        return (nmea(f"GPGGA,{hms},2630.000,N,07700.000,W,{q},08,1.0,1.0,M,,M,,")
                + nmea(f"GPRMC,{hms},A,2630.000,N,07700.000,W,1.0,0.0,{date},,,A"))
    with tempfile.TemporaryDirectory() as t:
        log = os.path.join(t, "GPS_z.log")
        with open(log, "w") as fh:
            fh.write(burst("120000.00", "240324", 1))
            for k in range(60):                       # an afternoon between them
                fh.write(burst(f"13{k:02d}00.00", "240324", 1))
            fh.write(burst("120000.00", "250324", 6))
            # and one fix on the second day whose GGA never arrived
            fh.write(nmea("GPRMC,130000.00,A,2630.000,N,07700.000,W,1.0,0.0,250324,,,A"))
            # two inside one second, the second of them dead reckoning
            fh.write(burst("140000.00", "250324", 1))
            fh.write(burst("140000.50", "250324", 6))
        got = {r[0].strftime("%d %H:%M:%S"): r[5] for r in parse_nmea.parse_file(log)}
    check("a fix takes the quality of its own burst, across days and within a second",
          (got["24 12:00:00"], got["25 12:00:00"], got["25 13:00:00"], got["25 14:00:00"])
          == (1, 6, 0, 1), str({k: v for k, v in got.items() if k[3:5] != "13" or k[:2] == "25"}))

    # The browser check is one failed check or one skip, never a traceback that
    # takes the rest of the suite's verdict with it.
    import shutil
    import subprocess
    real, before = subprocess.run, (len(_fail), _pass)
    script = os.path.join(C.HERE, "map", "browser_check.js")

    def late(cmd, **kw):
        if script in cmd:
            raise subprocess.TimeoutExpired(cmd, kw.get("timeout"))
        return real(cmd, **kw)
    subprocess.run, said, raised = late, io.StringIO(), None
    try:
        with contextlib.redirect_stdout(said):
            test_browser()
    except subprocess.TimeoutExpired as e:
        raised = e
    finally:
        subprocess.run = real
    ran = "SKIP" not in said.getvalue()
    recorded = _fail[before[0]:] == ["the browser check ran to the end"]
    del _fail[before[0]:]
    if ran:
        check("a browser check that never answers is one failed check",
              raised is None and recorded,
              "" if recorded else said.getvalue().strip()[-200:])
        skip = subprocess.run(["node", script, "http://127.0.0.1:9/"], cwd=C.HERE,
                              capture_output=True, text=True, timeout=60,
                              env=dict(os.environ, CHROME="/nonexistent/chrome"))
        check("a machine with the driver and no browser skips it",
              skip.returncode == 0 and '"skip"' in skip.stdout, skip.stdout[-200:])


def test_build_refuses_first():
    """A build that has to stop for stale media stops before it writes."""
    import contextlib
    import io
    import tempfile
    from map import build as B
    section("a refused build")
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(os.path.join(t, "media", "view"))
        os.makedirs(os.path.join(t, "media", "thumb"))
        with open(os.path.join(t, "media", "thumb", "p99999.jpg"), "wb") as fh:
            fh.write(b"x")
        wrote, real = [], (B.E.export, B.copy_site, sys.argv)
        B.E.export = lambda *a, **k: wrote.append("data") or {}
        B.copy_site = lambda *a, **k: wrote.append("site") or []
        sys.argv = ["build", "--reuse-index", "--out", t]
        stopped = None
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                B.main()
        except SystemExit as e:
            stopped = str(e)
        finally:
            B.E.export, B.copy_site, sys.argv = real
        left = sorted(os.listdir(t))
    check("a build that must refuse stale media refuses before it writes anything",
          bool(stopped) and "has been changed" in stopped and not wrote and left == ["media"],
          f"{wrote} {left} {(stopped or '')[:80]}")


def main():
    test_units()
    test_edges()
    spans = test_coverage()
    test_stories()
    test_derive_cache()
    test_fit_uses_the_reading_that_won()
    test_honest_uncertainty()
    test_receiver_windows()
    test_track_notes()
    test_journal()
    test_land_cache_follows_its_source()
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
        test_gaps(photos, placed)
        test_nothing_published_carries_metadata(placed)
        test_build_refuses_first()
    test_site_build()
    test_browser()

    print(f"\n{_pass} passed, {len(_fail)} failed")
    if _fail:
        for f in _fail:
            print(f"  failed: {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
