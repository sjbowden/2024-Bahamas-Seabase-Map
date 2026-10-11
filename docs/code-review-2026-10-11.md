# Code review — 11 October 2026

Reviewed commit: `1447186` (`Name thirty more cays from the gazetteer`).

This review covers the first-party Python pipeline, interactive chart JavaScript and HTML/CSS, existing tests, and the relevant cached and built data. No implementation changes were made. Findings below distinguish defects visible in the current inputs from defects reproduced with controlled inputs.

## Findings at a glance

| # | Priority | Issue | Evidence |
|---|---|---|---|
| 1 | P1 | Builds without `--media` can publish photographs removed from the index | Reproduced with temporary media and manifest |
| 2 | P2 | JPEG comments survive the metadata stripping pipeline | Reproduced through `prepare()` and `render()` |
| 3 | P2 | Photo placement consumes position spikes rejected elsewhere | 42 such fixes in the current departure-day data |
| 4 | P2 | Matching endpoints across long gaps are treated as a bounded position | Reproduced with a four-hour gap |
| 5 | P2 | Clock fitting chooses the raw-count winner instead of the supported winner | Reproduced with deterministic synthetic timestamps |
| 6 | P2 | Located photographs without a date disappear from both browsing paths | Reproduced in Python and JavaScript |
| 7 | P2 | Selecting the largest photo copy discards usable metadata from other copies | Reproduced through `_merge()` |
| 8 | P2 | One malformed coordinate aborts parsing the whole log batch | Reproduced with a checksum-valid NMEA sentence |
| 9 | P3 | Stories remain open after their day is deselected | Reproduced with the actual JavaScript function |
| 10 | P3 | Shoal cache confuses different geometries with the same area and part count | Reproduced with two translated squares |

P1 means high priority because the failure can expose removed material. P2 means a correctness, reliability, or privacy defect under the stated trigger. P3 means a narrower visual or interaction defect.

## 1. P1 — Removed photographs survive a successful build without `--media`

**Locations:** [map/derive.py:247](../map/derive.py#L247), [map/build.py:174](../map/build.py#L174).

`stale()` checks the derivatives requested by the new index, but never checks whether the media directory contains additional IDs. Only `run()` calls `_sweep()`, and the normal build skips `run()` unless `--media` is supplied.

If the final photograph is removed from the archive/index, the remaining IDs and fingerprints stay unchanged. `stale()` returns `[]`, the build reports success, and both derivatives of the deleted photograph remain in the folder uploaded to the host. Removing an unreadable final record can produce the same condition. The picture is absent from `photos.json` but remains retrievable by its predictable media URL.

**Verification:** Created two indexed IDs with matching fingerprints and nonempty derivatives in a temporary folder. Called `stale()` with only the first record. It returned `[]`; the removed record's viewing copy still existed.

**Suggested correction:** Validate the complete media file set against the readable index even when rendering is skipped. Remove or reject orphan derivatives and unfinished files before reporting a publishable build. No current orphan was found in the existing media directory.

## 2. P2 — JPEG comments bypass the promise that published images contain no metadata

**Location:** [map/derive.py:140](../map/derive.py#L140).

`prepare()` and `render()` retain the image's `info` dictionary. Omitting `exif=` and `icc_profile=` from `save()` removes those fields, but the installed Pillow JPEG encoder also takes the comment from `im.info['comment']` when no explicit comment is supplied. The comment consequently survives resizing and re-encoding in both derivative sizes.

A source JPEG comment can contain an owner's name, coordinates, timestamps, or other information intended to be stripped. The existing metadata tests inspect EXIF and ICC only, so they would approve this output.

**Verification:** Encoded an 8×8 synthetic JPEG with a comment containing dummy GPS, owner, and serial fields. Passed its bytes through `render(prepare(bytes), THUMB)`. Opening the result returned the complete original comment. Scanned the current 5,010 derivatives: none currently contains a JPEG comment, so this is a confirmed pipeline vulnerability rather than an observed disclosure in this build.

**Suggested correction:** Save normalized pixels with explicitly cleared metadata, including comments, and verify the output's metadata markers rather than checking only EXIF and ICC.

## 3. P2 — Placement uses position spikes that the other track consumers reject

**Locations:** [map/place.py:109](../map/place.py#L109), [trip.py:591](../trip.py#L591).

`place.track()` reads `read_fixes()`, which applies the quality gate but deliberately leaves residual coordinate spikes in the stream. `recorded_fixes()` already provides a full-cadence stream with those spikes removed, and corroboration uses it. Placement does not apply an equivalent guard before interpolation or uncertainty calculation. The combined-receiver fallback inherits the same unfiltered handheld positions.

A photograph at or near one of these fixes can be positioned on a spurious excursion. Spikes within a timing window can also inflate its uncertainty. This makes photo placement disagree with the cleaned receiver record even when the timestamp is independently known.

**Verification:** Compared `read_fixes()` and `recorded_fixes()` for all seven days. The departure day contains **42 rejected spikes** that placement still consumes. The worst excluded fix, at `2024-03-28T13:56:25Z`, is about **1.48 km** from the nearby accepted fix. Comparing current published track-placed photographs against interpolation on the cleaned stream found no discrepancy above 30 m; the current photo timestamps do not demonstrate a large misplacement from this defect.

**Suggested correction:** Use the spike-cleaned full-cadence record consistently for placement and its receiver fallback. Retain the separation from the spatially thinned drawing track.

## 4. P2 — Long gaps with nearby endpoints receive unjustifiably small uncertainty rings

**Locations:** [map/place.py:161](../map/place.py#L161), [map/place.py:182](../map/place.py#L182).

`moored_at()` treats endpoints less than 50 m apart as evidence that the receiver stayed there throughout the gap, regardless of duration. `moored_through()` checks additional recorded points in the timing window, but cannot detect a journey and return between sparse reports. The resulting ring is based on observed endpoint displacement, plus 35 m when inReach participates.

Two matching reports four hours apart are compatible with both remaining moored and travelling kilometres before returning. The implementation turns the former interpretation into a bounded position and can label it `calibrated`. Accurate timing does not establish an accurate position during an unobserved interval. The README already acknowledges that sparse overnight reports cannot exclude a trip and return; the exported uncertainty does not carry that limitation.

**Verification:** Supplied identical inReach coordinates four hours apart and asked `moored_through()` about the midpoint with a two-second timing window. It returned a position with `reach_m=0` and `gap_s=14400`. Placement's inReach adjustment would turn that into a 35 m claim, despite there being no report inside the gap.

**Suggested correction:** Represent this as an assumption-based location with unbounded spatial uncertainty, or require additional evidence/appropriate gap limits before publishing a bounded ring. This finding does not establish that an unrecorded journey actually happened.

## 5. P2 — Clock fitting rejects a valid hypothesis after selecting an unsupported raw peak

**Location:** [map/clock_fit.py:257](../map/clock_fit.py#L257).

The coarse winner is chosen by raw coincidence count. Coverage is applied only after that winner is selected and refined. Rivals, however, are ranked by coincidences multiplied by coverage. If the largest raw peak has poor coverage, the function rejects it and stops instead of evaluating the stronger supported peak. Winner and rival therefore use different objectives.

This can leave an entire camera unresolved even though an alternative offset clears the acceptance requirements and substantially exceeds the unsupported peak's coverage-weighted score. The wider search used for archive variants also makes unsupported peaks outside the accepted offset range possible.

**Verification:** Used 100 sorted timestamps generated with `random.Random(442)` across six days beginning 23 March. Reference timestamps contained 100 matches at −4 hours and 80 at +4 hours. Receiver spans covered ±60 seconds around each +4-hour timestamp. The function selected −4 hours and refused it with coverage `0.01` and margin `0.01`; it identified +4 hours as the rival. With the supported reference peak alone, it accepted +4 hours with 80 coincidences and coverage `1.0`.

**Suggested correction:** Compare admissible peaks using the same objective used to judge rivals, then refine and assess the supported winner. An invalid raw-count winner should not prevent evaluation of a viable alternative.

## 6. P2 — GPS photographs without a date become inaccessible

**Locations:** [map/site/app.js:327](../map/site/app.js#L327), [map/site/app.js:669](../map/site/app.js#L669), [map/place.py:390](../map/place.py#L390).

Placement correctly allows a photograph with GPS but no trusted timestamp to receive tier `gps`. If it also has no local date, its day remains `null`. The browser puts it in `onChart`, then removes it from `state.shown` because `state.days` contains only named trip days. The tray includes only records whose tier is outside `ON_CHART`, so it excludes this record too.

The photograph has a valid position and generated media but cannot be opened from either the chart or the tray, even with every day selected. This conflicts with the clock fitter's explicit support for cameras whose coordinates are usable while their times remain unknown.

**Verification:** Passed a GPS-only record at `(26.5, -77.0)` through placement: it returned `tier='gps', day=None`. Executed the actual `refreshPhotos()` function in a Node VM with that record and a named day selected: `state.shown.length` became zero. No such record exists in the current exported dataset.

**Suggested correction:** Define an explicit browsing policy for undated located photographs, such as keeping them visible independently of day toggles or listing them in an undated tray section.

## 7. P2 — Metadata from a valid alternate photo copy is discarded

**Location:** [map/photo_index.py:236](../map/photo_index.py#L236).

`_merge()` chooses the largest copy as the pixel source and also takes all primary metadata from that copy. GPS, GPS UTC, timezone offset, and local time available only in another matched copy are lost. Even a readable alternate copy cannot rescue a group if the largest copy is marked unreadable: `readable()` subsequently drops the whole photograph.

Choosing the best pixels does not imply that copy has the best metadata. A re-export that preserves pixels but strips tags can downgrade a previously located photograph to inferred or unplaced, or remove it entirely when the chosen copy is unreadable. The header documents that the currently measured shared copies have no GPS asymmetry; this is a conditional defect when that property changes.

**Verification:** Merged two copies with matching identity and local time. The larger copy lacked GPS/timezone fields; the smaller carried GPS, GPS UTC, and `-04:00`. The merged record returned `None` for all three fields.

**Suggested correction:** Choose a readable pixel source and resolve metadata independently across matched copies, preserving conflicts for downstream handling rather than treating file size as the metadata authority.

## 8. P2 — A malformed coordinate crashes the NMEA batch parser

**Locations:** [parse_nmea.py:30](../parse_nmea.py#L30), [parse_nmea.py:89](../parse_nmea.py#L89).

Coordinate conversion occurs outside a `try` block. A checksum-valid active RMC sentence with a malformed latitude or longitude raises `ValueError` from `float()`, aborting `parse_file()` and the entire batch. Other malformed fields are skipped, making coordinates an inconsistent failure path. Checksum validity only establishes that the supplied bytes match the checksum; it does not validate their numeric format.

**Verification:** Generated a valid checksum for `GPRMC,120000.00,A,xxxx,N,07700.000,W,1.0,0.0,250324,,,A` and passed the sentence to `parse_file()` in a temporary log. It raised `ValueError: could not convert string to float: 'x'` rather than skipping the fix. This malformed sentence is synthetic; no such failure was observed in the committed logs.

**Suggested correction:** Treat invalid coordinate conversions as rejected records, and validate coordinate/hemisphere ranges before admitting a fix.

## 9. P3 — Deselecting a day leaves its story popup visible

**Location:** [map/site/app.js:447](../map/site/app.js#L447).

`refreshStories()` hides markers according to the selected days, but removes the open popup only when the entire stories layer is disabled. Opening a story and then deselecting its day, or clicking `none`, leaves that day's story over an otherwise filtered chart. A popup combining nearby stories from multiple days also retains deselected content.

**Verification:** Executed the actual function in a Node VM with stories enabled, a Sunday story/popup, and only Monday selected. The marker's display became `none`, but the popup's `remove()` method was never called.

**Suggested correction:** Track which stories an open popup contains and close or rebuild it when day selection changes.

## 10. P3 — Shoal memoization can return geometry from a different coastline

**Location:** [trip.py:670](../trip.py#L670).

The cache key contains buffer distance, rounded area, and polygon count. Different geometries can share all three values, including a simple translation or a shape change preserving area. A second request then receives the first geometry's shoal halo. The key does not establish the spatial identity described in the function's documentation.

**Verification:** Requested the same buffer for `box(0, 0, 1, 1)` and `box(10, 0, 11, 1)` in one process. The returned objects were identical; the second halo's bounds remained around the first square near longitude zero. No collision was demonstrated between the current poster and map coastlines.

**Suggested correction:** Key the memoization on geometry content or an equivalent reliable geometry identity in addition to the buffer distance.

## Validation and limits

- Ran `.venv/bin/python -m map.tests`: **221 passed, 1 failed**. The failure was `this built folder is not carrying the candidate preview`; the existing build carries the optional preview. This is a build-state observation, not an additional implementation finding. The test initially hit the sandbox's multiprocessing socket restriction and completed after approved execution outside the sandbox.
- Ran `node --check map/site/app.js`: passed.
- Exercised targeted Python functions with temporary fixtures and actual JavaScript functions with a Node VM and minimal DOM/map stubs. These interaction reproductions do not constitute a full browser test.
- Checked all current derivatives for JPEG comments, compared raw and cleaned receiver streams, and checked current media IDs/fingerprints. The existing media set has no orphan IDs and the fingerprints match the current index.
- Did not deploy, regenerate the site/poster, modify source files, or install dependencies. Existing tests can create disposable fixtures and ignored geometry caches; tracked files remained unchanged before adding this report.
- Vendored MapLibre internals were not audited. Full image-decoder robustness, visual layout on real devices, and hosting/account configuration were outside this review. Passing checks and the absence of additional findings are not a guarantee that no other defects exist.
