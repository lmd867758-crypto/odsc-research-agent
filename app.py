"""Web server for the ODSC AI x Nebius research agent.

Standard library only (plus `requests`, used by agent.py).
Serves the single-page UI and the JSON API:

    GET  /            the web page
    GET  /api/health {"status": "ok", "nebius_configured": bool, ...}
    POST /api/ask    {"question": "..."} -> answer + sources + evidence

Run:  python3 app.py        (reads .env if present)
Env:  PORT (default 8000), HOST (default 0.0.0.0),
      NEBIUS_API_KEY, TAVILY_API_KEY, NEBIUS_MODEL, NEBIUS_BASE_URL
"""

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent import MissingKeyError, ProviderError, research

BASE_DIR = Path(__file__).resolve().parent


def load_dotenv():
    """Minimal .env loader: sets vars that are not already in the env."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


load_dotenv()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send_file(BASE_DIR / "static" / "index.html", "text/html; charset=utf-8")
        elif self.path == "/api/health":
            self._send_json(200, {
                "status": "ok",
                "nebius_configured": bool(os.environ.get("NEBIUS_API_KEY")),
                "tavily_configured": bool(os.environ.get("TAVILY_API_KEY")),
                "model": os.environ.get("NEBIUS_MODEL", "deepseek-ai/DeepSeek-V4-Flash"),
            })
        elif self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/ask":
            self._send_json(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError):
            self._send_json(400, {"error": "invalid JSON body"})
            return

        question = (payload.get("question") or "").strip()
        if not question:
            self._send_json(400, {"error": "question is required"})
            return
        if len(question) > 500:
            self._send_json(400, {"error": "question is too long (max 500 characters)"})
            return

        try:
            result = research(question)
        except MissingKeyError as exc:
            self._send_json(503, {
                "error": "API key(s) not configured",
                "missing": exc.missing,
                "hint": "Copy .env.example to .env and add your Nebius and Tavily keys.",
            })
            return
        except ProviderError as exc:
            self._send_json(502, {"error": str(exc)})
            return
        except Exception as exc:  # never leak a stack trace to the client
            self._send_json(500, {"error": f"unexpected error: {exc}"})
            return

        self._send_json(200, result)


if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Research agent running at http://{host}:{port}")
    print("Keys configured:",
          "Nebius" if os.environ.get("NEBIUS_API_KEY") else "Nebius MISSING",
          "|",
          "Tavily" if os.environ.get("TAVILY_API_KEY") else "Tavily MISSING")
    server.serve_forever()
