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
    for name in ("index.html", "app.js", "style.css"):
        src = os.path.join(SITE_SRC, name)
        shutil.copy2(src, os.path.join(dest, name))
        copied.append(name)
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


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--media", action="store_true",
                    help="also generate thumbnails and viewing copies (~920 MB)")
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
              f"{made['bytes'] / 2**20:.0f} MB ({time.time() - t:.0f}s)")
    else:
        print("[derive] skipped — pass --media for the 920 MB step")

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
