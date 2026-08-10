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

- **Crew archive** — `photos/Seabase 2024-1-001.zip`, 2,479 images, the superset.
- **Your archive** — `photos/Seabase 2024.zip`, 845 images, 819 also in the
  crew's.

2,505 photographs, indexed in 4.3 s without unpacking 32 GB. Milestone 2 built
this and three of the assumptions above did not survive it:

**There is nothing to transplant.** The crew's copies were said to be stripped of
GPS, with yours donating it back to 819 photographs. Across all 819 shared
photographs there is not one where either copy carries GPS the other lacks. The
premise was simply wrong, and the "restores coordinates to 819" benefit does not
exist.

**Size and hash are the wrong join guard.** 653 of the 819 shared photographs
differ in bytes, because rewriting EXIF rewrites the file — so a content guard
rejects the matches it exists to confirm. Identity is the basename confirmed by
camera model. The zip's own central directory carries a CRC32 per member, which
makes an exact-bytes comparison free where it is actually wanted, with no hashing
of 32 GB.

**The archives disagree about time for 148 photographs** — every one the FinePix,
every one by exactly 975 min. One copy had that camera's clock corrected and the
other did not. Both readings are recorded and flagged rather than picked; the fit
settles it (below).

### Camera identity

Cameras group by EXIF **serial number**, falling back to model — but only the
Canon, the two GoPros and the drone report one. **Every phone leaves the tag
blank**, so eleven cameras collapse to their models, and two crew members with
the same phone would be one clock here. Nothing in the EXIF can separate them;
`camera_key()` names the limit rather than inventing a discriminator.

### Getting to UTC

Everything downstream needs one thing from a timestamp: the real instant, so it
can be looked up against the track. Three methods of decreasing strength, and
each photograph carries the name of the one that resolved it.

| | photographs | how |
|---|---|---|
| `gps_utc` | 490 | `GPSDateStamp`/`GPSTimeStamp` — UTC off the satellites, the camera's clock playing no part |
| `tz_tag` | 1,093 | local minus `OffsetTimeOriginal` |
| `correlate` | 810 | fitted against when every other camera was shooting |
| unresolved | 112 | no timestamp, or no camera to group by |

The design imagined one method — minimise the distance between a photograph's own
GPS and the track position at the corrected time — and it turns out to be needed
for none of them. 490 photographs already know their UTC exactly. Another 1,093
carry a timezone tag, and against the photographs that have both, that tag is
right to a second: median (local − tag − satellite UTC) is **+0.017 min over 480
samples**.

That measurement also kills the idea of one offset per camera. The iPhone 15
Pro's tag reads −07:00 in Portland, −04:00 all week in Abaco, and −07:00 again
flying home. **A camera's offset is not a constant; it is a timezone, and it
moves.** Only cameras with no tag at all get a single fitted number, and only
because they sat in one zone all week.

### Fitting the cameras that have neither

Three cameras carry no GPS and no timezone tag: the Canon (547), the FinePix
(149) and a GoPro (114). For these the design's anchorless method was undefined —
it scores offsets by "what fraction land near the track", and a camera with no
GPS has no position to measure. What these cameras have instead is company:
eleven cameras photographed one week and the crew pointed them at the same things
at the same moments.

So the statistic is **coincidence**: how many of this camera's frames land within
20 s of a frame whose UTC is already known. The offset maximising it is the
offset that makes the clock true, and the null distribution comes free — the same
count evaluated at every other candidate offset in the search.

| camera | coincidences | null | offset | localised to |
|---|---|---|---|---|
| Canon EOS REBEL T3i | 176 / 547 | 27.6 ± 25.0 | +401.4 min | under 30 s |
| FinePix XP90 | 84 / 149 | 8.4 ± 11.7 | −61.2 min | ±10 min |
| GoPro HERO5 | 48 / 114 | 7.5 ± 8.8 | +310.5 min | ±20.5 min |

A third of the Canon's frames sitting within 20 s of somebody else's is not a
coincidence about coincidences. The peak widths differ by two orders of magnitude
and **`place.py` must carry them through**: ±20.5 min is ~3 km of track at 5 kn,
so the GoPro's 114 photographs deserve a visibly wider claim than the Canon's 547.

This also settles the FinePix's rival readings on evidence rather than taste. Both
give the same 84 coincidences — they are the same photographs shifted by a
constant — so the discriminators are coverage (0.953 against 0.906) and
plausibility: as indexed it needs a −61 min clock error, the crew's copy needs
**+15.2 h**, and no clock is set to that.

### The refusal rule

**An offset is applied only when its coincidence count stands clear of the null
and of the best genuinely different hypothesis.** Below that the camera stays
uncalibrated and its photographs drop a tier. A confident wrong answer is worse
than an admitted uncertain one.

Two bars, and two ways of getting them wrong that the tests caught — both fixed
by changing the rule rather than the threshold:

**The search is bounded to ±12 h.** The crew's days look alike, so searched
wider, an offset a whole day out scores nearly as well as the truth. The GoPro's
best peak across ±26 h was −21.4 h, a lag no clock setting can produce. ±12 h is
the widest a clock set to *some* real timezone can be.

**Coverage is not a bar for correctness.** It ranks rival offsets, where it breaks
ties the coincidence count cannot — but photographs taken ashore in the evening
while the receiver sat on its charger are perfectly real. Hiding the iPhone 15
Pro's satellite times and refitting recovers +240.03 min, right to two seconds,
at a coverage of **0.844**. Any floor above that refuses a demonstrably correct
answer, which is the opposite of this rule's job.

The Mavic still needs no fit — every drone frame carries GPS, so it is skipped
before the question arises, which is what it was always going to teach. And the
residual-shape concern it motivated has no purchase here: this method never
measures distance from the track, so a camera that flies away from the boat
cannot bias it.

All 810 fitted photographs currently land at `inferred` rather than `calibrated`.
The Canon misses by a whisker (z = 5.9 against a 6.0 bar) on the strongest
evidence of the three, which says less about the Canon than about `z` being
sensitive to a camera's photograph count. Worth revisiting once `place.py` shows
whether the distinction changes anything a viewer can see; being conservative
costs nothing until then.

### Tiers

| tier | meaning | source |
|---|---|---|
| `gps` | where the **camera** was | its own EXIF coordinates |
| `calibrated` | where the **receiver** was | UTC known exactly, then the track |
| `inferred` | where the receiver probably was | UTC from a fitted offset, then the track |
| `unplaced` | unknown | no UTC, or no track to look it up against |

Positions come from **interpolation between bracketing fixes**, not the nearest
one. At 5 kn, nearest-fix lookup is needlessly ~10 m out.

**The `bracket` tier is gone, and this is why.** The idea was sound: a
GPS-less photograph sitting 40 seconds after one of its own camera's GPS
photographs and 30 seconds before the next, with those two 30 m apart, belongs
between them — not on a boat lying 400 m offshore. Same camera, same person, same
walk through the village, and no clock fit needed because a camera's own
timestamps are self-consistent whatever they read.

Measured, it reaches six photographs, and **all six are in Portland** — bracketed
between two of the iPhone 15 Pro's Oregon photographs on 21 March. They are
`travel`. On the Sea of Abaco its reach is zero.

Which is a correction to the count reported when this tier was added, and it came
from a bug worth recording: the bracket branch did not apply the region guard the
`gps` branch does, so those six were counted as placed and would have plotted on
the Abaco chart at **latitude 45**. The guard is now shared by both branches, and
a test asserts that nothing plotted falls outside the chart.

The reason it earns nothing is structural rather than bad luck: the tier needs a
camera with *partial* GPS coverage, and this set is almost all-or-nothing. The
drone tagged every frame; the Canon, the FinePix, the GoPro and every other phone
tagged none. Only one iPhone is mixed, at 480 of 511, and its untagged frames are
the ones in Portland.

So the placement branch is **removed** — a tier that names nothing has no business
in the exported data or the viewer's legend, and unused code is where the missing
region guard came from in the first place. What stays is
`clock_fit.bracket_reach()`, which measures it every build and prints the number.
If photographs ever arrive from a crew member whose phone tagged intermittently,
that number moves off zero and this is twenty lines to put back.

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

### Where they all landed

Milestone 3 resolved every photograph:

| tier | count | |
|---|---|---|
| `calibrated` | 826 | UTC known exactly, position from the track |
| `inferred` | 786 | UTC from a fitted offset, position from the track |
| `gps` | 471 | the camera's own coordinates, on the chart |
| `unplaced` | 312 | has a UTC, but in a hole where the receiver was not recording |
| `travel` | 110 | away from Abaco — 41 by their own GPS, 69 by their UTC |
| `bracket` | 0 | reaches six photographs, all of them in Portland |

**2,083 photographs plot on the Abaco chart**, every one of them inside its
bounds and carrying a sailing day.

The 312 `unplaced` are not a failure of the fit — they have good timestamps, and
they are the evenings ashore after the receiver went on its charger. That is the
irreducible limit named above, arriving as a number.

### Uncertainty is the boat's behaviour, not the clock's

A photograph's timing is uncertain by its camera's fit width, and the tempting way
to turn that into metres is to multiply by an assumed speed. The honest way is to
ask where the boat *actually was* across that window — sample the track at both
ends of it and measure. Which produces a result the assumed-speed version cannot:

| camera | fit width | median | 90th | worst |
|---|---|---|---|---|
| iPhone 14 Pro | ±2 s | 0 m | 6 m | 7 m |
| Canon EOS REBEL T3i | under 30 s | 8 m | 38 m | 53 m |
| FinePix XP90 | ±10 min | 4 m | 776 m | 924 m |
| GoPro HERO5 | ±20.5 min | 8 m | 1,714 m | 1,868 m |

The FinePix and the GoPro have small medians and enormous tails, because **half
their frames were taken at anchor**, where a twenty-minute timing error costs a
few metres, and the rest were taken under sail, where it costs kilometres. Same
camera, same fit, different answers, and the difference is real: a ten-minute
window measures 5 m at anchor and 1,822 m under way. The viewer can therefore be
confident about a GoPro photograph from Tilloo Pond and honest about one from the
passage to Guana, which a single per-camera number could never do.

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

| | size | estimated | actual |
|---|---|---|---|
| thumbnail | 256 px, q72 | ~38 MB | 25 MB |
| view | 1600 px, q82 | ~880 MB | 595 MB |

2,505 of each, in 206 s across seven workers, no errors. 623 MB and 5,029 files
in total — a third under the estimate, because the archives are stored
uncompressed on the Linux filesystem and JPEG at q82 is kinder than assumed.

EXIF is **stripped from both** — no GPS, no serial numbers on anything published.
Generation is idempotent, so an interrupted build resumes. Three things this stage
has to get right that are not obvious:

**Orientation before stripping.** A phone records a portrait photograph as
landscape pixels plus an orientation flag. Strip the tags first and every portrait
frame is on its side, permanently, in a 600 MB artefact. The rotation is baked
into the pixels and *then* the tags go.

**Colour before stripping.** Recent iPhones write Display P3 pixels with an ICC
profile saying so. Drop the profile and a browser reads those numbers as sRGB,
pushing every saturated colour — the water, most of this trip — harder than it
was. P3 is converted properly first.

**"No serial numbers published" is about the artefact, not the EXIF.** Stripping
tags out of 2,505 files and then printing `GoPro HERO5 Session #C3211354671075`
under every one of them in the viewer would have honoured the letter of the rule
and missed its point. `export.public_camera()` drops the serial; the build keeps
it internally, because it is what tells one camera from another. A test asserts
both halves.

## The map

Milestone 4 built this and milestone 5 put the photographs on it. What follows is
what the chart actually does, with the corrections the screenshots forced.

**Renderer — MapLibre GL 5.24.0, vendored, not Leaflet.** This is forced by the geometry, not
taste. The land is 1,370 polygons and 117,850 exterior vertices; Leaflet draws
GeoJSON as SVG paths, and that many nodes will not pan smoothly on a phone,
which is the stated target. A GL renderer handles it. No third-party tiles
either way — the chart is our own GeoJSON.

**Levels of detail — built, and it works.** `geo/coastline.json` alone is 6.5 MB,
and the shoals are two buffers over the same geometry. Three bands, simplified to
about half a pixel at the scale each serves, with sub-pixel islets dropped at the
coarsest:

| band | max zoom | land parts | size | gzipped |
|---|---|---|---|---|
| coarse | 11 | 298 of 1,370 | 138 KB | 38 KB |
| medium | 13 | 792 | 469 KB | 120 KB |
| fine | 22 | 1,371 | 1,162 KB | 277 KB |

Every band keeps the land's area to within 0.1%, so the coarse chart is cheaper
without being visibly wrong. **First paint is 1,076 KB, or 134 KB gzipped** —
coarse band, tracks, places and all 2,505 photograph records. The fine band's
1.5 MB loads only on zoom. Static hosts gzip by default, which is what turns a
757 KB `photos.json` into 46 KB on the wire.

One trap, worth recording because the geometry looked fine either way. Simplifying
1,370 islands *individually* produced a MultiPolygon whose every part was valid
and whose whole was not: `preserve_topology` only promises a part will not
self-intersect, so neighbours drifted into each other. Simplifying the collection
as one geometry fixed the coarse band and not the finer two — because rounding
coordinates to five decimals on the way out snapped near-coincident vertices
together, at a 1 m grid against the fine band's 4 m tolerance. The operation
actually wanted is `shapely.set_precision(..., mode="valid_output")`, which snaps
to the output grid and keeps the result valid. All nine exported layers now
validate, and a test asserts it.

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

The split has to happen where somebody is still exploring. Clustering applies per
integer tile zoom, so a `clusterMaxZoom` of 15 meant nothing became an individual
pin until z16 — and against a max zoom of 17 that left one level in which to look
at a photograph. At 13, pins appear from z14 and there are four.

**Uncertainty is drawn, not described.** Opening a photograph shades a ring of its
own `uncertainty_m` around it, in metres, so it grows correctly as you zoom. A
camera's own fix is a 15 m dot nobody notices; the GoPro frame from the passage to
Guana is an honest 1.9 km disc. Nothing else in the interface would have made that
difference feel real.

**Two typographic constraints, one cause.** There is no glyph server, because
hosting a font stack for a static folder is a dependency this site does not need.
So place names and cluster counts are HTML markers rather than symbol layers —
sixteen labels and rarely more than forty counts, positioned from the map each
frame. It also means the poster's own typography carries over directly, which a
symbol layer could not have done.

**Tray** — what is not pinned: unplaced and travel photographs, grouped by day
and camera.

**Phones first.** The crew will open this from a text message. Layer controls
collapse to a sheet, the viewer goes full-screen, and the tray's 422 thumbnails
load 80 — only what is on screen, via `loading="lazy"`.

Screenshotting at 390×844 rather than trusting the media queries caught three
things a desktop never shows. The phone fits the chart at **z9.83** where a
desktop fits it at z10.36, and every label threshold was set at 10 — so the
stated primary target was the one device that opened with nothing named. The wide
spaced legends are anchored to points that fall off a narrow screen, so they
appeared as fragments: "AT ABACO". And the attribution wrapped to two lines,
taking a tenth of the chart to say something nobody opened this to read.

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
  photo_index.py       walk the zips, read EXIF headers          [done]
  clock_fit.py         resolve UTC per photograph, per-camera fits [done]
  tests.py             the build's tests, no pytest              [done]
  place.py             bracket + interpolate positions, apply guards [done]
  export.py            GeoJSON at three zoom bands + photos.json [done]
  derive.py            thumbnails and viewing copies
  site/                web app source
photos/                ARCHIVES — gitignored, read in place
out/photo_index.json   gitignored: 4 s to rebuild, 512 EXIF coordinates in it
out/clock_fit.json     gitignored: 0.5 s to rebuild
site_build/            OUTPUT — gitignored
```

**Two refactors, both small.** Milestone 3 needed a second: `PLACES`,
`ANCHORAGES`, `AIRPORT`, `HOTEL` and `MARINA` moved from `poster.py` into
`trip.py` alongside `DAYS`, together with the chart `EXTENT` and `LAND_BBOX`.
`export.py` has to write a places layer and `place.py` has to name the anchorage a
photograph sits off, and the alternative was a second copy of every coordinate.
The poster's PNGs came out byte-identical again afterwards, which is the test that
makes this kind of move cheap.

**The first refactor** — done in milestone 1, and slightly larger than an
extraction. `DAYS`, `load_day()`, `haversine()`, the barrier test and
`_shoal()` moved into `trip.py`, with `read_fixes()` added underneath
`load_day()`. `_shoal()` had to come along: the map needs it, and importing
`poster` pulls in matplotlib and runs font registration — which is the whole
reason for the split. It depends on shapely only, so it moved cleanly. The
poster's PNGs came out byte-identical.

## Failure modes

| failure | response |
|---|---|
| Archive moved | Path is a CLI argument defaulting to `photos/`; missing gives a clear error |
| HEIC unreadable (98 files) | Needs `pillow-heif`; installed, and absent they are listed as unreadable, not fatal |
| EXIF past the read prefix | 28 files, all 10–12 MB iPhone frames, are only large not broken; the read escalates to the whole member |
| Filename collision between cameras | Basename plus camera model; a name two cameras share becomes two records |
| No timestamp and no GPS | `unplaced`, still browsable — 75 of them |
| No camera to group by | 109 photographs have no make or model; no single offset is fitted to them |
| Bogus GPS date stamp | One Samsung reports a date 54 years out; anything outside March–April 2024 is discarded, not fitted |
| Timestamp outside receiver coverage | `unplaced` — no inReach fallback |
| Interrupted build | Derivatives are idempotent; re-running resumes |

## Testing

`python -m map.tests` — 41 assertions, no pytest, no new dependency, because
verification in this repo has always been "run it and compare". The
archive-backed tests skip with a clear message when `out/photo_index.json` is
absent.

In order of value:

1. **Anchor starvation** — hide the iPhone 15 Pro's satellite times *and* its
   timezone tag, forcing it down the correlation path, and check it recovers what
   its own satellites already agreed on. It comes back at **+240.03 min against a
   truth of +239.98** — two seconds — and is the only test that exercises
   `correlate`, the method shipping positions nobody can otherwise verify. It has
   already earned its keep twice, catching the ±26 h diurnal alias and the
   coverage floor that refused this very fit.
2. **Synthetic offsets** — inject a known clock error into the iPhone 14 Pro's
   real timestamps and confirm it comes back. Recovered to within 0.3 min at
   −180, −7, 0, +23.5 and +419 min.
3. **Refusal** — times scattered through the week belong to no camera and must
   not produce a confident offset. Refused at z = 2.3. A fitter that never
   refuses is not a fitter.
4. **Invariants** — every photograph gets exactly one verdict; no method name
   outside the known set; a time never appears without the method that found it;
   every resolved time parses; a camera whose photographs all carry GPS is never
   fitted.
5. **Coverage** — spans sorted and disjoint, arrival day broken at its 28-minute
   hole rather than bridged.

Dropped: the **hold-out** test the design ranked second. It fits a GPS-bearing
camera on part of its photographs and measures error on the rest — but a camera
with GPS is tier `gps` and its fit is never used, so it validates the one path
that needs no validation. Test 1 does the same job on the path that does.

## Milestones

The build and the site are separable, and the build is where the risk lives.

1. **Shared trip module** — ✅ done. `trip.py` extracted including `_shoal()`,
   `read_fixes()` added. Gated on the poster's **PNG** rather than the PDF, into
   which matplotlib stamps a wall-clock `/CreationDate`; all three renders came
   out byte-identical, and `out/compare_offset.png` regenerated to its committed
   bytes.
2. **Index and calibrate** — ✅ done. 2,505 photographs indexed in 4.3 s; 2,393
   have a UTC instant. The question this milestone existed to answer — are the
   crew's eleven clocks tractable? — is answered yes, but almost none of it by
   the method the design expected: 490 photographs know their UTC from the
   satellites, 1,093 from a timezone tag good to a second, and only 810 needed
   fitting at all. The design's own assumptions about the archives were wrong in
   three ways, all corrected above. The `bracket` tier reaches 6.
3. **Place and export** — ✅ done. 2,083 photographs plot on the chart, every one
   inside its bounds and carrying a sailing day; 312 are `unplaced` because the
   receiver was off, 110 are `travel`. Uncertainty is measured along the track
   rather than assumed from a speed, which is what lets one GoPro photograph be
   trusted to 8 m and another from the same camera be honest about 1.8 km. The
   nine data files total 3.2 MB, 675 KB gzipped, with first paint at 134 KB.
4. **The map, with data but no photographs** — ✅ done. Chart, tracks, places and
   layer controls on MapLibre, assembled by `map/build.py` in 17 s. Verified by
   screenshot at 1280×900 and 390×844, which is the only reason the cropped
   initial view, the collapsed legend spacing and the label-free phone were found.
5. **Derivatives and photographs on the map** — ✅ done. 2,505 thumbnails and
   2,505 viewing copies in 206 s, 623 MB total; then clusters, pins coloured by
   tier, the viewer with its uncertainty ring, and the tray of 422 photographs
   that are not on the chart.
6. **Deploy** — not done, and deliberately not attempted unattended: publishing
   2,505 photographs of a youth crew is not something to infer permission for.
   When it happens: unlisted with `noindex` (the build already writes `_headers`
   and `robots.txt`), then confirm a plain `python -m http.server` over the same
   folder behaves identically, which is the portability guarantee. The local
   preview already runs that way — `python -m map.build --serve` — so the
   guarantee is half-tested already.

Milestone 2 was the natural stop-and-look point, and looking was worth it: the
fitting method the design specified would have been wasted work on 1,583
photographs that already knew their own time, and undefined on the 810 that
didn't. Nothing downstream had been built on it yet, which is the whole argument
for putting the risky half first.

Milestone 3 did inherit the peak widths and turned them into metres per
photograph. Two bugs it found are recorded above, both of the same shape — a guard
that existed in one branch and not its neighbour, and a topology promise that held
per part but not per collection. Both were caught by asking the output a question
it had not been asked before, which is the argument for the invariant tests over
the eyeball.

Milestones 4 and 5 did draw them, and the level-of-detail budget survived: 134 KB
gzipped to first paint, with the fine band arriving only on zoom.

The pattern across all five milestones is worth naming, because it held every
time: **the bugs were never in the arithmetic, they were in a guard that existed
in one branch and not its neighbour.** The bracket tier skipped the region check
the `gps` branch made. `preserve_topology` held per part and not per collection.
`clusterMaxZoom` counts integer tile zooms and not the zoom you are at. Label
thresholds were set against the zoom a desktop opens at and not a phone. Each was
found by asking the output a question it had not been asked before — never by
reading the code again.

One thing the chart now shows that no amount of prose in this document managed to:
zoom into Hope Town and the green pins, where cameras recorded their own position,
are scattered through the village among the houses, while the blue ones, placed
from the boat's track, sit in a tidy line out in the channel. That is the ashore
limitation, drawn.

## Out of scope

- **Videos** — 1,249 files across the two archives (659 in the crew's alone, which
  is where the design's figure came from), and the bulk of the 32 GB. Several GB
  even transcoded. Photographs first.
- **Original-resolution downloads** — families will want them for their own
  crew member; 32 GB of originals is a different distribution problem, best
  solved by sending a zip to whoever asks.
- **A time scrubber or animation** — free exploration was chosen over a
  prescribed narrative.
- **A second map for the Portland legs** — travel photographs stay browsable
  rather than plotted.
