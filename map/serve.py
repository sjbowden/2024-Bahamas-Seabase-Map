#!/usr/bin/env python3
"""Serve site_build locally, with caching disabled.

    python -m map.serve              # http://127.0.0.1:8123
    python -m map.serve --port 8200

Not plain `python -m http.server`, which sends Last-Modified and nothing else:
browsers heuristically cache on that, and a tab once held a stale
places.geojson through four refreshes -- hard reloads included, because the
chart fetches its data after the page loads, outside the reload's cache
bypass -- drawing week-old label positions under brand-new code. no-store
makes every refresh a real one.

Local preview only. The published host sets its own headers, from _headers.
"""
import argparse
import functools
import http.server
import os

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8123)
    a = ap.parse_args()
    site = os.path.join(HERE, "site_build")
    if not os.path.isdir(site):
        raise SystemExit("no site_build to serve -- run: python -m map.build")
    srv = http.server.ThreadingHTTPServer(
        ("127.0.0.1", a.port), functools.partial(Handler, directory=site))
    print(f"serving {site} on http://127.0.0.1:{a.port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
