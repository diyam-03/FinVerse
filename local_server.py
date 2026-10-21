"""Run FinVerse locally (no AWS, no installs):  python3 local_server.py
Open http://localhost:8000"""
import json
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "backend"))
import app  # noqa: E402

FRONTEND = os.path.join(HERE, "frontend")
API_PREFIXES = ("/twin", "/simulate", "/result", "/history", "/health")


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, data, ctype="application/json"):
        if not isinstance(data, (bytes, bytearray)):
            data = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api(self, method):
        body = {}
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            try:
                body = json.loads(self.rfile.read(length))
            except json.JSONDecodeError:
                return self._send(400, {"error": "Invalid JSON"})
        status, payload = app.route(method, self.path.split("?")[0], body)
        self._send(status, payload)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path.startswith(API_PREFIXES):
            return self._api("GET")
        rel = "index.html" if path == "/" else path.lstrip("/")
        full = os.path.normpath(os.path.join(FRONTEND, rel))
        if not full.startswith(FRONTEND) or not os.path.isfile(full):
            return self._send(404, {"error": "Not found"})
        with open(full, "rb") as f:
            self._send(200, f.read(), mimetypes.guess_type(full)[0] or "application/octet-stream")

    def do_POST(self):
        self._api("POST")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"FinVerse running on http://localhost:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
