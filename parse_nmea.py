#!/usr/bin/env python3
"""Parse raw NMEA logs from the 2024 Sea Base trip into clean per-day tracks.

Reads GPSFILES/GPS_*.log, keeps valid $GPRMC fixes, and writes tracks/*.csv
with columns: utc, lat, lon, sog_kn, cog_deg.
"""
import csv
import glob
import os
from datetime import datetime, timezone

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
    dot = val.find(".")
    deg = float(val[: dot - 2])
    minutes = float(val[dot - 2 :])
    d = deg + minutes / 60.0
    return -d if hemi in ("S", "W") else d


def parse_gga(path):
    """Fix-quality sidecar keyed by hhmmss: (quality, n_sats, hdop).

    quality 1=GPS, 2=DGPS, 6=dead-reckoning (an estimate, not a real fix).
    """
    q = {}
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line.startswith("$GPGGA") or not nmea_checksum_ok(line):
                continue
            f = line[1:].split("*")[0].split(",")
            if len(f) < 9 or not f[1] or not f[6]:
                continue
            try:
                q[f[1][:6]] = (int(f[6]), int(f[7] or 0), float(f[8] or 99.0))
            except ValueError:
                continue
    return q


def parse_file(path):
    rows = []
    qual = parse_gga(path)
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for line in fh:
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
                ts = datetime(
                    2000 + int(datestr[4:6]),
                    int(datestr[2:4]),
                    int(datestr[0:2]),
                    int(hhmmss[0:2]),
                    int(hhmmss[2:4]),
                    int(hhmmss[4:6]),
                    tzinfo=timezone.utc,
                )
            except ValueError:
                continue
            lat = dm_to_deg(f[3], f[4])
            lon = dm_to_deg(f[5], f[6])
            if lat is None or lon is None:
                continue
            try:
                sog = float(f[7]) if f[7] else 0.0
                cog = float(f[8]) if f[8] else float("nan")
            except ValueError:
                continue
            gq, gsat, ghdop = qual.get(hhmmss[:6], (0, 0, 99.0))
            rows.append((ts, lat, lon, sog, cog, gq, gsat, ghdop))
    rows.sort(key=lambda r: r[0])
    # drop exact-duplicate timestamps
    out, last = [], None
    for r in rows:
        if r[0] != last:
            out.append(r)
            last = r[0]
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
                w.writerow([ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
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
