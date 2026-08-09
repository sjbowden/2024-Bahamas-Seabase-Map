#!/usr/bin/env python3
"""Read every photograph's EXIF header out of the archives, without unpacking.

One record per photograph, carrying everything later steps need to place it:
who took it, when its own clock said, what timezone it thought it was in, and
where it was if it knew. Nothing here decides a position — that is place.py.

    python -m map.photo_index                    # write out/photo_index.json
    python -m map.photo_index --report           # and describe what it found

Two archives, and which is which matters:

  photos/Seabase 2024.zip          845 images — mine
  photos/Seabase 2024-1-001.zip  2,479 images — the crew's, the superset

819 photographs are in both. The design assumed the crew's copies had been
stripped of GPS and that mine could donate it back; measured, that is not so —
across all 819 shared photographs there is not one where either copy carries
GPS the other lacks. What the two copies *do* disagree about is time: 148 of
them differ, and always by a constant per camera (16h15m for the FinePix), which
is the signature of someone having corrected a camera's clock in one copy and
not the other. So both timestamps are recorded and the disagreement is flagged,
because which one is right is a question for clock_fit, not for a reader of
headers.

Identity is the basename, confirmed by camera model. Not size or CRC: 653 of the
819 shared photographs differ in bytes, because rewriting EXIF rewrites the
file, so a content guard would reject the very matches it was meant to confirm.
Not the filename alone either — IMG_0001.JPG is a name four different cameras in
this set will happily produce.
"""
import argparse
import collections
import io
import json
import os
import zipfile
from datetime import datetime, timedelta

from PIL import Image, ImageFile

# Some of these are 12 MB iPhone frames whose EXIF sits past any sane prefix;
# tolerating a short read is what lets us look at a header without the pixels.
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = None           # a 108 Mpx panorama is not an attack

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_OK = True
except ImportError:                     # 98 HEIC files; without this they are
    HEIC_OK = False                     # listed as unreadable, not fatal

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVES = [("mine", os.path.join(HERE, "photos", "Seabase 2024.zip")),
            ("crew", os.path.join(HERE, "photos", "Seabase 2024-1-001.zip"))]
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic"}

# 256 KB carries the EXIF of all but 28 of these files, and those 28 are only
# large, not broken — so a failure escalates to the whole member rather than
# being reported as unreadable.
PREFIX = 256 * 1024

# The trip. A GPS date stamp outside this window is a bad tag, not a fact: one
# Samsung reports a date 54 years off, which would otherwise fit a clock offset
# of 28 million minutes.
TRIP_LO = datetime(2024, 3, 1)
TRIP_HI = datetime(2024, 4, 30)

_IFD_EXIF, _IFD_GPS = 0x8769, 0x8825
_MAKE, _MODEL, _SERIAL = 0x010F, 0x0110, 0xA431
_DTO, _OFFSET, _SUBSEC = 0x9003, 0x9011, 0x9291
_LAT_REF, _LAT, _LON_REF, _LON, _GPS_TIME, _GPS_DATE = 0x1, 0x2, 0x3, 0x4, 0x7, 0x1D


def _clean(v):
    if v is None:
        return None
    return str(v).replace("\x00", "").strip() or None


def _stamp(v):
    """An EXIF 'YYYY:MM:DD HH:MM:SS', or None if it isn't one.

    A camera that has never had its clock set writes 0000:00:00 00:00:00 rather
    than leaving the tag out, and that parses as a string but not as a time.
    """
    s = _clean(v)
    if not s:
        return None
    try:
        datetime.strptime(s, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None
    return s


def _dms(v, ref):
    """EXIF (deg, min, sec) rationals plus a hemisphere letter to a float."""
    try:
        d, m, s = (float(x) for x in v)
    except (TypeError, ValueError):
        return None
    deg = d + m / 60.0 + s / 3600.0
    return -deg if str(ref).upper().strip() in ("S", "W") else deg


def read_tags(data):
    """The fields we care about, or {'error': ...}. Never raises."""
    try:
        ex = Image.open(io.BytesIO(data)).getexif()
    except Exception as e:                      # noqa: BLE001 - any decoder fault
        return {"error": f"{type(e).__name__}: {e}"[:80]}
    out = {}
    if not ex:
        return out
    out["make"] = _clean(ex.get(_MAKE))
    out["model"] = _clean(ex.get(_MODEL))
    out["serial"] = _clean(ex.get(_SERIAL))
    try:
        sub = ex.get_ifd(_IFD_EXIF)
    except Exception:                           # noqa: BLE001
        sub = {}
    out["time_local"] = _stamp(sub.get(_DTO))
    out["tz_offset"] = _clean(sub.get(_OFFSET))
    out["subsec"] = _clean(sub.get(_SUBSEC))
    out["serial"] = out["serial"] or _clean(sub.get(_SERIAL))
    try:
        g = ex.get_ifd(_IFD_GPS)
    except Exception:                           # noqa: BLE001
        g = {}
    if g and _LAT in g and _LON in g:
        lat = _dms(g[_LAT], g.get(_LAT_REF, "N"))
        lon = _dms(g[_LON], g.get(_LON_REF, "E"))
        if lat is not None and lon is not None and (lat, lon) != (0.0, 0.0):
            out["gps"] = [round(lat, 7), round(lon, 7)]
    # GPS date and time are UTC straight from the satellites — the camera's own
    # clock had no part in them. For any photograph carrying both, the offset
    # between what the camera wrote and what actually happened is arithmetic,
    # not a fit, and that is the strongest anchor in this dataset.
    if g and _GPS_DATE in g and _GPS_TIME in g:
        try:
            d = datetime.strptime(_clean(g[_GPS_DATE]), "%Y:%m:%d")
            h, m, s = (float(x) for x in g[_GPS_TIME])
            t = d + timedelta(hours=h, minutes=m, seconds=s)
            if TRIP_LO <= t <= TRIP_HI:
                out["gps_utc"] = t.strftime("%Y-%m-%dT%H:%M:%SZ")
            else:
                out["gps_utc_rejected"] = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:                       # noqa: BLE001
            pass
    return {k: v for k, v in out.items() if v is not None}


def read_member(zf, info):
    """EXIF for one archive member, escalating past the prefix only if needed."""
    with zf.open(info) as fh:
        tags = read_tags(fh.read(PREFIX))
    if "error" in tags and info.file_size > PREFIX:
        with zf.open(info) as fh:
            tags = read_tags(fh.read())
    return tags


def camera_key(t):
    """How this photograph's camera is identified.

    Serial number where there is one — but only the Canon, the two GoPros and
    the drone report one. Every phone in this set leaves it blank, so eleven
    cameras collapse to their models, and two crew members with the same phone
    would be one clock here. Nothing in the EXIF can separate them; the honest
    move is to name the limit rather than invent a discriminator.
    """
    make, model, serial = t.get("make"), t.get("model"), t.get("serial")
    if not make and not model:
        return "unknown"
    name = " ".join(x for x in (make, model) if x)
    # Canon writes "Canon" into both fields; don't say it twice.
    parts = name.split()
    if len(parts) > 1 and parts[0].lower() == parts[1].lower():
        name = " ".join(parts[1:])
    return f"{name} #{serial}" if serial else name


def index(archives=ARCHIVES, progress=None):
    """One record per photograph across the archives. Returns (photos, stats)."""
    found = collections.OrderedDict()        # basename -> list of copies
    stats = collections.Counter()
    for arch, path in archives:
        if not os.path.exists(path):
            raise SystemExit(f"archive not found: {path}\n"
                             f"(pass --archive mine=PATH --archive crew=PATH)")
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                ext = os.path.splitext(info.filename)[1].lower()
                if ext not in IMAGE_EXT:
                    stats["skipped_not_image"] += 1
                    continue
                if ext == ".heic" and not HEIC_OK:
                    stats["heic_no_decoder"] += 1
                tags = read_member(zf, info)
                stats[f"read_{arch}"] += 1
                if "error" in tags:
                    stats["unreadable"] += 1
                name = os.path.basename(info.filename)
                found.setdefault(name, []).append(dict(
                    archive=arch, member=info.filename, size=info.file_size,
                    crc=info.CRC, ext=ext, tags=tags))
                if progress and stats.total() % 500 == 0:
                    progress(stats)

    photos = []
    for name, copies in found.items():
        # Same name, different camera: a genuine collision, not one photograph.
        by_cam = collections.OrderedDict()
        for c in copies:
            by_cam.setdefault(camera_key(c["tags"]), []).append(c)
        if len(by_cam) > 1:
            stats["name_collisions"] += 1
        for cam, group in by_cam.items():
            photos.append(_merge(name, cam, group, stats,
                                 suffix=len(by_cam) > 1))
    photos.sort(key=lambda p: (p["time_local"] or "9999", p["name"]))
    for i, p in enumerate(photos):
        p["id"] = f"p{i:05d}"
    return photos, stats


def _merge(name, cam, group, stats, suffix=False):
    """Fold every copy of one photograph into a single record."""
    # Pixels come from the largest copy: re-encoding only ever cost detail.
    src = max(group, key=lambda c: c["size"])
    times = {c["archive"]: c["tags"].get("time_local") for c in group}
    distinct = {t for t in times.values() if t}
    rec = dict(
        id=None, name=name, ext=src["ext"], camera=cam,
        src=dict(archive=src["archive"], member=src["member"],
                 size=src["size"], crc=src["crc"]),
        copies=[dict(archive=c["archive"], size=c["size"], crc=c["crc"])
                for c in group],
        time_local=src["tags"].get("time_local"),
        tz_offset=src["tags"].get("tz_offset"),
        subsec=src["tags"].get("subsec"),
        gps=src["tags"].get("gps"),
        gps_utc=src["tags"].get("gps_utc"),
        unreadable="error" in src["tags"],
    )
    if len(distinct) > 1:
        # Keep both readings. One of these cameras had its clock corrected in
        # one archive and not the other; deciding which is clock_fit's job.
        rec["time_disagree"] = {k: v for k, v in times.items() if v}
        stats["time_disagreements"] += 1
    if suffix:
        rec["name"] = f"{name}~{cam.replace(' ', '_')}"
    for k in ("gps", "gps_utc", "time_local"):
        if rec[k]:
            stats[f"have_{k}"] += 1
    if len(group) > 1:
        stats["in_both_archives"] += 1
    return rec


# ------------------------------------------------------------------ report ---
def report(photos, stats):
    n = len(photos)
    print(f"\n{n} photographs across {stats['read_mine']} + {stats['read_crew']} "
          f"archive members ({stats['in_both_archives']} in both)")
    print(f"  {stats['have_time_local']} carry a timestamp "
          f"({n - stats['have_time_local']} do not)")
    print(f"  {stats['have_gps']} carry GPS, {stats['have_gps_utc']} carry GPS UTC")
    print(f"  {stats['time_disagreements']} disagree on time between archives")
    print(f"  {stats['name_collisions']} filename collisions between cameras")
    print(f"  {stats['unreadable']} unreadable"
          + ("" if HEIC_OK else f", pillow-heif absent ({stats['heic_no_decoder']} HEIC)"))

    print(f"\n{'camera':34} {'imgs':>5} {'gps':>5} {'gpsUTC':>6} {'noTime':>6} "
          f"{'tz tags seen':>16}  first .. last (camera's own clock)")
    groups = collections.defaultdict(list)
    for p in photos:
        groups[p["camera"]].append(p)
    for cam, ps in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        tz = collections.Counter(p["tz_offset"] for p in ps if p["tz_offset"])
        ts = sorted(p["time_local"] for p in ps if p["time_local"])
        span = f"{ts[0][5:16]} .. {ts[-1][5:16]}" if ts else "no timestamps"
        print(f"  {cam[:32]:32} {len(ps):5} {sum(1 for p in ps if p['gps']):5} "
              f"{sum(1 for p in ps if p['gps_utc']):6} "
              f"{sum(1 for p in ps if not p['time_local']):6} "
              f"{(','.join(f'{k}x{v}' for k, v in tz.most_common(2)) or '-'):>16}  {span}")

    placeable = [p for p in photos if p["gps"]]
    print(f"\n  {len(placeable)} photographs already carry their own position.")
    needy = [p for p in photos if not p["gps"] and p["time_local"]]
    print(f"  {len(needy)} have a timestamp but no position — these are what "
          f"clock_fit has to earn.")
    nothing = [p for p in photos if not p["gps"] and not p["time_local"]]
    print(f"  {len(nothing)} have neither, and can only ever be browsable.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=os.path.join(HERE, "out", "photo_index.json"))
    ap.add_argument("--archive", action="append", metavar="LABEL=PATH",
                    help="override an archive path (repeatable)")
    ap.add_argument("--report", action="store_true", help="describe what was found")
    a = ap.parse_args()

    archives = list(ARCHIVES)
    for spec in a.archive or []:
        label, _, path = spec.partition("=")
        archives = [(l, path if l == label else p) for l, p in archives]

    photos, stats = index(archives)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w") as fh:
        json.dump(photos, fh, indent=1)
    print(f"wrote {a.out} — {len(photos)} photographs")
    if a.report:
        report(photos, stats)


if __name__ == "__main__":
    main()
