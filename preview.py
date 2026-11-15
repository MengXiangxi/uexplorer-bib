#!/usr/bin/env python3
"""Standalone local preview server for the uEXPLORER publications project.

Serves this repository directly over HTTP with UTF-8 headers and no-store
caching so edits to ``uExplorer.bib``, ``index.html``, or ``assets/`` appear
immediately on reload.

Usage:
    uv run --no-project python preview.py              # 0.0.0.0:8765 (local + Tailscale), opens a tab
    uv run --no-project python preview.py --no-open    # serve only
    uv run --no-project python preview.py --port 9000
    uv run --no-project python preview.py --host 127.0.0.1
"""

from __future__ import annotations

import argparse
import ipaddress
import socket
import sys
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent

UTF8_TYPES = (
    "text/html",
    "text/css",
    "text/javascript",
    "application/javascript",
    "application/json",
    "application/x-bibtex",
    "text/plain",
)


def make_handler(root: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def guess_type(self, path):
            ctype = super().guess_type(path)
            if path.endswith(".bib"):
                return "text/plain; charset=utf-8"
            return ctype + "; charset=utf-8" if ctype in UTF8_TYPES else ctype

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

    return Handler


def port_busy(host: str, port: int) -> bool:
    """Windows SO_REUSEADDR lets a second bind share a live listener, so probe first."""
    target = "127.0.0.1" if host in ("0.0.0.0", "") else host
    with socket.socket() as probe:
        probe.settimeout(0.25)
        return probe.connect_ex((target, port)) == 0


def tailscale_ipv4() -> str | None:
    """Return the local Tailscale IPv4 address (100.64.0.0/10) if active."""
    cg_net = ipaddress.ip_network("100.64.0.0/10")
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ipaddress.ip_address(ip) in cg_net:
                return ip
    except OSError:
        pass
    return None

def serve(root: Path, host: str, port: int) -> tuple[ThreadingHTTPServer, int]:
    handler = make_handler(root)
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
    ap.add_argument("--host", default="0.0.0.0", help="bind address (default: 0.0.0.0 for local + Tailscale)")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    args = ap.parse_args(argv)

    httpd, port = serve(REPO, args.host, args.port)
    local_host = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    url = f"http://{local_host}:{port}/"
    print(f"repo:      {REPO}")
    print(f"ready:     {url}")
    if args.host in ("0.0.0.0", ""):
        ts_ip = tailscale_ipv4()
        if ts_ip:
            print(f"tailscale: http://{ts_ip}:{port}/")
    if not args.no_open:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
