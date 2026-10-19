#!/usr/bin/env python3
"""Build the whole site into site_build/, from the archives to a servable folder.

    python -m map.build                  # everything except the 620 MB of media
    python -m map.build --media          # ...including derivatives
    python -m map.build --serve          # then serve it on :8000

Stages, in the order the risk runs:

    photo_index  read EXIF out of the zips            ~4 s
    clock_fit    resolve every photograph's UTC       ~1 s
    place        positions, tiers, uncertainties      ~1 s
    export       GeoJSON at three zoom bands          ~17 s
    site         copy index.html, app.js, style.css, vendor/
    derive       thumbnails and viewing copies        long, and only with --media
    record       what was read and what was written, for publish and the suite

Everything but `derive` runs in under half a minute, so the chart can be rebuilt
and looked at freely; the expensive stage is opt-in and idempotent.
"""
import argparse
import json
import os
import shutil
import time

# Before the imports below, because a module may read its data as it loads:
# from here on every file read is noted, for the record the build ends with.
from map import record as R
R.watch()

from map import clock_fit as C                                    # noqa: E402
from map import export as E                                       # noqa: E402
from map import photo_index as PI                                 # noqa: E402
from map import place as PL                                       # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")
OUT = os.path.join(HERE, "site_build")
VENDOR = os.path.join(SITE_SRC, "vendor")
# The vendored library's own notes, which stay where they are.
VENDOR_NOTES = ("README", "VERSION")


def copy_site(dest):
    """The web app itself: three files and the vendored map library."""
    os.makedirs(dest, exist_ok=True)
    copied = []
    for name in ("index.html", "app.js", "style.css", "journal.css"):
        src = os.path.join(SITE_SRC, name)
        shutil.copy2(src, os.path.join(dest, name))
        copied.append(name)
    # The journal, as a page: rendered here rather than kept as HTML, so the text
    # is edited in one plain file.
    from map import journal
    with open(os.path.join(dest, "journal.html"), "w", encoding="utf-8") as fh:
        fh.write(journal.render())
    copied.append("journal.html")
    # The printed sheet, for download. Only what export() listed in meta.json,
    # so the page never offers a file that is not there.
    for f in E.poster_files():
        os.makedirs(os.path.join(dest, "poster"), exist_ok=True)
        shutil.copy2(f["src"], os.path.join(dest, f["href"]))
        copied.append(f["href"])
    # Listed and not opened, so noted here, where the listing is: a file added
    # to vendor/ changes what a build makes as surely as an edit to one.
    R.look([VENDOR], but=VENDOR_NOTES)
    if os.path.isdir(VENDOR):
        vdst = os.path.join(dest, "vendor")
        os.makedirs(vdst, exist_ok=True)
        for name in sorted(os.listdir(VENDOR)):
            if name in VENDOR_NOTES:
                continue
            shutil.copy2(os.path.join(VENDOR, name), os.path.join(vdst, name))
            copied.append(f"vendor/{name}")
    # A host that reads this will keep the chart out of search results. Cloudflare
    # Pages and Netlify both honour it; a plain http.server ignores it, which is
    # only ever a local preview.
    with open(os.path.join(dest, "_headers"), "w") as fh:
        fh.write("/*\n  X-Robots-Tag: noindex, nofollow\n")
    with open(os.path.join(dest, "robots.txt"), "w") as fh:
        fh.write("User-agent: *\nDisallow: /\n")
    copied += ["_headers", "robots.txt"]
    return copied


def seal(out, record, made, seen):
    """The end of a build of site_build: clear what this build did not write,
    and record what it read (`seen`, each as it was then) and what it wrote."""
    late = R.changed(seen)
    if late:
        raise SystemExit(f"[record] changed while the build ran: {', '.join(late)} "
                         f"— build again; {out} holds what was built from the "
                         "earlier files and is not recorded as built")
    # Before anything is cleared, which cannot be taken back: if the build did
    # not write what it says it wrote, the list it would clear by is wrong.
    short = R.unwritten(out, made)
    if short:
        raise SystemExit(f"[record] the build did not write {', '.join(short)}; "
                         f"nothing in {out} has been cleared and it is not "
                         "recorded as built")
    # A poster no longer rendered, a data file no longer exported: an earlier
    # build's, and nothing a build from these sources would publish. Then the
    # folders that leaves empty.
    left = R.strays(out, made)
    for name in left:
        try:
            (os.rmdir if name.endswith("/") else os.remove)(os.path.join(out, name))
        except OSError as e:
            raise SystemExit(f"[site  ] could not clear {name} from {out} ({e}); "
                             "it is not recorded as built") from None
    if left:
        print(f"[site  ] cleared {len(left)} files and folders this build did not "
              f"write: {', '.join(left)}")
    written = R.write_record(record, out, seen, made)
    print(f"[record] {len(written['inputs'])} sources, {len(written['outputs'])} files")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--media", action="store_true",
                    help="also generate thumbnails and viewing copies (~620 MB)")
    ap.add_argument("--serve", action="store_true",
                    help="serve the result on :8000 when the build finishes")
    ap.add_argument("--reuse-index", action="store_true",
                    help="skip re-reading the archives if out/photo_index.json exists")
    a = ap.parse_args()

    t0 = time.time()
    index_path = R.INDEX
    if a.reuse_index and os.path.exists(index_path):
        photos = json.load(open(index_path))
        print(f"[index ] reused {len(photos)} photographs from {index_path}")
    else:
        photos, stats = PI.index()
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        json.dump(photos, open(index_path, "w"), indent=1)
        print(f"[index ] {len(photos)} photographs, {stats['unreadable']} unreadable "
              f"({time.time() - t0:.1f}s)")

    # A source whether this run read it or wrote it.
    R.look([index_path])
    photos, dropped = PI.readable(photos)
    if dropped:
        print(f"[index ] {dropped} could not be read and are left off the site")

    t = time.time()
    per_photo, cameras, _ = C.fit(photos)
    fitted = sum(1 for v in per_photo.values() if v["utc"])
    print(f"[clock ] {fitted} of {len(photos)} have a UTC instant ({time.time() - t:.1f}s)")

    t = time.time()
    placed = PL.place(photos, per_photo, cameras)
    plotted = sum(1 for r in placed
                  if r["tier"] in ("gps", "bracket", "calibrated", "inferred"))
    print(f"[place ] {plotted} plot on the chart ({time.time() - t:.1f}s)")

    # Before anything in the folder is replaced. Not rendering is fine;
    # publishing pictures that no longer belong to their records is not. Ids
    # are positions in the index, so if the index moved under an existing media
    # folder, say so and stop -- with the old data still beside the old pictures,
    # and not new records pointing at them.
    # Whatever no render made is in the way of publishing, with or without
    # --media: nothing here has stripped its metadata. Not removed, since it
    # may be the only copy of something; named, and the build goes no further.
    from map import derive
    strange = derive.foreign(os.path.join(a.out, "media"))
    if strange:
        raise SystemExit(f"[derive] {len(strange)} files in the media folder were not "
                         f"made by the build (e.g. {', '.join(strange[:3])}) — move "
                         f"them out; nothing in {a.out} has been changed")
    media_note = None
    if not a.media:
        from map import derive
        stale = derive.stale(photos, os.path.join(a.out, "media"))
        if stale:
            raise SystemExit(
                f"[derive] {len(stale)} photographs or leftover files do not match "
                f"the media on disk (e.g. {', '.join(stale[:3])}) — run again "
                f"with --media; nothing in {a.out} has been changed")
        media_note = ("[derive] skipped — pass --media for the 620 MB step"
                      if stale is None else
                      f"[derive] skipped — the media on disk matches all "
                      f"{len(photos)} photographs")

    # Only site_build has a record; a build to another folder is one to look
    # at. From here the folder changes, and the last build's record is no
    # longer its: gone now, so that a build which stops leaves none.
    home = os.path.abspath(a.out) == os.path.abspath(OUT)
    if home and os.path.exists(R.RECORD):
        os.remove(R.RECORD)

    t = time.time()
    written = E.export(os.path.join(a.out, "data"), placed)
    print(f"[export] {len(written)} data files, "
          f"{sum(written.values()) / 1024:.0f} KB ({time.time() - t:.1f}s)")

    t = time.time()
    copied = copy_site(a.out)
    print(f"[site  ] {len(copied)} files ({time.time() - t:.1f}s)")

    if a.media:
        from map import derive
        t = time.time()
        made = derive.run(photos, os.path.join(a.out, "media"))
        print(f"[derive] {made['thumbs']} thumbnails, {made['views']} viewing copies, "
              f"{made['bytes'] / 2**20:.0f} MB, {made['made']} rendered this run, "
              f"{made['removed']} removed, {made['errors']} errors "
              f"({time.time() - t:.0f}s)")
        # Before "built": a site with thumbnails missing is not built.
        derive.fail_on_errors(made)
    else:
        print(media_note)

    # Last, when everything has been read and written: what publishing and the
    # suite will hold the folder to.
    if home:
        seal(a.out, R.RECORD, [f"data/{n}" for n in written] + copied, R.read())

    print(f"\nbuilt {a.out} in {time.time() - t0:.0f}s")
    if a.serve:
        # map/serve.py's server: this machine only, and nothing cached.
        from map import serve
        serve.run(a.out, 8000)


if __name__ == "__main__":
    main()
