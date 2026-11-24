"""Fleet Architect: web design officer on the local vision model (Gemma 4 12B).

Two modes (roster.py add architect "brief" --mode ...):
  critique  Judge a finished page. --file page.html (path from NEXUS root) or --url URL.
            1. measure - headless Chrome at phone and desktop size: overflow, text size, tap targets,
                         covered buttons, broken images (architect_measure.mjs). Hard facts, no opinions.
            2. look    - the model sees the screenshots and grades the fixed checklist in its orders.
            3. gate    - every checklist item answered, and the model's grades must not contradict the
                         measurements (a "5/5 mobile" on a page that scrolls sideways fails).
  copy      Write page copy and a section plan from a fact sheet. --read briefs/<client>-facts.md
            Output: report + a .copy.json the Chief Engineer can pour into a finished template.
            Gate: no number that isn't in the fact sheet, no hype words, no dashes, length limits.

The Architect never designs or edits HTML. Design comes from NEXUS and the design library; the
Architect judges pages and writes words. Lesson from the Chief Engineer, 2026-11-18: local models
fill templates well and design badly.
"""
import base64
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fleet_lib import FLEET_DIR, NEXUS_ROOT, Ollama, make_room_for, slugify  # noqa: E402

ORDERS = FLEET_DIR / "officers" / "architect.md"
MEASURE = FLEET_DIR / "officers" / "architect_measure.mjs"
CHECKLIST = ["first_impression", "headline", "call_to_action", "hierarchy", "readability",
             "spacing", "imagery", "trust", "mobile", "polish"]
HYPE = ["leverage", "elevate", "unlock", "seamless", "cutting-edge", "cutting edge", "world-class", "world class",
        "best-in-class", "revolutionize", "revolutionise", "synergy", "game-changer", "game changer",
        "next-level", "next level", "unparalleled", "state-of-the-art", "state of the art", "empower",
        "supercharge", "in today's", "look no further", "one-stop", "top-notch", "delve"]
DASHES = ["\u2014", "\u2013"]

ITEM = {"type": "object",
        "properties": {"score": {"type": "integer"}, "seen": {"type": "string"}, "fix": {"type": "string"}},
        "required": ["score", "seen", "fix"]}
CRITIQUE_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "checklist": {"type": "object", "properties": {k: ITEM for k in CHECKLIST}, "required": CHECKLIST},
        "top_fixes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "checklist", "top_fixes"],
}
SECTION = {"type": "object",
           "properties": {"id": {"type": "string"}, "purpose": {"type": "string"}, "heading": {"type": "string"},
                          "body": {"type": "string"}, "bullets": {"type": "array", "items": {"type": "string"}},
                          "cta": {"type": "string"}},
           "required": ["id", "purpose", "heading", "body", "bullets", "cta"]}
COPY_SCHEMA = {
    "type": "object",
    "properties": {
        "meta": {"type": "object", "properties": {"title": {"type": "string"}, "description": {"type": "string"}},
                 "required": ["title", "description"]},
        "hero": {"type": "object",
                 "properties": {"eyebrow": {"type": "string"}, "headline": {"type": "string"},
                                "subhead": {"type": "string"}, "cta_primary": {"type": "string"},
                                "cta_secondary": {"type": "string"}},
                 "required": ["eyebrow", "headline", "subhead", "cta_primary", "cta_secondary"]},
        "sections": {"type": "array", "items": SECTION},
        "faq": {"type": "array", "items": {"type": "object", "properties": {"q": {"type": "string"}, "a": {"type": "string"}},
                                           "required": ["q", "a"]}},
    },
    "required": ["meta", "hero", "sections", "faq"],
}


def run(job, cfg, log):
    oc = cfg["officers"]["architect"]
    mode = (job.get("mode") or "critique").lower()
    llm = Ollama(cfg["ollama_host"])
    make_room_for(cfg, llm, oc["model"])
    t0 = time.time()
    orders = ORDERS.read_text(encoding="utf-8")

    def ask(user, schema, images=None):
        msg = {"role": "user", "content": user}
        if images:
            msg["images"] = [base64.b64encode(Path(p).read_bytes()).decode() for p in images]
        return llm.chat(oc["model"], [{"role": "system", "content": orders}, msg], num_ctx=oc["num_ctx"],
                        temperature=oc["temperature"], think=False, schema=schema, timeout=900)

    if mode == "critique":
        result = critique(job, cfg, ask, log)
    elif mode == "copy":
        result = write_copy(job, ask, log)
    else:
        raise ValueError(f"architect mode must be critique or copy, not {mode!r}")
    result["mode"] = mode
    result["stats"] = {"seconds": round(time.time() - t0), "model": oc["model"], "calls": llm.calls,
                       "tokens_in": llm.tokens_in, "tokens_out": llm.tokens_out}
    return result


# ------------------------------------------------------------------ critique

def measure(target, out_dir, cfg):
    chrome = cfg.get("review", {}).get("chrome", "C:/Program Files/Google/Chrome/Application/chrome.exe")
    p = subprocess.run(["node", str(MEASURE), target, str(out_dir), chrome], capture_output=True, text=True,
                       encoding="utf-8", timeout=240)
    if p.returncode != 0:
        raise RuntimeError("page measure failed: " + (p.stderr or p.stdout)[-400:])
    return json.loads(p.stdout.strip().splitlines()[-1])


def critique(job, cfg, ask, log):
    if job.get("files"):
        target = str((NEXUS_ROOT / job["files"][0]).resolve())
        if not Path(target).exists():
            raise FileNotFoundError(job["files"][0])
    elif job.get("urls"):
        target = job["urls"][0]
    else:
        raise ValueError("critique needs --file page.html or --url URL")
    shots_dir = FLEET_DIR / "roster" / "workshop" / job["id"]
    shots_dir.mkdir(parents=True, exist_ok=True)
    m = measure(target, shots_dir, cfg)
    log(f"measured {target}")
    ph, dk = m["sizes"]["phone"], m["sizes"]["desktop"]
    facts = measured_facts(m)

    # Images: both first screens, then the rest of the phone page (where most visitors are).
    images = [dk["shots"][0], ph["shots"][0]] + ph["shots"][1:4]
    labels = ["image 1: desktop, first screen", "image 2: phone, first screen"] + \
             [f"image {i + 3}: phone, screen {i + 2}" for i in range(len(ph["shots"][1:4]))]
    got = ask(f"Brief from NEXUS: {job['brief']}\n\nYou are looking at one web page. Images, in order:\n- "
              + "\n- ".join(labels) +
              "\n\nMEASURED FACTS (from code, always true, trust these over your eyes):\n" + "\n".join(facts) +
              "\n\nGrade the page on every checklist item in your orders. For each: score 1 to 5, 'seen' = what you "
              "actually see in the images (name the element and the image number), 'fix' = one concrete change. "
              "Then top_fixes: the 3 changes that would help most, most important first. Reply as JSON.",
              CRITIQUE_SCHEMA, images)
    gate = critique_gate(got, m)
    return {"target": target, "measured": m, "facts": facts, "review": got, "gate": gate,
            "shots": [str(Path(p)) for p in images]}


def measured_facts(m):
    out = []
    for label, s in m["sizes"].items():
        out.append(f"{label} ({s['viewport']}): page {s['page_height']}px tall, "
                   + ("SCROLLS SIDEWAYS, page is " + str(s["page_width"]) + "px wide: " + "; ".join(s["too_wide"])
                      if s["sideways_scroll"] else "no sideways scroll"))
        out.append(f"{label}: smallest text {s['smallest_text_px']}px"
                   + (", under 12px: " + "; ".join(s["text_under_12px"]) if s["text_under_12px"] else ""))
        out.append(f"{label}: {s['tap_targets_under_40px']} of {s['tap_targets']} links/buttons are under 40px"
                   + (" (e.g. " + "; ".join(s["tap_examples"][:3]) + ")" if s["tap_examples"] else ""))
        out.append(f"{label}: links/buttons on the first screen: " + (", ".join(s["first_screen_links"]) or "NONE"))
        if s["covered_on_first_screen"]:
            out.append(f"{label}: COVERED by another layer (dimmed or unclickable): " + "; ".join(s["covered_on_first_screen"]))
        if s["images_broken"]:
            out.append(f"{label}: BROKEN images: " + ", ".join(s["images_broken"]))
    d = m["sizes"]["desktop"]
    out.append(f"h1 headings: {d['h1_count']}; images {d['images']}, {d['images_no_alt']} without alt text; "
               f"viewport meta tag: {'yes' if d['has_viewport_meta'] else 'MISSING'}; title: {d['title']!r}")
    out += [f"page error: {e}" for e in m.get("errors", [])[:5]]
    return out


def critique_gate(got, m):
    """Answered every item, and the grades don't contradict what was measured."""
    problems = []
    cl = got.get("checklist", {})
    for k in CHECKLIST:
        it = cl.get(k)
        if not it:
            problems.append(f"no grade for {k}")
            continue
        if not 1 <= int(it.get("score", 0)) <= 5:
            problems.append(f"{k}: score {it.get('score')} is not 1 to 5")
        no_fix_needed = int(it.get("score", 0)) == 5 and (it.get("fix") or "").strip().lower().rstrip(".") in ("none", "", "n/a")
        if len((it.get("seen") or "").split()) < 4 or (len((it.get("fix") or "").split()) < 3 and not no_fix_needed):
            problems.append(f"{k}: 'seen' or 'fix' is too thin to act on")
    if len(got.get("top_fixes", [])) < 3:
        problems.append("fewer than 3 top fixes")
    ph = m["sizes"]["phone"]
    score = lambda k: int((cl.get(k) or {}).get("score", 0))  # noqa: E731
    if ph["sideways_scroll"] and score("mobile") >= 4:
        problems.append("graded mobile 4+ but the phone page scrolls sideways")
    if (not ph["first_screen_links"] or ph["covered_on_first_screen"]) and score("call_to_action") >= 4:
        problems.append("graded call to action 4+ but the phone first-screen button is missing or covered")
    if ph["text_under_12px"] and score("readability") >= 5:
        problems.append("graded readability 5 but there is text under 12px on phone")
    if ph["tap_targets"] and ph["tap_targets_under_40px"] / ph["tap_targets"] > 0.5 and score("mobile") >= 5:
        problems.append("graded mobile 5 but most tap targets are under 40px")
    text = json.dumps(got, ensure_ascii=False)
    if any(d in text for d in DASHES):
        problems.append("contains an em or en dash")
    return {"passed": not problems, "problems": problems}


# ------------------------------------------------------------------ copy

def write_copy(job, ask, log):
    if not job.get("read"):
        raise ValueError("copy needs a fact sheet: --read Areas/Fleet/briefs/<client>-facts.md")
    sheet_path = NEXUS_ROOT / job["read"][0]
    sheet = sheet_path.read_text(encoding="utf-8")
    got = ask(f"Brief from NEXUS: {job['brief']}\n\nFACT SHEET (the only facts you may use):\n---\n{sheet}\n---\n\n"
              "Write the page copy as JSON. 'sections' is the page in order from top to bottom (after the hero), "
              "5 to 8 sections, each with an id (one lowercase word), its purpose (why it is on the page), heading, "
              "body (1 to 3 short sentences), bullets (0 to 6, short) and cta (button text, or empty). "
              "faq: 4 to 6 questions a customer of this business really asks, answered only from the fact sheet. "
              "Follow every copy rule in your orders.", COPY_SCHEMA)
    log(f"copy written: {len(got.get('sections', []))} sections, {len(got.get('faq', []))} FAQs")
    gate = copy_gate(got, sheet)
    return {"sheet": str(sheet_path.relative_to(NEXUS_ROOT)), "copy": got, "gate": gate}


def copy_strings(got):
    out = []
    def walk(x):
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            for k, v in x.items():
                if k not in ("id",):
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(got)
    return out


def copy_gate(got, sheet):
    problems = []
    sheet_nums = set(re.findall(r"\d+", sheet))
    for s in copy_strings(got):
        for n in re.findall(r"\d+", s):
            if n not in sheet_nums:
                problems.append(f"number {n} is not in the fact sheet: {s[:80]!r}")
        low = s.lower()
        for w in HYPE:
            if re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low):
                problems.append(f"hype word {w!r}: {s[:80]!r}")
        if any(d in s for d in DASHES):
            problems.append(f"dash: {s[:80]!r}")
    hero, meta = got.get("hero", {}), got.get("meta", {})
    if len(hero.get("headline", "").split()) > 10:
        problems.append(f"headline over 10 words: {hero.get('headline')!r}")
    if len(meta.get("title", "")) > 60:
        problems.append(f"meta title over 60 characters ({len(meta['title'])})")
    if len(meta.get("description", "")) > 160:
        problems.append(f"meta description over 160 characters ({len(meta['description'])})")
    if not 5 <= len(got.get("sections", [])) <= 8:
        problems.append(f"{len(got.get('sections', []))} sections, want 5 to 8")
    for sec in got.get("sections", []):
        if not sec.get("heading", "").strip():
            problems.append(f"section {sec.get('id')!r} has no heading")
    return {"passed": not problems, "problems": sorted(set(problems))}


# ------------------------------------------------------------------ report

def write_report(job, result, cfg):
    out_dir = NEXUS_ROOT / cfg["reports_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    g, st = result["gate"], result["stats"]
    name = f"{datetime.now():%Y-%m-%d-%H%M}-architect-{result['mode']}-{slugify(job['brief'], 35)}"
    lines = [f"# Fleet Architect {result['mode']}: {job['brief'][:80]}", "",
             "> **Status: needs NEXUS review.** Drafted by a local model. Not checked yet.",
             f"> Gate: **{'PASSED' if g['passed'] else 'FAILED'}** - {len(g['problems'])} problems.",
             f"> Run: {st['model']}, {st['seconds']}s, {st['calls']} model calls, {st['tokens_in']:,} tokens in / "
             f"{st['tokens_out']:,} out (local, free). Job `{job['id']}`.", "", "**Brief:** " + job["brief"], ""]
    if result["mode"] == "critique":
        rv = result["review"]
        lines += [f"**Page:** `{result['target']}`", "", "## Summary", rv.get("summary", ""), "",
                  "## Top fixes"] + [f"{i}. {f}" for i, f in enumerate(rv.get("top_fixes", []), 1)]
        lines += ["", "## Measured (code, not opinion)"] + [f"- {f}" for f in result["facts"]]
        lines += ["", "## Checklist", "", "| Item | Score | Seen | Fix |", "|---|---|---|---|"]
        for k in CHECKLIST:
            it = rv.get("checklist", {}).get(k, {})
            cell = lambda s: (s or "").replace("|", "/").replace("\n", " ")  # noqa: E731
            lines.append(f"| {k.replace('_', ' ')} | {it.get('score', '-')}/5 | {cell(it.get('seen'))} | {cell(it.get('fix'))} |")
        lines += ["", "**Screenshots:** " + ", ".join(f"`{Path(p).relative_to(NEXUS_ROOT)}`" for p in result["shots"])]
    else:
        c = result["copy"]
        jpath = out_dir / (name + ".copy.json")
        jpath.write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")
        h, m = c.get("hero", {}), c.get("meta", {})
        lines += [f"**Fact sheet:** `{result['sheet']}`  **JSON for the Chief Engineer:** `{jpath.relative_to(NEXUS_ROOT)}`", "",
                  f"**Meta title:** {m.get('title')}  ", f"**Meta description:** {m.get('description')}", "",
                  "## Hero", f"*{h.get('eyebrow')}*", f"### {h.get('headline')}", h.get("subhead", ""), "",
                  f"[{h.get('cta_primary')}]  [{h.get('cta_secondary')}]", "", "## Section plan (top to bottom)"]
        for i, s in enumerate(c.get("sections", []), 1):
            lines.append(f"{i}. **{s.get('id')}**: {s.get('purpose')}")
        for s in c.get("sections", []):
            lines += ["", f"## {s.get('heading')}", f"<sub>`{s.get('id')}`</sub>", "", s.get("body", "")]
            lines += [f"- {b}" for b in s.get("bullets", [])]
            if s.get("cta"):
                lines.append(f"\n[{s['cta']}]")
        lines += ["", "## FAQ"]
        for q in c.get("faq", []):
            lines += [f"**{q.get('q')}**  ", q.get("a", ""), ""]
    if g["problems"]:
        lines += ["", "## Gate problems (for NEXUS)"] + [f"- {p}" for p in g["problems"]]
    path = out_dir / (name + ".md")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
