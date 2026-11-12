#!/usr/bin/env python3
"""Local preview for the uEXPLORER publications page.

The page at ``/Link/uexplorer.html`` lives in the GitHub Pages site and pulls
its data from ``<bibtex src="/uexplorer-bib/uExplorer.bib">``, i.e. through
absolute site-root paths.  To preview it without copying the whole site or
touching either repository, this script serves

    /                    -> this repo's index.html (redirect to the page)
    /uexplorer-bib/...   -> this repo (uExplorer.bib, live as you edit it)
    everything else      -> the GitHub Pages site checkout (css, js, Link/)

so absolute paths resolve exactly as they do on mengxiangxi.info.

Usage:
    uv run --no-project python preview.py                      # sibling checkout, port 8765, opens a tab
    uv run --no-project python preview.py --site D:/path/to/MengXiangxi.github.io
    uv run --no-project python preview.py --port 9000 --no-open
"""

from __future__ import annotations

import argparse
import socket
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO = Path(__file__).resolve().parent
DEFAULT_SITE = REPO.parent / "MengXiangxi.github.io"
MOUNT = "/uexplorer-bib/"
PAGE = "/Link/uexplorer.html"
PAGE_FILE = PAGE.lstrip("/")

# The page has no <meta charset> and relies on the response header, as GitHub
# Pages sends it.  Bare http.server would fall back to the system code page and
# turn "孟祥溪" into mojibake.
UTF8_TYPES = (
    "text/html",
    "text/css",
    "text/javascript",
    "application/javascript",
    "application/json",
    "application/x-bibtex",
    "text/plain",
)


def make_handler(site: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(site), **kwargs)

        def translate_path(self, path):
            clean = unquote(urlsplit(path).path)
            if clean == "/":
                return str(REPO / "index.html")
            if clean.startswith(MOUNT):
                parts = [p for p in clean[len(MOUNT):].split("/") if p not in ("", ".", "..")]
                return str(REPO.joinpath(*parts))
            return super().translate_path(path)

        def guess_type(self, path):
            ctype = super().guess_type(path)
            return ctype + "; charset=utf-8" if ctype in UTF8_TYPES else ctype

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    return Handler


def port_busy(host: str, port: int) -> bool:
    """Windows SO_REUSEADDR lets a second bind share a live listener, so probe first."""
    with socket.socket() as probe:
        probe.settimeout(0.25)
        return probe.connect_ex((host, port)) == 0


def serve(site: Path, host: str, port: int) -> tuple[ThreadingHTTPServer, int]:
    handler = make_handler(site)
    for candidate in range(port, port + 20):
        if port_busy(host, candidate):
            continue
        try:
            return ThreadingHTTPServer((host, candidate), handler), candidate
        except OSError:
            continue
    raise SystemExit(f"no free port in {port}-{port + 19}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--site", type=Path, default=DEFAULT_SITE, help=f"GitHub Pages checkout (default: {DEFAULT_SITE})")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    args = ap.parse_args(argv)

    site = args.site.expanduser().resolve()
    if not (site / PAGE_FILE).is_file():
        raise SystemExit(f"site checkout not found: {site}\nmissing {PAGE_FILE}\npass --site <path to MengXiangxi.github.io>")

    httpd, port = serve(site, args.host, args.port)
    url = f"http://{args.host}:{port}{PAGE}"
    print(f"repo:  {REPO}")
    print(f"site:  {site}")
    print(f"ready: {url}")
    if not args.no_open:
        webbrowser.open(f"http://{args.host}:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
