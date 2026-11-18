# Research Agent — ODSC AI x Nebius Hackathon

Ask a question, get a **sourced answer from the live web** — with a clear
warning when the evidence is thin.

**Agent flow:** Tavily (real-time web search) → Nebius Token Factory
(OpenAI-compatible inference) → synthesized answer with numbered
citations and an explicit evidence assessment (`solid` / `thin` / `none`).

This directly targets the hackathon judging:
- **10% — uses both required tools:** Tavily search + Nebius Token Factory inference.
- **30% — sourced / verifiable:** every claim must carry a `[n]` citation
  pointing at a real source; the UI renders sources as clickable links.
- **25% — working agent, question → answer:** one question in, a complete
  researched answer out, end to end.

## What it does

1. You type a question in the web page (mobile-friendly).
2. The agent searches the live web with **Tavily** (5–8 results).
3. The results are passed to a model on **Nebius Token Factory**
   (default: `deepseek-ai/DeepSeek-V4-Flash`, a cheap open model) with
   strict instructions: answer only from the sources, cite every claim,
   and say plainly what could not be verified.
4. The page shows the answer with clickable `[n]` citations, the numbered
   source list, and a banner:
   - ✅ **Evidence solid** — 3+ sources back the answer.
   - ⚠️ **Evidence thin** — only 1–2 sources found; verify before relying on it.
   - ❌ **No sources found** — no verified answer is possible; the agent says so.

## Install

```bash
cd odsc-nebius-research-agent
pip install -r requirements.txt   # only `requests`; the server is stdlib
cp .env.example .env              # then fill in your two keys
```

## Get the two free API keys

**1. Nebius Token Factory** — free builder credits
- Go to <https://dev.nebius.com/builders> and sign up for the AI Builder
  program (free Token Factory credits; the hackathon briefing lists $25
  Token Factory + $25 Tavily builder credits, expiring 90 days).
- In the Token Factory dashboard, create an API key and copy it into
  `NEBIUS_API_KEY` in `.env`.

**2. Tavily** — free tier
- Sign up at <https://tavily.com> (free tier: 1,000 searches/month).
- Copy your API key from the dashboard into `TAVILY_API_KEY` in `.env`.

Optional: change the model with `NEBIUS_MODEL` (any model id on Token
Factory — check `GET https://api.tokenfactory.nebius.com/v1/models` if an
id is ever renamed; Token Factory version-stamps model ids).

## Run

```bash
./run.sh        # or: python3 app.py
```

Open <http://localhost:8000>. To demo from a phone on the same Wi-Fi,
open `http://<your-computer-IP>:8000` (the server binds `0.0.0.0`).

`GET /api/health` shows whether each key is configured (booleans only —
keys are never printed or sent to the client).

## Demo outline (2–3 minutes, record from a phone)

| Time | What to show |
|---|---|
| 0:00–0:20 | Open the page, explain the idea in one line: "Ask a question, the agent searches the live web and answers with sources." |
| 0:20–1:00 | Ask **"What is Nebius Token Factory and what models does it offer?"** Show the steps appearing (Tavily search → synthesis), then the answer with `[1] [2]` citations and the green "Evidence solid" banner. Tap a citation to open the source. |
| 1:00–1:40 | Ask a **fresh news question** (e.g. "What is the current price of gold per ounce?") to prove the search is live, not memorised. |
| 1:40–2:20 | Ask something **obscure / unanswerable** (e.g. a made-up local event) to show the amber "Evidence thin" or red "No sources" banner — the agent says when it does not know. |
| 2:20–2:40 | Wrap up: "Tavily finds it, Nebius explains it, every claim is cited." Show the sources list once more. |

## Files

| File | Purpose |
|---|---|
| `app.py` | Web server (stdlib `http.server`): serves the UI + `POST /api/ask`, `GET /api/health` |
| `agent.py` | The agent: Tavily search → Nebius chat completion → citations + evidence assessment |
| `static/index.html` | Mobile-friendly single-page UI (no build step) |
| `test_mock.py` | End-to-end test with mocked Tavily/Nebius responses |
| `.env.example` | Key placeholders (copy to `.env`; never commit real keys) |
| `requirements.txt` | `requests` only |
| `run.sh` | Convenience launcher |

## Verification status (honest)

- ✅ `python3 test_mock.py` — **13/13 checks pass**: server starts, page +
  health endpoint serve, full ask flow with mocked providers, evidence
  `solid` / `thin` / `none` all behave, empty question rejected, missing
  keys raise an honest error.
- ✅ Real server process started and probed with `curl`: `/api/health`
  returns `ok` with both keys unconfigured; `POST /api/ask` with no keys
  returns **HTTP 503** with the exact missing keys listed.
- ❌ **NOT yet verified with real keys:** no `NEBIUS_API_KEY` /
  `TAVILY_API_KEY` exists yet, so the live Tavily search and the live
  Nebius inference call have not been exercised. Before recording the
  demo, add both keys to `.env`, restart, and ask one real question —
  expect a 200 with real sources and a real model answer.
