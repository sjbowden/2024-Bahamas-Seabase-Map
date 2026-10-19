#!/usr/bin/env python3
"""Thumbnails and viewing copies, streamed out of the zips and stripped of EXIF.

    python -m map.derive                 # into site_build/media
    python -m map.derive --only 40       # a sample, for checking the settings

Two sizes per photograph, ~620 MB in total, and this is the only expensive stage
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
stripped clean, and wrong. So each run records, per id and per size, a
fingerprint of the source (archive, member, CRC, size) and of that size's render
settings, and renders again whatever no longer matches. A change to the thumbnail
settings therefore leaves the viewing copies alone.

The record is `out/derived.json`, deliberately *outside* the folder that gets
published: its hashes are of file names that are easy to guess, so publishing it
would let anyone confirm a guess. An entry that no longer matches is struck from
the record before anything is rendered, and the record is saved even when the run
is interrupted, so a file is never vouched for by a fingerprint it does not have.
A media folder with no record is rebuilt once, because nothing says what it was
made from.

**The folder holds what the index asks for and nothing else.** A photograph
dropped from the index has its derivatives removed, and half-written `.part`
files from a killed run are swept up, so neither is published. A sample run
(`--only`) removes nothing.

A photograph that cannot be read or written is an error, and any error fails the
run: a build that says "built" with thumbnails missing is worse than one that
stops.
"""
import argparse
import hashlib
import io
import json
import os
import re
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
# 2: render() stopped copying a JPEG comment through (11 October 2026). Files
# made before that must not pass for current, whatever their source.
RENDER_VERSION = 2
MANIFEST = os.path.join(HERE, "out", "derived.json")
LEGACY_MANIFEST = ".derived.json"      # once kept inside the published folder
_DERIVED = re.compile(r"^(p\d+)\.jpg$")

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
    # No exif=, no icc_profile=: this is where metadata stops. The encoder also
    # writes a JPEG comment out of info if it finds one there, so info goes too.
    copy.info = {}
    copy.save(buf, "JPEG", quality=spec["quality"], optimize=True,
              progressive=spec["progressive"], subsampling="4:2:0")
    return buf.getvalue()


def fingerprint(photo, spec):
    """What one derivative was made from: the source bytes and that size's settings."""
    src = photo["src"]
    key = json.dumps([src["archive"], src["member"], src.get("crc"), src.get("size"),
                      spec, RENDER_VERSION], sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()


def digest(path):
    """The hash of a file's bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _digest_or_none(path):
    """The hash of a file's bytes, or None if it cannot be read: a file that
    cannot be read is not one that can be vouched for."""
    try:
        return digest(path)
    except OSError:
        return None


def _entry(e):
    """(what a derivative was made from, the hash of its bytes) from the record.
    A record from before the bytes were kept has the first and not the second."""
    if isinstance(e, dict):
        return e.get("from"), e.get("sha")
    return (e, None) if isinstance(e, str) else (None, None)


def one(job):
    """Make the derivatives one photograph needs. Returns (id, bytes, files,
    error, {size: hash of what was written}).

    `fresh` names the sizes whose files on disk are known to be from this source,
    so those can be kept if they exist; any other size is rendered again whatever
    is there.
    """
    pid, archive, member, dest, fresh, crc, size = job
    made = files = 0
    shas = {}
    try:
        wanted = [s for s in (THUMB, VIEW)
                  if not (s["name"] in fresh
                          and _exists(os.path.join(dest, s["name"], f"{pid}.jpg")))]
        if not wanted:
            return pid, 0, 0, None, shas
        zf = _zip(archive)
        info = zf.getinfo(member)
        # The index may have been read from an archive somewhere else. A member
        # of the same name here is only the same photograph if it is the same
        # bytes, and a picture filed under another's fingerprint is not allowed.
        if crc is not None and (info.CRC, info.file_size) != (crc, size):
            raise ValueError(f"{member} in {os.path.basename(archive)} is not "
                             "the file the index was made from")
        with zf.open(info) as fh:
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
            shas[spec["name"]] = hashlib.sha256(payload).hexdigest()
            made += len(payload)
            files += 1
        return pid, made, files, None, shas
    except Exception as e:                   # noqa: BLE001
        return pid, made, files, f"{type(e).__name__}: {e}"[:120], shas


def _exists(path):
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def _load_manifest(path, dest):
    """This folder's fingerprints. One record serves every destination, keyed by
    where the files are, so a sample in /tmp cannot vouch for site_build."""
    try:
        with open(path) as fh:
            m = json.load(fh).get(os.path.abspath(dest), {})
        return m if isinstance(m, dict) else {}
    except (OSError, ValueError, AttributeError):
        return {}


def _save_manifest(path, dest, manifest):
    try:
        with open(path) as fh:
            everything = json.load(fh)
        if not isinstance(everything, dict):
            everything = {}
    except (OSError, ValueError):
        everything = {}
    everything[os.path.abspath(dest)] = manifest
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w") as fh:
        json.dump(everything, fh, separators=(",", ":"), sort_keys=True)
    os.replace(tmp, path)


def _orphans(dest, keep):
    """What the index no longer asks for, as (path, what to call it).

    Only this module's own names: pNNNNN.jpg for an id not in `keep`, called by
    its id, and the .part files a killed run leaves behind, called by their file
    names. `keep` of None spares every derivative and leaves only the debris.
    The one rule for both _sweep(), which removes these, and stale(), which
    refuses to publish beside them.
    """
    for spec in (THUMB, VIEW):
        folder = os.path.join(dest, spec["name"])
        for name in (sorted(os.listdir(folder)) if os.path.isdir(folder) else ()):
            m = _DERIVED.match(name)
            if name.endswith(".jpg.part"):
                yield os.path.join(folder, name), name
            elif m and keep is not None and m.group(1) not in keep:
                yield os.path.join(folder, name), m.group(1)


def foreign(dest):
    """Files in a media folder that this module never makes, as paths within
    it: anything but pNNNNN.jpg, and its .part, directly in thumb/ or view/.

    An original copied in by hand, a note, a folder of its own: none of it has
    been through the stripping of metadata, and all of it would be published.
    Named, never removed -- it may be the only copy of something. A link is
    named too, whatever it points at.
    """
    allowed = {spec["name"] for spec in (THUMB, VIEW)}
    found = []
    for folder, sub, names in os.walk(dest):
        rel = os.path.relpath(folder, dest).replace(os.sep, "/")
        ours = rel in allowed
        for name in list(sub):
            path = os.path.join(folder, name)
            if os.path.islink(path):
                found.append(f"{rel}/{name}" if rel != "." else name)
                sub.remove(name)
        for name in names:
            path = os.path.join(folder, name)
            here = f"{rel}/{name}" if rel != "." else name
            if rel == "." and name == LEGACY_MANIFEST:
                continue                # _legacy() names this one
            if not (ours and not os.path.islink(path)
                    and (_DERIVED.match(name) or name.endswith(".jpg.part"))):
                found.append(here)
    return sorted(found)


def _sweep(dest, keep):
    """Remove what the index no longer asks for. Returns how many files went.

    `keep` of None means a sample run, which sweeps the debris and leaves every
    derivative alone.
    """
    gone = 0
    for path, _ in list(_orphans(dest, keep)):
        os.remove(path)
        gone += 1
    legacy = os.path.join(dest, LEGACY_MANIFEST)
    if os.path.exists(legacy):
        os.remove(legacy)
    return gone


def stale(photos, dest, manifest_path=None):
    """Ids whose derivatives on disk are not known to be from this index.

    None if there is no media folder to be wrong -- nothing has been rendered,
    which is a build without pictures, not a build with the wrong ones. It
    renders nothing, but it reads every derivative to hash it: about 610 MB,
    a few seconds with the files in the page cache and longer without.

    A derivative nothing in the index asks for counts too, and so does a .part
    file from a killed run: a photograph taken out of the archive leaves every
    remaining id and fingerprint as it was, and its picture would otherwise go
    on being published at an address that is easy to guess. Only run() sweeps.
    """
    if not any(_count(os.path.join(dest, s["name"])) for s in (THUMB, VIEW)):
        # Nothing finished -- but a run killed before its first rename leaves a
        # .part behind, and that is a picture in the folder all the same.
        return (sorted({what for _, what in _orphans(dest, set())})
                + _legacy(dest)) or None
    manifest = _load_manifest(manifest_path or MANIFEST, dest)
    out = []
    for p in photos:
        if p.get("unreadable"):
            continue
        have = manifest.get(p["id"])
        have = have if isinstance(have, dict) else {}
        for spec in (THUMB, VIEW):
            made_from, sha = _entry(have.get(spec["name"]))
            path = os.path.join(dest, spec["name"], f"{p['id']}.jpg")
            # The bytes as well as the source: a file damaged or replaced since
            # it was made keeps its name and its size, and is not that file.
            if (made_from != fingerprint(p, spec) or sha is None or not _exists(path)
                    or _digest_or_none(path) != sha):
                out.append(p["id"])
                break
    wanted = {p["id"] for p in photos if not p.get("unreadable")}
    return out + sorted({what for _, what in _orphans(dest, wanted)}) + _legacy(dest)


def _legacy(dest):
    """The manifest once kept inside the published folder, if it is still there.

    It lists source fingerprints, which is why it moved out; only run() removes
    it, so a build that does not render has to refuse to publish beside it.
    """
    return [LEGACY_MANIFEST] if os.path.exists(os.path.join(dest, LEGACY_MANIFEST)) else []


def fail_on_errors(result):
    """Stop with a failing exit status if any photograph could not be derived."""
    if result["errors"]:
        raise SystemExit(f"{result['errors']} photographs could not be derived — "
                         "the media folder is incomplete")


def run(photos, dest, workers=None, only=None, progress=True, archive_dir=None,
        manifest_path=None):
    for spec in (THUMB, VIEW):
        os.makedirs(os.path.join(dest, spec["name"]), exist_ok=True)
    archive_dir = archive_dir or os.path.join(HERE, "photos")
    manifest_path = manifest_path or MANIFEST
    todo = [p for p in photos if not p.get("unreadable")]
    if only:
        todo = todo[:only]
    ids = {p["id"] for p in todo}
    removed = _sweep(dest, None if only else ids)

    prints = {p["id"]: {s["name"]: fingerprint(p, s) for s in (THUMB, VIEW)}
              for p in todo}
    # Strike what no longer matches *before* rendering, and say so on disk. If
    # the run dies after replacing a file, the record must not still be holding
    # the old fingerprint for it -- that is how a wrong picture gets trusted.
    was = _load_manifest(manifest_path, dest)
    manifest = {}
    for pid, old in was.items():
        if not isinstance(old, dict):
            continue                # a record from before sizes had their own
        if pid not in prints:
            if only:
                manifest[pid] = old     # a sample says nothing about the rest
            continue                # otherwise: gone from the index
        # Kept only if it is still from this source and still the bytes that
        # were made: a file damaged or pasted over since is made again. So is
        # one recorded before the bytes were kept: what is on disk under it is
        # exactly what this cannot vouch for.
        kept = {}
        for name, e in old.items():
            made_from, sha = _entry(e)
            path = os.path.join(dest, name, f"{pid}.jpg")
            if prints[pid].get(name) != made_from or sha is None or not _exists(path):
                continue
            if _digest_or_none(path) == sha:
                kept[name] = {"from": made_from, "sha": sha}
        if kept:
            manifest[pid] = kept
    if manifest != was:
        _save_manifest(manifest_path, dest, manifest)

    jobs = [(p["id"], os.path.join(archive_dir, os.path.basename(_archive_path(p))),
             p["src"]["member"], dest, tuple(manifest.get(p["id"], ())),
             p["src"].get("crc"), p["src"].get("size"))
            for p in todo]

    total, done, errors, t0 = len(jobs), 0, [], time.time()
    written = rendered = files = 0
    workers = workers or max(1, min(8, (os.cpu_count() or 2) - 1))
    try:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(one, j) for j in jobs]
            for f in as_completed(futures):
                pid, made, n, err, shas = f.result()
                done += 1
                written += made
                files += n
                rendered += bool(n)
                if err:
                    errors.append((pid, err))
                    manifest.pop(pid, None)     # whatever is on disk is not vouched for
                else:
                    was_kept = manifest.get(pid, {})
                    manifest[pid] = {
                        name: {"from": made_from,
                               "sha": shas.get(name) or was_kept.get(name, {}).get("sha")}
                        for name, made_from in prints[pid].items()}
                # Often enough that an interrupted run keeps nearly all its work.
                if done % 200 == 0:
                    _save_manifest(manifest_path, dest, manifest)
                if progress and (done % 100 == 0 or done == total):
                    rate = done / max(time.time() - t0, 1e-6)
                    left = (total - done) / rate if rate else 0
                    print(f"  {done}/{total}  {written / 2**20:6.0f} MB  "
                          f"{rate:4.1f}/s  ~{left / 60:4.1f} min left"
                          + (f"  {len(errors)} errors" if errors else ""),
                          flush=True)
    finally:
        # Ctrl-C, or a worker killed for memory: what did finish is still true.
        _save_manifest(manifest_path, dest, manifest)
    for pid, err in errors[:10]:
        print(f"  ! {pid}: {err}", file=sys.stderr)
    if len(errors) > 10:
        print(f"  ! ... and {len(errors) - 10} more", file=sys.stderr)
    return dict(thumbs=_count(os.path.join(dest, "thumb")),
                views=_count(os.path.join(dest, "view")),
                bytes=_dir_bytes(dest), errors=len(errors), made=rendered,
                files=files, removed=removed,
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
          f"{r['removed']} removed, {r['errors']} errors, {r['seconds']:.0f}s")
    fail_on_errors(r)


if __name__ == "__main__":
    main()
