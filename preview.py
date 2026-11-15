#!/usr/bin/env python3
"""Standalone local preview server for the uEXPLORER publications project.

Serves this repository directly over HTTP with UTF-8 headers and no-store
caching so edits to ``uExplorer.bib``, ``index.html``, or ``assets/`` appear
immediately on reload.

Usage:
    uv run --no-project python preview.py                # 127.0.0.1 + Tailscale IP, opens a tab
    uv run --no-project python preview.py --no-open      # serve only
    uv run --no-project python preview.py --no-tailscale # loopback 127.0.0.1 only
    uv run --no-project python preview.py --port 9000
"""

from __future__ import annotations

import argparse
import ipaddress
import socket
import sys
import threading
import webbrowser
from http import HTTPStatus
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
    root_resolved = root.resolve()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root_resolved), **kwargs)

        def send_head(self):
            target = Path(self.translate_path(self.path)).resolve()
            try:
                rel = target.relative_to(root_resolved)
            except ValueError:
                self.send_error(HTTPStatus.FORBIDDEN)
                return None
            if any(part.startswith(".") for part in rel.parts):
                self.send_error(HTTPStatus.FORBIDDEN)
                return None
            return super().send_head()

        def list_directory(self, path):
            self.send_error(HTTPStatus.FORBIDDEN)
            return None

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

def serve(root: Path, hosts: list[str], port: int) -> tuple[list[ThreadingHTTPServer], int]:
    handler = make_handler(root)
    for candidate in range(port, port + 20):
        if any(port_busy(h, candidate) for h in hosts):
            continue
        servers: list[ThreadingHTTPServer] = []
        try:
            for h in hosts:
                servers.append(ThreadingHTTPServer((h, candidate), handler))
            return servers, candidate
        except OSError:
            for s in servers:
                s.server_close()
            continue
    raise SystemExit(f"no free port in {port}-{port + 19}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1", help="primary bind address (default: 127.0.0.1)")
    ap.add_argument("--no-tailscale", action="store_true", help="do not also bind the local Tailscale IPv4")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    args = ap.parse_args(argv)

    hosts = [args.host]
    ts_ip = None if args.no_tailscale or args.host in ("0.0.0.0", "") else tailscale_ipv4()
    if ts_ip and ts_ip not in hosts:
        hosts.append(ts_ip)

    servers, port = serve(REPO, hosts, args.port)
    local_host = "127.0.0.1" if args.host in ("0.0.0.0", "") else args.host
    url = f"http://{local_host}:{port}/"
    print(f"repo:      {REPO}")
    print(f"ready:     {url}")
    if ts_ip:
        print(f"tailscale: http://{ts_ip}:{port}/")
    if not args.no_open:
        webbrowser.open(url)

    extra_threads = [
        threading.Thread(target=s.serve_forever, daemon=True) for s in servers[1:]
    ]
    for t in extra_threads:
        t.start()
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        for s in servers:
            s.shutdown()
            s.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
