#!/usr/bin/env python3
"""Serve web/ for local play and for the headless test.

    python3 tools/serve.py [port] [--rom PATH]

Threaded, because a single-threaded handler deadlocks the moment the page asks
for the 1 MB core while the ROM request is still open.  --rom exposes one local
file at /_rom.gba for the test harness only; without it nothing outside web/ is
reachable.  Binds to localhost.
"""
import argparse
import functools
import http.server
import pathlib
import socketserver
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "web"


class Handler(http.server.SimpleHTTPRequestHandler):
    rom: pathlib.Path | None = None

    def do_GET(self):
        if self.path.split("?")[0] == "/_rom.gba" and self.rom:
            data = self.rom.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, fmt, *a):
        pass


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("port", nargs="?", type=int, default=8585)
    ap.add_argument("--rom", type=pathlib.Path)
    a = ap.parse_args()
    if a.rom:
        if not a.rom.is_file():
            print(f"no such ROM: {a.rom}")
            return 1
        Handler.rom = a.rom.resolve()
    h = functools.partial(Handler, directory=str(ROOT))
    with Server(("127.0.0.1", a.port), h) as srv:
        print(f"serving {ROOT} on http://localhost:{a.port}/"
              + (f"  (+ /_rom.gba -> {a.rom})" if a.rom else ""), flush=True)
        srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
