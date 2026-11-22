#!/usr/bin/env python3
"""Stamp one version onto every script and stylesheet the site loads.

    python scripts/web_version.py 11

Browsers keep scripts that other scripts import, so after an update a visitor can end up
running an old file. Every relative import in web/js and web/engine, the page's script tag and
the stylesheet links get `?v=<version>`, the same string everywhere, so one module is never
loaded twice under two names and an update always fetches fresh files. Run it with a new
number whenever the site changes.
"""
import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"


def main() -> int:
    v = sys.argv[1] if len(sys.argv) > 1 else None
    if not v or not re.fullmatch(r"[A-Za-z0-9.]+", v):
        sys.exit("usage: web_version.py <version>")
    imp = re.compile(r'''(from\s+|import\s*\(\s*)(["'])(\.{1,2}/[^"'?]+\.js)(\?v=[^"']*)?\2''')
    for f in list((WEB / "js").glob("*.js")) + list((WEB / "engine").glob("*.js")):
        s = f.read_text(encoding="utf-8")
        new = imp.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}?v={v}{m.group(2)}", s)
        if new != s:
            f.write_text(new, encoding="utf-8", newline="\n")
    for page in ["index.html", "log.html", "model-card.html"]:
        f = WEB / page
        if not f.exists():
            continue
        s = f.read_text(encoding="utf-8")
        s = re.sub(r'src="js/main\.js(\?v=[^"]*)?"', f'src="js/main.js?v={v}"', s)
        s = re.sub(r'href="(site|doc)\.css(\?v=[^"]*)?"', lambda m: f'href="{m.group(1)}.css?v={v}"', s)
        f.write_text(s, encoding="utf-8", newline="\n")
    print("version", v)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
