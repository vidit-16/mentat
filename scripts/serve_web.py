#!/usr/bin/env python3
"""Serve the project site locally with caching turned off, so every reload shows the latest
files (a plain http.server lets the browser keep old copies of the page or its scripts).

    python scripts/serve_web.py [port]
"""
import functools
import http.server
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    handler = functools.partial(NoCache, directory=str(WEB))
    print(f"serving {WEB} at http://127.0.0.1:{port}/")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
