"""Research agent for the ODSC AI x Nebius Hackathon.

Flow:  Tavily (real-time web search)  ->  Nebius Token Factory
(OpenAI-compatible inference)  ->  synthesized answer with numbered
source citations and an explicit evidence assessment.

Keys come from the environment only:
    NEBIUS_API_KEY   - Token Factory API key
    TAVILY_API_KEY    - Tavily API key
    NEBIUS_MODEL      - model id on Token Factory (optional)
    NEBIUS_BASE_URL   - Token Factory base URL (optional)

No key is ever hard-coded here.
"""

import os
import re
import time

import requests

TAVILY_URL = "https://api.tavily.com/search"
DEFAULT_BASE_URL = "https://api.tokenfactory.nebius.com/v1"
# Cheap open model on Token Factory at time of writing ($0.14/M input).
# If the id is ever renamed, check GET {base}/v1/models or set NEBIUS_MODEL.
DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4-Flash"

MAX_SOURCES = 8
MIN_SOLID_SOURCES = 3


class MissingKeyError(Exception):
    """Raised when a required API key is not configured."""

    def __init__(self, missing):
        self.missing = missing
        super().__init__(
            "Missing API key(s): " + ", ".join(missing)
            + ". Set them in .env or the environment."
        )


class ProviderError(Exception):
    """Raised when Tavily or Nebius returns an error."""


def _config():
    return {
        "nebius_key": os.environ.get("NEBIUS_API_KEY", "").strip(),
        "tavily_key": os.environ.get("TAVILY_API_KEY", "").strip(),
        "model": os.environ.get("NEBIUS_MODEL", DEFAULT_MODEL).strip()
        or DEFAULT_MODEL,
        "base_url": os.environ.get("NEBIUS_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
    }


def tavily_search(query, api_key, max_results=6):
    """Real-time web search via Tavily. Returns a list of sources.

    Each source: {"title": str, "url": str, "content": str}
    """
    resp = requests.post(
        TAVILY_URL,
        json={
            "api_key": api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": max_results,
            "include_answer": False,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise ProviderError(f"Tavily search failed ({resp.status_code}): {resp.text[:300]}")
    sources = []
    for item in resp.json().get("results", [])[:MAX_SOURCES]:
        content = (item.get("content") or "").strip()
        url = (item.get("url") or "").strip()
        if not url or not content:
            continue
        sources.append(
            {
                "title": (item.get("title") or url).strip(),
                "url": url,
                "content": content,
            }
        )
    return sources


def nebius_chat(messages, api_key, model, base_url):
    """One chat-completions call against Nebius Token Factory."""
    resp = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "temperature": 0.2,
        },
        timeout=120,
    )
    if resp.status_code != 200:
        raise ProviderError(
            f"Nebius inference failed ({resp.status_code}): {resp.text[:300]}"
        )
    return resp.json()["choices"][0]["message"]["content"].strip()


def _build_prompt(question, sources):
    numbered = "\n\n".join(
        f"[{i + 1}] {s['title']}\nURL: {s['url']}\n{s['content']}"
        for i, s in enumerate(sources)
    )
    return (
        "You are a careful research assistant. Answer the user's question "
        "using ONLY the numbered web sources below. Every factual claim in "
        "your answer must end with a citation like [1] or [2] that matches "
        "the source number it came from. Never cite a number that is not in "
        "the list. If the sources do not cover part of the question, say so "
        "plainly in a short 'What we could not verify' section instead of "
        "guessing. Keep the answer concise and useful.\n\n"
        f"Question: {question}\n\nSources:\n{numbered}"
    )


def assess_evidence(sources):
    """How much the search results actually support an answer.

    solid: 3+ sources with real content.
    thin:  1-2 sources, or very little text in total.
    none:  no usable sources at all.
    """
    if not sources:
        return "none"
    total_chars = sum(len(s["content"]) for s in sources)
    if len(sources) >= MIN_SOLID_SOURCES and total_chars >= 800:
        return "solid"
    return "thin"


def cited_numbers(answer, n_sources):
    """Which [n] citations in the answer point at real sources."""
    nums = {int(n) for n in re.findall(r"\[(\d+)\]", answer)}
    return sorted(n for n in nums if 1 <= n <= n_sources)


def research(question, max_results=6):
    """Run the full agent flow. Returns a dict ready to JSON-encode."""
    cfg = _config()
    missing = []
    if not cfg["nebius_key"]:
        missing.append("NEBIUS_API_KEY")
    if not cfg["tavily_key"]:
        missing.append("TAVILY_API_KEY")
    if missing:
        raise MissingKeyError(missing)

    steps = []
    t0 = time.time()
    sources = tavily_search(question, cfg["tavily_key"], max_results=max_results)
    steps.append({"step": "searched the web (Tavily)", "seconds": round(time.time() - t0, 1),
                  "detail": f"{len(sources)} source(s) found"})

    evidence = assess_evidence(sources)
    if evidence == "none":
        return {
            "question": question,
            "answer": (
                "I could not find any usable web sources for this question, "
                "so I have no verified answer to give. Try rephrasing the "
                "question or asking about a more specific topic."
            ),
            "sources": [],
            "evidence": "none",
            "cited": [],
            "model": cfg["model"],
            "steps": steps,
            "seconds": round(time.time() - t0, 1),
        }

    t1 = time.time()
    answer = nebius_chat(
        [
            {"role": "system", "content": "You are a careful research assistant."},
            {"role": "user", "content": _build_prompt(question, sources)},
        ],
        api_key=cfg["nebius_key"],
        model=cfg["model"],
        base_url=cfg["base_url"],
    )
    steps.append({"step": f"synthesized answer ({cfg['model']})",
                  "seconds": round(time.time() - t1, 1),
                  "detail": f"{len(cited_numbers(answer, len(sources)))} citation(s) used"})

    return {
        "question": question,
        "answer": answer,
        "sources": [{"title": s["title"], "url": s["url"]} for s in sources],
        "evidence": evidence,
        "cited": cited_numbers(answer, len(sources)),
        "model": cfg["model"],
        "steps": steps,
        "seconds": round(time.time() - t0, 1),
    }
