"""Chief Engineer: local coding officer. Drives Aider (open-source terminal coder) against Ollama.

Safety model: the engineer never edits live files. Each job copies its target files into
roster/workshop/<job-id>/ (same relative paths as in NEXUS), Aider works there, then a gate checks the
result. NEXUS reads the diff in the report and copies approved files into place by hand.

Job fields (from roster.py add engineer "brief" ...):
  files       files to create or edit, paths from the NEXUS root (repeatable --file)
  read        read-only context files, paths from the NEXUS root (repeatable --read)
  tests       test files NEXUS wrote, paths from the NEXUS root (repeatable --test). Copied into the
              workshop read-only and restored from the original before every check, so the engineer
              cannot weaken them. The engineer's own self-tests never count as proof.
  check       test command run inside the workshop (e.g. "python Areas/Fleet/tests/test_x.py")
  edit_format "whole" or "diff" (default: whole for small files, diff once any file is long)

Also callable as a checker (Aider's --test-cmd uses this):
  python chief_engineer.py --check <workshop>/.check.json
"""
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fleet_lib import FLEET_DIR, NEXUS_ROOT, Ollama, make_room_for, slugify  # noqa: E402

WORKSHOP = FLEET_DIR / "roster" / "workshop"
ORDERS = FLEET_DIR / "officers" / "chief-engineer.md"
DIFF_LIMIT = 400  # lines of diff shown in the report


# ------------------------------------------------------------ checks (also run by Aider after each edit)

def check_file(path):
    """Basic sanity check by file type. Returns a problem string or None."""
    if not path.exists():
        return f"{path.name}: file was not created"
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return f"{path.name}: file is empty"
    ext = path.suffix.lower()
    if ext == ".py":
        r = subprocess.run([sys.executable, "-m", "py_compile", str(path)], capture_output=True, text=True)
        if r.returncode:
            return f"{path.name}: Python syntax error\n{(r.stderr or r.stdout).strip()[-1500:]}"
    elif ext in (".js", ".mjs", ".cjs"):
        r = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True, shell=os.name == "nt")
        if r.returncode:
            return f"{path.name}: JavaScript syntax error\n{(r.stderr or r.stdout).strip()[-1500:]}"
    elif ext in (".html", ".htm"):
        low = text.lower()
        missing = [t for t in ("<html", "</html>", "<head", "<body", "</body>", 'name="viewport"') if t not in low]
        if missing:
            return f"{path.name}: HTML is missing {', '.join(missing)}"
        if low.count("<style") != low.count("</style>") or low.count("<script") != low.count("</script>"):
            return f"{path.name}: unclosed <style> or <script> tag"
    elif ext == ".json":
        try:
            json.loads(text)
        except ValueError as e:
            return f"{path.name}: invalid JSON: {e}"
    if re.search(r"TODO: implement|#\s*\.\.\.\s*$|//\s*\.\.\.\s*$", text, re.M):
        return f"{path.name}: placeholder left in code (TODO: implement or ...)"
    if ext == ".py" and re.search(r"finally:[^\n]*\n(?:[ \t]+[^\n]*\n)*?[ \t]+sys\.exit\(0\)", text):
        return f"{path.name}: sys.exit(0) inside a finally block hides failures"
    return None


def run_checks(spec):
    """spec = {"workshop": str, "files": [rel paths], "check": str|None}. Returns (passed, problems, output)."""
    ws = Path(spec["workshop"])
    for t in spec.get("tests", []):  # anti-tamper: always run NEXUS's copy
        (ws / t).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(NEXUS_ROOT / t, ws / t)
    problems = [p for p in (check_file(ws / f) for f in spec["files"]) if p]
    output = ""
    if spec.get("check") and not problems:
        r = subprocess.run(spec["check"], cwd=ws, shell=True, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=300)
        output = (r.stdout + r.stderr).strip()[-3000:]
        if r.returncode:
            problems.append(f"check command failed (exit {r.returncode}): {spec['check']}\n{output}")
    return not problems, problems, output


def check_main(spec_path):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    passed, problems, output = run_checks(spec)
    if output:
        print(output)
    for p in problems:
        print(p, file=sys.stderr)
    sys.exit(0 if passed else 1)


# ------------------------------------------------------------ job

def _rel(p):
    """Path from the NEXUS root as a forward-slash string (or the bare name for outside files)."""
    p = Path(p)
    full = p if p.is_absolute() else NEXUS_ROOT / p
    try:
        return full.resolve().relative_to(NEXUS_ROOT.resolve()).as_posix()
    except ValueError:
        return full.name


def _src(rel):
    return NEXUS_ROOT / rel


def run(job, cfg, log):
    c = cfg["officers"]["engineer"]
    model = c["model"]
    files = [_rel(f) for f in job.get("files") or []]
    if not files:
        raise ValueError("engineer job needs at least one --file to create or edit")
    reads = [str(_src(_rel(r))) for r in job.get("read") or []]
    for r in reads:
        if not Path(r).exists():
            raise FileNotFoundError(f"--read file not found: {r}")
    tests = [_rel(t) for t in job.get("tests") or []]
    for t in tests:
        if not _src(t).exists():
            raise FileNotFoundError(f"--test file not found: {t}")
    if tests and not job.get("check"):
        raise ValueError("--test given without --check (the command that runs it)")

    ws = WORKSHOP / job["id"]
    if ws.exists():
        shutil.rmtree(ws)
    ws.mkdir(parents=True)
    originals = {}
    for f in files:
        src, dst = _src(f), ws / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.exists():
            shutil.copy2(src, dst)
            originals[f] = src.read_text(encoding="utf-8", errors="replace")
        else:
            originals[f] = None
    log(f"workshop {ws.relative_to(NEXUS_ROOT).as_posix()}: {len(files)} file(s), {len(reads)} read-only, "
        f"{len(job.get('tests') or [])} NEXUS test(s)")

    spec = {"workshop": str(ws), "files": files, "check": job.get("check"), "tests": tests}
    for t in tests:
        (ws / t).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_src(t), ws / t)
    spec_path = ws / ".check.json"
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")

    longest = max((len(t.splitlines()) for t in originals.values() if t), default=0)
    edit_format = job.get("edit_format") or ("diff" if longest > c.get("whole_max_lines", 250) else "whole")

    settings = ws / ".aider.model.settings.yml"
    settings.write_text(
        f"- name: ollama_chat/{model}\n  extra_params:\n    num_ctx: {c['num_ctx']}\n"
        f"    temperature: {c.get('temperature', 0.2)}\n", encoding="utf-8")

    llm = Ollama(cfg["ollama_host"])
    make_room_for(cfg, llm, model)

    test_cmd = f'"{sys.executable}" "{Path(__file__).resolve()}" --check "{spec_path}"'
    cmd = [c.get("aider", "aider"), "--model", f"ollama_chat/{model}", "--model-settings-file", str(settings),
           "--edit-format", edit_format, "--no-git", "--yes-always", "--no-auto-commits",
           "--no-show-model-warnings", "--no-check-update", "--analytics-disable", "--no-pretty", "--no-stream",
           "--no-fancy-input", "--map-tokens", "0", "--test-cmd", test_cmd, "--auto-test",
           "--chat-history-file", str(ws / ".aider.chat.history.md"),
           "--input-history-file", str(ws / ".aider.input.history"),
           "--read", str(ORDERS)]
    for r in reads + [str(ws / t) for t in tests]:
        cmd += ["--read", r]
    env = dict(os.environ, OLLAMA_API_BASE=cfg["ollama_host"], PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    t0 = time.time()
    transcript, message, rounds = "", job["brief"], 1 + int(c.get("fix_rounds", 1))
    for rnd in range(1, rounds + 1):
        log(f"aider round {rnd}/{rounds} on {model} ({edit_format} edits, ctx {c['num_ctx']})")
        r = subprocess.run(cmd + ["--message", message] + files, cwd=ws, env=env, capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=c.get("timeout_seconds", 1800))
        transcript += f"\n===== round {rnd} =====\n" + (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
        passed, problems, check_out = run_checks(spec)
        if passed or rnd == rounds:
            break
        log(f"  gate failed, sending the error back: {problems[0].splitlines()[0][:100]}")
        message = ("The original job was:\n" + job["brief"] + "\n\nYour code still fails the NEXUS check. "
                   "Fix the code so it passes. Do not edit the test file. The failure:\n\n"
                   + "\n".join(problems)[-2500:])
    secs = round(time.time() - t0)
    (ws / ".aider.run.log").write_text(transcript, encoding="utf-8")

    sent = sum(_tok(m) for m in re.findall(r"Tokens: ([\d.,]+k?) sent", transcript))
    recv = sum(_tok(m) for m in re.findall(r"([\d.,]+k?) received", transcript))
    if r.returncode:
        problems.append(f"aider exited with code {r.returncode} (see .aider.run.log)")
    changes = []
    for f in files:
        new = (ws / f).read_text(encoding="utf-8", errors="replace") if (ws / f).exists() else None
        changes.append({"file": f, "new_file": originals[f] is None, "changed": new is not None and new != originals[f],
                        "lines": len(new.splitlines()) if new else 0,
                        "diff": _diff(f, originals[f], new)})
    if not any(ch["changed"] for ch in changes):
        problems.append("no file was changed")
    passed = not problems
    log(f"aider finished in {secs}s, gate {'PASSED' if passed else 'FAILED'}")
    return {"gate": {"passed": passed, "problems": problems}, "changes": changes, "workshop": ws,
            "check": job.get("check"), "check_output": check_out, "edit_format": edit_format,
            "stats": {"model": model, "seconds": secs, "calls": transcript.count("Tokens:"),
                      "tokens_in": sent, "tokens_out": recv}}


def _tok(s):
    s = s.replace(",", "")
    return int(float(s[:-1]) * 1000) if s.endswith("k") else int(float(s))


def _diff(name, old, new):
    if new is None or new == old:
        return ""
    lines = list(difflib.unified_diff((old or "").splitlines(), new.splitlines(),
                                      f"live/{name}", f"workshop/{name}", lineterm=""))
    if len(lines) > DIFF_LIMIT:
        lines = lines[:DIFF_LIMIT] + [f"... ({len(lines) - DIFF_LIMIT} more diff lines, see the workshop file)"]
    return "\n".join(lines)


def write_report(job, result, cfg):
    out_dir = NEXUS_ROOT / cfg["reports_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    g, st = result["gate"], result["stats"]
    ws = result["workshop"].relative_to(NEXUS_ROOT).as_posix()
    lines = [f"# Chief Engineer report: {job['brief'][:80]}", "",
             "> **Status: needs NEXUS review.** Written by a local model in the workshop. Live files untouched.",
             f"> Gate: **{'PASSED' if g['passed'] else 'FAILED'}** - "
             f"{sum(c['changed'] for c in result['changes'])}/{len(result['changes'])} file(s) changed, "
             f"{len(g['problems'])} problems.",
             f"> Run: {st['model']} via Aider ({result['edit_format']} edits), {st['seconds']}s, "
             f"{st['tokens_in']:,} tokens in / {st['tokens_out']:,} out (local, free). Job `{job['id']}`.", "",
             "**Brief:** " + job["brief"], "",
             f"**Workshop:** `{ws}/` (Aider log: `.aider.run.log`, chat: `.aider.chat.history.md`)", "",
             "## To install (NEXUS, after review)"]
    for c in result["changes"]:
        state = "new file" if c["new_file"] else ("changed" if c["changed"] else "unchanged")
        lines.append(f"- `{ws}/{c['file']}` -> `{c['file']}` ({state}, {c['lines']} lines)")
    if result.get("check"):
        lines += ["", f"**Check:** `{result['check']}`"]
        if result.get("check_output"):
            lines += ["```", result["check_output"][-1500:], "```"]
    if g["problems"]:
        lines += ["", "## Gate problems (for NEXUS)"] + [f"- {p}" for p in g["problems"]]
    for c in result["changes"]:
        if c["diff"]:
            lines += ["", f"## Diff: {c['file']}", "```diff", c["diff"], "```"]
    path = out_dir / f"{datetime.now():%Y-%m-%d-%H%M}-engineer-{slugify(job['brief'], 40)}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        check_main(sys.argv[2])
    else:
        print(__doc__)
