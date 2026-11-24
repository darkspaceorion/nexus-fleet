"""Shared tools for the NEXUS fleet: config, Ollama calls, GPU memory handover, web search and fetch.
Standard library + requests/bs4 only, so it runs on Windows or a Mac unchanged."""
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup

FLEET_DIR = Path(__file__).resolve().parent
NEXUS_ROOT = FLEET_DIR.parents[1]
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def load_config():
    return json.loads((FLEET_DIR / "config.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- Ollama

class Ollama:
    def __init__(self, host):
        self.host = host.rstrip("/")
        self.tokens_in = 0
        self.tokens_out = 0
        self.calls = 0

    def chat(self, model, messages, *, num_ctx=8192, temperature=0.3, think=False, schema=None, timeout=600):
        body = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": think,
            "keep_alive": "5m",
            "options": {"num_ctx": num_ctx, "temperature": temperature},
        }
        if schema is not None:
            body["format"] = schema
        r = requests.post(f"{self.host}/api/chat", json=body, timeout=timeout)
        r.raise_for_status()
        d = r.json()
        self.calls += 1
        self.tokens_in += d.get("prompt_eval_count", 0) or 0
        self.tokens_out += d.get("eval_count", 0) or 0
        text = d["message"]["content"]
        if schema is not None:
            return json.loads(text)
        return text.strip()

    def loaded(self):
        r = requests.get(f"{self.host}/api/ps", timeout=10)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]

    def unload(self, model):
        requests.post(f"{self.host}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)


def make_room_for(cfg, ollama, model):
    """12 GB card: one big model at a time. Unload other Ollama models and ask ComfyUI to free VRAM."""
    for name in ollama.loaded():
        if name != model:
            ollama.unload(name)
    try:
        requests.post(f"{cfg['comfyui_host'].rstrip('/')}/free",
                      json={"unload_models": True, "free_memory": True}, timeout=5)
    except requests.RequestException:
        pass  # ComfyUI not running, nothing to free


# ---------------------------------------------------------------- web

class SearchUnavailable(RuntimeError):
    pass


def web_search(query, n=5, cfg=None):
    """Search the web with the provider named in config.json -> search.provider.
    Returns [{title, url, snippet}]. Keys come from Windows user env vars, never from the vault."""
    import os
    s = (cfg or load_config()).get("search", {})
    provider = s.get("provider", "duckduckgo")
    if provider == "brave":
        key = os.environ.get("BRAVE_API_KEY") or _raise(SearchUnavailable("BRAVE_API_KEY env var not set"))
        r = requests.get("https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": n},
                         headers={"X-Subscription-Token": key, "Accept": "application/json"}, timeout=20)
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x["url"], "snippet": x.get("description", "")}
                for x in r.json().get("web", {}).get("results", [])][:n]
    if provider == "tavily":
        key = os.environ.get("TAVILY_API_KEY") or _raise(SearchUnavailable("TAVILY_API_KEY env var not set"))
        r = requests.post("https://api.tavily.com/search", json={"query": query, "max_results": n},
                          headers={"Authorization": f"Bearer {key}"}, timeout=30)
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x["url"], "snippet": x.get("content", "")[:300]}
                for x in r.json().get("results", [])][:n]
    if provider == "searxng":
        r = requests.get(f"{s.get('searxng_url', 'http://127.0.0.1:8888').rstrip('/')}/search",
                         params={"q": query, "format": "json"}, timeout=20)
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x["url"], "snippet": x.get("content", "")}
                for x in r.json().get("results", [])][:n]
    return _duckduckgo(query, n)


def _raise(e):
    raise e


def _duckduckgo(query, n):
    """DuckDuckGo's plain HTML page. Free, but it serves a bot check to repeated automated use (seen 2026-11-16)."""
    r = requests.post("https://html.duckduckgo.com/html/", data={"q": query},
                      headers={"User-Agent": UA}, timeout=20)
    r.raise_for_status()
    if "anomaly" in r.text[:5000] or r.status_code == 202:
        raise SearchUnavailable("DuckDuckGo served a bot check; pick another search provider in config.json")
    soup = BeautifulSoup(r.text, "lxml")
    out = []
    for res in soup.select("div.result"):
        if "result--ad" in (res.get("class") or []):
            continue
        a = res.select_one("a.result__a")
        if not a or not a.get("href"):
            continue
        url = a["href"]
        if url.startswith("//"):
            url = "https:" + url
        if "duckduckgo.com/l/" in url:  # redirect wrapper
            url = unquote(parse_qs(urlparse(url).query).get("uddg", [url])[0])
        if "duckduckgo.com" in urlparse(url).netloc:
            continue
        snip = res.select_one(".result__snippet")
        out.append({"title": a.get_text(" ", strip=True), "url": url,
                    "snippet": snip.get_text(" ", strip=True) if snip else ""})
        if len(out) >= n:
            break
    return out


SKIP_EXT = (".pdf", ".zip", ".jpg", ".png", ".mp4", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")


def fetch_text(url, max_chars=7000):
    """Fetch a page and return (title, readable text). Raises on failure."""
    if urlparse(url).path.lower().endswith(SKIP_EXT):
        raise ValueError("not a web page")
    r = requests.get(url, headers={"User-Agent": UA}, timeout=20, stream=True)
    r.raise_for_status()
    ctype = r.headers.get("content-type", "")
    if "html" not in ctype and "text" not in ctype:
        raise ValueError(f"skipped content type {ctype}")
    raw = r.raw.read(2_000_000, decode_content=True)
    r.close()
    soup = BeautifulSoup(raw, "lxml")
    title = soup.title.get_text(strip=True) if soup.title else url
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "iframe"]):
        tag.decompose()
    main = soup.find("article") or soup.find("main") or soup.body or soup
    text = re.sub(r"\n\s*\n+", "\n\n", main.get_text("\n", strip=True))
    if len(text) < 300:
        raise ValueError("too little text on page")
    return title[:200], text[:max_chars]


def slugify(s, n=50):
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:n].rstrip("-") or "job"


def polite_pause(seconds=1.5):
    time.sleep(seconds)


# ---------------------------------------------------------------- phone pings (ntfy)

def _ntfy_topic():
    """Channel name lives in the NTFY_TOPIC user env var, never in NEXUS. Read the registry too, because a
    process started before the var was set (VS Code, the phone bridge) does not see it in os.environ."""
    t = os.environ.get("NTFY_TOPIC")
    if not t and os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                t = winreg.QueryValueEx(k, "NTFY_TOPIC")[0]
        except OSError:
            t = None
    return t


def notify(message, title="NEXUS", priority="default", tags=None):
    """Ping my phone through ntfy. Keep it short and free of client details (the channel is public-by-name).
    Returns True if sent. Never raises: a failed ping must not break a job."""
    topic = _ntfy_topic()
    if not topic:
        return False
    try:
        r = requests.post(f"https://ntfy.sh/{topic}", data=message.encode("utf-8"), timeout=15,
                          headers={"Title": title, "Priority": priority, "Tags": ",".join(tags or [])})
        return r.ok
    except requests.RequestException:
        return False
