# Interactive map — design

An unlisted, zoomable chart of the 2024 Sea Base 1830 trek, carrying the crew's
photographs placed on the boat's track.

The printed poster answers "where did we go". This answers "what happened
there" — 2,505 photographs from eleven cameras, positioned against 42,510 GPS
fixes, on a chart you can zoom into.

## Decisions

| | |
|---|---|
| Audience | Unlisted link — the crew and their families, who will forward it, which is fine |
| Hosting | Cloudflare Pages, but **portable**: no platform features, so moving to a self-hosted box is a file copy |
| Core interaction | Free exploration, chart-plotter style, with toggleable layers |
| Media | All 2,505 photographs, two sizes (~920 MB). Videos out of scope |
| Uncertainty | Surfaced, quietly — an estimated position never masquerades as a measured one |
| Travel photos | Browsable, not pinned |

## Shape of the system

Two halves that never run at the same time.

```
  ARCHIVES (local, never published)
  photos/Seabase 2024.zip · photos/Seabase 2024-1-001.zip · GPSFILES/ · geo/
                         │
                         ▼
  BUILD (Python, offline, on your machine)
    photo_index → clock_fit → place → derive → export
                         │
                         ▼
  site_build/          ← plain static files, gitignored
    index.html  app.js  style.css
    data/   coast.geojson  shoals.geojson  tracks.geojson
            places.geojson  photos.json
    media/  thumb/<id>.jpg   view/<id>.jpg
                         │
                         ▼
  DEPLOY  ← upload the folder
```

**The browser never computes placement.** Every position, confidence tier and
clock correction is resolved during the build and baked into `photos.json`. The
site draws what it is told. The hard logic stays in Python where it can be
tested against the real track, and the site keeps zero runtime dependencies —
no API, no functions, no third-party tiles. Changing hosts is a copy.

**The build reuses existing code** rather than reimplementing it: land polygons
from `abaco_geo.py`, the shoal buffer and the sailing-day metadata from the
shared trip module, the barrier test from `corroborate.py`. The poster and the
map stay in agreement because they read the same source. A track fix corrects
both.

**The archives are never unpacked.** The build streams EXIF headers and image
data straight out of the zips in `photos/` — 32 GB, on the Linux filesystem
rather than across the Windows mount, which matters once the derivative pass
starts moving image bodies rather than headers. Reading 845 headers takes 1.8 s;
the 1600 px pass is a different order of work and should be measured, not
extrapolated from that.

`site_build/` is a build artifact of roughly 1 GB across ~5,000 files. Neither
it nor `photos/` may enter git — re-committing rendered output is what took this
repo's history to 510 MB once already. Both are in `.gitignore`.

## The track

Placement reads the receiver differently from the way the poster draws it, and
conflating the two is the easiest way to get this quietly wrong.

`load_day()` exists to *plot*. It thins to 22 m between plotted points and
splits the walk to the marina and the van to the airport into separate lists.
Measured, that takes 42,510 quality-filtered fixes down to 5,201:

| day | plotted | walk | road | quality-filtered |
|---|---|---|---|---|
| Fri 22 Mar | 68 | — | — | 1,489 |
| Sat 23 Mar | 175 | 42 | — | 6,507 |
| Sun 24 Mar | 1,315 | — | — | 8,938 |
| Mon 25 Mar | 1,242 | — | — | 8,559 |
| Tue 26 Mar | 1,043 | — | — | 7,648 |
| Wed 27 Mar | 1,340 | — | — | 7,731 |
| Thu 28 Mar | 18 | — | 26 | 1,638 |
| | **5,201** | | | **42,510** |

The thinning is spatial, so it costs *time* resolution precisely where the boat
sat still — which is precisely where the crew was ashore with cameras. Thursday
is 18 points across 2 h 42 m. Interpolating a 15:30 photograph between a 13:00
and a 17:00 fix is not a position.

So `trip.py` exposes **`read_fixes(stem)`**: quality-filtered, full cadence, no
thinning, and every segment in one time-ordered stream. The walk/road split is a
cartographic distinction — the receiver's position is the receiver's position
whether it was on a boat, on foot or in a van, and a photograph taken during
Saturday's walk to the marina must not come back `unplaced` from a track that
covers it. `load_day()` becomes a thin wrapper over `read_fixes()` so the poster
is unaffected.

Two consequences for the fitter, both easy to miss:

- **Anchors must come from moving stretches.** Shifting a clock offset along a
  stationary hour changes the distance metric by nothing, so hours at anchor
  contribute no gradient and dilute the median. Anchors are restricted to fixes
  with `sog_kn > MOVING_KN`, and the ≥5 anchor threshold below counts
  *informative* anchors, not merely available ones.
- **Fit against `read_fixes()`, never `load_day()`.** A 22 m-quantised track
  puts a floor under the residual, well above the 10 m the iPhone actually
  achieved.

## Placement

The whole design turns on one question: where was each photograph taken?

### Sources

- **Crew archive** — 2,479 images, the superset. GPS mostly stripped; ~97.5%
  retain timestamps; 11 camera models.
- **Your archive** — 845 images, 819 of them also in the crew archive, with GPS
  intact on 499.

Photographs join on filename, guarded by size and hash so a coincidental name
clash cannot attach one photo's coordinates to another. The crew archive
supplies pixels; yours supplies GPS where the crew copy was stripped. That
restores coordinates to 819 photographs and, more valuably, spreads calibration
anchors across the week.

### Camera identity

Cameras group by EXIF **serial number**, falling back to model. Two crew
members with iPhone 15 Pros are two independent clocks; grouping by model would
average their offsets into an answer wrong for both.

### Fitting a clock

Only for cameras that have GPS-less photographs to place. **A camera whose
photographs all carry GPS needs no fit.**

- **With anchors** — search offsets across ±6 h coarsely, refine to 5 s,
  minimising median distance between each photograph's own GPS and the track
  position at the corrected time. Record the residual. This method returned
  exactly +0 min at 10 m median for 436 iPhone 15 Pro photographs.
- **Without anchors** — score candidate offsets by plausibility: what fraction
  of that camera's photographs land near the track, inside hours the receiver
  was actually recording. Best score wins; marked `inferred`.

### The refusal rule

**An offset is applied only with ≥5 informative anchors and a residual under
~150 m, and only when the anchor residuals look like noise rather than a bias.**
Below that the camera stays uncalibrated and its photographs drop a tier. A
confident wrong answer is worse than an admitted uncertain one.

The last clause is the one that earns its keep, and the Mavic Mini is why. Its
fit suggested **+125 min** from three usable points, shoving the Lynyard Cay
evening shots past the receiver's shutdown. The count test catches that
particular case, but the count test is not what was actually wrong: a drone
flies *away* from the boat, so minimising the distance between drone GPS and
boat track optimises toward a false assumption. A drone with twenty anchors and
a 120 m residual passes a count-and-magnitude gate and is still wrong. What
distinguishes it is that its residuals carry a direction — offset from the track
in a consistent sense — where a genuine clock error leaves residuals scattered.
Test the shape of the residuals, not just their size.

(In the event the Mavic needs no fit at all: every drone frame carries GPS. The
rule exists for the cameras with *partial* GPS, where a plausible-looking fit
gets applied to the rest.)

### Tiers

| tier | meaning | source |
|---|---|---|
| `gps` | where the **camera** was | its own EXIF coordinates |
| `bracket` | where the **camera** almost certainly was | interpolated between two of *that camera's own* GPS photographs |
| `calibrated` | where the **receiver** was | timestamp + a fitted, validated offset |
| `inferred` | where the receiver probably was | timestamp + a plausibility-fitted offset |
| `unplaced` | unknown | no timestamp, or no plausible fit |

Positions come from **interpolation between bracketing fixes**, not the nearest
one. At 5 kn, nearest-fix lookup is needlessly ~10 m out.

**The `bracket` tier is the one worth adding.** A GPS-less photograph sitting 40
seconds after one of its own camera's GPS photographs and 30 seconds before the
next, with those two 30 m apart, belongs between them — not on a boat lying 400 m
offshore. Same camera, same person, same walk through the village. It needs no
clock fit, because the camera's clock is self-consistent whatever it reads.

Applied when both brackets are from the same camera, ≤2 min away in time and
≤200 m apart from each other. Its reach is bounded by which cameras have
*partial* GPS coverage — your iPhone, with 499 of 845, is the clear case; the
crew's fully-stripped cameras get nothing from it. **How many photographs it
actually reaches is a build-time measurement, reported by milestone 2.** If the
answer is a handful, it is still the highest-quality handful on the chart.

### What placement cannot know

A time-placed photograph is put where the **GPS receiver** was, not where the
camera was. Much of this trip happened ashore — Hope Town, Little Harbour,
Great Guana, Tahiti Beach, the hotel, the walk to the marina. When the crew went
ashore and the receiver stayed aboard, a photograph taken in the village is
pinned to the anchorage a few hundred metres offshore.

The `bracket` tier reclaims part of this, and only part: it works where the
camera itself recorded position often enough to fence the gap. Beyond its reach
the limit is irreducible, and is handled by being explicit rather than by
pretending. The viewer says *"placed from the boat's track at 14:32 — may have
been taken nearby ashore"* for track-placed photographs, and states the camera's
own position for `gps` and `bracket` ones. Those are different claims and the
interface makes the difference legible.

Where the boat was demonstrably stationary through the surrounding window, the
note names the anchorage — *"at anchor off Hope Town"* — rather than implying a
metre-level position the method cannot support.

### Guards

The guard differs by tier, because the failure modes are different.

**For `gps` and `bracket` photographs the only test is the chart region.**
Distance from the boat's track is *not* a rejection criterion — a photograph
taken ashore in Hope Town while the boat lay anchored offshore is several
hundred metres from the track and is entirely correct. Its own GPS beats the
track, which is the point.

**For track-placed photographs the test is temporal, not spatial.**
Interpolation puts them on the track by construction, so no distance check can
fire. What can fail is the *time*: the receiver died each evening and charged
overnight, so a corrected timestamp may land in a gap where there is nothing to
interpolate. **A timestamp outside the receiver's coverage is `unplaced`.**

**Not "on land".** Most of the cays are land, and the crew was on them.

**The inReach is not a placement source.** It was going to be the overnight and
flat-battery cover, interpolated wherever its bracketing points fell within 20
minutes. Measured against the 150 points in `geo/inreach.gpx`, that rule buys
almost nothing:

- 19.3 h of ≤20-minute-bracketed coverage across a 107.6 h span
- overnight, 2 usable intervals out of 14 — the rest is the 4-hourly cadence
- intervals that are both ≤20 min apart *and* outside handheld coverage: **one,
  totalling 0.17 h**

Both devices were recording while the boat sailed, so the fallback overlaps what
the handheld already gives. The single genuine intra-day hole — 28 minutes on
Fri 22 Mar — falls before the inReach track begins at 23 Mar 14:39 Z. A tier, a
threshold and a guard branch for ten minutes of coverage is not worth its
weight. The inReach stays as a **map layer**, where showing the boat's overnight
berth earns its place on its own terms.

**Travel photographs** — 41 with GPS sit outside the Bahamas, plus GPS-less ones
on the same dates. Tagged `travel`, kept out of the Abaco chart (Portland on a
Sea of Abaco chart is nonsense), browsable in the tray.

### Derivatives

Streamed from the zips, never unpacked:

| | size | total |
|---|---|---|
| thumbnail | 256 px, q72 | ~38 MB |
| view | 1600 px, q82 | ~880 MB |

EXIF is **stripped from both** — no GPS, no serial numbers on anything
published. Generation is idempotent, so an interrupted build resumes.

## The map

**Renderer — MapLibre GL, not Leaflet.** This is forced by the geometry, not
taste. The land is 1,370 polygons and 117,850 exterior vertices; Leaflet draws
GeoJSON as SVG paths, and that many nodes will not pan smoothly on a phone,
which is the stated target. A GL renderer handles it. No third-party tiles
either way — the chart is our own GeoJSON.

**Levels of detail.** `geo/coastline.json` alone is 6.5 MB, and the shoals are
two buffer operations on the same geometry. Shipped raw, the chart layer is the
better part of 10 MB that a phone must fetch and parse before drawing anything.
So the build emits 2–3 zoom bands per layer, simplified with shapely
`.simplify()` at roughly half a pixel for the band's scale, dropping polygons
below a pixel of area at the coarsest. Cheap in Python, done once.

**Layers, all toggleable**

- **Chart** — land, shoal halos, water in the poster's palette. Shoals are
  pre-computed at build time; that buffering is already solved and is slow to
  redo in a browser.
- **Tracks** — seven days in poster colours, each independently toggleable, all
  drawn **true**. The lateral offset was a compromise for one fixed print scale;
  zoom solves the crowding properly. Drawn from the thinned `load_day()` output,
  which is what thinning is for.
- **Places** — towns, cays, anchorages, airport, marina, hotel, revealed
  progressively with zoom so the chart never crowds.
- **Photographs** — clustered points that split as you zoom.
- **Overnight track** — inReach positions, off by default. The only evidence of
  where the boat sat overnight. Display only; nothing is placed from it.

**Interaction** — cluster → zoom splits it → pin opens the viewer. The viewer
shows image, time, day, camera and placement note, with previous/next moving in
**time order**, so paging follows the day as it happened rather than wandering
by proximity.

**Tray** — what is not pinned: unplaced and travel photographs, grouped by day
and camera.

**Phones first.** The crew will open this from a text message. Layer controls
collapse to a sheet, the viewer goes full-screen, thumbnails load only for what
is on screen.

**Scale bar, no compass rose.** The rose is a signature of the printed sheet,
but on a north-up zoomable map it is decoration needing redrawing at every
scale. A scale bar responds to zoom and earns its place. The two artefacts are
tied together through palette and typography instead.

**Fonts** — Lato is OFL and fine to self-host. P052 is not served; it is paired
with a cleanly-licensed serif or a system stack, matching the poster in spirit
rather than transplanting its fonts.

## Publishing

The link is unlisted and will be forwarded, which is the point of sending it.
Two consequences worth handling anyway:

- **`X-Robots-Tag: noindex`** plus a `robots.txt`. Forwarding is expected;
  turning up in search results for "Sea Base 2024" is not, and the cost of
  preventing it is one header. No obfuscated URL — a path nobody can type is
  friction for the crew and buys nothing against a link that gets shared by
  design.
- **Cloudflare Pages over Netlify**, on bandwidth. A full browse of the view
  copies is most of a gigabyte; Netlify's free tier meters at around 100 GB a
  month, which a hundred browses would reach, and Pages does not meter. This
  changes nothing about portability — no platform features are used either way,
  which milestone 6 verifies.

EXIF is already stripped from every published derivative, so no serial number or
original coordinate leaves the build regardless of who holds the link.

## Code layout

```
trip.py                shared: DAYS, read_fixes(), load_day(), haversine(),
                       EDT, shoal buffer, barrier test
poster.py              imports trip
corroborate.py         imports trip
map/
  build.py             CLI orchestrator
  photo_index.py       walk the zips, read EXIF headers
  clock_fit.py         per-camera offset, tier assignment
  place.py             bracket + interpolate positions, apply guards
  derive.py            thumbnails and viewing copies
  export.py            GeoJSON + photos.json
  site/                web app source
photos/                ARCHIVES — gitignored, read in place
site_build/            OUTPUT — gitignored
```

**One refactor, and only this one** — but it is slightly larger than an
extraction. `DAYS`, `load_day()`, `haversine()`, the barrier test and `_shoal()`
move into `trip.py`, and `read_fixes()` is added underneath `load_day()` as
described above. `_shoal()` has to come along: it lives in `poster.py` today,
and the map needs it, and importing `poster` pulls in matplotlib and runs font
registration — which is the whole reason for the split. It depends on shapely
only, so it moves cleanly.

## Failure modes

| failure | response |
|---|---|
| Archive moved | Path is a CLI argument defaulting to `photos/`; missing gives a clear error |
| HEIC unreadable (95 files) | Needs `pillow-heif`; absent, they are listed as unreadable, not fatal |
| Filename collision | Size and hash compared before transplanting GPS |
| No timestamp and no GPS | `unplaced`, still browsable |
| Timestamp outside receiver coverage | `unplaced` — no inReach fallback |
| Interrupted build | Derivatives are idempotent; re-running resumes |

## Testing

In order of value:

1. **Synthetic offsets** — inject a known clock error into real photographs and
   confirm the fitter recovers it. This tests the component most likely to be
   quietly wrong.
2. **Anchor starvation** — take a camera with plenty of anchors, hide all but
   three so it fails the ≥5 gate, and confirm the anchorless plausibility
   fitter recovers the offset the anchored fit found. This is the only test that
   exercises the `inferred` path, which is the path shipping positions nobody
   can check.
3. **Regression** — the iPhone 15 Pro must keep fitting to ~0 min at ~10 m
   against `read_fixes()`. Known-good answer, cheap to assert.
4. **Hold-out** — fit each GPS-bearing camera on part of its photographs,
   measure error on the rest. Worth having as a sanity check, but note what it
   does *not* prove: a camera with GPS is tier `gps` and its fit is never used.
   The cameras that depend on fitting have no ground truth by construction, and
   no test can supply one. Test 2 is the closest available substitute.
5. **Invariants** — every photograph appears exactly once across
   placed/unplaced/travel; every photograph has a tier; every path in
   `photos.json` resolves to a file that exists.

## Milestones

The build and the site are separable, and the build is where the risk lives.

1. **Shared trip module** — extract `trip.py` including `_shoal()`, add
   `read_fixes()`, confirm the poster's **PNG** is byte-identical afterwards.
   Not the PDF: matplotlib stamps a wall-clock `/CreationDate` into it, so the
   comparison would fail for a reason having nothing to do with the refactor.
   (Or pin `metadata={'CreationDate': None}` and compare both.) Small, and
   everything else depends on it.
2. **Index and calibrate** — `photo_index` + `clock_fit`, with the synthetic
   offset and anchor-starvation tests. Ends with a report: photographs per tier,
   offset and residual per camera, and **how many photographs the `bracket`
   tier reaches**. This is the point at which we learn whether the crew's eleven
   clocks are tractable, before a single derivative is generated.
3. **Place and export** — `place` + `export`, producing the GeoJSON at each zoom
   band and `photos.json` with no media.
4. **The map, with data but no photographs** — chart, tracks, places, layers, on
   MapLibre. Verifiable on its own, and the point at which the level-of-detail
   budget gets checked on an actual phone rather than a desktop browser.
5. **Derivatives and photographs on the map** — `derive`, then pins, clusters,
   viewer and tray. The 900 MB step comes last, once placement is trusted.
6. **Deploy** — unlisted with `noindex`, then confirm a plain
   `python -m http.server` over the same folder behaves identically, which is
   the portability guarantee.

Milestone 2 is the natural stop-and-look point: if a camera's clock cannot be
calibrated, that is better known before generating its derivatives.

## Out of scope

- **Videos** — 659 files, several GB even transcoded. Photographs first.
- **Original-resolution downloads** — families will want them for their own
  crew member; 32 GB of originals is a different distribution problem, best
  solved by sending a zip to whoever asks.
- **A time scrubber or animation** — free exploration was chosen over a
  prescribed narrative.
- **A second map for the Portland legs** — travel photographs stay browsable
  rather than plotted.
