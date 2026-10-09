# Open items

What is left to do on the chart, the poster and the journal, as of 9 October 2026.
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
- [ ] **Names wanting local confirmation:** Goliath Cay, and the three that carry
  only OpenStreetMap's name — Outer Point Cay, Gumelemi Cay and Little Ambergris
  Cay. `docs/map-labels.md` marks all four.

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

- [ ] **Cays the charts name that are not on the chart.** Each was read on the
  Explorer sheets but could not be tied to one island the coastline draws:
  - joined to Great Abaco in the coastline data: Davids, Snake, Archers, Okra,
    Randalls and Armstrong Cays;
  - ambiguous between neighbours: Black Point, Hills, Joes, Rocky Harbour, Aaron
    and Spirit Cays;
  - too small, or mangrove with no outline: Chicken, Marsh, North, Nurse, Little
    Pigeon and Big Lake Cays.
- [ ] **Three chart tiles not read**, over the Marls and inland Great Abaco,
  which the Explorer sheets barely cover.
- [ ] **Three unnamed mangrove islands** on the Great Abaco shore, listed in a
  comment in `trip.py`.
- [ ] **A second copy of `bahamas-pre-rewrite.bundle`**, the only copy of the
  history from before the rewrite. It is on one machine only.
- [ ] **The hand-drawn Abaco map** (`out/LOCALABACOMAP.jpg`, gitignored), if a
  second reference for the cay names is wanted on this machine.

## Done since this list was first written

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
