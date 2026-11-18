"""End-to-end test of the research agent with MOCKED provider responses.

What this verifies (real code paths, no real API keys):
  - the HTTP server starts and serves the page + /api/health
  - POST /api/ask runs the full flow: Tavily search -> Nebius synthesis
    -> answer with citations, numbered sources, evidence assessment
  - evidence "solid" (6 sources), "thin" (1 source) and "none" (0 sources)
  - missing API keys are reported honestly as a 503, not faked

What this does NOT verify (needs real keys):
  - the actual Tavily and Nebius Token Factory API calls

Run:  python3 test_mock.py
Exit code 0 = all checks passed.
"""

import json
import os
import sys
import threading
import urllib.request
from http.server import ThreadingHTTPServer

# Fake keys so the app accepts requests; the providers are mocked below.
os.environ["NEBIUS_API_KEY"] = "test-key"
os.environ["TAVILY_API_KEY"] = "test-key"
os.environ.pop("NEBIUS_MODEL", None)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent  # noqa: E402
from app import Handler  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def fake_post(url, json=None, headers=None, timeout=None):
    if "tavily.com" in url:
        query = (json or {}).get("query", "")
        if "nothing" in query.lower():
            results = []
        elif "thin" in query.lower():
            results = [{
                "title": "Only one page",
                "url": "https://example.com/only",
                "content": "A short page with barely any detail about the topic.",
            }]
        else:
            results = [{
                "title": f"Source {i + 1} about the topic",
                "url": f"https://example.com/source-{i + 1}",
                "content": f"This is the content of source {i + 1}. " * 10,
            } for i in range(6)]
        return FakeResponse({"results": results})
    if "chat/completions" in url:
        return FakeResponse({
            "choices": [{"message": {
                "content": (
                    "The topic is explained by several sources [1]. "
                    "A second point is also covered [2]. "
                    "What we could not verify: the very latest figures."
                )
            }}]
        })
    raise AssertionError(f"unexpected URL in mock: {url}")


agent.requests.post = fake_post

PASS = 0


def check(name, condition, detail=""):
    global PASS
    if not condition:
        print(f"FAIL: {name} {detail}")
        sys.exit(1)
    PASS += 1
    print(f"PASS: {name}")


def http_get(port, path):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
        return r.status, r.read().decode("utf-8")


def http_post(port, path, payload):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    # 1. Page serves
    status, body = http_get(port, "/")
    check("GET / serves the UI", status == 200 and "Research Agent" in body
          and "Ask" in body and "Tavily" in body and "Nebius" in body)

    # 2. Health endpoint (booleans only, never key values)
    status, data = http_get(port, "/api/health")
    data = json.loads(data)
    check("GET /api/health", status == 200 and data["status"] == "ok"
          and data["nebius_configured"] is True and data["tavily_configured"] is True
          and "test-key" not in json.dumps(data))

    # 3. Solid-evidence flow
    status, data = http_post(port, "/api/ask", {"question": "What is Nebius Token Factory?"})
    check("POST /api/ask solid: 200", status == 200, str(data)[:200])
    check("solid: 6 sources", len(data["sources"]) == 6)
    check("solid: evidence flag", data["evidence"] == "solid")
    check("solid: answer has citations", "[1]" in data["answer"] and "[2]" in data["answer"])
    check("solid: cited numbers parsed", data["cited"] == [1, 2])
    check("solid: source URLs present",
          all(s["url"].startswith("https://example.com/") for s in data["sources"]))
    check("solid: steps recorded", len(data["steps"]) == 2)

    # 4. Thin-evidence flow
    status, data = http_post(port, "/api/ask", {"question": "thin topic with one source"})
    check("thin: evidence flag", status == 200 and data["evidence"] == "thin"
          and len(data["sources"]) == 1)

    # 5. No-evidence flow
    status, data = http_post(port, "/api/ask", {"question": "nothing about this anywhere"})
    check("none: evidence flag + honest answer", status == 200
          and data["evidence"] == "none" and data["sources"] == []
          and "could not find" in data["answer"])

    # 6. Validation
    status, data = http_post(port, "/api/ask", {"question": "   "})
    check("empty question rejected", status == 400)

    # 7. Missing keys reported honestly (direct agent call, no env keys)
    os.environ.pop("NEBIUS_API_KEY", None)
    os.environ.pop("TAVILY_API_KEY", None)
    try:
        agent.research("anything")
        check("missing keys raise MissingKeyError", False)
    except agent.MissingKeyError as exc:
        check("missing keys raise MissingKeyError",
              exc.missing == ["NEBIUS_API_KEY", "TAVILY_API_KEY"])

    server.shutdown()
    print(f"\nAll {PASS} checks passed (mocked providers — real Tavily/Nebius calls NOT tested).")


if __name__ == "__main__":
    main()
