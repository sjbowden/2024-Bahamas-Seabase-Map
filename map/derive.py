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

**A derivative is only reused if it came from the same source.** Ids are
positions in the time-sorted index, so one photograph added to an archive
renumbers everything after it, and a cache keyed on the id alone would keep
p00001.jpg and show it at whatever is p00001 now -- present, sized right,
stripped clean, and wrong. So each run records, per id, a fingerprint of the
source (archive, member, CRC, size) and of the render settings, and anything
whose fingerprint has changed is rendered again. The record is `.derived.json`
beside the two folders; it holds hashes, not names. A media folder from before
that file existed is rebuilt once, because nothing says what it was made from.

A photograph that cannot be read or written is an error, and any error fails the
run: a build that says "built" with thumbnails missing is worse than one that
stops.
"""
import argparse
import hashlib
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
# Bump when prepare() or render() changes what comes out for the same settings,
# so derivatives made the old way are not mistaken for current ones.
RENDER_VERSION = 1
MANIFEST = ".derived.json"

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


def prepare(data):
    """Decode and normalise one photograph: rotation baked in, sRGB, RGB pixels.

    Everything both sizes share. Split from render() so tests.py can re-derive
    a photograph through the very code that published it, not a hand copy."""
    im = Image.open(io.BytesIO(data))
    im = ImageOps.exif_transpose(im)     # bake rotation in before EXIF goes
    im = _to_srgb(im)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    return im


def render(im, spec):
    """One derivative of a prepared image, as JPEG bytes.

    The only statement of the save settings: one() writes these bytes to disk,
    and tests.py insists a fresh rebuild produces the same ones."""
    copy = im.copy()
    copy.thumbnail((spec["px"], spec["px"]), Image.LANCZOS)
    buf = io.BytesIO()
    # No exif=, no icc_profile=: this is where metadata stops.
    copy.save(buf, "JPEG", quality=spec["quality"], optimize=True,
              progressive=spec["progressive"], subsampling="4:2:0")
    return buf.getvalue()


def fingerprint(photo):
    """What a derivative was made from: the source bytes and the settings.

    A hash rather than the fields themselves, because the record sits in the
    folder that gets published and archive member names are not for publishing.
    """
    src = photo["src"]
    key = json.dumps([src["archive"], src["member"], src.get("crc"), src.get("size"),
                      THUMB, VIEW, RENDER_VERSION], sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()


def one(job):
    """Make both derivatives for one photograph. Returns (id, bytes, error).

    `fresh` says the files on disk are known to be from this source, so any that
    exist can be kept; otherwise both are rendered again whatever is there.
    """
    pid, archive, member, dest, fresh = job
    made = 0
    try:
        wanted = [s for s in (THUMB, VIEW)
                  if not (fresh and _exists(os.path.join(dest, s["name"], f"{pid}.jpg")))]
        if not wanted:
            return pid, 0, None
        with _zip(archive).open(member) as fh:
            im = prepare(fh.read())
        for spec in wanted:
            out = os.path.join(dest, spec["name"], f"{pid}.jpg")
            payload = render(im, spec)
            # Written beside and moved into place, so a run killed mid-write
            # leaves the old file or the new one and never half of either.
            tmp = out + ".part"
            with open(tmp, "wb") as f:
                f.write(payload)
            os.replace(tmp, out)
            made += len(payload)
        return pid, made, None
    except Exception as e:                   # noqa: BLE001
        return pid, made, f"{type(e).__name__}: {e}"[:120]


def _exists(path):
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def _load_manifest(dest):
    try:
        with open(os.path.join(dest, MANIFEST)) as fh:
            m = json.load(fh)
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_manifest(dest, manifest):
    tmp = os.path.join(dest, MANIFEST + ".part")
    with open(tmp, "w") as fh:
        json.dump(manifest, fh, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, os.path.join(dest, MANIFEST))


def fail_on_errors(result):
    """Stop with a failing exit status if any photograph could not be derived."""
    if result["errors"]:
        raise SystemExit(f"{result['errors']} photographs could not be derived — "
                         "the media folder is incomplete")


def run(photos, dest, workers=None, only=None, progress=True, archive_dir=None):
    for spec in (THUMB, VIEW):
        os.makedirs(os.path.join(dest, spec["name"]), exist_ok=True)
    archive_dir = archive_dir or os.path.join(HERE, "photos")
    manifest = _load_manifest(dest)
    todo = [p for p in photos if not p.get("unreadable")]
    if only:
        todo = todo[:only]
    prints = {p["id"]: fingerprint(p) for p in todo}
    jobs = [(p["id"], os.path.join(archive_dir, os.path.basename(_archive_path(p))),
             p["src"]["member"], dest, manifest.get(p["id"]) == prints[p["id"]])
            for p in todo]

    total, done, errors, t0 = len(jobs), 0, [], time.time()
    written = rendered = 0
    workers = workers or max(1, min(8, (os.cpu_count() or 2) - 1))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(one, j) for j in jobs]
        for f in as_completed(futures):
            pid, made, err = f.result()
            done += 1
            written += made
            rendered += bool(made)
            if err:
                errors.append((pid, err))
                manifest.pop(pid, None)     # whatever is on disk is not vouched for
            else:
                manifest[pid] = prints[pid]
            # Often enough that an interrupted run keeps nearly all its work.
            if done % 200 == 0:
                _save_manifest(dest, manifest)
            if progress and (done % 100 == 0 or done == total):
                rate = done / max(time.time() - t0, 1e-6)
                left = (total - done) / rate if rate else 0
                print(f"  {done}/{total}  {written / 2**20:6.0f} MB  "
                      f"{rate:4.1f}/s  ~{left / 60:4.1f} min left"
                      + (f"  {len(errors)} errors" if errors else ""),
                      flush=True)
    _save_manifest(dest, manifest)
    for pid, err in errors[:10]:
        print(f"  ! {pid}: {err}", file=sys.stderr)
    if len(errors) > 10:
        print(f"  ! ... and {len(errors) - 10} more", file=sys.stderr)
    return dict(thumbs=_count(os.path.join(dest, "thumb")),
                views=_count(os.path.join(dest, "view")),
                bytes=_dir_bytes(dest), errors=len(errors), made=rendered,
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
          f"{r['bytes'] / 2**20:.0f} MB, {r['made']} rendered this run, "
          f"{r['errors']} errors, {r['seconds']:.0f}s")
    fail_on_errors(r)


if __name__ == "__main__":
    main()
