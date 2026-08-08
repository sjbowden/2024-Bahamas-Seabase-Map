# Interactive map — design

An unlisted, zoomable chart of the 2024 Sea Base 1830 trek, carrying the crew's
photographs placed on the boat's track.

The printed poster answers "where did we go". This answers "what happened
there" — 2,505 photographs from eleven cameras, positioned against 42,510 GPS
fixes, on a chart you can zoom into.

## Decisions

| | |
|---|---|
| Audience | Unlisted link — the crew and their families |
| Hosting | Cloudflare Pages or Netlify, but **portable**: no platform features, so moving to a self-hosted box is a file copy |
| Core interaction | Free exploration, chart-plotter style, with toggleable layers |
| Media | All 2,505 photographs, two sizes (~920 MB). Videos out of scope |
| Uncertainty | Surfaced, quietly — an estimated position never masquerades as a measured one |
| Travel photos | Browsable, not pinned |

## Shape of the system

Two halves that never run at the same time.

```
  ARCHIVES (local, never published)
  Seabase 2024.zip · Seabase 2024-1-001.zip · GPSFILES/ · geo/
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
from `abaco_geo.py`, day metadata and the quality filter from the shared trip
module, the barrier test from `corroborate.py`. The poster and the map stay in
agreement because they read the same source. A track fix corrects both.

**The archives are never unpacked.** The build streams EXIF headers and image
data straight out of the zips. Reading 845 headers takes 1.8 s.

`site_build/` is a build artifact of roughly 1 GB across ~5,000 files. It must
not enter git — re-committing rendered output is what took this repo's history
to 510 MB once already.

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
photographs all carry GPS needs no fit** — this is what the Mavic Mini taught
(below).

- **With anchors** — search offsets across ±6 h coarsely, refine to 5 s,
  minimising median distance between each photograph's own GPS and the track
  position at the corrected time. Record the residual. This method returned
  exactly +0 min at 10 m median for 436 iPhone 15 Pro photographs.
- **Without anchors** — score candidate offsets by plausibility: what fraction
  of that camera's photographs land near the track, inside hours the receiver
  was actually recording. Best score wins; marked `inferred`.

### The refusal rule

The Mavic Mini fit suggested **+125 min** — from three usable points, because
the drone shots are from the Lynyard Cay evening and that shift pushes them past
the receiver's 20:05 shutdown. Worse, a drone flies away from the boat, so
minimising the distance between drone GPS and boat track optimises toward a
false assumption.

**An offset is applied only with ≥5 anchors and a residual under ~150 m.** Below
that the camera stays uncalibrated and its photographs drop a tier. A confident
wrong answer is worse than an admitted uncertain one.

### Tiers

| tier | meaning | source |
|---|---|---|
| `gps` | where the **camera** was | its own EXIF coordinates |
| `calibrated` | where the **receiver** was | timestamp + a fitted, validated offset |
| `inferred` | where the receiver probably was | timestamp + a plausibility-fitted offset |
| `unplaced` | unknown | no timestamp, or no plausible fit |

Positions come from **interpolation between bracketing track fixes**, not the
nearest fix. At 5 kn, nearest-fix lookup is needlessly ~10 m out.

### What placement cannot know

A time-placed photograph is put where the **GPS receiver** was, not where the
camera was. Much of this trip happened ashore — Hope Town, Little Harbour,
Great Guana, Tahiti Beach, the hotel, the walk to the marina. When the crew went
ashore and the receiver stayed aboard, a photograph taken in the village is
pinned to the anchorage a few hundred metres offshore.

This is irreducible. It is handled by being explicit rather than by pretending:
the viewer says *"placed from the boat's track at 14:32 — may have been taken
nearby ashore"* for time-placed photographs, and states the camera's own
position for `gps` ones. Those are different claims and the interface makes the
difference legible.

### Guards

The guard differs by tier, because the failure modes are different.

**For `gps` photographs the only test is the chart region.** Distance from the
boat's track is *not* a rejection criterion — a photograph taken ashore in Hope
Town while the boat lay anchored offshore is several hundred metres from the
track and is entirely correct. Its own GPS beats the track, which is the point.

**For time-placed photographs the test is temporal, not spatial.** Interpolation
puts them on the track by construction, so no distance check can fire. What can
fail is the *time*: the receiver died each evening and charged overnight, so a
corrected timestamp may land in a gap where there is nothing to interpolate.

- If the **inReach** covers that moment and its bracketing points are ≤20 min
  apart, interpolate from it instead — tier `inferred`, since the tracker's
  cadence is coarser. This is the overnight and flat-battery cover the handheld
  cannot give.
- If the inReach is on its 4-hourly overnight cadence, the interpolation would
  be worthless. `unplaced`.
- Outside every source's coverage — `unplaced`.

**Not "on land".** Most of the cays are land, and the crew was on them.

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

**Layers, all toggleable**

- **Chart** — land, shoal halos, water in the poster's palette. Shoals are
  pre-computed at build time; that buffering work is already solved in
  `abaco_geo.py` and is slow to redo in a browser.
- **Tracks** — seven days in poster colours, each independently toggleable, all
  drawn **true**. The lateral offset was a compromise for one fixed print scale;
  zoom solves the crowding properly.
- **Places** — towns, cays, anchorages, airport, marina, hotel, revealed
  progressively with zoom so the chart never crowds.
- **Photographs** — clustered points that split as you zoom.
- **Overnight track** — inReach positions, off by default. The only evidence of
  where the boat sat overnight.

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

## Code layout

```
trip.py                shared: DAYS, load_day(), haversine(), EDT, barrier test
poster.py              imports trip
corroborate.py         imports trip
map/
  build.py             CLI orchestrator
  photo_index.py       walk the zips, read EXIF headers
  clock_fit.py         per-camera offset, tier assignment
  place.py             interpolate positions, apply guards
  derive.py            thumbnails and viewing copies
  export.py            GeoJSON + photos.json
  site/                web app source
site_build/            OUTPUT — gitignored
```

**One refactor, and only this one.** `DAYS`, `load_day()`, `haversine()` and the
barrier test live in `poster.py` today. Importing that module pulls in
matplotlib and runs font registration, so a photo-indexing script would drag in
the whole poster renderer and emit font warnings. Extracting them into `trip.py`
keeps one definition of a sailing day rather than two that drift.

## Failure modes

| failure | response |
|---|---|
| Archive moved | Path is a CLI argument; missing gives a clear error |
| HEIC unreadable (95 files) | Needs `pillow-heif`; absent, they are listed as unreadable, not fatal |
| Filename collision | Size and hash compared before transplanting GPS |
| No timestamp and no GPS | `unplaced`, still browsable |
| Interrupted build | Derivatives are idempotent; re-running resumes |

## Testing

In order of value:

1. **Synthetic offsets** — inject a known clock error into real photographs and
   confirm the fitter recovers it. This tests the component most likely to be
   quietly wrong.
2. **Hold-out validation** — fit each GPS-bearing camera on part of its
   photographs, measure error on the rest.
3. **Regression** — the iPhone 15 Pro must keep fitting to ~0 min at ~10 m.
   Known-good answer, cheap to assert.
4. **Invariants** — every photograph appears exactly once across
   placed/unplaced/travel; every photograph has a tier; every path in
   `photos.json` resolves to a file that exists.

## Milestones

The build and the site are separable, and the build is where the risk lives.

1. **Shared trip module** — extract `trip.py`, confirm poster output is
   byte-identical afterwards. Small, and everything else depends on it.
2. **Index and calibrate** — `photo_index` + `clock_fit`, with the synthetic
   offset and hold-out tests. Ends with a report: photographs per tier, offset
   and residual per camera. This is the point at which we learn whether the
   crew's eleven clocks are tractable, before a single derivative is generated.
3. **Place and export** — `place` + `export`, producing the GeoJSON and
   `photos.json` with no media.
4. **The map, with data but no photographs** — chart, tracks, places, layers.
   Verifiable on its own.
5. **Derivatives and photographs on the map** — `derive`, then pins, clusters,
   viewer and tray. The 900 MB step comes last, once placement is trusted.
6. **Deploy** — unlisted, then confirm a plain `python -m http.server` over the
   same folder behaves identically, which is the portability guarantee.

Milestone 2 is the natural stop-and-look point: if a camera's clock cannot be
calibrated, that is better known before generating its derivatives.

## Out of scope

- **Videos** — 659 files, several GB even transcoded. Photographs first.
- **A time scrubber or animation** — free exploration was chosen over a
  prescribed narrative.
- **A second map for the Portland legs** — travel photographs stay browsable
  rather than plotted.
