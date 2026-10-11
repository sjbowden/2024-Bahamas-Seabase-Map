# Gazetteer cay names not on the map

Worked up on 10 October 2026. **On 11 October the thirty names in the first two
classes below were added to the map**, in `MAP_CAYS` in `trip.py`, at the proposed
points. The fourteen unsettled names and the eleven that do not belong were not,
except Bunks Cay, which was added later the same day and has its own section below.
Six more were dropped from the unsettled names the same day, each with its reason
under Not for the map: Wood Cay, Long Bay Cay, Dunc Cays, Burnt Cay, Potato Cays and
Meal Cay. The last seven, which never had one island to point at, were dropped that
evening after OpenStreetMap was searched for each and had none of them, so nothing
is unsettled now and `python -m map.build --candidates` marks nothing. The source is the GeoNames gazetteer for the Bahamas
(geonames.org, CC BY 4.0): every island, island group and peninsula it lists inside
the map whose name the map does not already carry. There are 55.

## What changed since these were set aside

These names were left off because the gazetteer's points did not sit on islands,
and each had two or more islands that could answer to it. The points turn out to be
wrong in a regular way.

Of the gazetteer names the map already carries, 54 are on islands under 40 ha,
where a point should land on its island. South of about 26.76° N their islands lie a
median 377 m west and 46 m north of the gazetteer's point; north of 26.80° N the
median is about 60 m. That is consistent with positions taken from an older chart
datum and never converted, though nothing here proves the cause. At least five
entries in the south show no offset and presumably come from another survey: Anna Cay, Parrot Cays, Delia's Cay, Lower Hill Cay and
Woolendean Cay.

So each unplaced name was moved by the median offset of its seven nearest matched
neighbours and looked up again. Most then fall squarely on one island. The Explorer
charts were read at close zoom at 20 of the corrected positions, those on the Sea of
Abaco side and around Snake Cay, and at a wider zoom over ten areas including the
Marls. OpenStreetMap's names were compared for all of them.

| Verdict | Names | Meaning |
|---|---|---|
| Two sources | 6 | The chart letters it, or OpenStreetMap names the same island. |
| Gazetteer alone, one island | 24 | The corrected point is within 60 m of one island, and the next nearest is at least 125 m further off. No second source. |
| Unsettled, then added | 1 | Bunks Cay, held back and then added on a second listing. |
| Unsettled | 0 | More than one island fits, or the sources disagree. |
| Not for the map | 24 | Already named, a peninsula, the mainland, or no island there; thirteen of them were unsettled and then dropped as uncorroborated. |

The table is as things stand after 11 October. As first worked up it read 14
unsettled and 11 not for the map.

The map already has four cays in the second class (Pond Apple, Push, Lower Hill and
Woolendean), marked ☐ in `docs/map-labels.md`.

## Two sources — added

| Name | Kind | Gazetteer point | Corrected by | Proposed label point | Island | Note |
|---|---|---|---|---|---|---|
| Bluff Cay | island | 26.78320, -77.33983 | 119 m W, 22 m N | 26.78350, -77.34248 | 0.4 ha | Explorer chart letters BLUFF CAY beside this islet, off Andrews Bluff at Green Turtle Cay. |
| Dilly Cay | island | 26.59955, -77.00580 | 430 m W, 42 m N | 26.59979, -77.00996 | 0.2 ha | Explorer chart letters DILLY CAY beside this islet in Man-O-War's harbour. |
| Lockhart Cay | island | 26.58769, -77.36129 | 407 m W, 64 m N | 26.59519, -77.35770 | 87.5 ha | OpenStreetMap gives the same island the same name. |
| Minos Cay | island | 26.57759, -77.12314 | 391 m W, 56 m N | 26.57797, -77.12730 | 0.2 ha | Explorer chart letters MINOS ROCK in the water just north of this islet; the chart's noun is Rock, the gazetteer's is Cay. |
| Cistern Cay | island | 26.57448, -77.11466 | 391 m W, 56 m N | 26.57265, -77.11525 | 0.1 ha | Explorer chart letters CISTERN CAY beside this islet. This gazetteer entry is one of the few with no offset: uncorrected it is 184 m from the islet, corrected it is on the mainland. |
| Moore’s Island | island | 26.29273, -77.54958 | 407 m W, 64 m N | 26.29343, -77.55808 | — | The settled island in the Bight of Abaco; OpenStreetMap names it too. The position is OpenStreetMap's. |

## Gazetteer alone, one island — added

| Name | Kind | Gazetteer point | Corrected by | Proposed label point | Island | Note |
|---|---|---|---|---|---|---|
| Lilly Cay | island | 26.69705, -77.17806 | 314 m W, 3 m N | 26.69743, -77.18094 | 0.5 ha | Chart draws the islet unnamed, 400 m west of Gumelemi Cay. |
| Jobes Cay | island | 26.65059, -77.08268 | 392 m W, 35 m N | 26.65038, -77.08687 | 1.2 ha | Chart draws it unnamed: the northern of two islets off Scotland Cay's west end. |
| Canes Cay | island | 26.64812, -77.08064 | 392 m W, 35 m N | 26.64849, -77.08518 | 2.6 ha | Chart draws it unnamed: the southern of the same two islets. Uncorrected, both points fall on Scotland Cay itself. |
| Brush Cay | island | 26.63770, -77.05579 | 392 m W, 35 m N | 26.63813, -77.05966 | 0.3 ha | Chart draws it unnamed, off Scotland Cay's airstrip end. |
| With Low Fall Cay | island | 26.62754, -77.03490 | 392 m W, 35 m N | 26.62791, -77.03900 | 0.7 ha | Chart draws it unnamed, on the reef line in the Fowl Cay preserve. |
| Fish Hawk Cay | island | 26.62294, -77.03012 | 392 m W, 35 m N | 26.62342, -77.03420 | 1.3 ha | Chart draws it unnamed, the next islet south-east on the same reef line. |
| Sudy Mangrove | island | 26.56629, -77.34451 | 407 m W, 64 m N | 26.56727, -77.34861 | 1.0 ha | In the Marls; the charts name nothing there. |
| Paddy’s Head | island | 26.55805, -77.14004 | 391 m W, 56 m N | 26.55855, -77.14384 | 0.1 ha | In Bustick Bight on the Marls side; chart draws the islet unnamed. |
| Little Bill Bo Cay | island | 26.55638, -77.23711 | 391 m W, 4 m N | 26.55687, -77.24099 | 0.4 ha | In the Marls. |
| Carrion Crow Cay | island | 26.55337, -77.13396 | 391 m W, 56 m N | 26.55410, -77.13772 | 0.3 ha | In Bustick Bight; chart draws the islet unnamed. |
| Red Shank Swash | island | 26.55297, -77.29195 | 401 m W, 46 m N | 26.55385, -77.29641 | 1.5 ha | In the Marls. A swash is a channel, so the name may belong to the water beside the island. |
| Little Potato Cay | island | 26.54073, -77.14153 | 391 m W, 60 m N | 26.54139, -77.14539 | 1.3 ha | Chart draws it unnamed, 700 m north-west of the island it letters BIG POTATO. |
| Little Pelican Bush | group | 26.53848, -77.36842 | 407 m W, 64 m N | 26.53589, -77.37213 | 10.5 ha | A group name; the corrected point is 21 m from this island. In the Marls. |
| Man-O-War Bush | island | 26.53491, -77.15854 | 391 m W, 56 m N | 26.53552, -77.16221 | 0.2 ha | In the Marls; nothing to do with Man-O-War Cay. |
| South Mangrove | group | 26.53214, -77.35046 | 407 m W, 64 m N | 26.53486, -77.35478 | 21.5 ha | A group name. In the Marls. |
| Big Pelican Bush | island | 26.52474, -77.36520 | 407 m W, 64 m N | 26.52495, -77.36882 | 1.1 ha | In the Marls. |
| Cambridge Harbour Cays | group | 26.50599, -77.33856 | 407 m W, 64 m N | 26.50604, -77.34117 | 2.7 ha | A group name. In the Marls. |
| Sailor’s Choice | island | 26.49003, -77.31804 | 401 m W, 64 m N | 26.49081, -77.32236 | 9.9 ha | In the Marls. |
| Bevans Cay | island | 26.48545, -77.30859 | 401 m W, 64 m N | 26.48602, -77.31210 | 17.5 ha | In the Marls. |
| Toucans Cay | island | 26.48084, -77.30208 | 401 m W, 64 m N | 26.48112, -77.30709 | 7.3 ha | In the Marls. |
| Bibins Cay | island | 26.47858, -77.29763 | 401 m W, 64 m N | 26.47902, -77.30174 | 11.1 ha | In the Marls. |
| Little Crab Cay | island | 26.47418, -77.28205 | 396 m W, 64 m N | 26.47483, -77.28628 | 18.7 ha | In the Marls. |
| John Doctor Cay | island | 26.43071, -77.04139 | 398 m W, 49 m N | 26.43111, -77.04546 | 0.7 ha | Chart draws it unnamed, 400 m south of Mocking Bird Cay. |
| Big Mangrove | island | 26.28239, -77.29145 | 375 m W, 72 m N | 26.28378, -77.29510 | 0.3 ha | South of the Marls; 56 m from the only island near. |

## Unsettled

None now. One was added and thirteen dropped on 11 October; the dropped ones are
under Not for the map, each with the note it had here.

## Unsettled, then added

| Name | Kind | Gazetteer point | Corrected by | Proposed label point | Island | Note |
|---|---|---|---|---|---|---|
| Bunks Cay | peninsula | 26.45912, -77.05080 | 396 m W, 60 m N | 26.45969, -77.05467 | 2.0 ha | The gazetteer classes it as a peninsula. The corrected point is on a 2 ha piece of land the chart draws as part of the shore at Snake Cay. Added on 11 October: a second listing of the name, source not recorded, gives 26°27′35″N 77°03′15″W, 50 m from the corrected point and 340 m from the gazetteer's own. It calls the place an islet, which is not relied on; whether it is an islet or a spit is still open. |

## Not for the map

| Name | Kind | Gazetteer point | Note |
|---|---|---|---|
| Guineaman Cay | island | 26.99654, -77.69304 | Already on the map as Guineamans Cay. |
| Rock Harbour Cays | group | 26.80002, -77.48731 | A group name whose point is on Basin Harbour Cay, already named. |
| Round Cay | peninsula | 26.67008, -77.30961 | A peninsula; the point is on Great Abaco. |
| Matt Lowe Cay | peninsula | 26.66538, -77.34621 | A peninsula of the island already carrying Goliath Cay's name. |
| Strangers Cay | peninsula | 26.66411, -77.33085 | A peninsula of the same island. |
| Joe Downer Cay | group | 26.64287, -77.43407 | The pair already named singly, Big and Little Joe Downer Cay. |
| Sonny Cay | island | 26.63710, -77.35773 | No island within 450 m, corrected or not. |
| Big Tom Lowe Cay | island | 26.57596, -77.21509 | No island within 450 m, corrected or not. |
| Minus Cay | island | 26.56365, -77.13641 | No island near; probably a second spelling of Minos Cay, 3 km away. |
| Abaco Island | island | 26.46504, -77.13432 | Great Abaco itself. |
| John Keys Cay | island | 26.42957, -77.04752 | The point is on Deep Sea Cay, already named from the chart. |
| Wood Cay | island | 26.36494, -77.27780 | Dropped on 11 October, having been unsettled: corrected, the point is on a 45 ha island at 26.36815, -77.28265, but OpenStreetMap puts Wood Cay 3 km to the south, nothing decides between them, and it is far from anywhere the trip went. |
| Long Bay Cay | island | 26.77250, -77.31981 | Dropped on 11 October, having been unsettled: a 0.2 ha islet near 26.77289, -77.32275, and no second source for the name was found. The offset fades out at this latitude, so the correction is uncertain. The nearest islet is 171 m from the corrected point and 277 m from the raw one; the chart draws it on the reef off Green Turtle Cay, unnamed. |
| Dunc Cays | group | 26.61466, -77.36571 | Dropped on 11 October, having been unsettled: a group name in the Marls, and a second listing (also known as Thatch Cays) gives 26°31′N 77°22′W, 11 km south of the corrected point at 26.61449, -77.37010. Neither picks out an island. A group name, and two large islands 170 m apart could both belong to it. |
| Burnt Cay | peninsula | 26.57572, -77.24117 | Dropped on 11 October, having been unsettled: no second source was found; the one other listing repeats the gazetteer's own point. The gazetteer classes it as a peninsula, but the corrected point is on a 40 ha island beside Wills Cay. |
| Potato Cays | group | 26.55200, -77.21971 | Dropped on 11 October, having been unsettled, with no second source. A group name; the point is on a 60 ha island with a 47 ha one 300 m south. 8 km from Big Potato Cay, so possibly a different Potato. |
| Meal Cay | island | 26.51860, -77.35629 | Dropped on 11 October, having been unsettled, with no second source: the one other listing is the gazetteer's point rounded to the minute. Three islets within 75 m of the corrected point; this is the largest. |
| Thurston Islet | island | 26.70478, -77.30693 | Dropped on 11 October, having been unsettled: no one island to put it on, and OpenStreetMap has no such name in Abaco. The coastline draws no island. The chart draws a speck 130 m north-west of the corrected point, off Sandbank Landing, unnamed. |
| Leaf Cay | island | 26.60403, -77.34774 | Dropped on 11 October, having been unsettled: no one island to put it on, and OpenStreetMap has no such name in Abaco. Corrected, the point is on the island OpenStreetMap calls Lockhart Cay, where the chart draws a separate island the coastline does not. Uncorrected, it is 48 m from a 0.4 ha islet. |
| Daniel’s Cay | island | 26.57218, -77.11117 | Dropped on 11 October, having been unsettled: no one island to put it on, and OpenStreetMap has no such name in Abaco. Corrected, the point is on the islet the chart letters CISTERN CAY. |
| Sparrowhawk Cay | island | 26.51409, -77.34871 | Dropped on 11 October, having been unsettled: no one island to put it on, and OpenStreetMap has no such name in Abaco. Lands on an island either way: uncorrected on a 0.25 ha islet, corrected on a 10 ha island 400 m west. |
| Big Crab Cay | island | 26.46846, -77.27289 | Dropped on 11 October, having been unsettled: no one island to put it on, and OpenStreetMap has no such name in Abaco. The only island near is 265 m off and 2 ha, a ninth the size of Little Crab Cay next door. |
| New Current Cay | island | 26.42544, -77.04338 | Dropped on 11 October, having been unsettled: no one island to put it on, and OpenStreetMap has no such name in Abaco. The chart draws the corrected point on a large island; the coastline draws only specks there. |
| Johnies Cays | group | 26.42138, -77.04733 | Dropped on 11 October, having been unsettled: no one island to put it on, and OpenStreetMap has no such name in Abaco. A group name; the chart draws the point on one of a dozen islets, and the coastline's nearest is 170 m off. |

## If more are added

- Each goes in `MAP_CAYS` in `trip.py` as longitude, latitude, name and the zoom it
  first shows at, with a row in `docs/map-labels.md`.
- The gazetteer writes its apostrophes curly; the map's names use a straight one.

## How far to trust this

- The correction is a median over neighbours, so it is good to perhaps 50 m. That
  settles a name where one island stands alone and not where islets crowd together,
  which is why the crowded ones are under Unsettled.
- In the Marls the nearest matched neighbours are up to 19 km away. The offset is
  steady across the whole southern area, so it should hold there, but no chart or
  second gazetteer names anything in the Marls to check it against.
- A name landing on an island says where the gazetteer's compilers put it. It does
  not say anyone uses the name now.
- The coastline and the chart do not always agree on what is an island. Three of the
  unsettled names turn on that.

