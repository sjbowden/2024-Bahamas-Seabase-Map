# Open items

What is left to do on the chart, the poster and the journal, as of 10 October 2026.
Everything built so far is committed; these are loose ends and one decision.

## Needs a person

- [ ] **Look over the interactive chart on a real screen.** Run
  `python -m map.build` then `python -m map.serve` and open
  http://127.0.0.1:8123/. The labels have been checked for overlap by
  calculation (see below) and the story dots in headless screenshots, but
  nobody has yet judged how the chart looks.
- [ ] **Decide who gets the link when the chart is published.** The site is built
  but not hosted. The stories carry the crew's first names, alongside their
  photographs; two of the sixteen scouts were 18 and the rest were minors. The
  site tells search engines not to index it (`robots.txt`, `_headers`, the page's
  own meta tag), but anyone with the link can read it.
- [ ] **Read the published journal through** (`journal.html`) for anything that
  should not be public. It is live in the repository as `map/journal.md`.
- [ ] **Locations for about 1,040 of the crew's phone photographs.** Google
  Photos removed them from the shared album, so these are placed from the
  track by time. The owners would need to turn on location sharing for the
  album, or send their originals. The keeper's own originals were checked
  and add nothing: all 512 camera positions are already in the build.
- [ ] **Two wordings in the photograph notes to confirm:** every stop on the
  water reads "at anchor", moorings included, and "or ashore nearby" is
  offered within 600 m of land.
- [ ] **Names wanting local confirmation.** Little Ambergris Cay is in
  OpenStreetMap and nowhere else. Four cays carry only the GeoNames gazetteer's
  name, where the charts draw the island unnamed: Pond Apple, Push, Lower Hill
  and Woolendean Cays. Goliath Cay is where the chart letters it; the gazetteer
  puts it 900 m further east. `docs/map-labels.md` has the detail for each.

## The journal

The journal is kept outside this repository. The transcript is complete: every
left-hand page has been checked against the notebook, and nothing follows p.43.

Nothing is open here.

## Label overlaps

Each label's box was estimated from its text and type size, and every pair
checked at the lowest zoom where both show. Two overlaps were fixed on 9 October:
Lubbers Quarters ran into Elbow Cay's name until z10.5, and Hotel into Marina
until z12.8. Two remain, both below the zoom the chart opens at (z9.9 on a
phone, z10.4 on a desktop), so they are seen only after zooming out:

- MARSH HARBOUR and HOPE TOWN, z9 to z9.4;
- Elbow Cay and Lubbers Quarters, z9.6 to z9.8.

The estimate does not cover the story dots or the photograph cluster counts,
which can still sit on a name.

## Optional

- [ ] **Two readings to check by eye**, both in Cherokee Sound: North Cay and
  Chicken Cay are lettered over mangrove with no shore drawn, so each label is
  where the chart's lettering is rather than on an island.
- [ ] **Two unnamed mangrove islands** on the Great Abaco shore, listed in a
  comment in `trip.py`. Neither the charts nor the gazetteer names them.
- [ ] **About fifty more gazetteer names**, most of them in the Marls. They were
  left off because the gazetteer's points run up to 400 m east of the charts,
  and each of these has two or more islands that could answer to the name.

## Done since this list was first written

- The clone on the other machine replaced with a fresh one after the history
  rewrite. The old commits on GitHub are left for its garbage collection.
- The photograph notes no longer offer "ashore" under way or out of reach of
  land, and no longer call a fix on land the boat's track.
- Fifteen more cays named with the GeoNames gazetteer as a second source: eleven
  the charts letter too, four on the gazetteer alone. Outer Point Cay turned out
  to be lettered on the chart after all, and Gumelemi Cay is in the gazetteer.
  Aaron Cay and Goliath Cay each moved to where the two sources point.
- Nurse Cay closed: the only one in the Bahamas gazetteer is in the Ragged
  Islands, so the earlier note of it in Abaco was a misreading.
- Seventeen more cays named from a closer reading of the Explorer charts, with a
  graticule over each view so positions could be read off it. The three chart
  tiles over the Marls were read too: the Explorer sheets do not reach them,
  and the base chart names nothing there.
- The drive home on 28 March cut at the Hillsboro exit, and old poster renders
  removed, in every commit. A backup of the history as it was is kept outside
  the repository, as is the reference material that was parked in `out/`.
- The poster re-rendered and found identical; the published photographs checked
  for metadata, and both pages for broken links and script errors.
- The journal published as a page of the site, lightly edited; the poster offered
  for download from the chart; photographs and stories off until ticked.
- Two code reviews' findings fixed, nineteen in all, each with a test.
- `out/compare_offset.png` regenerated, so it shows Lubbers Quarters where it now is.
- The journal's `locations.md` brought up to date.
- The full site build runs on this machine, thumbnails included.
- The transcript's readings confirmed: both stray year headings are 2024, the
  chart spellings stay, and the two supplied words are right.
- The notebook's left-hand pages checked: nothing was missed, and the journal
  ends at p.43.
- The two jottings settled: the p.5 one expanded from memory, and the p.17 one
  found to be an outline whose every item the entry already tells.
- Vernon's Store placed from its plus code, G2RR+2FP on Queen's Highway, 300 m
  from the earlier guess. Hope Town's name moved 700 m east on the map to stay
  clear of the story dots.
- The washing-up story moved to the first anchorage on Sunday morning, where the
  journal has it. It is now story 3.
