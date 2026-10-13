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
import hashlib
import json
import os
import shutil
import sys
import time

# Every file opened for reading from here on, so that the build can say at its
# end what it was made from. Before the imports below, because a module may
# read its data as it loads.
_opened = set()


def _note(event, args):
    if event == "open" and isinstance(args[1], str) and args[1][:1] == "r" \
            and "+" not in args[1] and isinstance(args[0], (str, os.PathLike)):
        _opened.add(os.fspath(args[0]))


sys.addaudithook(_note)

from map import clock_fit as C                                    # noqa: E402
from map import export as E                                       # noqa: E402
from map import photo_index as PI                                 # noqa: E402
from map import place as PL                                       # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")
OUT = os.path.join(HERE, "site_build")
# What the last build of site_build read and wrote. Beside the folder and not
# in it: it names files that are not published.
RECORD = os.path.join(HERE, "out", "build_record.json")
# Not sources: the archives stand behind the index, which is one; the media
# are checked against that index by derive; the rest is not this project's.
NOT_SOURCE = (".venv", ".git", "photos", "node_modules", "site_build", "__pycache__")


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
    vsrc = os.path.join(SITE_SRC, "vendor")
    if os.path.isdir(vsrc):
        vdst = os.path.join(dest, "vendor")
        os.makedirs(vdst, exist_ok=True)
        for name in sorted(os.listdir(vsrc)):
            if name in ("README", "VERSION"):
                continue
            shutil.copy2(os.path.join(vsrc, name), os.path.join(vdst, name))
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


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _built(out):
    """The files of a built folder, but for its media, as paths within it."""
    found = []
    for folder, sub, names in os.walk(out):
        if folder == out and "media" in sub:
            sub.remove("media")
        found += [os.path.relpath(os.path.join(folder, n), out).replace(os.sep, "/")
                  for n in names]
    return sorted(found)


def sources(out, root=HERE):
    """What this run has read so far that a build is made from: the modules
    loaded and the files opened, within the project."""
    out = os.path.abspath(out)
    seen = set(_opened) | {getattr(m, "__file__", None) or ""
                           for m in list(sys.modules.values())}
    keep = set()
    for path in seen:
        path = os.path.abspath(path)
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        if (rel.startswith("../") or path.startswith(out + os.sep)
                or any(part in NOT_SOURCE for part in rel.split("/"))
                or not os.path.isfile(path)):
            continue
        keep.add(path)
    return sorted(keep)


def write_record(path, out, inputs, root=HERE):
    """Record what a folder was built from and what the build left in it."""
    record = dict(
        inputs={os.path.relpath(p, root).replace(os.sep, "/"): _sha(p) for p in inputs},
        outputs={n: _sha(os.path.join(out, n)) for n in _built(out)})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".part", "w") as fh:
        json.dump(record, fh, indent=1, sort_keys=True)
    os.replace(path + ".part", path)
    return record


def outdated(path, out, root=HERE):
    """Reasons a folder is not the build of the sources as they stand; empty if
    it is. The media are not looked at: derive.stale answers for those."""
    if not os.path.exists(path):
        return [f"no record of the build ({os.path.relpath(path, root)})"]
    record = json.load(open(path))

    def changed(was, folder):
        return [n for n, sha in sorted(was.items())
                if not os.path.isfile(os.path.join(folder, n))
                or _sha(os.path.join(folder, n)) != sha]

    def some(names):
        return ", ".join(names[:4]) + (f" and {len(names) - 4} more" if len(names) > 4 else "")
    why = []
    src = changed(record["inputs"], root)
    if src:
        why.append(f"changed since the build: {some(src)}")
    made = changed(record["outputs"], out)
    if made:
        why.append(f"not as the build left it: {some(made)}")
    extra = [n for n in _built(out) if n not in record["outputs"]]
    if extra:
        why.append(f"not written by the build: {some(extra)}")
    return why


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
    index_path = os.path.join(HERE, "out", "photo_index.json")
    if a.reuse_index and os.path.exists(index_path):
        photos = json.load(open(index_path))
        print(f"[index ] reused {len(photos)} photographs from {index_path}")
    else:
        photos, stats = PI.index()
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        json.dump(photos, open(index_path, "w"), indent=1)
        print(f"[index ] {len(photos)} photographs, {stats['unreadable']} unreadable "
              f"({time.time() - t0:.1f}s)")

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
    # suite will hold the folder to. Another folder's record goes beside it.
    home = os.path.abspath(a.out) == OUT
    record = write_record(RECORD if home else os.path.abspath(a.out) + ".record.json",
                          a.out, sources(a.out) + [index_path])
    print(f"[record] {len(record['inputs'])} sources, {len(record['outputs'])} files")

    print(f"\nbuilt {a.out} in {time.time() - t0:.0f}s")
    if a.serve:
        # map/serve.py's server: this machine only, and nothing cached.
        from map import serve
        serve.run(a.out, 8000)


if __name__ == "__main__":
    main()
