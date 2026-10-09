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

The journal is kept outside this repository. These need the notebook to hand.

- [ ] **Left-hand pages.** About 25 of the page photographs show only the right
  page, so a short note near the outer edge of a left page could have been
  missed: pp. 1–4, 6–8, 11–13, 15, 20–25, 27, 33–34, 37–39 and 42.
- [ ] **Confirm three readings in the transcript:**
  - the page headings dated 2025 (p.22) and 2023 (p.24), read as 2024;
  - the spellings standardized to "Hope Town" and "Cay";
  - the two words supplied: "get" on p.24, "trip" on p.43.
- [ ] **Expand the two jottings**, on p.5 and p.17, if wanted.
- [ ] **Story 6, washing up.** Placed at Tilloo Pond on Sunday evening with no
  time shown. The journal describes it that morning at the first anchorage, where
  it would sit on top of story 2.
- [ ] **Story 8, Vernon's.** The marker is an estimate of where the settlement
  is, not the grocery's surveyed position.

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
