"""NEXUS-written test for Areas/Agentic_OS/tools/dash_check.py (Chief Engineer job).
Run from the folder that holds Areas/ (the workshop, or the NEXUS root after install)."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TOOL = Path(os.environ.get("DASH_CHECK", "Areas/Agentic_OS/tools/dash_check.py")).resolve()  # in this repo: examples/engineer-output/dash_check.py
EM, EN = chr(0x2014), chr(0x2013)  # em dash, en dash (written as codes so the file holds none)

CASES = {  # input line -> expected line after --fix
    f"spaced em {EM} dash": "spaced em - dash",
    f"spaced en {EN} dash": "spaced en - dash",
    f"word{EM}word": "word, word",
    f"word{EN}word": "word, word",
    f"one side {EM}only": "one side - only",
    f"years 2020{EN}2024": "years 2020-2024",
    f"{EM} leading": "- leading",
    f"en one side {EN}only": "en one side - only",
    f"    - nested bullet {EM} note": "    - nested bullet - note",
    f"  two  spaces {EM}  here": "  two  spaces - here",
}
CLEAN = "well-known hyphen - and a spaced hyphen stay as they are\n"


def run(*args, cwd):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.run([sys.executable, str(TOOL), *args], cwd=cwd, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", env=env)


def main():
    d = Path(tempfile.mkdtemp())
    body = "\n".join(CASES) + "\n" + CLEAN
    (d / "notes.md").write_text(body, encoding="utf-8")
    (d / "page.html").write_text(f"<p>a {EM} b</p>\n", encoding="utf-8")
    (d / "clean.txt").write_text(CLEAN, encoding="utf-8")
    (d / "skip.js").write_text(f"// a {EM} b\n", encoding="utf-8")
    (d / "Archive").mkdir()
    (d / "Archive" / "old.md").write_text(f"old {EM} file\n", encoding="utf-8")

    r = run(cwd=d)  # default: current folder
    out = r.stdout
    assert r.returncode == 1, f"expected exit 1 with hits, got {r.returncode}\n{out}{r.stderr}"
    assert "notes.md:1:" in out and f"notes.md:{len(CASES)}:" in out, f"missing notes.md hits:\n{out}"
    assert "page.html:1:" in out, f"missing page.html hit:\n{out}"
    for bad in ("clean.txt", "skip.js", "old.md", f"notes.md:{len(CASES) + 1}:"):
        assert bad not in out, f"{bad} should not be reported:\n{out}"
    hit_lines = [l for l in out.splitlines() if ".md:" in l or ".html:" in l]
    assert len(hit_lines) == len(CASES) + 1, f"expected {len(CASES) + 1} hits, got {len(hit_lines)}:\n{out}"

    import os as _os, time as _time
    _os.utime(d / "clean.txt", (1_000_000_000, 1_000_000_000))
    r = run("--fix", str(d), cwd=d)
    assert (d / "clean.txt").stat().st_mtime == 1_000_000_000, "--fix must not rewrite files with no hits"
    got = (d / "notes.md").read_text(encoding="utf-8").splitlines()
    want = list(CASES.values()) + [CLEAN.rstrip("\n")]
    for g, w in zip(got, want):
        assert g == w, f"--fix gave {g!r}, expected {w!r}"
    assert len(got) == len(want), f"line count changed: {len(got)} vs {len(want)}"
    assert (d / "page.html").read_text(encoding="utf-8") == "<p>a - b</p>\n"
    assert (d / "clean.txt").read_text(encoding="utf-8") == CLEAN, "clean file was changed"
    assert EM in (d / "Archive" / "old.md").read_text(encoding="utf-8"), "Archive must be skipped"
    assert EM in (d / "skip.js").read_text(encoding="utf-8"), ".js must not be touched"

    r = run(str(d), cwd=d)
    assert r.returncode == 0, f"expected exit 0 after fix, got {r.returncode}\n{r.stdout}"
    print("nexus test ok")


if __name__ == "__main__":
    main()
