# Working in this repository

A chart, a poster and a small website of a week's sailing in the Sea of Abaco in
March 2024. The README is the full account; this is what to do and what not to.

This repository is public. The site it builds is unlisted, and its address, the
host's project name and the upload token are deliberately not in it. They are in
`~/.config/bahamas/cloudflare.env` on the keeper's machine.

## The loop: change, build, test, publish

```bash
.venv/bin/python -m map.build --reuse-index    # rebuild site_build/, about a minute
.venv/bin/python -m map.tests                  # everything, about two minutes
.venv/bin/python -m map.publish                # upload, then check what is live
```

- **Build** after any change under `map/` or to `trip.py`, `roads.py`, `poster.py`.
  `--reuse-index` skips re-reading the photo archives. Add `--media` only when
  the build says the media do not match: it re-renders 5,010 images (7 minutes).
  A build removes from `site_build/` any file outside `media/` that it did not
  write, and stops without a record if a source is saved while it runs.
- **Test** before every commit. The suite reads `site_build/`, and fails if that
  folder is not the build of the sources as they stand, so build first: the
  build records what it read and wrote in `out/build_record.json`. The
  last section drives a real browser; it needs Node, Chrome and
  `npm install --no-save playwright-core@1.64.0`, and skips without them.
- **Publish** only when the keeper asks. `python -m map.publish` refuses a folder
  that is stale, uploads, retries if the host fails, and then compares the live
  pages and data with the folder byte for byte. `--check` does everything but
  the upload, and is how to answer "is the website up to date?"; it exits 1
  if it is not.
- A push to GitHub changes nothing on the site. The photographs are not in the
  repository, so nothing is built from it there; the site changes only on publish.

A change that only touches documents or tests needs no build of the site's
files and no publish.

## Setting up a machine

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

The photo archives go in `photos/` (ignored) and are not in the repository;
without them the build can only reuse an existing `out/photo_index.json`.
Publishing needs `~/.config/bahamas/cloudflare.env` with the four settings
`map/publish.py` names at its top. Never print that file, and never ask for a
secret to be pasted into a chat.

## The poster

`.venv/bin/python poster.py --final` writes the 18 x 24 in PNG and PDF to `out/`,
and both are tracked: about 20 MB of history each time. Re-render and commit
them only when the sheet has visibly changed. Compare a new render with the old
one pixel by pixel first; if it is identical, restore the committed files. The
build copies whatever is in `out/` to the site.

## Conventions the keeper has set

- Commit to `main`; it is a solo repository with a linear history. Ask before
  each commit, push and publish, and say what will be uploaded.
- Stage files by name. `docs/code-review-*.md` are working papers and are
  ignored: never commit them. Ask before committing any file you did not create.
- Every fix comes with a test in `map/tests.py`, ideally one shown to fail on
  the old code. Report what was not checked as plainly as what was.
- Report a change in terms of what moved: how many photographs changed tier,
  position, uncertainty or caption, and whether the poster's pixels changed.
- The thumbnails are encoded with Pillow by decision; do not switch them to
  mozjpeg. The keeper is settled on what the site and journal publish; do not
  add privacy caveats to things written for them.
- Temporary files go outside the repository and outside `/tmp`, which is a
  small memory disk on this machine: `~/.cache/` works.

## Where things are

| | |
|---|---|
| `trip.py` | the days, places, labels and track readers everything shares |
| `map/build.py` | the site build: index, clock fit, placement, export, copy |
| `map/site/` | the page: `index.html`, `app.js`, `style.css` |
| `map/tests.py`, `map/browser_check.js` | the suite and its browser half |
| `map/record.py` | what a build read and wrote, and whether the folder still matches |
| `map/publish.py` | upload and verify |
| `poster.py` | the printed sheet and the photobook page |
| `docs/open-items.md` | what is left to do, and what was decided |
