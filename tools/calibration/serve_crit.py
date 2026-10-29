"""Serve the blind calibration crit on localhost and save verdicts to disk.

    python3 -I tools/calibration/serve_crit.py [port] [packets_dir] [verdicts_file]
    defaults: 8770, data/calibration/packets, cards/kevin-mccoy/calibration/verdicts.json
    e.g. the benchmark audit: serve_crit.py 8771 benchmark/v1/audit benchmark/v1/audit/verdicts.json

Serves the packets (never _key.json) and the page in tools/templates/crit_bench.html, and writes
verdicts and rankings to the verdicts file. For any card, use `tools/bench.py crit <card>`, which
calls serve() with that card's values.
"""
import json, re, sys, threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "tools" / "templates" / "crit_bench.html"
LOCK = threading.Lock()
PACKETS = STORE = CONFIG = None
SAFE_IMAGE = re.compile(r"^P\d{2}-\d+\.(png|jpg|jpeg)$")


def load():
    return json.loads(STORE.read_text()) if STORE.exists() else {"verdicts": {}, "rankings": {}}


def save(data):
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(STORE)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE.read_text(), "text/html; charset=utf-8")
        if self.path == "/api/packets":
            return self._send(200, (PACKETS / "packets.json").read_text())
        if self.path == "/api/config" and CONFIG:
            return self._send(200, json.dumps(CONFIG))
        if self.path == "/api/verdicts":
            with LOCK:
                return self._send(200, json.dumps(load()))
        if self.path.startswith("/images/"):
            name = self.path.removeprefix("/images/")
            if SAFE_IMAGE.match(name) and (PACKETS / "images" / name).exists():
                ctype = "image/png" if name.endswith(".png") else "image/jpeg"
                return self._send(200, (PACKETS / "images" / name).read_bytes(), ctype)
        self._send(404, '{"error":"not found"}')

    def do_POST(self):
        m = re.match(r"^/api/(verdicts|rankings)/([A-Za-z0-9_-]+)$", self.path)
        if not m:
            return self._send(404, '{"error":"not found"}')
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        except ValueError:
            return self._send(400, '{"error":"bad json"}')
        body["updated"] = datetime.now(timezone.utc).isoformat()
        with LOCK:
            data = load()
            data[m.group(1)][m.group(2)] = body
            save(data)
        sys.stderr.write(f"saved {m.group(1)} {m.group(2)}\n")
        self._send(200, '{"ok":true}')

    def log_message(self, *args):
        pass


def serve(port, packets, store, config=None):
    """config: {"scores": [[value_id, label], ...], "score_all": bool, "store": shown path}; None keeps the page's defaults."""
    global PACKETS, STORE, CONFIG
    PACKETS, STORE, CONFIG = Path(packets), Path(store), config
    STORE.parent.mkdir(parents=True, exist_ok=True)
    print(f"Crit: http://127.0.0.1:{port}/  (verdicts -> {STORE.relative_to(ROOT)})", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8770,
          (ROOT / sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "calibration" / "packets",
          (ROOT / sys.argv[3]) if len(sys.argv) > 3 else ROOT / "cards" / "kevin-mccoy" / "calibration" / "verdicts.json")
