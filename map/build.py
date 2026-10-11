#!/usr/bin/env python3
"""Build the whole site into site_build/, from the archives to a servable folder.

    python -m map.build                  # everything except the 900 MB of media
    python -m map.build --media          # ...including derivatives
    python -m map.build --serve          # then serve it on :8000

Stages, in the order the risk runs:

    photo_index  read EXIF out of the zips            ~4 s
    clock_fit    resolve every photograph's UTC       ~1 s
    place        positions, tiers, uncertainties      ~1 s
    export       GeoJSON at three zoom bands          ~17 s
    site         copy index.html, app.js, style.css, vendor/
    derive       thumbnails and viewing copies        long, and only with --media

Everything but `derive` runs in under half a minute, so the chart can be rebuilt
and looked at freely; the expensive stage is opt-in and idempotent.
"""
import argparse
import json
import os
import shutil
import time

from map import clock_fit as C
from map import export as E
from map import photo_index as PI
from map import place as PL

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site")
OUT = os.path.join(HERE, "site_build")


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


CANDIDATES = os.path.join(HERE, "docs", "gazetteer-candidates.md")


def candidates(dest):
    """Write the names in docs/gazetteer-candidates.md as points to look at.

    A preview for deciding which of them to add: the page marks each with a red
    dot. The document is the one record of them, so its tables are read rather
    than kept a second time; a row counts if it has a proposed label point.
    """
    feats, verdict = [], None
    for line in open(CANDIDATES, encoding="utf-8"):
        if line.startswith("## "):
            verdict = line[3:].strip()
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 7 or cells[0] in ("Name", "---"):
            continue
        try:
            lat, lon = (float(v) for v in cells[4].split("(")[0].split(","))
        except ValueError:
            continue
        feats.append(dict(type="Feature",
                          properties=dict(label=cells[0], verdict=verdict,
                                          kind=cells[1], note=cells[6]),
                          geometry=dict(type="Point", coordinates=[lon, lat])))
    with open(os.path.join(dest, "data", "candidates.geojson"), "w") as fh:
        json.dump(dict(type="FeatureCollection", features=feats), fh)
    return len(feats)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--media", action="store_true",
                    help="also generate thumbnails and viewing copies (~920 MB)")
    ap.add_argument("--serve", action="store_true",
                    help="serve the result on :8000 when the build finishes")
    ap.add_argument("--reuse-index", action="store_true",
                    help="skip re-reading the archives if out/photo_index.json exists")
    ap.add_argument("--candidates", action="store_true",
                    help="mark the unadded gazetteer names in red, to look at "
                         "locally; never upload a folder built this way")
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
        # Not rendering is fine; publishing pictures that no longer belong to
        # their records is not. Ids are positions in the index, so if the index
        # moved under an existing media folder, say so and stop.
        from map import derive
        media = os.path.join(a.out, "media")
        stale = derive.stale(photos, media)
        if stale is None:
            print("[derive] skipped — pass --media for the 920 MB step")
        elif stale:
            raise SystemExit(
                f"[derive] {len(stale)} photographs no longer match the media on "
                f"disk (e.g. {', '.join(stale[:3])}) — run again with --media")
        else:
            print(f"[derive] skipped — the media on disk matches all "
                  f"{len(photos)} photographs")

    # Every build settles this, so a folder that had the preview loses it on the
    # next ordinary build rather than carrying it to the host.
    meta_path = os.path.join(a.out, "data", "meta.json")
    meta = json.load(open(meta_path))
    cand_path = os.path.join(a.out, "data", "candidates.geojson")
    if a.candidates:
        n = candidates(a.out)
        meta["candidates"] = True
        print(f"[names ] {n} gazetteer candidates marked in red -- LOCAL PREVIEW, "
              f"do not upload")
    else:
        meta.pop("candidates", None)
        if os.path.exists(cand_path):
            os.remove(cand_path)
    json.dump(meta, open(meta_path, "w"))

    print(f"\nbuilt {a.out} in {time.time() - t0:.0f}s")
    if a.serve:
        import http.server
        import socketserver
        os.chdir(a.out)
        print("serving http://localhost:8000/  (ctrl-c to stop)")
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("", 8000),
                                    http.server.SimpleHTTPRequestHandler) as s:
            s.serve_forever()


if __name__ == "__main__":
    main()
