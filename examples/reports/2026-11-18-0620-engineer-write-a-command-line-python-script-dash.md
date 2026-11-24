# Chief Engineer report: Write a command-line Python script dash_check.py that finds and fixes em dashes 

> **Status: needs NEXUS review.** Written by a local model in the workshop. Live files untouched.
> Gate: **FAILED** - 1/1 file(s) changed, 1 problems.
> Run: qwen2.5-coder:14b via Aider (whole edits), 354s, 78,800 tokens in / 9,540 out (local, free). Job `20261118-061600-write-a-command-line-python-sc`.

**Brief:** Write a command-line Python script dash_check.py that finds and fixes em dashes (U+2014) and en dashes (U+2013). Scan the files or folders given as arguments (default: current folder, recursive), only .md, .html, .txt and .py files, skipping folders named .git, node_modules, Archive and __pycache__. Print each hit as path:line: <line trimmed to 120 chars>, then a total. Exit 1 if any hits, 0 if none. --fix rewrites only files that had hits, line by line. Fix rules, in order, applied to BOTH dash characters: (1) digit, dash, digit becomes digit-digit; (2) letter, dash, letter (no spaces) becomes 'letter, letter'; (3) any other dash together with the spaces and tabs directly next to it becomes ' - ', or '- ' at the start of the line after its indentation. Only touch the dash and the spaces directly around it: never change leading indentation, normal hyphens, other spacing or line endings. Read and write as UTF-8 and call sys.stdout.reconfigure(encoding='utf-8'). Standard library only. The test file Areas/Fleet/tests/test_dash_check.py is the spec: make it pass, do not edit it.

**Workshop:** `Areas/Fleet/roster/workshop/20261118-061600-write-a-command-line-python-sc/` (Aider log: `.aider.run.log`, chat: `.aider.chat.history.md`)

## To install (NEXUS, after review)
- `Areas/Fleet/roster/workshop/20261118-061600-write-a-command-line-python-sc/Areas/Agentic_OS/tools/dash_check.py` -> `Areas/Agentic_OS/tools/dash_check.py` (new file, 76 lines)

**Check:** `python Areas/Fleet/tests/test_dash_check.py`
```
Traceback (most recent call last):
  File "<workspace>\Areas\Fleet\roster\workshop\20261118-061600-write-a-command-line-python-sc\Areas\Fleet\tests\test_dash_check.py", line 73, in <module>
    main()
    ~~~~^^
  File "<workspace>\Areas\Fleet\roster\workshop\20261118-061600-write-a-command-line-python-sc\Areas\Fleet\tests\test_dash_check.py", line 60, in main
    assert g == w, f"--fix gave {g!r}, expected {w!r}"
           ^^^^^^
AssertionError: --fix gave 'spaced em,dash', expected 'spaced em - dash'
```

## Gate problems (for NEXUS)
- check command failed (exit 1): python Areas/Fleet/tests/test_dash_check.py
Traceback (most recent call last):
  File "<workspace>\Areas\Fleet\roster\workshop\20261118-061600-write-a-command-line-python-sc\Areas\Fleet\tests\test_dash_check.py", line 73, in <module>
    main()
    ~~~~^^
  File "<workspace>\Areas\Fleet\roster\workshop\20261118-061600-write-a-command-line-python-sc\Areas\Fleet\tests\test_dash_check.py", line 60, in main
    assert g == w, f"--fix gave {g!r}, expected {w!r}"
           ^^^^^^
AssertionError: --fix gave 'spaced em,dash', expected 'spaced em - dash'

## Diff: Areas/Agentic_OS/tools/dash_check.py
```diff
--- live/Areas/Agentic_OS/tools/dash_check.py
+++ workshop/Areas/Agentic_OS/tools/dash_check.py
@@ -0,0 +1,76 @@
+import os
+import sys
+import re
+from pathlib import Path
+
+EM_DASH = chr(0x2014)
+EN_DASH = chr(0x2013)
+
+RULES = [
+    (re.compile(r'(\d+)[ \t]*' + re.escape(EM_DASH) + r'[ \t]*(\d+)'), r'\1-\2'),  # digit, dash, digit becomes digit-digit
+    (re.compile(r'([a-zA-Z])[ \t]*' + re.escape(EM_DASH) + r'[ \t]*([a-zA-Z])'), r'\1,\2'),  # letter, dash, letter becomes 'letter, letter'
+    (re.compile(r'([ \t]*)([ \t]*' + re.escape(EM_DASH) + r'[ \t]*)'), r'\1 - \2'),  # any other dash with spaces/tabs becomes ' - '
+    (re.compile(r'(\d+)[ \t]*' + re.escape(EN_DASH) + r'[ \t]*(\d+)'), r'\1-\2'),  # digit, dash, digit becomes digit-digit
+    (re.compile(r'([a-zA-Z])[ \t]*' + re.escape(EN_DASH) + r'[ \t]*([a-zA-Z])'), r'\1,\2'),  # letter, dash, letter becomes 'letter, letter'
+    (re.compile(r'([ \t]*)([ \t]*' + re.escape(EN_DASH) + r'[ \t]*)'), r'\1 - \2'),  # any other dash with spaces/tabs becomes ' - '
+]
+
+def fix_line(line):
+    for pattern, replacement in RULES:
+        line = pattern.sub(replacement, line)
+    return line
+
+def process_file(file_path, fix):
+    hits = 0
+    fixed_lines = []
+    with open(file_path, 'r', encoding='utf-8') as file:
+        lines = file.readlines()
+        for line in lines:
+            original_line = line
+            line = fix_line(line)
+            if line != original_line:
+                hits += 1
+                fixed_lines.append(line)
+            else:
+                fixed_lines.append(original_line)
+    
+    if hits > 0 and fix:
+        with open(file_path, 'w', encoding='utf-8') as file:
+            file.writelines(fixed_lines)
+    
+    return hits, lines
+
+def main():
+    sys.stdout.reconfigure(encoding='utf-8')
+    args = sys.argv[1:]
+    fix = '--fix' in args
+    if fix:
+        args.remove('--fix')
+    
+    if not args:
+        args = ['.']
+    
+    total_hits = 0
+    for arg in args:
+        for root, dirs, files in os.walk(arg):
+            if any(exclude in root for exclude in ['.git', 'node_modules', 'Archive', '__pycache__']):
+                dirs[:] = []
+                continue
+            
+            for file in files:
+                if file.endswith(('.md', '.html', '.txt', '.py')):
+                    file_path = Path(root) / file
+                    hits, lines = process_file(file_path, fix)
+                    total_hits += hits
+                    for i, line in enumerate(lines):
+                        if line != fix_line(line):
+                            print(f"{file_path}:{i + 1}: {line[:120].rstrip()}")
+    
+    if total_hits > 0:
+        print(f"Total hits: {total_hits}")
+        sys.exit(1)
+    else:
+        sys.exit(0)
+
+if __name__ == '__main__':
+    main()
```
