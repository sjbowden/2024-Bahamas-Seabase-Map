#!/usr/bin/env python3
"""Thumbnails and viewing copies, streamed out of the zips and stripped of EXIF.

    python -m map.derive                 # into site_build/media
    python -m map.derive --only 40       # a sample, for checking the settings

Two sizes per photograph, ~920 MB in total, and this is the only expensive stage
in the build — which is why the design put it last, after placement was trusted.

    thumbnail   256 px, q72   ~38 MB    what the clusters and the tray show
    view       1600 px, q82  ~880 MB    what the viewer opens

Three things it must get right, none of them obvious:

**Orientation before stripping.** A phone records a portrait photograph as
landscape pixels plus an EXIF orientation flag. Strip the EXIF first and every
portrait frame on the chart is on its side, permanently, in a 900 MB artefact.
So the rotation is baked into the pixels and *then* the tags are dropped.

**Colour before stripping.** Recent iPhones write Display P3 pixels with an ICC
profile to say so. Drop that profile and a browser reads the same numbers as
sRGB, which pushes every saturated colour — the water, most of this trip —
noticeably harder than it was. So P3 is converted to sRGB properly first.

**Nothing published carries metadata.** No GPS, no serial numbers, no timestamps
in the files themselves: the coordinates the site needs are in photos.json, where
they have been through the guards, and the ones the camera wrote are not.

Idempotent: an interrupted run resumes, because it skips any derivative already
on disk. That matters at this size on a laptop.
"""
import argparse
import io
import json
import os
import sys
import time
import zipfile
from concurrent.futures import ProcessPoolExecutor, as_completed

from PIL import Image, ImageCms, ImageFile, ImageOps

ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

THUMB = dict(name="thumb", px=256, quality=72, progressive=False)
VIEW = dict(name="view", px=1600, quality=82, progressive=True)

_ZIPS = {}          # per-process handle cache; a zip is cheap to reopen, not to reopen 2,505 times
_SRGB = None


def _zip(path):
    if path not in _ZIPS:
        _ZIPS[path] = zipfile.ZipFile(path)
    return _ZIPS[path]


def _srgb():
    global _SRGB
    if _SRGB is None:
        _SRGB = ImageCms.createProfile("sRGB")
    return _SRGB


def _to_srgb(im):
    """Convert away from a tagged wide-gamut profile, or leave sRGB alone."""
    icc = im.info.get("icc_profile")
    if not icc:
        return im
    try:
        src = ImageCms.getOpenProfile(io.BytesIO(icc))
        if "sRGB" in (ImageCms.getProfileDescription(src) or ""):
            return im
        return ImageCms.profileToProfile(im, src, _srgb(), outputMode="RGB")
    except Exception:                       # noqa: BLE001 - a bad profile is not fatal
        return im


def one(job):
    """Make both derivatives for one photograph. Returns (id, bytes, error)."""
    pid, archive, member, dest = job
    made = 0
    try:
        wanted = [s for s in (THUMB, VIEW)
                  if not _exists(os.path.join(dest, s["name"], f"{pid}.jpg"))]
        if not wanted:
            return pid, 0, None
        with _zip(archive).open(member) as fh:
            data = fh.read()
        im = Image.open(io.BytesIO(data))
        im = ImageOps.exif_transpose(im)     # bake rotation in before EXIF goes
        im = _to_srgb(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        for spec in wanted:
            out = os.path.join(dest, spec["name"], f"{pid}.jpg")
            copy = im.copy()
            copy.thumbnail((spec["px"], spec["px"]), Image.LANCZOS)
            # No exif=, no icc_profile=: this is where metadata stops.
            copy.save(out, "JPEG", quality=spec["quality"], optimize=True,
                      progressive=spec["progressive"], subsampling="4:2:0")
            made += os.path.getsize(out)
        return pid, made, None
    except Exception as e:                   # noqa: BLE001
        return pid, made, f"{type(e).__name__}: {e}"[:120]


def _exists(path):
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def run(photos, dest, workers=None, only=None, progress=True):
    for spec in (THUMB, VIEW):
        os.makedirs(os.path.join(dest, spec["name"]), exist_ok=True)
    jobs = [(p["id"], os.path.join(HERE, "photos",
                                   os.path.basename(_archive_path(p))),
             p["src"]["member"], dest)
            for p in photos if not p.get("unreadable")]
    if only:
        jobs = jobs[:only]

    total, done, errors, t0 = len(jobs), 0, [], time.time()
    written = 0
    workers = workers or max(1, min(8, (os.cpu_count() or 2) - 1))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, j) for j in jobs]
        for f in as_completed(futures):
            pid, made, err = f.result()
            done += 1
            written += made
            if err:
                errors.append((pid, err))
            if progress and (done % 100 == 0 or done == total):
                rate = done / max(time.time() - t0, 1e-6)
                left = (total - done) / rate if rate else 0
                print(f"  {done}/{total}  {written / 2**20:6.0f} MB  "
                      f"{rate:4.1f}/s  ~{left / 60:4.1f} min left"
                      + (f"  {len(errors)} errors" if errors else ""),
                      flush=True)
    for pid, err in errors[:10]:
        print(f"  ! {pid}: {err}", file=sys.stderr)
    return dict(thumbs=_count(os.path.join(dest, "thumb")),
                views=_count(os.path.join(dest, "view")),
                bytes=_dir_bytes(dest), errors=len(errors),
                seconds=round(time.time() - t0, 1))


def _archive_path(p):
    """Which zip this photograph's pixels come from."""
    label = p["src"]["archive"]
    return {"mine": "Seabase 2024.zip",
            "crew": "Seabase 2024-1-001.zip"}[label]


def _count(d):
    return sum(1 for n in os.listdir(d) if n.endswith(".jpg")) if os.path.isdir(d) else 0


def _dir_bytes(d):
    t = 0
    for root, _, names in os.walk(d):
        for n in names:
            t += os.path.getsize(os.path.join(root, n))
    return t


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--index", default=os.path.join(HERE, "out", "photo_index.json"))
    ap.add_argument("--dest", default=os.path.join(HERE, "site_build", "media"))
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--only", type=int, default=None,
                    help="stop after N photographs, for checking the settings")
    a = ap.parse_args()

    photos = json.load(open(a.index))
    r = run(photos, a.dest, workers=a.workers, only=a.only)
    print(f"\n{r['thumbs']} thumbnails, {r['views']} viewing copies, "
          f"{r['bytes'] / 2**20:.0f} MB, {r['errors']} errors, {r['seconds']:.0f}s")


if __name__ == "__main__":
    main()
