# Open items

What is left to do on the chart, the poster and the journal, as of 10 October 2026.
Everything built so far is committed and the site is hosted; these are loose ends.

## Needs a person

- [ ] **Look over the interactive chart on a real screen and a phone.** It is
  hosted (see the README), or run `python -m map.build` then
  `python -m map.serve` and open http://127.0.0.1:8123/. Everything below has
  been checked by measuring the page in a headless browser, which cannot show
  how the chart looks. Changed on 10 October and not yet judged by eye: the
  island names set on their islands and the two water legends moved clear of
  them, Pelican Cays' name in the middle of its chain, story dots seated beside
  the photograph counts, and the viewer's notice on a step to a different spot.
- [ ] **Decide who gets the link.** The site is hosted, unlisted: it asks search
  engines to stay away, and anyone with the address can read it. The stories
  carry the crew's first names, alongside their photographs; two of the sixteen
  scouts were 18 and the rest were minors.
- [ ] **Read the published journal through** (`journal.html`) for anything that
  should not be public. It is live in the repository as `map/journal.md` and on
  the site.
- [ ] **Locations for about 1,040 of the crew's phone photographs.** Google
  Photos removed them from the shared album, so these are placed from the
  track by time. The owners would need to turn on location sharing for the
  album, or send their originals. The keeper's own originals were checked
  and add nothing: all 512 camera positions are already in the build.
- [ ] **Names wanting local confirmation.** Little Ambergris Cay is in
  OpenStreetMap and nowhere else. Twenty-nine cays carry only the GeoNames
  gazetteer's name, where the charts draw the island unnamed or do not reach;
  they are marked ☐ in `docs/map-labels.md`. Goliath Cay is where the chart letters it; the gazetteer
  puts it 900 m further east. `docs/map-labels.md` has the detail for each.

## The journal

The journal is kept outside this repository. The transcript is complete: every
left-hand page has been checked against the notebook, and nothing follows p.43.

Nothing is open here.

## Label overlaps

Each label's box was estimated from its text and type size, and every pair
checked at the lowest zoom where both show. Two overlaps were fixed on 9 October,
and one was left that is seen only below the zoom the chart opens at (z9.9 on a
phone, z10.4 on a desktop): MARSH HARBOUR and HOPE TOWN, z9 to z9.4.

On 10 October the five island names and the two water legends moved. Those seven
were then measured in a headless browser at eleven zooms from 8.5 to 15, each
against every other label and every story dot on screen, and none overlapped.

On 11 October, with 160 labels, every pair was measured in headless Chrome at
each tenth of a zoom from 8 to 18, at a desktop width and a phone's, comparing
the lines of text themselves. The only overlap is the one already known: MARSH
HARBOUR and HOPE TOWN, 19 by 5 px at z9 and gone by z9.3.

The 21 story dots were then measured against every name the same way. Eighteen
dot-and-name pairs cross at some zoom, nearly all of them only while the chart
is zoomed well out. Two stay crossed at every zoom, because the story is set at
the place the name is for: Little Harbour on LITTLE HARBOUR, and Boarding the
Adonai on Marina. Four more last past z11: the three Hope Town stories on HOPE
TOWN, to z12.4 at most, and Fishing for Megalodon on SEA OF ABACO, to z11.2.
Stories start switched off, so none of this shows until they are turned on.

Those three names were then changed, the same day, to start beside their dots
and not straddle them: LITTLE HARBOUR, Marina and HOPE TOWN each begin a fixed
few pixels to the right of the story set at that place, at every zoom, which is
also how the sheet sets the two towns. HOPE TOWN came back from 700 m east to do
it. Measured again: no two names overlap at any zoom, MARSH HARBOUR and HOPE
TOWN included, and twelve dot-and-name pairs are left, all clear by z11.3. Four
of the twelve are still crossed where the chart opens: Fishing for Megalodon on
SEA OF ABACO (to z11.2), The outer reef on Man-O-War Cay (to z11), “Dad…” on
Tilloo Cay (to z10.4) and The barge wreck on Lubbers Quarters (to z10.2).
Clearing those would mean moving island names placed on 10 October, and they
are accepted as they are.

Both measurements are now part of `python -m map.tests`, in
`map/browser_check.js`: it fails if two names overlap at any zoom, or if a
story dot is on a name from z11.5 in.

A story dot under a photograph count now moves to the count's rim.

## Optional

- [ ] **A narrower key for uploads, and the old one rolled.** Uploads now go
  through wrangler's own browser sign-in, not the account's global key, but
  that sign-in can do far more than upload this site. A token limited to
  "Cloudflare Pages: Edit", made in the dashboard and given to wrangler as
  `CLOUDFLARE_API_TOKEN`, would do the same job. The global key was used for
  the first uploads and should be rolled in the dashboard either way.

## Done since this list was first written

- Three optional items closed on 11 October. The seven gazetteer names still
  unsettled were dropped: none had one island to go on, and OpenStreetMap,
  searched that day, has none of them. The two unnamed mangrove islands on the
  Great Abaco shore stay unnamed: the charts, the gazetteer and OpenStreetMap
  all leave them so. North Cay and Chicken Cay in Cherokee Sound stay where the
  chart letters them, over mangrove with no shore drawn; OpenStreetMap has
  neither name, and the by-eye check against the chart was not made.
- Bunks Cay added on 11 October, the first of the unsettled names: a second
  listing puts it 50 m from the corrected point. The map now draws 160 labels.
  Its spacing was then measured with every other label's; see Label overlaps.
  Wood Cay, Long Bay Cay, Dunc Cays, Burnt Cay, Potato Cays and Meal Cay were dropped
  the same day, none of them corroborated; `docs/gazetteer-candidates.md` has each reason.
- Thirty more cays named from the gazetteer on 11 October, once its points were
  found to be offset by a steady 380 m: six with a second source, twenty-four
  on the gazetteer alone. The map now draws 159 labels. Each new one was
  measured in a headless browser at three zooms and overlaps nothing.
- Two figures confirmed on 10 October: the viewer says a step has landed at a
  different spot past 250 m, and a click on a photograph count opens the viewer
  once the count would not break up before zoom 16. The site's address stays
  out of the README, which is public.
- The site hosted on Cloudflare Pages, unlisted, by uploading the built folder.
  The live copy was checked against the local one: pages, data, the poster, and
  a sample of fifty photographs byte for byte.
- The island names set on their islands. Elbow Cay's stood south of Elbow Cay,
  off Tilloo Cay's north tip, on the sheet and the map alike; the sheet was
  re-rendered with it and Tilloo Cay's beside the right shores. Lubbers Quarters'
  name ends at the island's west shore instead of standing 2 km off it, and
  Pelican Cays' sits in the middle of its chain.
- A photograph's stop named for the anchorage, settlement or island it was at,
  where it had taken the nearest of eight labels: the Pelican Cays, Sandy Cay,
  Tahiti Beach and the first night's anchorage off Outer Point Cay were all
  wrong or unnamed. "At anchor" for every stop and "or ashore nearby" within
  600 m of land were both confirmed.
- Photographs taken in one spot stay a count that opens on a click; a story's
  dot moves out from under a count; the key to the photograph dots shows only
  with the photographs; the viewer counts each photograph within its spot and
  says when a step lands at a different one.
- The square photobook page rendered again in both water treatments, so it has
  the corrected names.
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
  removed, in every commit. The backup of the history as it was has since been
  deleted; the reference material that was parked in `out/` is kept outside the
  repository.
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
