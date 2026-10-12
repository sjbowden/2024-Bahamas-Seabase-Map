#!/usr/bin/env python3
"""Parse raw NMEA logs from the 2024 Sea Base trip into clean per-day tracks.

Reads GPSFILES/GPS_*.log, keeps valid $GPRMC fixes, and writes tracks/*.csv
with columns: utc, lat, lon, sog_kn, cog_deg.
"""
import csv
import glob
import math
import os
from datetime import datetime, timezone

from trip import second_of, utc_text

SRC = os.path.join(os.path.dirname(__file__), "GPSFILES")
OUT = os.path.join(os.path.dirname(__file__), "tracks")


def nmea_checksum_ok(line):
    if "*" not in line:
        return False
    body, _, ck = line[1:].partition("*")
    try:
        want = int(ck[:2], 16)
    except ValueError:
        return False
    got = 0
    for ch in body:
        got ^= ord(ch)
    return got == want


def dm_to_deg(val, hemi):
    """NMEA ddmm.mmmm -> signed decimal degrees."""
    if not val:
        return None
    if hemi not in ("N", "S", "E", "W"):
        raise ValueError(f"no such hemisphere: {hemi!r}")
    dot = val.find(".")
    if dot < 0:
        dot = len(val)
    deg = float(val[: dot - 2])
    minutes = float(val[dot - 2 :])
    if not 0.0 <= minutes < 60.0:
        raise ValueError(f"minutes out of range in {val!r}")
    d = deg + minutes / 60.0
    return -d if hemi in ("S", "W") else d


# A fix and its quality are two sentences of one burst: in these logs the RMC
# comes four to seven lines after the GGA of the same instant. This is generous,
# and still far short of the day's worth of lines between two noons.
NEAR_LINES = 40


def parse_gga(path):
    """Fix quality by the time it was reported: {time field: [(line, quality)]}.

    quality is (fix quality, satellites, hdop); fix quality 1=GPS, 2=DGPS,
    6=dead-reckoning (an estimate, not a real fix).

    Every occurrence is kept, with the line it was on. Keyed on the time of day
    alone, a log that ran past 24 hours gave Monday's noon fix Tuesday's noon
    quality, and two fixes inside one second shared whichever came last.
    """
    q = {}
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for n, line in enumerate(fh):
            line = line.strip()
            if not line.startswith("$GPGGA") or not nmea_checksum_ok(line):
                continue
            f = line[1:].split("*")[0].split(",")
            if len(f) < 9 or not f[1] or not f[6]:
                continue
            try:
                hdop = float(f[8] or 99.0)
                # "nan" is a float, and nan > MAX_HDOP is False: unknown is bad.
                q.setdefault(f[1], []).append(
                    (n, (int(f[6]), int(f[7] or 0),
                         hdop if math.isfinite(hdop) else 99.0)))
            except ValueError:
                continue
    return q


NO_QUALITY = (0, 0, 99.0)


def quality_at(qual, when, line):
    """The quality reported with the fix on `line`: the same instant, nearby.

    The nearest GGA carrying the same time field, if it is within NEAR_LINES.
    None that near means this fix came without one, and it gets no quality
    rather than another day's.
    """
    near = min(qual.get(when, ()), key=lambda c: abs(c[0] - line), default=None)
    if near is None or abs(near[0] - line) > NEAR_LINES:
        return NO_QUALITY
    return near[1]


def parse_file(path):
    rows, loose = [], []
    qual = parse_gga(path)
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for n, line in enumerate(fh):
            line = line.strip()
            if not line.startswith("$GPRMC") or not nmea_checksum_ok(line):
                continue
            f = line[1:].split("*")[0].split(",")
            # $GPRMC,hhmmss.sss,A,lat,N,lon,W,sog,cog,ddmmyy,...
            if len(f) < 10 or f[2] != "A":
                continue
            hhmmss, datestr = f[1], f[9]
            if len(hhmmss) < 6 or len(datestr) != 6:
                continue
            try:
                # The receiver reports to the millisecond, and the fraction is
                # part of the time: without it two fixes inside one second are
                # one, and every other is stamped up to a second early. A
                # fraction that is not digits is no fraction; the fix is still
                # a fix, in that second.
                frac = hhmmss[7:] if hhmmss[6:7] == "." else ""
                unread = bool(hhmmss[6:]) and not (frac.isascii() and frac.isdigit())
                if unread:
                    frac = ""
                ts = datetime(
                    2000 + int(datestr[4:6]),
                    int(datestr[2:4]),
                    int(datestr[0:2]),
                    int(hhmmss[0:2]),
                    int(hhmmss[2:4]),
                    int(hhmmss[4:6]),
                    int(frac[:6].ljust(6, "0")) if frac else 0,
                    tzinfo=timezone.utc,
                )
            except ValueError:
                continue
            # A checksum says the bytes arrived as sent, not that they are numbers.
            try:
                lat = dm_to_deg(f[3], f[4])
                lon = dm_to_deg(f[5], f[6])
            except ValueError:
                continue
            if lat is None or lon is None:
                continue
            if not (abs(lat) <= 90.0 and abs(lon) <= 180.0):
                continue
            if f[4] not in ("N", "S") or f[6] not in ("E", "W"):
                continue
            try:
                sog = float(f[7]) if f[7] else 0.0
                cog = float(f[8]) if f[8] else float("nan")
            except ValueError:
                continue
            # float() reads "nan" and "inf" as numbers. A speed has to be one;
            # a course may be absent, which is what the nan above stands for.
            if not math.isfinite(sog) or (f[8] and not math.isfinite(cog)):
                continue
            gq, gsat, ghdop = quality_at(qual, hhmmss, n)
            (loose if unread else rows).append((ts, lat, lon, sog, cog, gq, gsat, ghdop))
    rows.sort(key=lambda r: r[0])
    # drop exact-duplicate timestamps
    out, last = [], None
    for r in rows:
        if r[0] != last:
            out.append(r)
            last = r[0]
    if loose:
        # A fix whose fraction could not be read is somewhere in its second. It
        # is that second's fix if the second has no other; beside one whose time
        # is known it could only be put before or after it by guessing.
        taken = {second_of(r[0]) for r in out}
        for r in loose:
            if r[0] not in taken:
                taken.add(r[0])
                out.append(r)
        out.sort(key=lambda r: r[0])
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for path in sorted(glob.glob(os.path.join(SRC, "GPS_*.log"))):
        rows = parse_file(path)
        stem = os.path.basename(path).replace(".log", "")
        dest = os.path.join(OUT, stem + ".csv")
        with open(dest, "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["utc", "lat", "lon", "sog_kn", "cog_deg",
                        "quality", "sats", "hdop"])
            for ts, lat, lon, sog, cog, gq, gsat, ghdop in rows:
                w.writerow([utc_text(ts),
                            f"{lat:.6f}", f"{lon:.6f}", f"{sog:.2f}",
                            "" if cog != cog else f"{cog:.1f}",
                            gq, gsat, f"{ghdop:.1f}"])
        total += len(rows)
        if rows:
            print(f"{stem}: {len(rows):6d} fixes  "
                  f"{rows[0][0]:%m-%d %H:%M}Z -> {rows[-1][0]:%m-%d %H:%M}Z  "
                  f"lat {min(r[1] for r in rows):.3f}..{max(r[1] for r in rows):.3f}  "
                  f"lon {min(r[2] for r in rows):.3f}..{max(r[2] for r in rows):.3f}")
        else:
            print(f"{stem}: no valid fixes")
    print(f"total {total} fixes")


if __name__ == "__main__":
    main()
