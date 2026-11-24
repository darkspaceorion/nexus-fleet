"""Review and keep: officer work goes to my Drive as a PDF review sheet, and into NEXUS once he approves.

  python review.py send --title "Short title" --verdict "NEXUS's check, plain English" [--recommend approve|changes|reject]
                        [--item SRC DEST ...] [--body notes.md] [--shots page.html] [--attach file ...] [--link URL]
  python review.py approve R-004     # copy each item SRC -> DEST (backing up anything replaced), file the sheet
  python review.py reject R-005 [--note "why"]
  python review.py rebuild R-004     # regenerate a sheet in place
  python review.py list [--all]

Paths are from the NEXUS root. The sheet lands in My Drive/NEXUS Review/ (local Google Drive folder, synced by the
Drive app). Text items are shown in the sheet as formatted text, web pages as phone + desktop screenshots.
Log: Areas/Fleet/review/log.json. Drive rule exception for this folder only: AGENTS.md (Approvals).
"""
import argparse
import base64
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fleet_lib import FLEET_DIR, NEXUS_ROOT, load_config, notify  # noqa: E402

LOG = FLEET_DIR / "review" / "log.json"
TEXT_EXT = {".md", ".txt"}
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4"}


# ------------------------------------------------------------ helpers

def cfg():
    return load_config()["review"]


def drive_dir():
    c = cfg()
    for d in c["drive_dirs"]:
        if Path(d).is_dir():
            out = Path(d) / c["folder"]
            for sub in ("", "Approved", "Rejected"):
                (out / sub).mkdir(parents=True, exist_ok=True)
            return out
    raise SystemExit(f"No Google Drive folder found (tried {c['drive_dirs']}). Is the Drive app running?")


def load_log():
    return json.loads(LOG.read_text(encoding="utf-8")) if LOG.exists() else []


def save_log(items):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text(json.dumps(items, indent=2), encoding="utf-8")


def nexus(p):
    p = Path(p)
    return p if p.is_absolute() else NEXUS_ROOT / p


def rel(p):
    try:
        return Path(p).resolve().relative_to(NEXUS_ROOT.resolve()).as_posix()
    except ValueError:
        return str(p)


def safe_name(s, n=60):
    s = re.sub(r'[<>:"/\\|?*\n\r\t]+', " ", s).strip()
    return re.sub(r"\s+", " ", s)[:n].rstrip(" .")


def find(items, rid):
    rid = rid.upper()
    for it in items:
        if it["id"] == rid:
            return it
    raise SystemExit(f"No review item {rid}. Try: python review.py list --all")


def chrome(*args):
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([cfg()["chrome"], "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        f"--user-data-dir={prof}", *args], capture_output=True, timeout=180)


def screenshot(page, width, height, out):
    chrome(f"--window-size={width},{height}", f"--screenshot={out}", "--virtual-time-budget=4000",
           Path(page).resolve().as_uri())
    if not Path(out).exists():
        raise RuntimeError(f"screenshot failed for {page}")


def img_tag(path, alt, cls=""):
    data = base64.b64encode(Path(path).read_bytes()).decode()
    mime = "image/png" if str(path).lower().endswith(".png") else "image/jpeg"
    return f'<img class="{cls}" alt="{html.escape(alt)}" src="data:{mime};base64,{data}">'


def md_to_html(text):
    """Markdown to HTML. Raw HTML in the text is shown as text, never run (reports quote <style> etc.)."""
    import markdown
    md = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
    md.preprocessors.deregister("html_block")
    md.inlinePatterns.deregister("html")
    return md.convert(text)


def split_tall(png, parts, out_dir):
    """Cut a tall phone screenshot into side-by-side columns so it fits one page."""
    from PIL import Image
    im = Image.open(png)
    h = im.height // parts
    outs = []
    for i in range(parts):
        o = Path(out_dir) / f"part{i}.png"
        im.crop((0, i * h, im.width, (i + 1) * h)).save(o)
        outs.append(o)
    return outs


# ------------------------------------------------------------ the sheet

CSS = """
@page { size: Letter; margin: 14mm 13mm; }
* { box-sizing: border-box; }
body { font: 11pt/1.5 'Segoe UI', Arial, sans-serif; color: #1a2233; margin: 0; }
.top { background: #0f172a; color: #e9edf5; padding: 14px 18px; border-radius: 10px; }
.top .id { font: 700 10pt monospace; color: #e0b23a; letter-spacing: .08em; }
.top h1 { font-size: 18pt; margin: 4px 0 2px; line-height: 1.2; }
.top .meta { color: #94a0b8; font-size: 9.5pt; }
.badge { display: inline-block; padding: 3px 10px; border-radius: 99px; font-weight: 700; font-size: 10pt; margin-top: 8px; }
.approve { background: #16a34a; color: #fff; } .changes { background: #e0b23a; color: #1a2233; } .reject { background: #d80e25; color: #fff; }
.box { border: 1px solid #d6dbe6; border-radius: 10px; padding: 10px 14px; margin: 12px 0; }
.box h2 { font-size: 11pt; margin: 0 0 4px; color: #5a6478; text-transform: uppercase; letter-spacing: .06em; }
.reply { background: #f6f5f2; }
code { font-size: 9.5pt; background: #eef1f6; padding: 1px 4px; border-radius: 4px; word-break: break-all; }
pre { background: #eef1f6; padding: 8px; border-radius: 6px; white-space: pre-wrap; font-size: 8.5pt; }
.content h1 { font-size: 15pt; } .content h2 { font-size: 13pt; margin-top: 16px; } .content h3 { font-size: 11.5pt; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; } td, th { border: 1px solid #d6dbe6; padding: 4px 6px; }
blockquote { border-left: 3px solid #e0b23a; margin: 8px 0; padding: 2px 10px; color: #5a6478; }
.shots { break-before: page; border: 0; padding: 0; }
.shotrow { display: flex; gap: 14px; justify-content: center; }
.shot-phone { width: 240px; border: 1px solid #d6dbe6; display: block; }
.shot-desk { width: 500px; border: 1px solid #d6dbe6; display: block; margin: 0 auto; }
.cap { text-align: center; font-size: 9pt; color: #5a6478; margin: 4px 0 0; }
.deskpage { break-before: page; }
a { color: #b00c1f; }
"""


def build_sheet(entry, body_html, shots_html, out_pdf):
    rec = entry["recommend"]
    label = {"approve": "NEXUS recommends: APPROVE", "changes": "NEXUS recommends: CHANGES NEEDED",
             "reject": "NEXUS recommends: REJECT"}[rec]
    goes = "".join(f"<li><code>{html.escape(i['dest'])}</code>"
                   + (" (replaces the current file, backed up first)" if nexus(i["dest"]).exists() else " (new)")
                   + "</li>" for i in entry["items"]) or "<li>Nothing to install. For reading only.</li>"
    links = "".join(f'<li><a href="{html.escape(u)}">{html.escape(u)}</a></li>' for u in entry.get("links", []))
    attach = "".join(f"<li>{html.escape(a)}</li>" for a in entry.get("attachments", []))
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{html.escape(entry['id'])}</title>
<style>{CSS}</style></head><body>
<div class="top"><div class="id">{entry['id']} &middot; REVIEW</div><h1>{html.escape(entry['title'])}</h1>
<div class="meta">{entry['created'][:16].replace('T', ' ')} &middot; from {html.escape(entry['source'])}</div>
<span class="badge {rec}">{label}</span></div>
<div class="box"><h2>NEXUS check</h2>{md_to_html(entry['verdict'])}</div>
<div class="box"><h2>Where it goes if approved</h2><ul>{goes}</ul></div>
{f'<div class="box"><h2>Links</h2><ul>{links}</ul></div>' if links else ''}
{f'<div class="box"><h2>Also in this folder</h2><ul>{attach}</ul></div>' if attach else ''}
<div class="box reply"><h2>To answer</h2>Reply in chat: <b>approve {entry['id']}</b>, <b>reject {entry['id']}</b>,
or <b>{entry['id']}: what to change</b>.</div>
{shots_html}
<div class="content">{body_html}</div>
</body></html>"""
    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "sheet.html"
        page.write_text(doc, encoding="utf-8")
        chrome("--no-pdf-header-footer", f"--print-to-pdf={out_pdf}", page.as_uri())
    if not Path(out_pdf).exists():
        raise RuntimeError("PDF was not written (Chrome print failed)")


def make_pdf(entry, pdf):
    body = ""
    if entry.get("body_src"):
        text = nexus(entry["body_src"]).read_text(encoding="utf-8", errors="replace")
        body = md_to_html(text) if entry["body_src"].lower().endswith(".md") else f"<pre>{html.escape(text)}</pre>"
    shots = ""
    if entry.get("shots"):
        with tempfile.TemporaryDirectory() as tmp:
            ph, dk = Path(tmp) / "phone.png", Path(tmp) / "desk.png"
            screenshot(nexus(entry["shots"]), 375, 2400, ph)
            screenshot(nexus(entry["shots"]), 1440, 2400, dk)
            halves = split_tall(ph, 2, tmp)
            shots = ('<div class="box shots"><h2>How it looks on a phone (375px, top then bottom)</h2><div class="shotrow">'
                     + "".join(img_tag(h, "Phone view", "shot-phone") for h in halves)
                     + '</div></div><div class="box deskpage"><h2>How it looks on a desktop (1440px)</h2>'
                     + img_tag(dk, "Desktop view", "shot-desk") + '</div>')
    build_sheet(entry, body, shots, pdf)


def rebuild(a):
    """Regenerate a waiting item's sheet in place (after a fix to the sheet or the item)."""
    items = load_log()
    entry = find(items, a.id)
    pdf = drive_dir() / entry["drive_files"][0]
    make_pdf(entry, pdf)
    print(f"{entry['id']} rebuilt: {pdf}")


# ------------------------------------------------------------ commands

def send(a):
    items = load_log()
    n = max((int(i["id"][2:]) for i in items), default=0) + 1
    entry = {"id": f"R-{n:03d}", "title": a.title, "verdict": a.verdict, "recommend": a.recommend,
             "source": a.source, "created": datetime.now().isoformat(timespec="seconds"), "status": "waiting",
             "items": [], "links": a.link or [], "attachments": [], "drive_files": []}
    for src, dest in a.item or []:
        if not nexus(src).exists():
            raise SystemExit(f"--item source not found: {src}")
        entry["items"].append({"src": rel(nexus(src)), "dest": dest.replace("\\", "/")})

    entry["body_src"] = a.body or next((i["src"] for i in entry["items"]
                                        if Path(i["src"]).suffix.lower() in TEXT_EXT), None)
    entry["shots"] = a.shots

    out = drive_dir()
    stem = f"{entry['id']} {safe_name(a.title)}"
    # Picture and video items also go to Drive, so they can be viewed before approving
    # (2026-11-18: portrait picks only reached Drive when NEXUS copied them by hand).
    media = [i["src"] for i in entry["items"] if Path(i["src"]).suffix.lower() in MEDIA_EXT]
    for f in dict.fromkeys(media + [rel(nexus(x)) if nexus(x).exists() else x for x in (a.attach or [])]):
        p = nexus(f)
        if not p.exists():
            raise SystemExit(f"--attach file not found: {f}")
        name = f"{entry['id']} {p.name}"
        shutil.copy2(p, out / name)
        entry["attachments"].append(name)
        entry["drive_files"].append(name)
    pdf = out / f"{stem}.pdf"
    make_pdf(entry, pdf)
    entry["drive_files"].insert(0, pdf.name)
    items.append(entry)
    save_log(items)
    pinged = notify(f"{entry['id']} ready for review: {entry['title'][:80]}. Drive > NEXUS Review.",
                    title="NEXUS review", tags=["clipboard"])
    print(f"{entry['id']} sent: {pdf}" + ("" if pinged else "  (phone ping NOT sent)"))


def move_drive(entry, sub):
    out = drive_dir()
    for name in entry["drive_files"]:
        if (out / name).exists():
            shutil.move(str(out / name), out / sub / name)


def approve(a):
    items = load_log()
    entry = find(items, a.id)
    if entry["status"] != "waiting":
        raise SystemExit(f"{entry['id']} is already {entry['status']}")
    stamp = datetime.now()
    backup_root = NEXUS_ROOT / "Archive" / f"review-backups-{stamp:%Y-%m-%d}"
    done = []
    for it in entry["items"]:
        src, dest = nexus(it["src"]), nexus(it["dest"])
        if dest.exists():
            b = backup_root / f"{entry['id']}-{stamp:%H%M%S}" / it["dest"]
            b.parent.mkdir(parents=True, exist_ok=True)
            (shutil.copytree if dest.is_dir() else shutil.copy2)(dest, b)
            it["backup"] = rel(b)
            done.append(f"backed up {it['dest']} -> {rel(b)}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dest)
        done.append(f"installed {it['src']} -> {it['dest']}")
    move_drive(entry, "Approved")
    entry.update(status="approved", decided=stamp.isoformat(timespec="seconds"))
    save_log(items)
    print(f"{entry['id']} approved.")
    for d in done:
        print(" ", d)


def reject(a):
    items = load_log()
    entry = find(items, a.id)
    move_drive(entry, "Rejected")
    entry.update(status="rejected", decided=datetime.now().isoformat(timespec="seconds"), note=a.note)
    save_log(items)
    print(f"{entry['id']} rejected. Sheet moved to Rejected/. Nothing installed.")


def list_items(a):
    for it in load_log():
        if a.all or it["status"] == "waiting":
            print(f"{it['id']}  {it['status']:9} {it['created'][:10]}  {it['title']}")


def main():
    ap = argparse.ArgumentParser(description="NEXUS review and keep")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send")
    s.add_argument("--title", required=True)
    s.add_argument("--verdict", required=True, help="NEXUS's check in plain English (markdown ok)")
    s.add_argument("--recommend", default="approve", choices=["approve", "changes", "reject"])
    s.add_argument("--source", default="NEXUS", help="who made it, e.g. 'Chief Engineer'")
    s.add_argument("--item", nargs=2, action="append", metavar=("SRC", "DEST"), help="file or folder to install on approve")
    s.add_argument("--body", help="markdown or text file to show in the sheet (default: first text item)")
    s.add_argument("--shots", help="HTML page to screenshot at phone and desktop width")
    s.add_argument("--attach", action="append", help="file to put next to the sheet (images, video)")
    s.add_argument("--link", action="append", help="preview link to show")
    p = sub.add_parser("approve")
    p.add_argument("id")
    rb = sub.add_parser("rebuild")
    rb.add_argument("id")
    r = sub.add_parser("reject")
    r.add_argument("id")
    r.add_argument("--note")
    ls = sub.add_parser("list")
    ls.add_argument("--all", action="store_true")
    a = ap.parse_args()
    {"send": send, "rebuild": rebuild, "approve": approve, "reject": reject, "list": list_items}[a.cmd](a)


if __name__ == "__main__":
    main()
