# Labels on the chart

All 34 labels the interactive chart draws, north to south. Generated
from `site_build/data/places.geojson`, so this is what actually ships.

- **Source** — `poster + map` labels are shared with the printed sheet, so moving
  one moves the poster as well. `map only` labels live in `MAP_CAYS`, `MAP_SPOTS`
  and `MAP_REGIONS` in `trip.py`, and the sheet never sees them.
- **From z** — the zoom at which the label appears. The chart opens near z10.4 on
  a desktop and z9.9 on a phone.
- **On** — whether the label sits on land or in water.
- **In frame** — whether it falls inside the printed sheet's chart frame.

| ✓ | Name | Kind | Latitude | Longitude | Lat (DMS) | Lon (DMS) | On | From z | In frame | Source |
|---|------|------|---------:|----------:|-----------|-----------|----|-------:|----------|--------|
| ☐ | **Spanish Cay** | cay | 26.94675 | -77.53761 | 26° 56.805′ N | 77° 32.257′ W | land | 11 | — | map only |
| ☐ | **Powell Cay** | cay | 26.90338 | -77.47842 | 26° 54.203′ N | 77° 28.705′ W | land | 11 | — | map only |
| ☐ | **Little Abaco Island** | cay | 26.88000 | -77.64000 | 26° 52.800′ N | 77° 38.400′ W | land | 10 | — | map only |
| ☐ | **Manjack Cay** | cay | 26.83119 | -77.37152 | 26° 49.871′ N | 77° 22.291′ W | land | 11 | — | map only |
| ☐ | **Green Turtle Cay** | cay | 26.77384 | -77.32683 | 26° 46.430′ N | 77° 19.610′ W | land | 11 | — | map only |
| ☐ | **Whale Cay** | cay | 26.70974 | -77.23625 | 26° 42.584′ N | 77° 14.175′ W | land | 11 | — | map only |
| ☐ | **Baker's Bay** | spot | 26.68600 | -77.14800 | 26° 41.160′ N | 77° 08.880′ W | water | 12 | yes | map only |
| ☐ | **Great Guana Cay** | isle | 26.67900 | -77.13100 | 26° 40.740′ N | 77° 07.860′ W | land | 9.6 | yes | poster + map |
| ☐ | **Treasure Cay** | spot | 26.67690 | -77.28580 | 26° 40.614′ N | 77° 17.148′ W | land | 11 | — | map only |
| ☐ | **Scotland Cay** | cay | 26.64559 | -77.07431 | 26° 38.735′ N | 77° 04.459′ W | land | 11 | yes | map only |
| ☐ | **S E A   O F   A B A C O** | water | 26.63000 | -77.04500 | 26° 37.800′ N | 77° 02.700′ W | water | 8.5 | yes | poster + map |
| ☐ | **Water Cay** | cay | 26.60567 | -77.18448 | 26° 36.340′ N | 77° 11.069′ W | water | 13 | yes | map only |
| ☐ | **Dickie's Cay** | cay | 26.59472 | -77.00851 | 26° 35.683′ N | 77° 00.511′ W | land | 13.5 | yes | map only |
| ☐ | **Man-O-War Cay** | isle | 26.59300 | -77.00300 | 26° 35.580′ N | 77° 00.180′ W | land | 9.6 | yes | poster + map |
| ☐ | **Matt Lowe's Cay** | cay | 26.56386 | -77.01460 | 26° 33.832′ N | 77° 00.876′ W | land | 11 | yes | map only |
| ☐ | **Sugar Loaf Cay** | cay | 26.55015 | -77.02866 | 26° 33.009′ N | 77° 01.720′ W | land | 11 | yes | map only |
| ☐ | **Marina** | marina | 26.54688 | -77.05192 | 26° 32.813′ N | 77° 03.115′ W | land | 12 | yes | poster + map |
| ☐ | **Hotel** | hotel | 26.54522 | -77.04891 | 26° 32.713′ N | 77° 02.935′ W | land | 12 | yes | poster + map |
| ☐ | **HOPE TOWN** | town | 26.54070 | -76.95940 | 26° 32.442′ N | 76° 57.564′ W | land | 9 | yes | poster + map |
| ☐ | **MARSH HARBOUR** | town | 26.53100 | -77.06400 | 26° 31.860′ N | 77° 03.840′ W | land | 9 | yes | poster + map |
| ☐ | **Leonard M. Thompson Intl** | airport | 26.51350 | -77.07820 | 26° 30.810′ N | 77° 04.692′ W | land | 12 | yes | poster + map |
| ☐ | **Elbow Cay** | isle | 26.49500 | -76.97000 | 26° 29.700′ N | 76° 58.200′ W | water | 9.6 | yes | poster + map |
| ☐ | **A T L A N T I C O C E A N** | water | 26.47800 | -76.94000 | 26° 28.680′ N | 76° 56.400′ W | water | 8.5 | yes | poster + map |
| ☐ | **Lubbers Quarters** | isle | 26.47000 | -77.02700 | 26° 28.200′ N | 77° 01.620′ W | water | 9.6 | yes | poster + map |
| ☐ | **T H E   M A R L S** | region | 26.45000 | -77.32000 | 26° 27.000′ N | 77° 19.200′ W | water | 10 | — | map only |
| ☐ | **Tilloo Pond** | anchorage | 26.44880 | -76.99070 | 26° 26.928′ N | 76° 59.442′ W | water | 11.5 | yes | poster + map |
| ☐ | **Tilloo Cay** | isle | 26.44000 | -76.98300 | 26° 26.400′ N | 76° 58.980′ W | water | 9.6 | yes | poster + map |
| ☐ | **G R E A T   A B A C O** | big | 26.43000 | -77.15500 | 26° 25.800′ N | 77° 09.300′ W | land | 8.5 | yes | poster + map |
| ☐ | **Channel Cay** | cay | 26.41404 | -76.99656 | 26° 24.842′ N | 76° 59.794′ W | land | 11 | yes | map only |
| ☐ | **Lynyard Cay** | anchorage | 26.36480 | -76.98290 | 26° 21.888′ N | 76° 58.974′ W | land | 11.5 | yes | poster + map |
| ☐ | **LITTLE HARBOUR** | town | 26.32420 | -77.00020 | 26° 19.452′ N | 77° 00.012′ W | land | 9 | yes | poster + map |
| ☐ | **Casuarina Point** | spot | 26.29370 | -77.09105 | 26° 17.622′ N | 77° 05.463′ W | land | 11 | — | map only |
| ☐ | **Winding Bay** | spot | 26.29000 | -77.01000 | 26° 17.400′ N | 77° 00.600′ W | water | 11 | — | map only |
| ☐ | **Cherokee Sound** | spot | 26.28000 | -77.05000 | 26° 16.800′ N | 77° 03.000′ W | land | 11 | — | map only |

## The ones I had to judge

Everything else is either shared with the poster or placed on its island's own
interior point from a coordinate you supplied.

**Spanish Cay** — Two figures were given, 40 km apart. This is the one that agrees with both reference maps; the other is down by Marsh Harbour.

**Manjack Cay** — Placed from your description (north of Green Turtle Cay); the decimal figure given lands south of it, on Treasure Cay. Nunjack Cay.png then confirmed the 3.9 km island rather than the 1.8 km one between it and Green Turtle.

**Baker's Bay** — On Great Guana Cay, 25 m off the shore, as given.

**Water Cay** — Your anchorage coordinate, used exactly as given. It is water rather than land on purpose: moving it 616 m onto the nearest islet crossed a headland and put the name on the wrong side of the point.

**Dickie's Cay** — Held to z13.5: it sits 400 m from Man-O-War Cay's label, and these labels are HTML markers with no collision detection.

**Matt Lowe's Cay** — The 20 ha island north-east of Sugar Loaf Cay, corrected from the 25 ha one now labelled Sugar Loaf.

**Sugar Loaf Cay** — Labelled Matt Lowe's Cay for one build. Corrected.

**T H E   M A R L S** — A region rather than an island, so in water by intent. Named from the reference maps.

**Channel Cay** — Labelled Pelican Cays for one build. That is the name of the whole group of cays here, so the island got its own name instead.

**Lynyard Cay** — Nudged 0.9 km north and 0.2 km east on the map only, to the middle of the 4.3 km cay. The poster draws this label too and places its day badges around it, so the shared coordinate is untouched.

**Winding Bay** — The coordinate given was 400 m inland, so it moved to open water, then 1.4 km further south to the Atlantic shore at your direction.

## Islands in the trip area that nothing names

Largest first, with the size and length the coastline gives them. Listed rather
than guessed at, since naming them is local knowledge.

| Latitude | Longitude | Size | Length |
|---------:|----------:|-----:|-------:|
| 26.50003 | −76.99741 | 143 ha | 2.7 km |
| 26.43754 | −77.05112 | 73 ha | 2.6 km |
| 26.29510 | −77.05458 | 41 ha | 1.1 km |
| 26.40549 | −77.04310 | 40 ha | 1.5 km |
| 26.35872 | −77.02272 | 22 ha | 0.9 km |
| 26.33446 | −77.02760 | 20 ha | 1.5 km |
| 26.42328 | −77.04093 | 19 ha | 1.7 km |
| 26.41405 | −76.99644 | 10 ha | 0.9 km |

