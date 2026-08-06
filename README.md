# Sea of Abaco — Boy Scout Sea Base, March 2024

GPS tracks from a Bahamas Sea Base sailing trek out of Marsh Harbour, Abaco,
21–28 March 2024, rendered as a print-quality nautical-chart poster.

## Pipeline

```
GPSFILES/*.log        raw NMEA 0183 straight off the handheld receiver
   │
   ├─ parse_nmea.py       $GPRMC fixes + $GPGGA quality → tracks/*.csv
   ├─ fetch_coastline.py  OSM coastline/places for the Abaco bbox → geo/*.json (cached)
   ├─ abaco_geo.py        coastline ways → land polygons (left-hand-rule polygonize)
   ├─ roads.py            OSM road graph + Dijkstra, for the ashore legs
   ├─ analyze.py          per-day distance, speeds, anchorage detection
   └─ poster.py           the poster → out/
```

```bash
python3 -m venv .venv && .venv/bin/pip install shapely matplotlib numpy
.venv/bin/python parse_nmea.py
.venv/bin/python fetch_coastline.py     # network; results cached in geo/
.venv/bin/python poster.py              # 100 dpi proof → out/proof.png
.venv/bin/python poster.py --final      # 300 dpi PNG + vector PDF, 18×24 in
```

## Notes on the data

Three corrections matter, and all three change the numbers:

- **Time.** Logs are **UTC**; the Bahamas was on EDT (UTC−4) that week, so
  several files look like they cross midnight but are single local days.
  `analyze.py` and `poster.py` both shift to UTC−4.
- **Fix quality.** `$GPGGA` carries a quality flag, satellite count and HDOP —
  use them. 22 and 28 Mar contain fixes of **quality 6 (dead reckoning)**, plus
  HDOP up to 50 and 0-satellite fixes; that garbage is what produced a fake
  "9.5 nm airport transfer" on arrival day. The filter (quality ∈ 1/2/4/5,
  ≥ 4 sats, HDOP ≤ 4) drops 825 fixes and is surgical: the five sailing days
  lose 0.3% of their fixes and their distances don't move.
- **Anchor drift.** Distance only accumulates while reported SOG > 0.5 kn.
  Without that gate, hours of swinging on a hook silently add ~2.5 nm/day.
  Also keep distance accumulation separate from the 22 m plot-thinning — one
  early version measured against the last *plotted* point and reported 265 nm.

Other things worth remembering:

- 21 Mar and part of 28 Mar are Portland legs (lat ≈ 45 N); everything filters
  to `lat < 30`. The 25.8 kn peak on 28 Mar is the airport van, not the boat.
- **22 Mar has no usable passage at all** — the whole log fits in an 870 m box.
  The airport→hotel drive shown on the poster is *reconstructed* by routing
  over the OSM road network (`roads.py`, 5.90 km / 3.2 nm), not recorded. The
  poster says so in the footer. Sanity check: Thursday's real reverse trip
  measures 3.4 nm.
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
- **The tracks are contiguous — nothing is missing.** Zero gaps over 3 minutes
  on any of the six on-the-water days, so the long straight legs are real
  sailing rather than interpolation across lost signal. The receiver was off
  overnight, but the boat moved only 12–210 m between each day's last fix and
  the next day's first, i.e. anchor swing, not an unrecorded passage. (Only the
  22 Mar arrival log has gaps: five of them, totalling 133 m of movement.)
- Thursday is afloat until 09:52:40 EDT — a 270 m hop off the mooring to the
  dock — and in a van after that (`road_split`). Distances quoted anywhere on
  the poster are made on the water only; the road legs are drawn but never
  counted.

## Chart conventions

The poster is drawn to read like a paper chart rather than a data plot:

- **Neatline.** The border is graduated in whole minutes of arc, alternating
  light and dark, labelled every 5′ along the south and west edges.
- **Depth tinting.** Deep water is near-white and the tint deepens inshore,
  following chart convention. These are buffers around the coastline, not
  surveyed contours — there is no bathymetry in this repo.
- **Compass rose.** A true ring graduated every 1°, an inner magnetic ring
  turned by the local variation, and a 16-point faceted star with a
  fleur-de-lis north. Variation is **9°05′ W (2024)**, computed from the WMM
  2020 coefficients at 26°30′N 77°03′W for epoch 2024.22 and cross-checked
  against WMM 2025 (−9.12° at epoch 2025.0). It is baked in as a constant in
  `poster.py`; `pygeomag` is only needed to re-derive it, not to build.

## Itinerary

| Local day | Route | Track |
|---|---|---|
| Fri 22 Mar | Arrival — MHH → hotel, by road (reconstructed) | 3.2 nm |
| Sat 23 Mar | Walk to the marina, then Marsh Harbour shakedown | 0.4 + 3.6 nm |
| Sun 24 Mar | Marsh Hbr → Man-O-War → Tahiti Beach → Tilloo Pond | 24.0 nm |
| Mon 25 Mar | Tilloo Pond → Hope Town Harbour → Lynyard Cay | 20.5 nm |
| Tue 26 Mar | Lynyard Cay → Little Harbour → north to Tilloo | 19.0 nm |
| Wed 27 Mar | Tilloo → Great Guana Cay → Marsh Harbour | 22.0 nm |
| Thu 28 Mar | Marsh Harbour → Leonard M. Thompson Intl (MHH) | 3.4 nm |

**89 nm under sail** over five sailing days; best speed 8.3 kn. The 235-minute
stop at 26.5135, −77.0782 on the last morning is the airport terminal.

## Next

An interactive version of this map (zoomable, day toggles, time scrubber) is
planned — `tracks/*.csv` and `geo/` are the inputs it should reuse.

Coastline data © OpenStreetMap contributors (ODbL).
