"""Duty roster: the fleet's job queue. One job at a time, in priority order, GPU handed over between officers.

  python roster.py add science "brief text" [--priority 1|2|3] [--depth quick|standard] [--url URL ...] [--urls-only]
  python roster.py run        # work the queue until empty, then stop
  python roster.py watch      # keep checking the queue (free, no tokens)
  python roster.py status     # what's queued, running, done, failed

Jobs are JSON files in roster/queue/. Anyone (NEXUS, a script, later Duet via Drive) adds work by
dropping a file there. Reports land in Inbox/fleet-reports/ marked for NEXUS review.
"""
import argparse
import json
import os
import shutil
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "officers"))

from fleet_lib import FLEET_DIR, NEXUS_ROOT, load_config, notify, slugify  # noqa: E402

ROSTER = FLEET_DIR / "roster"
DIRS = {k: ROSTER / k for k in ("queue", "running", "done", "failed")}
ALIASES = {"science": "science", "science-officer": "science", "science officer": "science", "research": "science",
           "holo": "holo", "holo-officer": "holo", "holo officer": "holo", "image": "holo", "images": "holo",
           "engineer": "engineer", "chief-engineer": "engineer", "chief engineer": "engineer", "code": "engineer",
           "architect": "architect", "fleet-architect": "architect", "fleet architect": "architect", "design": "architect"}
_used = {}  # officer modules used this watch, so they can be stood down
_ran = {}   # this run's done/failed counts, for the phone ping


def officer_module(name):
    key = ALIASES.get(name.strip().lower())
    if key == "science":
        import science_officer as m
    elif key == "holo":
        import holo_officer as m
    elif key == "engineer":
        import chief_engineer as m
    elif key == "architect":
        import architect_officer as m
    else:
        raise ValueError(f"no officer called {name!r} on the roster yet")
    _used[key] = m
    return m


def stand_down(cfg):
    """Queue empty: let each officer that has something running (ComfyUI) shut it down."""
    for m in list(_used.values()):
        if hasattr(m, "shutdown"):
            try:
                m.shutdown(cfg, lambda s: log(f"  {s}"))
            except Exception as e:  # noqa: BLE001
                log(f"  stand-down problem: {e}")
    _used.clear()
    try:  # unload text models too, so the GPU goes idle (power + UPS)
        from fleet_lib import Ollama
        llm = Ollama(cfg["ollama_host"])
        for name in llm.loaded():
            llm.unload(name)
            log(f"  unloaded {name}")
    except Exception as e:  # noqa: BLE001
        log(f"  could not unload Ollama models: {e}")


def log(msg):
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with open(ROSTER / "roster.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ------------------------------------------------------------ single-runner lock (Windows and Mac)

class Lock:
    def __init__(self, path):
        self.path, self.fh = path, None

    def __enter__(self):
        self.fh = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.fh.close()
            raise SystemExit("Another duty roster is already running. Standing down.")
        return self

    def __exit__(self, *exc):
        self.fh.close()


# ------------------------------------------------------------ queue

def add(officer, brief, priority=2, depth="quick", requested_by="nexus", urls=None, urls_only=False, extra=None):
    officer_module(officer)  # fail now if unknown
    _used.clear()
    now = datetime.now()
    job = {"id": f"{now:%Y%m%d-%H%M%S}-{slugify(brief, 30)}", "officer": officer, "priority": int(priority),
           "depth": depth, "brief": brief, "requested_by": requested_by, "created": now.isoformat(timespec="seconds")}
    if urls:
        job["urls"] = list(urls)
        job["urls_only"] = bool(urls_only)
    job.update({k: v for k, v in (extra or {}).items() if v not in (None, False)})
    # Same second + same brief = same id; the second job overwrote the first (lesson 2026-11-18). Add -2, -3...
    base, n = job["id"], 1
    while any((d / f"{job['id']}.json").exists() for d in DIRS.values()):
        n += 1
        job["id"] = f"{base}-{n}"
    path = DIRS["queue"] / f"{job['id']}.json"
    path.write_text(json.dumps(job, indent=2), encoding="utf-8")
    log(f"queued {job['id']} for {officer} (priority {priority})")
    return path


def next_job():
    jobs = []
    for p in DIRS["queue"].glob("*.json"):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
            jobs.append((int(j.get("priority", 2)), j.get("created", ""), p, j))
        except Exception as e:  # noqa: BLE001
            log(f"unreadable job file {p.name}: {e}; moving to failed")
            shutil.move(str(p), DIRS["failed"] / p.name)
    jobs.sort(key=lambda x: (x[0], x[1]))
    return (jobs[0][2], jobs[0][3]) if jobs else (None, None)


def write_report(job, result, cfg):
    out_dir = NEXUS_ROOT / cfg["reports_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    title = cfg["officers"][ALIASES[job["officer"].lower()]]["title"]
    g, st = result["gate"], result["stats"]
    lines = [
        f"# {title} report: {job['brief'][:80]}",
        "",
        "> **Status: needs NEXUS review.** Drafted by a local model. Not checked yet.",
        f"> Gate: **{'PASSED' if g['passed'] else 'FAILED'}** - {g['sources_total']} sources read, "
        f"{len(g['sources_used'])} cited, {len(g['problems'])} problems.",
        f"> Run: {st['model']}, {st['seconds']}s, {st['calls']} model calls, "
        f"{st['tokens_in']:,} tokens in / {st['tokens_out']:,} out (local, free). Job `{job['id']}`.",
        "",
        "**Brief:** " + job["brief"],
        "",
        result["body"],
        "",
        "## Sources",
    ]
    for s in result["sources"]:
        lines.append(f"{s['n']}. [{s['title']}]({s['url']})" + (f" - dated {s['published']}" if s["published"] else ""))
    if g["problems"]:
        lines += ["", "## Gate problems (for NEXUS)"] + [f"- {p}" for p in g["problems"]]
    lines += ["", "<details><summary>Search log</summary>", "", "Queries: " + "; ".join(result["queries"]), ""]
    lines += [f"- skipped {s}" for s in result["skipped"]] + ["", "</details>", ""]
    path = out_dir / f"{datetime.now():%Y-%m-%d}-{job['officer']}-{slugify(job['brief'], 40)}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def work_one(cfg):
    path, job = next_job()
    if not path:
        return False
    running = DIRS["running"] / path.name
    shutil.move(str(path), running)
    log(f"start {job['id']} -> {job['officer']}")
    try:
        mod = officer_module(job["officer"])
        result = mod.run(job, cfg, lambda m: log(f"  {m}"))
        report = mod.write_report(job, result, cfg) if hasattr(mod, "write_report") else write_report(job, result, cfg)
        job.update(finished=datetime.now().isoformat(timespec="seconds"), report=str(report.relative_to(NEXUS_ROOT)),
                   gate_passed=result["gate"]["passed"], stats=result["stats"])
        (DIRS["done"] / path.name).write_text(json.dumps(job, indent=2), encoding="utf-8")
        running.unlink()
        _ran["done"] = _ran.get("done", 0) + 1; _ran.setdefault("failed", 0)
        log(f"done {job['id']} in {result['stats']['seconds']}s, gate {'PASSED' if job['gate_passed'] else 'FAILED'} -> {job['report']}")
    except Exception as e:  # noqa: BLE001
        job.update(failed=datetime.now().isoformat(timespec="seconds"), error=f"{type(e).__name__}: {e}",
                   trace=traceback.format_exc()[-2000:])
        (DIRS["failed"] / path.name).write_text(json.dumps(job, indent=2), encoding="utf-8")
        running.unlink(missing_ok=True)
        _ran["failed"] = _ran.get("failed", 0) + 1; _ran.setdefault("done", 0)
        log(f"FAILED {job['id']}: {e}")
    return True


def recover_stuck():
    for p in DIRS["running"].glob("*.json"):
        log(f"requeueing {p.name} (was running when the roster stopped)")
        shutil.move(str(p), DIRS["queue"] / p.name)


def status():
    for k, d in DIRS.items():
        files = sorted(d.glob("*.json"))
        print(f"{k:8} {len(files)}")
        for p in files[-5:]:
            print(f"         {p.stem}")


def main():
    for d in DIRS.values():
        d.mkdir(parents=True, exist_ok=True)
    ap = argparse.ArgumentParser(description="NEXUS fleet duty roster")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add")
    a.add_argument("officer")
    a.add_argument("brief")
    a.add_argument("--priority", type=int, default=2, choices=[1, 2, 3])
    a.add_argument("--depth", default="quick", choices=["quick", "standard"])
    a.add_argument("--url", action="append", help="page to read first (repeatable)")
    a.add_argument("--urls-only", action="store_true", help="read only the given pages, no web search")
    a.add_argument("--count", type=int, help="holo: number of images (different seeds)")
    a.add_argument("--width", type=int, help="holo: width in px (multiple of 16)")
    a.add_argument("--height", type=int, help="holo: height in px (multiple of 16)")
    a.add_argument("--seed", type=int, help="holo: first seed, for repeatable images")
    a.add_argument("--animate", action="store_true", help="holo: also make a hologram GIF")
    a.add_argument("--name", help="holo: short file name")
    a.add_argument("--face", help="holo: reference face photo (path from NEXUS root); ReActor swaps it in. Personal use only")
    a.add_argument("--motion", help="holo: animate each still with Wan 2.2, e.g. 'he slowly turns his head left, then right'")
    a.add_argument("--motion-seconds", type=float, help="holo: clip length for --motion (default 2, ~1 min of GPU per second)")
    a.add_argument("--file", action="append", dest="files", help="engineer: file to create or edit, path from NEXUS root (repeatable)")
    a.add_argument("--read", action="append", help="engineer: read-only context file, path from NEXUS root (repeatable)")
    a.add_argument("--test", action="append", dest="tests", help="engineer: NEXUS-written test file, read-only to the engineer (repeatable)")
    a.add_argument("--check", help="engineer: test command run in the workshop, e.g. \"python tool.py --selftest\"")
    a.add_argument("--mode", choices=["critique", "copy"], help="architect: critique a page (--file/--url) or write copy (--read fact sheet)")
    a.add_argument("--edit-format", choices=["whole", "diff"], help="engineer: force Aider's edit style")
    sub.add_parser("run")
    sub.add_parser("watch")
    sub.add_parser("status")
    args = ap.parse_args()

    if args.cmd == "add":
        extra = {k: getattr(args, k) for k in ("count", "width", "height", "seed", "animate", "name", "face", "motion", "motion_seconds",
                                               "files", "read", "tests", "check", "edit_format", "mode")}
        print(add(args.officer, args.brief, args.priority, args.depth, urls=args.url, urls_only=args.urls_only, extra=extra))
    elif args.cmd == "status":
        status()
    else:
        cfg = load_config()
        with Lock(ROSTER / ".lock"):
            recover_stuck()
            if args.cmd == "run":
                try:
                    while work_one(cfg):
                        pass
                finally:
                    stand_down(cfg)
                log("queue empty, standing down")
                if _ran:
                    notify(f"Fleet done: {_ran['done']} finished, {_ran['failed']} failed. NEXUS to review.",
                           title="NEXUS Fleet", tags=["anchor"])
            else:
                log(f"on watch, checking every {cfg['watch_interval_seconds']}s")
                try:
                    while True:
                        if not work_one(cfg):
                            if _used:
                                stand_down(cfg)
                            time.sleep(cfg["watch_interval_seconds"])
                finally:
                    stand_down(cfg)


if __name__ == "__main__":
    main()
