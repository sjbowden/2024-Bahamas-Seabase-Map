# Sea Base 1830 — Sea of Abaco, March 2024

GPS tracks from Boy Scout Sea Base crew 1830's sailing trek out of Marsh
Harbour, Abaco, **22–28 March 2024**, rendered as a print-quality
nautical-chart poster. (The logs also cover 21 March, the drive to Portland
airport.)

## Pipeline

```
GPSFILES/*.log        raw NMEA 0183 straight off the handheld receiver
   │
   ├─ parse_nmea.py       $GPRMC fixes + $GPGGA quality → tracks/*.csv
   ├─ fetch_coastline.py  OSM coastline/places for the Abaco bbox → geo/*.json (cached)
   ├─ abaco_geo.py        coastline ways → land polygons (left-hand-rule polygonize)
   ├─ roads.py            OSM road graph + Dijkstra, for the ashore legs
   ├─ analyze.py          per-day distance, speeds, anchorage detection
   ├─ corroborate.py      cross-check against the inReach track and camera GPS
   └─ poster.py           the poster → out/
```

```bash
python3 -m venv .venv && .venv/bin/pip install shapely matplotlib numpy
.venv/bin/python parse_nmea.py
.venv/bin/python fetch_coastline.py     # network; results cached in geo/
.venv/bin/python poster.py              # 100 dpi proof → out/proof.png
.venv/bin/python poster.py --final      # 300 dpi PNG + vector PDF, 18×24 in
.venv/bin/python poster.py --compare    # offset vs true, see below
```

Outputs, all under `out/`:

| file | what | in git |
|---|---|---|
| `abaco_poster_18x24_300dpi.png` | 5400×7200 print raster | yes |
| `abaco_poster_18x24.pdf` | vector, best for a print shop | yes |
| `compare_offset.png` | side-by-side proof of the one deliberate distortion | yes |
| `proof.png`, `proof_true.png`, `proof_offset.png` | 100 dpi working renders | no |

### Fonts

The poster is set in **P052** (URW's Palatino) and **Lato**, and both need to be
installed:

```bash
sudo apt install fonts-urw-base35 fonts-lato    # Debian/Ubuntu
rm -rf ~/.cache/matplotlib                      # if matplotlib doesn't see them
```

This matters more than it looks. If matplotlib can't find a family it doesn't
raise, and doesn't warn through `warnings` — it logs a single line and resolves
the name down the sans-serif chain, so *both* families become **DejaVu Sans**.
The sheet loses its serif altogether and every string sets 7–29% wider (the
40 pt stat numbers are the worst case). `fit_fontsize` still keeps the route
lines inside the column under fallback, but it can't restore the serif.

So `poster.py` checks at import and prints a loud warning naming any family it
couldn't find, rather than letting a wrong-looking poster render quietly. If the
system packages aren't an option, drop the font files into a `fonts/` directory
beside the script and they'll be registered automatically — that path is
gitignored, so nothing is redistributed here. Upstream:
[P052](https://github.com/ArtifexSoftware/urw-base35-fonts) (AGPL-3 with font
exception), [Lato](http://www.latofonts.com) (SIL OFL 1.1).

## Notes on the data

Three corrections matter, and all three change the numbers:

- **Time.** Logs are **UTC**; the Bahamas was on EDT (UTC−4) that week, so
  several files look like they cross midnight but are single local days.
  `analyze.py` and `poster.py` both shift to UTC−4.
- **Fix quality.** `$GPGGA` carries a quality flag, satellite count and HDOP —
  use them. 22 and 28 Mar contain fixes of **quality 6 (dead reckoning)**, plus
  HDOP up to 50 and 0-satellite fixes; that garbage is what produced a fake
  "9.5 nm airport transfer" on arrival day. The filter (quality ∈ 1/2/4/5,
  ≥ 4 sats, HDOP ≤ 4) drops **825** fixes, leaving 42,510, and is surgical: the
  five sailing days lose 0.3% of their fixes and their distances don't move.
- **Anchor drift.** Distance only accumulates while reported SOG > 0.5 kn.
  Without that gate, hours of swinging on a hook silently add ~2.5 nm/day.
  Also keep distance accumulation separate from the 22 m plot-thinning — one
  early version measured against the last *plotted* point and reported 265 nm.

Other things worth remembering:

- 21 Mar and part of 28 Mar are Portland legs (lat ≈ 45 N); everything filters
  to `lat < 30`. The 25.8 kn peak on 28 Mar is the airport van, not the boat.
- **22 Mar has no usable passage at all** — the whole log fits in an 870 m box.
  The airport→hotel drive shown on the poster is *reconstructed* by routing over
  the OSM road network (`roads.py`, 5.90 km / **3.2 nm**), not recorded. For
  scale, Thursday's recorded drive in the other direction — from the marina, not
  the hotel, and not necessarily the same streets — measures **2.7 nm**.
- The **hotel** (26.545222, −77.048906) comes from the GPS EXIF of a photograph
  taken there — 14:43 EDT 22 Mar, speed 0, ±4.6 m. (The photo itself is not in
  this repo; the coordinate it yielded is in `poster.py`.) It corroborates the
  log's 14:38–15:23 stop at 26.5452, −77.0490 to within a couple of metres,
  which is useful because that day's track is otherwise untrustworthy.
- **Saturday starts on foot.** The 23 Mar log opens 112 m from the hotel and
  covers 738 m in 12 minutes at 2.4 mph — walking pace along the road to the
  marina, ending 14:57:23Z where the boat then sits for 90 minutes. That leg is
  split out (`walk_split`) and drawn dotted, so the day is 0.4 nm on foot plus
  3.6 nm afloat. `analyze.py` reports the undivided 4.0 nm day total.
- **Thursday is mostly ashore.** Afloat until 09:52:40 EDT — a 270 m hop off the
  mooring to the dock, 0.6 nm all told — then in a van (`road_split`). Distances
  quoted anywhere on the poster are made on the water only; road legs are drawn
  but never counted, which is why the departure day reads 0.6 nm and not 3.4.
- **The tracks are contiguous — nothing is missing.** Zero gaps over 3 minutes
  on any of the six on-the-water days, so the long straight legs are real
  sailing rather than interpolation across lost signal. The receiver was off
  overnight, but the boat moved only 12–210 m between each day's last fix and
  the next day's first, i.e. anchor swing, not an unrecorded passage. (Only the
  22 Mar arrival log has gaps: five of them, totalling 133 m of movement.)

## Three independent records

The trip was recorded three times over, by devices that knew nothing about each
other. That is what makes the chart checkable rather than merely plausible.

| source | cadence | coverage |
|---|---|---|
| handheld GPS receiver (`GPSFILES/*.log`) | a fix every ~5 s | 10–13 h a day, one battery charge |
| inReach satellite communicator (`geo/inreach.gpx`) | 10 min by day, 4 h overnight | continuous, including nights |
| crew cameras (EXIF) | per shot | 458 located photos |

`python corroborate.py` regenerates every number below.

The inReach export is committed as `geo/inreach.gpx`, exactly as Garmin Explore
wrote it except that the two device IDs have been replaced with `00000001` and
`00000002`. It holds two *sequential* tracking sessions — 23–25 Mar and 25–27
Mar, handing over during a 2.4 hour gap on the Monday evening — not two devices
running at once, so combining them double-counts nothing.

### The inReach track is from the satellite communicator, not the handheld

Worth stating because the file is easy to mistake for a second copy of the
handheld log. Four independent tells:

- `creator="http://www.delorme.com"` in the GPX header — DeLorme built the
  inReach, Garmin bought them in 2016, and the Explore platform still writes
  that string. The `explore.gpx` / `explore.kmz` pair is a Garmin Explore export.
- **116 of 149 gaps are exactly 10 minutes** — a scheduled reporting interval,
  not a logger. The handheld writes every ~5 s.
- **It was recording while the handheld was off**, overnight on the charger.
  One device cannot be both.
- The tracks are named for the crew rather than a file — `Sea Base 1830
  (…)` — and every point carries `<fix>none</fix>`, which NMEA never says.

### Do the two tracks match? Yes

| test | median | 90th | max |
|---|---|---|---|
| same place at the same moment (108 coincident fixes) | 10 m | 23 m | 34 m |
| **same route** — each inReach point vs the handheld's path | **3 m** | 10 m | 20 m |

**All 150 inReach points lie within 50 m of the handheld's path.** The second
test is the more telling one: it ignores timing and asks whether the two
devices traced the same voyage. They did.

### Overnight the boat only swung at anchor

The handheld ran out of battery each evening and charged overnight, so every
night is a hole in the primary record. The inReach fills it:

| handheld off | fixes | path | net move | longest unwatched |
|---|---|---|---|---|
| Sat 20:06 → Sun 06:56 | 2 | 17 m | 17 m | 4.0 h |
| Sun 18:46 → Mon 07:17 | 3 | 27 m | 27 m | 4.0 h |
| Mon 20:05 → Tue 07:49 | 4 | 24 m | 5 m | 4.0 h |
| Tue 19:28 → Wed 08:20 | 4 | 18 m | 13 m | 4.0 h |
| Wed 18:20 → Thu 07:17 | 4 | 20 m | 4 m | 9.0 h |

Tens of metres — anchor swing, no night passages. This measures directly what
was previously only inferred from where one day's log stopped and the next
began.

The limit worth stating: the inReach drops to roughly 4-hourly overnight, so a
departure and return between two fixes isn't strictly excluded — but each
night's bracketing fixes sit within tens of metres of each other. The Fri→Sat
night has a single fix in 18.4 hours and is effectively unobserved; the crew
was ashore at the hotel, so there was no boat to move.

### The one trip outside the barrier cays

**Sunday 24 March, 10:05–12:03 EDT** — out through the cut by Man-O-War Cay to
**1.57 km beyond the cay chain**, including 97 minutes anchored at
26.6006, −76.9870 with 42% of fixes under 0.5 kn. A reef stop, on the ocean
side. Every other day stayed inside the Sea of Abaco.

All three records agree on it:

- the handheld logs the passage out and back,
- the inReach caught 4 position reports during it, two at the offshore anchorage,
- and `IMG_0606/0607/0608` were shot at 10:12 from 1.32 km offshore — deep blue
  Atlantic water rather than the turquoise shallows inside the cays.

`corroborate.py` locates this with a hand-drawn barrier polyline
(`BARRIER`), so anything within 0.5 km of the line is treated as "on the cays"
rather than offshore. Without that threshold the test also flags 76 photos taken
standing on Hope Town, Tahiti Beach, Lynyard Cay and Great Guana, where the
polyline simply runs a little inshore of the beach.

### Camera GPS

458 photos carry coordinates, and they agree with the boat's track to a
**median of 10 m** (90th percentile 34 m). Placement differs by camera, which
matters for putting photos on an interactive map:

| camera | images | with GPS | how to place |
|---|---|---|---|
| Apple iPhone 15 Pro | 543 | 466 | own GPS |
| FujiFilm XP90 | 148 | 0 | timestamp → track |
| GoPro HERO5 Session | 114 | 0 | timestamp → track |
| Mavic Mini (drone) | 22 | 22 | own GPS, with altitude |

**312 images have no GPS but do have a timestamp**, so the track places them.
That is the more general technique anyway: a photo's time pins it to the track
within metres, and the track is more accurate than the phone's own fix.

Note that Google Photos **strips latitude and longitude** from anything served
through a share link — the `GPSHPositioningError` tag survives, proving a fix
existed, while the coordinates are gone. Use the originals, Takeout, or
timestamp matching.

## Chart conventions

The poster is drawn to read like a paper chart rather than a data plot:

- **Neatline.** The border is graduated in whole minutes of arc, alternating
  light and dark, labelled every 5′ along the south and west edges.
- **North is straight up.** Longitude maps to x and latitude to y, with x
  stretched by 1/cos(26.5°), so the sheet has no rotation or convergence — the
  rose reads true for every point on the chart.
- **Depth tinting.** Deep water is near-white and the tint deepens inshore,
  following chart convention. These are buffers around the coastline, not
  surveyed contours — there is no bathymetry in this repo.
- **Compass rose.** A true ring graduated every 1°, an inner magnetic ring
  turned by the local variation, and a 16-point faceted star with a
  fleur-de-lis north. Variation is **9°05′ W (2024)**, computed from the WMM
  2020 coefficients at 26°30′N 77°03′W for epoch 2024.22 and cross-checked
  against WMM 2025 (−9.12° at epoch 2025.0). It is baked in as a constant in
  `poster.py`; `pygeomag` is only needed to re-derive it, not to build. The
  figure isn't printed on the rose — the inner ring's rotation *is* the
  variation — so if you need the number, it's here.

  The fleur-de-lis at north is built from the pieces the emblem actually has:
  one central point, **two** curls a side — a big outer scroll plus a finer
  tendril rising beside the centre — a banded waist, and a foot that resolves
  into two more scrolls curling outward. A single curl a side and a plain
  flared foot look approximately right and are visibly wrong next to the
  original. The side petals are the part that matters — they are
  tapering *ribbons* swept along a curved spine that curls out, over and back
  under, not lobes. Every attempt to draw them as a filled outline with
  hand-placed control points came out as horns or moth wings.

  It is drawn as an **outline with the paper showing through**, not a
  silhouette — that is what the engraved original does, and a solid fill reads
  as a blob. Only the centre petal keeps a dark core. Filling the outer petals
  dark was tried too and is also wrong: the engraving's value is much lighter
  than it first appears, carried by line rather than mass. Stroke weight has to be
  set against the printed size rather than the drawing: at a quarter of an inch
  tall, an outline that looks delicate when zoomed in closes up the interiors
  entirely.

  The star follows the engraved roses of period charts: eight faceted points
  split light and dark, the four cardinals continuing straight through both
  rings to a spearhead and eyelet outside, and the letters replacing the ring
  numerals at those four bearings so the spears have somewhere to go.

  Two things learned the hard way. The engraved originals shade each facet with
  fine strokes running along its own axis — worth trying, but at a two-inch
  printed rose they never resolve and read as stray drafting lines, so the
  facets are solid. And everything is placed through one aspect-corrected
  helper: don't reach for `plt.Circle` for the rings, because it takes a single
  radius in data units, and since a degree of latitude is 1.118× a degree of
  longitude here it draws an ellipse that pinches east–west and slices through
  the numerals.
- **The vessel.** A pen-and-ink drawing of the catamaran sits in the open
  Atlantic top right, balancing the rose bottom right. `vessel_rgba()` keys the
  alpha at render time and crops to the ink: the paper is neutral (saturation
  ~3) while the ink is sepia (~25), so it keys on chroma plus lightness and
  takes opacity from darkness. The chart therefore shows *between* the strokes,
  which is what makes it read as drawn on the chart rather than pasted onto it.

  Line art is essential here and a tonal engraving will not substitute. The
  first artwork was a photographic engraving of the boat at anchor, complete
  with sky, clouds and a full water field inside a circular vignette. The
  water hatching is exactly as dark as the vessel, so no threshold separates
  them — several were tried. Isolated line art is the thing to ask for.
- **The footer is a credit line, not a methods section** — it hangs on a wall.
  Every data caveat lives in this README instead.

### Offset tracks — the one deliberate inaccuracy

In the channel along the west side of Elbow Cay several days share one lane and
would otherwise overplot into a single stripe. Only there (**26.470–26.520 N**,
Tilloo Cut to short of Hope Town, ramping to nothing over 0.010° at each end) is
a day shifted sideways, by up to ~170 m perpendicular to its own heading.
Everywhere else — Little Harbour, Lynyard Cay, Tilloo Pond, Hope Town,
Man-O-War, Great Guana — **the tracks are drawn exactly as recorded**. The seven
day panels are true throughout.

The bounds were measured, not guessed: counting day-pairs that come within 250 m
per 0.005° band shows three-way congestion at 26.42–26.435 and 26.485–26.525,
while south of 26.355 only a single day is present at all.

`poster.py --compare` renders the chart with and without the offset, plus a
side-by-side zoom, so the distortion can be judged directly. **Check it by
pixel-diffing the two proofs** — changes must fall inside the band and nowhere
else. That test is what caught the trim pass still snipping loops out of
geometry drawn at its true position outside the corridor, a defect a
displacement metric misses entirely because a trimmed corner still lies on the
original line.

Offsetting a polyline is deceptively fiddly, and two obvious approaches fail:

| approach | loops introduced | route dropped |
|---|---|---|
| naive per-vertex normal | 7→26, 4→18 | none |
| GEOS `offset_curve` | none | **4.9 km of day 3** |
| taper + bounded trim (used) | none | none |

Offsetting a bend by more than its own radius folds the line into a loop, so
`offset_track` measures the local turn radius and **tapers the offset toward
zero** through tight turns — at a hairpin the line simply converges on the
truth. A trim pass removes any fold that survives, but only if it is small
relative to the offset; a genuine loop (the boat actually circling) is wider
than that and is left alone rather than quietly straightened out.

## Itinerary

| Local day | Route | On the water |
|---|---|---|
| Fri 22 Mar | Arrival — MHH → hotel by road (reconstructed, 3.2 nm) | — |
| Sat 23 Mar | Walk to the marina (0.4 nm), then out into the harbour | 3.6 nm |
| Sun 24 Mar | Marsh Hbr → Man-O-War → Tahiti Beach → Tilloo Pond | 24.0 nm |
| Mon 25 Mar | Tilloo Pond → Hope Town Harbour → Lynyard Cay | 20.5 nm |
| Tue 26 Mar | Lynyard Cay → Little Harbour → north to Tilloo | 19.0 nm |
| Wed 27 Mar | Tilloo → Great Guana Cay → Marsh Harbour | 22.0 nm |
| Thu 28 Mar | Off the mooring to the dock, then MHH by road (2.7 nm) | 0.6 nm |

**89 nm under sail** over five sailing days; best speed 8.3 kn. The 235-minute
stop at 26.5135, −77.0782 on the last morning is the airport terminal, and the
only excursion outside the barrier cays was Sunday's two-hour reef stop off
Man-O-War — see [Three independent records](#three-independent-records).

## Next

An interactive version of this map (zoomable, day toggles, time scrubber) is
planned — `tracks/*.csv` and `geo/` are the inputs it should reuse.

Coastline data © OpenStreetMap contributors (ODbL).
