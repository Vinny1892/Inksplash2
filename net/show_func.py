#!/usr/bin/env python3
"""Show decompiled functions whose display name matches a substring."""
import re, sys, pathlib

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                    pathlib.Path(__file__).resolve().parent / "decompiled")
pat = sys.argv[2] if len(sys.argv) > 2 else "."
maxn = int(sys.argv[3]) if len(sys.argv) > 3 else 20

files = sorted(root.glob("*.dem.c"))
rx = re.compile(pat)
shown = 0
for f in files:
    text = f.read_text(errors="replace")
    # split on comment headers
    chunks = re.split(r'(?m)^(?=/\* 0x[0-9a-f]+  size )', text)
    for ch in chunks:
        m = re.match(r'/\* (0x[0-9a-f]+)  size (\d+)  (.*?) \*/', ch)
        if not m:
            continue
        if rx.search(m.group(3)):
            print(f"########## {f.name}  {m.group(1)}  size {m.group(2)}  {m.group(3)}")
            print(ch.split('*/', 1)[1].strip())
            print()
            shown += 1
            if shown >= maxn:
                sys.exit(0)
