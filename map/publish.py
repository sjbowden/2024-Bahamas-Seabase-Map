#!/usr/bin/env python3
"""Upload site_build to the host, and check that what is live is what was built.

    python -m map.publish            # check, upload, verify
    python -m map.publish --check    # everything but the upload; exits 1 if
                                     # what is live is not the folder

The one command for publishing, so that nobody has to remember the four it
replaces. It reads its settings from a file outside the repository,
`~/.config/bahamas/cloudflare.env`, because the repository is public and the
site's address is not:

    CLOUDFLARE_API_TOKEN=...          a token that can edit Pages and nothing else
    CLOUDFLARE_ACCOUNT_ID=...
    CLOUDFLARE_PAGES_PROJECT=...      the Pages project's name
    SITE_URL=https://...              where it is served, for the check afterwards

Before uploading it refuses a folder that was not built from this source or
whose pictures do not belong to its records. Afterwards it fetches the pages and
the data back and compares them with the folder byte for byte, because an upload
that reports success and a site that has changed are two different facts: the
host has been seen to fail at the last step, and to take a minute to switch.

Nothing here builds. Build first: `python -m map.build --reuse-index`.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(HERE, "site_build")
SETTINGS = os.path.expanduser("~/.config/bahamas/cloudflare.env")
NEEDED = ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID",
          "CLOUDFLARE_PAGES_PROJECT", "SITE_URL")
# The version the uploads so far were made with. npx fetches it if it is not
# already cached, which is the whole of installing it.
WRANGLER = "wrangler@4.149.0"
TRIES = 3

# What to fetch back, as (address on the site, file in the folder). The host
# serves index.html at / and journal.html at /journal, and redirects the longer
# forms, so the short ones are asked for.
LIVE = [("", "index.html"), ("journal", "journal.html"), ("app.js", "app.js"),
        ("style.css", "style.css"), ("journal.css", "journal.css")]


def read_settings(path=SETTINGS, environ=None):
    """The settings, from the file and then from the environment, which wins."""
    got = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                got[k.strip()] = v.strip().strip("'\"")
    for k in NEEDED:
        if (environ if environ is not None else os.environ).get(k):
            got[k] = (environ if environ is not None else os.environ)[k]
    return got


def preflight(site=None, record=None, index=None):
    """Reasons this folder should not be uploaded; empty if there are none."""
    site = site or SITE
    if not os.path.isdir(site):
        return ["no site_build: run python -m map.build --reuse-index"]
    from map import record as R
    index = index or R.INDEX
    # Everything the build read and wrote, not only the files it copied: the
    # journal and the data are made from sources no file here sits beside.
    # A rebuild mends all of it but a file the build never wrote, which it
    # would leave where it is.
    why = [w + (": remove them" if w.startswith("not written") else ": rebuild")
           for w in R.outdated(record or R.RECORD, site)]
    # No index is no way to know whose pictures these are, which is not the
    # same as their being the right ones.
    if not os.path.exists(index):
        why.append("no out/photo_index.json to check the media against: "
                   "run python -m map.build")
    else:
        from map import derive
        from map import photo_index as PI
        photos, _ = PI.readable(json.load(open(index)))
        stale = derive.stale(photos, os.path.join(site, "media"))
        if stale is None:
            why.append("site_build has no media: build with --media")
        elif stale:
            why.append(f"{len(stale)} photographs do not match the media on disk "
                       f"(e.g. {', '.join(stale[:3])}): build with --media")
    return why


def data_files():
    folder = os.path.join(SITE, "data")
    return [(f"data/{n}", f"data/{n}") for n in sorted(os.listdir(folder))]


def poster_files():
    folder = os.path.join(SITE, "poster")
    return ([(f"poster/{n}", f"poster/{n}") for n in sorted(os.listdir(folder))]
            if os.path.isdir(folder) else [])


def differing(base, pairs, fetch=None):
    """The files whose live copy is not the folder's, as their names."""
    fetch = fetch or _fetch
    out = []
    for where, name in pairs:
        local = hashlib.sha256(open(os.path.join(SITE, name), "rb").read()).hexdigest()
        try:
            # A changing query, so that no cache between here and the host
            # answers with what it had a minute ago.
            live = hashlib.sha256(fetch(f"{base.rstrip('/')}/{where}?t={time.time():.0f}")
                                  ).hexdigest()
        except Exception as e:                     # noqa: BLE001 - reported, not hidden
            live = f"{type(e).__name__}"
        if live != local:
            out.append(name)
    return out


def _fetch(url):
    req = urllib.request.Request(url, headers={"Cache-Control": "no-cache",
                                               "User-Agent": "seabase-publish/1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def upload(settings):
    """Run the upload, again if the host fails it. True once it has succeeded."""
    env = dict(os.environ, **{k: settings[k] for k in NEEDED[:2]})
    cmd = ["npx", "--yes", WRANGLER, "pages", "deploy", SITE,
           "--project-name", settings["CLOUDFLARE_PAGES_PROJECT"],
           "--branch", "main", "--commit-dirty=true"]
    for attempt in range(1, TRIES + 1):
        run = subprocess.run(cmd, cwd=HERE, env=env, capture_output=True, text=True)
        tail = [l for l in (run.stdout + run.stderr).splitlines()
                if any(w in l for w in ("Uploaded", "Deployment", "ERROR", "rror:"))]
        print(f"[upload] attempt {attempt}: " + (" | ".join(t.strip() for t in tail)
                                                 or f"exit {run.returncode}"))
        if run.returncode == 0 and "Deployment complete" in run.stdout:
            return True
        time.sleep(15)
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true",
                    help="check the folder and compare it with what is live; upload nothing")
    a = ap.parse_args()

    settings = read_settings()
    missing = [k for k in NEEDED if not settings.get(k)]
    if missing:
        raise SystemExit(f"[publish] {', '.join(missing)} not set: see {SETTINGS} "
                         "and the Publishing section of the README")
    why = preflight()
    if why:
        raise SystemExit("[publish] not uploading:\n  " + "\n  ".join(why))
    print("[check ] site_build is built from this source and its media match")

    pairs = LIVE + data_files() + poster_files()
    if a.check:
        diff = differing(settings["SITE_URL"], pairs)
        print("[live  ] " + (f"{len(diff)} of {len(pairs)} files differ from the folder: "
                             f"{', '.join(diff)}" if diff
                             else f"all {len(pairs)} files checked are the folder's"))
        # For a script asking: out of date, or out of reach, is not success.
        return 1 if diff else 0

    if not upload(settings):
        raise SystemExit(f"[publish] the upload failed {TRIES} times; the site is "
                         "as it was. The host's status page may say why.")
    # The host can take a minute to serve the new files.
    for _ in range(12):
        diff = differing(settings["SITE_URL"], pairs)
        if not diff:
            print(f"[live  ] all {len(pairs)} files checked are the folder's")
            return
        time.sleep(10)
    raise SystemExit(f"[publish] uploaded, but after two minutes these are not "
                     f"what was built: {', '.join(diff)}")


if __name__ == "__main__":
    sys.exit(main())
