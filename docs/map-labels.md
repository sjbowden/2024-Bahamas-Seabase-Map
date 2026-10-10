# Labels on the chart

All 129 labels the interactive chart draws, north to south. Generated
from `site_build/data/places.geojson`, so this is what actually ships.

- **Source** — `poster + map` labels are shared with the printed sheet, so moving
  one moves the poster as well. `map only` labels live in `MAP_CAYS`, `MAP_SPOTS`
  and `MAP_REGIONS` in `trip.py`, and the sheet never sees them.
- **From z** — the zoom at which the label appears. The chart opens near z10.4 on
  a desktop and z9.9 on a phone.
- **On** — whether the label sits on land or in water.
- **In frame** — whether it falls inside the printed sheet's chart frame.
- **✓ / Against the Explorer charts** — each label was checked on 7 October 2026 (and thirty-two
  added from closer readings on 10 October) against the
  Explorer chartbook sheets for Abaco (AB 11–AB 24, Lewis Offshore, 2022–2025
  editions) as shown in the i-Boating web viewer. ☑ means the chart letters the same
  name on the feature the label sits on or beside; ☐ means the note says what
  differs, which for four cays is that the name comes from the GeoNames gazetteer
  (the Bahamas file, from the national topographic sheets) and not from a chart; — means the label is not something a chart names.

| ✓ | Name | Kind | Latitude | Longitude | Lat (DMS) | Lon (DMS) | On | From z | In frame | Source | Against the Explorer charts |
|---|------|------|---------:|----------:|-----------|-----------|----|-------:|----------|--------|----------------------------|
| ☑ | **Umbrella Cay** | cay | 27.00720 | -77.71636 | 27° 00.432′ N | 77° 42.982′ W | land | 13 | — | map only | UMBRELLA CAY |
| ☑ | **Guineamans Cay** | cay | 26.99731 | -77.69385 | 26° 59.839′ N | 77° 41.631′ W | land | 13.5 | — | map only | GUINEAMANS CAY (the gazetteer has Guineaman Cay) |
| ☑ | **Allans Cay** | cay | 26.99020 | -77.68274 | 26° 59.412′ N | 77° 40.964′ W | land | 12.5 | — | map only | ALLANS CAY, the north-west end of the island the chart's waypoint calls ALLANS-PENSACOLA |
| ☑ | **Big Murray Cay** | cay | 26.97752 | -77.64411 | 26° 58.651′ N | 77° 38.647′ W | land | 14 | — | map only | BIG MURRAY CAY |
| ☑ | **Little Murray Cay** | cay | 26.97608 | -77.64081 | 26° 58.565′ N | 77° 38.449′ W | land | 14.5 | — | map only | LITTLE MURRAY CAY |
| ☑ | **Pensacola Cay** | cay | 26.97440 | -77.65530 | 26° 58.464′ N | 77° 39.318′ W | land | 12.5 | — | map only | PENSACOLA CAY, the south-east end of the same island |
| ☑ | **Big Hog Cay** | cay | 26.96874 | -77.61689 | 26° 58.124′ N | 77° 37.013′ W | land | 13 | — | map only | BIG HOG CAY |
| ☑ | **Squashes Cay** | cay | 26.95721 | -77.55566 | 26° 57.433′ N | 77° 33.340′ W | land | 13.5 | — | map only | SQUASHES CAY (AKA SQUANCES CAY) |
| ☑ | **Prince Cay** | cay | 26.95063 | -77.60765 | 26° 57.038′ N | 77° 36.459′ W | land | 13.5 | — | map only | PRINCE CAY |
| ☑ | **Hog Cays** | cay | 26.94983 | -77.59526 | 26° 56.990′ N | 77° 35.716′ W | land | 13.5 | — | map only | HOG CAYS |
| ☑ | **Alec Cays** | cay | 26.94845 | -77.61914 | 26° 56.907′ N | 77° 37.148′ W | land | 13.5 | — | map only | ALEC CAYS |
| ☑ | **Spanish Cay** | cay | 26.94675 | -77.53761 | 26° 56.805′ N | 77° 32.257′ W | land | 11 | — | map only | SPANISH CAY |
| ☑ | **Goat Cay** | cay | 26.93480 | -77.51750 | 26° 56.088′ N | 77° 31.050′ W | land | 14 | — | map only | GOAT CAY |
| ☑ | **Crab Cay** | cay | 26.92447 | -77.59888 | 26° 55.468′ N | 77° 35.933′ W | land | 13 | — | map only | CRAB CAY — the one off Angelfish Point, not Manjack's neighbour |
| ☑ | **Soldier Cay** | cay | 26.90410 | -77.46652 | 26° 54.246′ N | 77° 27.991′ W | land | 14 | — | map only | SOLDIER CAY |
| ☑ | **Powell Cay** | cay | 26.90338 | -77.47842 | 26° 54.203′ N | 77° 28.705′ W | land | 11 | — | map only | POWELL CAY |
| ☑ | **High Cay** | cay | 26.89778 | -77.46136 | 26° 53.867′ N | 77° 27.682′ W | land | 14 | — | map only | HIGH CAY |
| ☑ | **Bonefish Cay** | cay | 26.89087 | -77.45089 | 26° 53.452′ N | 77° 27.053′ W | land | 14 | — | map only | BONEFISH CAY |
| ☑ | **Little Abaco Island** | cay | 26.88000 | -77.64000 | 26° 52.800′ N | 77° 38.400′ W | land | 10 | — | map only | outside the Explorer sheets; the viewer's base chart letters LITTLE ABACO ISLAND here |
| ☐ | **Little Ambergris Cay** | cay | 26.87861 | -77.43201 | 26° 52.717′ N | 77° 25.921′ W | land | 14 | — | map only | OpenStreetMap name; the chart viewer has no sheet over it |
| ☑ | **Ambergris Cay** | cay | 26.87033 | -77.42692 | 26° 52.220′ N | 77° 25.615′ W | land | 13 | — | map only | AMBERGRIS CAY (Private) |
| ☑ | **Randalls Cay** | cay | 26.85500 | -77.53850 | 26° 51.300′ N | 77° 32.310′ W | land | 13 | — | map only | RANDALLS CAY, lettered along the land; the coastline joins it to Great Abaco |
| ☐ | **Push Cay** | cay | 26.84721 | -77.50561 | 26° 50.833′ N | 77° 30.337′ W | land | 14.5 | — | map only | GeoNames gazetteer name; the chart draws the island unnamed |
| ☑ | **Manjack Cay** | cay | 26.83119 | -77.37152 | 26° 49.871′ N | 77° 22.291′ W | land | 11 | — | map only | MANJACK CAY AKA NUNJACK CAY |
| ☑ | **Rat Cay** | cay | 26.82063 | -77.36325 | 26° 49.238′ N | 77° 21.795′ W | land | 14 | — | map only | RAT CAY |
| ☑ | **Bamboo Cay** | cay | 26.81957 | -77.50948 | 26° 49.174′ N | 77° 30.569′ W | land | 12.5 | — | map only | BAMBOO CAY |
| ☑ | **Rocky Harbour Cay** | cay | 26.81530 | -77.50230 | 26° 48.918′ N | 77° 30.138′ W | land | 14 | — | map only | ROCKY HARBOUR CAY, lettered off the eastern arm of the island the coastline draws as one with Bamboo Cay |
| ☑ | **Crab Cay** | cay | 26.81432 | -77.35982 | 26° 48.859′ N | 77° 21.589′ W | land | 13 | — | map only | CRAB CAY |
| ☑ | **Fiddle Cay** | cay | 26.80567 | -77.34578 | 26° 48.340′ N | 77° 20.747′ W | land | 13.5 | — | map only | FIDDLE CAY |
| ☑ | **Basin Harbour Cay** | cay | 26.80357 | -77.50465 | 26° 48.214′ N | 77° 30.279′ W | land | 12.5 | — | map only | lettered BASIN HARB… at the sheet edge, beside the Basin Harbour waypoint |
| ☑ | **Green Turtle Cay** | cay | 26.77384 | -77.32683 | 26° 46.430′ N | 77° 19.610′ W | land | 11 | — | map only | GREEN TURTLE CAY |
| ☑ | **Pelican Cay** | cay | 26.76088 | -77.30520 | 26° 45.653′ N | 77° 18.312′ W | land | 13.5 | — | map only | PELICAN CAY — the single cay off Green Turtle, not the Pelican Cays |
| ☑ | **No Name Cay** | cay | 26.74718 | -77.29646 | 26° 44.831′ N | 77° 17.788′ W | land | 12.5 | — | map only | NO NAME CAY |
| ☑ | **Whale Cay** | cay | 26.70974 | -77.23625 | 26° 42.584′ N | 77° 14.175′ W | land | 11 | — | map only | WHALE CAY |
| ☐ | **Gumelemi Cay** | cay | 26.70037 | -77.17650 | 26° 42.022′ N | 77° 10.590′ W | land | 13.5 | yes | map only | OpenStreetMap and the GeoNames gazetteer both have the name; the chart draws the islet unnamed |
| ☑ | **Sand Bank Cays** | cay | 26.69330 | -77.26179 | 26° 41.598′ N | 77° 15.707′ W | land | 13.5 | — | map only | SAND BANK CAYS |
| ☑ | **Baker's Bay** | spot | 26.68500 | -77.16200 | 26° 41.100′ N | 77° 09.720′ W | water | 12 | yes | map only | BAKERS BAY, by the charted waypoint |
| ☑ | **Spoil Cay** | cay | 26.68285 | -77.17501 | 26° 40.971′ N | 77° 10.501′ W | land | 13.5 | yes | map only | SPOIL CAY (OpenStreetMap: Spoil Bank Cay) |
| ☑ | **Great Guana Cay** | isle | 26.67900 | -77.09800 | 26° 40.740′ N | 77° 05.880′ W | water | 9.6 | yes | poster + map | GREAT GUANA CAY |
| ☑ | **Theresa Cay** | cay | 26.67707 | -77.42715 | 26° 40.624′ N | 77° 25.629′ W | land | 13 | — | map only | THERESA CAY |
| ☑ | **Treasure Cay** | spot | 26.67690 | -77.28580 | 26° 40.614′ N | 77° 17.148′ W | land | 11 | — | map only | TREASURE CAY MARINA |
| ☑ | **Okra Cay** | cay | 26.67020 | -77.32520 | 26° 40.212′ N | 77° 19.512′ W | land | 13.5 | — | map only | OKRA CAY, lettered along the land; the coastline joins it to Great Abaco |
| ☑ | **Goliath Cay** | cay | 26.66820 | -77.34360 | 26° 40.092′ N | 77° 20.616′ W | land | 13 | — | map only | GOLIATH CAY, at the middle of the chart's lettering. The gazetteer puts Goliath Cay 900 m further east and calls the west of this land Matt Lowe Cay |
| ☑ | **Snapper Cay** | cay | 26.66608 | -77.42629 | 26° 39.965′ N | 77° 25.577′ W | land | 13 | — | map only | SNAPPER CAY |
| ☑ | **Delia's Cay** | cay | 26.66535 | -77.11805 | 26° 39.921′ N | 77° 07.083′ W | land | 14 | yes | map only | DELIAS CAY |
| ☑ | **Aaron Cay** | cay | 26.65889 | -77.40870 | 26° 39.533′ N | 77° 24.522′ W | land | 13 | — | map only | AARON CAY, lettered beside this island; the gazetteer's point is nearest it too |
| ☑ | **Big Lake Cay** | cay | 26.64800 | -77.35630 | 26° 38.880′ N | 77° 21.378′ W | land | 13 | — | map only | BIG LAKE CAY; the coastline joins it to Great Abaco |
| ☑ | **Scotland Cay** | cay | 26.64559 | -77.07431 | 26° 38.735′ N | 77° 04.459′ W | land | 11 | yes | map only | SCOTLAND CAY |
| ☑ | **Foots Cay** | cay | 26.64531 | -77.11324 | 26° 38.719′ N | 77° 06.794′ W | land | 13 | yes | map only | FOOTS CAY |
| ☐ | **Lower Hill Cay** | cay | 26.64470 | -77.28694 | 26° 38.682′ N | 77° 17.216′ W | land | 14.5 | — | map only | GeoNames gazetteer name; the chart draws the island unnamed |
| ☑ | **Little Joe Downer Cay** | cay | 26.64462 | -77.44009 | 26° 38.677′ N | 77° 26.405′ W | land | 12.5 | — | map only | LITTLE JOE DOWNER CAY |
| ☑ | **Fish Cays** | cay | 26.63761 | -77.15567 | 26° 38.257′ N | 77° 09.340′ W | land | 13 | yes | map only | FISH CAYS |
| ☑ | **Hills Cay** | cay | 26.63593 | -77.27925 | 26° 38.156′ N | 77° 16.755′ W | land | 13.5 | — | map only | HILLS CAY, lettered beside the island |
| ☑ | **Fowl Cay** | cay | 26.63475 | -77.05142 | 26° 38.085′ N | 77° 03.085′ W | land | 13 | yes | map only | FOWL CAY |
| ☑ | **Joes Cay** | cay | 26.63110 | -77.26740 | 26° 37.866′ N | 77° 16.044′ W | water | 14.5 | — | map only | JOES CAY, beside an islet too small for the coastline, so the label is in water. The gazetteer's point is 300 m south-south-east |
| ☑ | **Levi Cay** | cay | 26.61811 | -77.40957 | 26° 37.087′ N | 77° 24.574′ W | land | 13 | — | map only | LEVI CAY |
| ☑ | **Big Joe Downer Cay** | cay | 26.61364 | -77.42498 | 26° 36.818′ N | 77° 25.499′ W | land | 12.5 | — | map only | BIG JOE DOWNER CAY |
| ☑ | **Man-O-War Cay** | isle | 26.61340 | -77.01700 | 26° 36.804′ N | 77° 01.020′ W | water | 9.6 | yes | poster + map | MAN-O-WAR CAY |
| ☑ | **Water Cay** | cay | 26.60658 | -77.17260 | 26° 36.395′ N | 77° 10.356′ W | land | 13 | yes | map only | WATER CAY, on the islet the chart names |
| ☑ | **S E A   O F   A B A C O** | water | 26.60550 | -77.07500 | 26° 36.330′ N | 77° 04.500′ W | water | 8.5 | yes | poster + map | SEA OF ABACO |
| ☑ | **Archers Cay** | cay | 26.60350 | -77.17350 | 26° 36.210′ N | 77° 10.410′ W | land | 14 | yes | map only | ARCHERS CAY, the headland south of Water Cay; the coastline joins it to Great Abaco |
| ☑ | **Big Pigeon Cay** | cay | 26.59854 | -77.41222 | 26° 35.912′ N | 77° 24.733′ W | land | 13 | — | map only | BIG PIGEON CAY |
| ☑ | **Ballast Cay** | cay | 26.59777 | -77.42244 | 26° 35.866′ N | 77° 25.346′ W | land | 14 | — | map only | BALLAST CAY |
| ☑ | **Dickie's Cay** | cay | 26.59472 | -77.00851 | 26° 35.683′ N | 77° 00.511′ W | land | 13.5 | yes | map only | DICKIES CAY |
| ☑ | **Spirit Cay** | cay | 26.59320 | -77.41905 | 26° 35.592′ N | 77° 25.143′ W | land | 14 | — | map only | SPIRIT CAY, lettered just below the islet |
| ☑ | **Little Pigeon Cay** | cay | 26.58713 | -77.41213 | 26° 35.228′ N | 77° 24.728′ W | land | 14 | — | map only | LITTLE PIGEON CAY, a cluster of islets; the label is on one of them |
| ☑ | **Garden Cay** | cay | 26.58632 | -77.01171 | 26° 35.179′ N | 77° 00.703′ W | land | 14 | yes | map only | GARDEN CAY |
| ☑ | **Sandy Cay** | cay | 26.58352 | -77.00761 | 26° 35.011′ N | 77° 00.457′ W | land | 14 | yes | map only | SANDY CAY (the one off Man-O-War) |
| ☑ | **Wills Cay** | cay | 26.58113 | -77.23547 | 26° 34.868′ N | 77° 14.128′ W | land | 13 | — | map only | WILLS CAY |
| ☑ | **Johnny's Cay** | cay | 26.56802 | -76.97259 | 26° 34.081′ N | 76° 58.355′ W | land | 13 | yes | map only | JOHNNYS CAY |
| ☐ | **Woolendean Cay** | cay | 26.56616 | -77.39200 | 26° 33.970′ N | 77° 23.520′ W | land | 13.5 | — | map only | GeoNames gazetteer name; the Explorer sheets do not reach it |
| ☑ | **Matt Lowe's Cay** | cay | 26.56386 | -77.01460 | 26° 33.832′ N | 77° 00.876′ W | land | 11 | yes | map only | MATT LOWES CAY (Private) |
| ☑ | **Outer Point Cay** | cay | 26.55528 | -77.06565 | 26° 33.317′ N | 77° 03.939′ W | land | 13 | yes | map only | OUTER POINT CAY, lettered along the chain at a closer zoom than the first check used |
| ☑ | **Dry Cay** | cay | 26.55368 | -77.18057 | 26° 33.221′ N | 77° 10.834′ W | land | 12.5 | yes | map only | DRY CAY |
| ☑ | **Green Cay** | cay | 26.55016 | -77.15672 | 26° 33.010′ N | 77° 09.403′ W | land | 13 | yes | map only | GREEN CAY |
| ☑ | **Sugar Loaf Cay** | cay | 26.55015 | -77.02866 | 26° 33.009′ N | 77° 01.720′ W | land | 11 | yes | map only | SUGAR LOAF CAY |
| ☑ | **Anna Cay** | cay | 26.54987 | -76.96089 | 26° 32.992′ N | 76° 57.653′ W | land | 15 | yes | map only | ANNA CAY |
| ☑ | **Big Cay** | cay | 26.54697 | -77.06805 | 26° 32.818′ N | 77° 04.083′ W | land | 15 | yes | map only | BIG CAY |
| ☑ | **Grunt Cay** | cay | 26.54694 | -77.06976 | 26° 32.816′ N | 77° 04.186′ W | land | 15 | yes | map only | GRUNT CAY, lettered about 100 m west of the islet the label is on |
| — | **Marina** | marina | 26.54688 | -77.05192 | 26° 32.813′ N | 77° 03.115′ W | land | 12 | yes | poster + map | not a chart name; from the track |
| — | **Hotel** | hotel | 26.54522 | -77.04891 | 26° 32.713′ N | 77° 02.935′ W | land | 13 | yes | poster + map | not a chart name; from a photograph's EXIF |
| ☑ | **Mouth of Harbour Cay** | cay | 26.54230 | -76.96250 | 26° 32.538′ N | 76° 57.750′ W | land | 15 | yes | map only | MOUTH OF HARBOUR CAY, lettered on the land west of the harbour entrance; the coastline joins it to Elbow Cay |
| ☑ | **HOPE TOWN** | town | 26.54070 | -76.95240 | 26° 32.442′ N | 76° 57.144′ W | water | 9 | yes | poster + map | HOPE TOWN; on the map the name sits 700 m east of the sheet's position, clear of the story dots |
| ☑ | **Parrot Cays** | cay | 26.53958 | -76.97794 | 26° 32.375′ N | 76° 58.676′ W | land | 13 | yes | map only | PARROT CAYS |
| ☑ | **Big Potato Cay** | cay | 26.53543 | -77.14158 | 26° 32.126′ N | 77° 08.495′ W | land | 13 | yes | map only | BIG POTATO CAY |
| ☑ | **MARSH HARBOUR** | town | 26.53100 | -77.06400 | 26° 31.860′ N | 77° 03.840′ W | land | 9 | yes | poster + map | MARSH HARBOUR |
| — | **Leonard M. Thompson Intl** | airport | 26.51350 | -77.07820 | 26° 30.810′ N | 77° 04.692′ W | land | 12 | yes | poster + map | inland, outside the chart's detail |
| ☑ | **Dinner Cay** | cay | 26.51127 | -77.05107 | 26° 30.676′ N | 77° 03.064′ W | land | 14 | yes | map only | DINNER CAY |
| ☑ | **Pepper Cay** | cay | 26.50800 | -77.04786 | 26° 30.480′ N | 77° 02.872′ W | land | 14 | yes | map only | PEPPER CAY |
| ☑ | **Lubbers Quarters** | isle | 26.50300 | -77.02400 | 26° 30.180′ N | 77° 01.440′ W | water | 9.6 | yes | poster + map | LUBBERS QUARTER; on the map the name sits 1.7 km west of the sheet's position, clear of Elbow Cay's |
| ☑ | **Cooper Jacks Cay** | cay | 26.49702 | -76.98535 | 26° 29.821′ N | 76° 59.121′ W | land | 14 | yes | map only | COOPER JACKS CAY |
| ☑ | **Elbow Cay** | isle | 26.49500 | -76.97950 | 26° 29.700′ N | 76° 58.770′ W | water | 9.6 | yes | poster + map | ELBOW CAY |
| ☑ | **Davids Cay** | cay | 26.48850 | -77.04340 | 26° 29.310′ N | 77° 02.604′ W | land | 14 | yes | map only | DAVIDS CAY; the coastline joins it to Great Abaco |
| ☑ | **Tavern Cay** | cay | 26.47856 | -76.99564 | 26° 28.714′ N | 76° 59.738′ W | land | 14 | yes | map only | TAVERN CAY |
| ☑ | **A T L A N T I C O C E A N** | water | 26.47800 | -76.94000 | 26° 28.680′ N | 76° 56.400′ W | water | 8.5 | yes | poster + map | ATLANTIC OCEAN |
| ☑ | **Guano Cay** | cay | 26.47228 | -77.04969 | 26° 28.337′ N | 77° 02.981′ W | land | 14 | yes | map only | GUANO CAY |
| ☑ | **Cormorant Cay** | cay | 26.46375 | -77.05039 | 26° 27.825′ N | 77° 03.023′ W | land | 13 | yes | map only | CORMORANT CAY |
| ☑ | **Angel Cays** | cay | 26.45940 | -77.04430 | 26° 27.564′ N | 77° 02.658′ W | water | 13 | yes | map only | ANGEL CAYS, lettered offshore along the chain from Cormorant Cay to Snake Cay |
| ☑ | **Snake Cay** | cay | 26.45610 | -77.05230 | 26° 27.366′ N | 77° 03.138′ W | land | 14 | yes | map only | SNAKE CAY; the coastline joins it to Great Abaco |
| ☑ | **T H E   M A R L S** | region | 26.45000 | -77.32000 | 26° 27.000′ N | 77° 19.200′ W | water | 10 | — | map only | base chart: THE MARLS |
| ☑ | **Tilloo Pond** | anchorage | 26.44880 | -76.99070 | 26° 26.928′ N | 76° 59.442′ W | water | 11.5 | yes | poster + map | TILLOO POND |
| ☑ | **Tilloo Cay** | isle | 26.44000 | -76.98300 | 26° 26.400′ N | 76° 58.980′ W | water | 9.6 | yes | poster + map | TILLOO CAY |
| ☑ | **Deep Sea Cay** | cay | 26.43816 | -77.05019 | 26° 26.290′ N | 77° 03.011′ W | land | 12.5 | yes | map only | DEEP SEA CAY |
| ☑ | **Mocking Bird Cay** | cay | 26.43464 | -77.04568 | 26° 26.078′ N | 77° 02.741′ W | land | 13.5 | yes | map only | MOCKING BIRD CAY (unnamed in OpenStreetMap) |
| ☑ | **Iron Cay** | cay | 26.42317 | -77.04139 | 26° 25.390′ N | 77° 02.483′ W | land | 13 | yes | map only | IRON CAY |
| ☑ | **Pelican Cays** | cay | 26.41900 | -76.97650 | 26° 25.140′ N | 76° 58.590′ W | water | 13 | yes | map only | PELICAN CAYS, lettered along the chain |
| ☑ | **Channel Cay** | cay | 26.41404 | -76.99656 | 26° 24.842′ N | 76° 59.794′ W | land | 11 | yes | map only | CHANNEL CAY |
| ☑ | **G R E A T   A B A C O** | big | 26.41200 | -77.12050 | 26° 24.720′ N | 77° 07.230′ W | land | 8.5 | yes | poster + map | GREAT ABACO ISLAND |
| ☑ | **Gaulding Cay** | cay | 26.40767 | -77.00273 | 26° 24.460′ N | 77° 00.164′ W | land | 13.5 | yes | map only | GAULDING CAY |
| ☑ | **Armstrong Cay** | cay | 26.40580 | -77.03710 | 26° 24.348′ N | 77° 02.226′ W | land | 14 | yes | map only | ARMSTRONG CAY, lettered along the strip; the coastline joins it to Great Abaco |
| ☐ | **Pond Apple Cay** | cay | 26.40526 | -77.04445 | 26° 24.316′ N | 77° 02.667′ W | land | 14 | yes | map only | GeoNames gazetteer name; the chart draws the island unnamed beside ARMSTRONG CAY |
| ☑ | **Black Point Cay** | cay | 26.40030 | -77.02770 | 26° 24.018′ N | 77° 01.662′ W | land | 14 | yes | map only | BLACK POINT CAY, lettered off the tip of the lobe the label sits on |
| ☑ | **Sandy Cay** | cay | 26.39916 | -76.99270 | 26° 23.950′ N | 76° 59.562′ W | land | 13 | yes | map only | SANDY CAY — the reef the crew snorkelled on Tuesday |
| ☑ | **Cornish Cay** | cay | 26.39758 | -77.00678 | 26° 23.855′ N | 77° 00.407′ W | land | 13 | yes | map only | CORNISH CAY |
| ☑ | **Lynyard Cay** | anchorage | 26.36480 | -76.98290 | 26° 21.888′ N | 76° 58.974′ W | land | 11.5 | yes | poster + map | LYNYARD CAY |
| ☑ | **Bridges Cay** | cay | 26.35121 | -77.00092 | 26° 21.073′ N | 77° 00.055′ W | land | 13 | yes | map only | BRIDGES CAY |
| ☑ | **Goole Cay** | cay | 26.34431 | -76.98544 | 26° 20.659′ N | 76° 59.126′ W | land | 14 | yes | map only | GOOLE CAY |
| ☑ | **Riding Cays** | cay | 26.34202 | -77.02289 | 26° 20.521′ N | 77° 01.373′ W | land | 13.5 | yes | map only | RIDING CAYS |
| ☑ | **LITTLE HARBOUR** | town | 26.32420 | -77.00020 | 26° 19.452′ N | 77° 00.012′ W | land | 9 | yes | poster + map | LITTLE HARBOUR |
| ☑ | **Mangrove Cay** | cay | 26.29829 | -77.06623 | 26° 17.897′ N | 77° 03.974′ W | land | 13.5 | yes | map only | MANGROVE CAY (OpenStreetMap: Cormorant Cay) |
| ☑ | **Noah Bethel Cays** | cay | 26.29462 | -77.05570 | 26° 17.677′ N | 77° 03.342′ W | land | 13 | — | map only | NOAH BETHEL CAYS |
| ☑ | **Cherokee Sound** | spot | 26.29460 | -77.07120 | 26° 17.676′ N | 77° 04.272′ W | water | 11 | — | map only | CHEROKEE SOUND |
| ☑ | **Winding Bay** | spot | 26.29350 | -77.02390 | 26° 17.610′ N | 77° 01.434′ W | water | 11 | — | map only | WINDING BAY |
| ☑ | **Casuarina Point** | spot | 26.29320 | -77.08050 | 26° 17.592′ N | 77° 04.830′ W | water | 13 | — | map only | CASUARINA POINT |
| ☑ | **Marsh Cay** | cay | 26.29270 | -77.03820 | 26° 17.562′ N | 77° 02.292′ W | water | 14.5 | — | map only | MARSH CAY, an islet in mangrove flats the coastline draws as water |
| ☑ | **Sugar Cay** | cay | 26.29195 | -77.01628 | 26° 17.517′ N | 77° 00.977′ W | land | 13.5 | — | map only | SUGAR CAY |
| ☑ | **North Cay** | cay | 26.29080 | -77.04370 | 26° 17.448′ N | 77° 02.622′ W | water | 14.5 | — | map only | NORTH CAY, lettered over mangrove with no shore drawn; the label is where the chart letters it |
| ☑ | **Chicken Cay** | cay | 26.29080 | -77.05080 | 26° 17.448′ N | 77° 03.048′ W | water | 14.5 | — | map only | CHICKEN CAY, lettered over mangrove with no shore drawn; the label is where the chart letters it |
| ☑ | **Duck Cay** | cay | 26.27619 | -77.07685 | 26° 16.571′ N | 77° 04.611′ W | land | 12.5 | — | map only | DUCK CAY |

## The ones I had to judge

Everything else is either shared with the poster or placed on its island's own
interior point from a coordinate you supplied.

**Spanish Cay** — Two figures were given, 40 km apart. This is the one that agrees with both reference maps; the other is down by Marsh Harbour.

**Manjack Cay** — Placed from your description (north of Green Turtle Cay); the decimal figure given lands south of it, on Treasure Cay. Nunjack Cay.png then confirmed the 3.9 km island rather than the 1.8 km one between it and Green Turtle.

**Baker's Bay** — Moved 1.4 km west off the marina, to the water where the chart places the name.

**Water Cay** — On the islet the Explorer chart names, at the tip of the point north of Archers Cay. It stood at the anchorage coordinate 1.2 km west until the chart showed which islet was meant; an earlier move onto the nearest islet had picked the wrong one.

**Goliath Cay** — At the middle of the Explorer chart's lettering, on the 160 ha island. It was first placed 600 m west, on the island's own interior point. The GeoNames gazetteer puts Goliath Cay about 900 m east of the label and gives the west of the same land another name, Matt Lowe Cay, so the two sources agree on the neighbourhood and not on the spot.

**Dickie's Cay** — Held to z13.5: it sits 400 m from Man-O-War Cay's label, and these labels are HTML markers with no collision detection.

**Matt Lowe's Cay** — The 20 ha island north-east of Sugar Loaf Cay, corrected from the 25 ha one now labelled Sugar Loaf.

**Sugar Loaf Cay** — Labelled Matt Lowe's Cay for one build. Corrected.

**T H E   M A R L S** — A region rather than an island, so in water by intent. Named from the reference maps.

**Channel Cay** — Labelled Pelican Cays for one build. That is the name of the whole group of cays here, so the island got its own name instead.

**Pelican Cays** — A group label for the four islets between Tilloo Cay and Sandy Cay, set in the water on the ocean side, off the two northern islets, where Explorer Chart AB 23 letters the name. The crew landed on the northernmost on Tuesday 26 March.

**Lynyard Cay** — Nudged 0.9 km north and 0.2 km east on the map only, to the middle of the 4.3 km cay. The poster draws this label too and places its day badges around it, so the shared coordinate is untouched.

**Winding Bay** — Moved 1.4 km west-north-west into the bay, where the chart letters it; the earlier point was on Ocean Point.

**Cherokee Sound** — Moved 2.7 km north-west into the sound; the earlier point was on Cherokee settlement.

**Casuarina Point** — Moved 1 km east to the chart's lettering and held to z13, since Cherokee Sound's name is 900 m away.

**Lubbers Quarters** — Moved 4.4 km to the island the chart gives the name, beside Elbow Cay. Shared with the poster, so the sheet moved too.

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

