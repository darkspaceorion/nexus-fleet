"""Find and fix em and en dashes (NEXUS writing rule: use ' - ' or a comma).

  python dash_check.py [paths...]        list hits as path:line: text, exit 1 if any
  python dash_check.py --fix [paths...]  rewrite only the files that have hits

Fix rules, applied to both dash characters, in order:
  1. digit-dash-digit       -> digit-digit      (2020-2024)
  2. letter-dash-letter     -> 'letter, letter'
  3. any other dash plus the spaces/tabs right next to it -> ' - ' ('- ' after a line's indentation)
Indentation, normal hyphens and line endings are never changed.
Drafted by the Chief Engineer (qwen2.5-coder:14b), finished by NEXUS 2026-11-18.
Test: Areas/Fleet/tests/test_dash_check.py (run from the NEXUS root).
"""
import re
import sys
from pathlib import Path

DASH = "[" + chr(0x2014) + chr(0x2013) + "]"
EXTS = {".md", ".html", ".txt", ".py"}
SKIP = {".git", "node_modules", "Archive", "__pycache__"}
RULES = [
    (re.compile(r"(\d)" + DASH + r"(\d)"), r"\1-\2"),
    (re.compile(r"([^\W\d_])" + DASH + r"([^\W\d_])"), r"\1, \2"),
    (re.compile(r"^([ \t]*)" + DASH + r"[ \t]*", re.M), r"\1- "),
    (re.compile(r"[ \t]*" + DASH + r"[ \t]*"), " - "),
]
HAS_DASH = re.compile(DASH)


def fix_line(line):
    for pattern, repl in RULES:
        line = pattern.sub(repl, line)
    return line


def files_in(paths):
    for arg in paths:
        p = Path(arg)
        if p.is_file():
            if p.suffix.lower() in EXTS:
                yield p
        elif p.is_dir():
            for f in sorted(p.rglob("*")):
                rel = f.relative_to(p).parts
                if f.is_file() and f.suffix.lower() in EXTS and not SKIP.intersection(rel[:-1]):
                    yield f


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    fix = "--fix" in args
    paths = [a for a in args if a != "--fix"] or ["."]
    total = 0
    for f in files_in(paths):
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not HAS_DASH.search(text):
            continue
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines, 1):
            if HAS_DASH.search(line):
                total += 1
                print(f"{f}:{i}: {line.strip()[:120]}")
        if fix:
            with open(f, "w", encoding="utf-8", newline="") as out:
                out.write("".join(fix_line(l) for l in lines))
    print(f"Total hits: {total}" + (" (fixed)" if fix and total else ""))
    sys.exit(1 if total else 0)


if __name__ == "__main__":
    main()
