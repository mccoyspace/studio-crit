"""Serve the Crit Positions page on localhost and save answers to a JSON file.

    python3 -I tools/serve_positions.py [port] [answers_file]   (defaults: 8765, data/positions/reactions.json)

Builds the page from corpus/units.jsonl, then serves it at http://127.0.0.1:<port>/.
Answers are written to the answers file, one entry per unit id. For a card, use
`tools/bench.py positions <card>`, which saves to <card dir>/positions/reactions.json.
"""
import json, subprocess, sys, tempfile, threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STORE = (ROOT / sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "positions" / "reactions.json"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
LOCK = threading.Lock()

page = Path(tempfile.mkdtemp()) / "crit-positions.html"
subprocess.run([sys.executable, "-I", str(ROOT / "tools/build_reactions_page.py"), str(ROOT / "corpus/units.jsonl"),
                str(ROOT / "tools/templates/crit_positions.html"), str(page)], check=True)
# the page expects the artifact skeleton; add a minimal one for a plain browser
HTML = ('<!doctype html><html><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<style>body{margin:0;font:14px system-ui,sans-serif}[hidden]{display:none!important}</style>'
        '</head><body>' + page.read_text() + '</body></html>').encode()


def load():
    return json.loads(STORE.read_text()) if STORE.exists() else {}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, HTML, "text/html; charset=utf-8")
        elif self.path == "/api/reactions":
            with LOCK:
                self._send(200, json.dumps(load()).encode())
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        prefix = "/api/reactions/"
        unit = self.path[len(prefix):] if self.path.startswith(prefix) else ""
        if not unit or "/" in unit:
            return self._send(404, b'{"error":"not found"}')
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except ValueError:
            return self._send(400, b'{"error":"bad json"}')
        entry = {"unit": unit, "verdict": body.get("verdict"), "note": body.get("note", ""),
                 "matters": bool(body.get("matters")), "updated": datetime.now(timezone.utc).isoformat()}
        with LOCK:
            data = load()
            data[unit] = entry
            STORE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STORE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
            tmp.replace(STORE)  # atomic, so a crash never leaves a half-written file
        self._send(200, b'{"ok":true}')

    def log_message(self, fmt, *args):
        if self.command == "POST":
            sys.stderr.write("saved " + self.path.rsplit("/", 1)[-1] + "\n")


print(f"Crit Positions: http://127.0.0.1:{PORT}/  (answers -> {STORE.relative_to(ROOT)})", flush=True)
ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
