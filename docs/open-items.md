# Open items

What is left to do on the chart, the poster and the journal, as of 8 October 2026.
Everything built so far is committed and pushed; these are loose ends and one
decision.

## Worth doing soon

- [ ] **Look over the interactive chart on a real screen.** Run
  `python -m map.serve` and open http://127.0.0.1:8123/. The 97 place labels and
  21 story dots have only been checked in headless screenshots, which did not
  draw the chart reliably. The labels have no collision detection, so expect a
  few to crowd each other; the fix is each label's zoom threshold in `trip.py`
  (`MAP_CAYS`, `MAP_SPOTS`).
- [ ] **Regenerate `out/compare_offset.png`** with `python poster.py --compare`.
  It is tracked, covers the Lubbers Quarters area, and still shows that label in
  its old position.
- [ ] **Update `locations.md`** in the journal folder. Its "what doesn't line up"
  section lists discrepancies that have since been fixed (Tuesday night at Hope
  Town, Sandy Cay on the route line, Saturday's anchorage), and it still shows
  the Pelican Cay stop as open.

## A decision

- [ ] **Who gets the link when the chart is published.** The site is built but
  not hosted. The stories carry the crew's first names, alongside their
  photographs. The site tells search engines not to index it (`robots.txt`,
  `_headers`, the page's own meta tag), but anyone with the link can read it.

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
- [ ] **Names wanting local confirmation:** Goliath Cay, and the three that carry
  only OpenStreetMap's name — Outer Point Cay, Gumelemi Cay and Little Ambergris
  Cay. `docs/map-labels.md` marks all four.
- [ ] **Three unnamed mangrove islands** on the Great Abaco shore, listed in a
  comment in `trip.py`.
- [ ] **A second copy of `bahamas-pre-rewrite.bundle`**, the only copy of the
  history from before the rewrite. It is on one machine only.
- [ ] **The hand-drawn Abaco map** (`out/LOCALABACOMAP.jpg`, gitignored), if a
  second reference for the cay names is wanted on this machine.
