#!/usr/bin/env python3
"""Annotate decompiled files: replace Ghidra's func_0x... PLT stubs with the
demangled import name from the module's PLT map (gen-totk report)."""
import json
import re
import subprocess
import pathlib

import os
ROOT = pathlib.Path(os.environ.get("SPLAT2_WORK", pathlib.Path(__file__).resolve().parent.parent))
NET = ROOT / "net"
BASE = 0x100000

pm = json.loads((ROOT / "gen-totk/main/report.json").read_text())["plt_map"]
addrs = list(pm)
names = [pm[a] or ("sub_%s" % a) for a in addrs]
dem = subprocess.run(["c++filt"] + names, capture_output=True, text=True).stdout.splitlines()
if len(dem) != len(names):
    dem = names


def clean(s: str) -> str:
    s = s.split("(")[0] if "(" in s else s
    s = re.sub(r"[^A-Za-z0-9_:<>~,.*& ]+", "_", s)
    s = s.replace(" ", "_")
    return s or "imp"


mapping = {}
for a, d in zip(addrs, dem):
    va = int(a, 16) + BASE
    mapping[f"func_0x{va:08x}"] = "IMP_" + clean(d)

# longest keys first, not needed (fixed width)
pat = re.compile("|".join(re.escape(k) for k in mapping))

count = 0
for f in sorted(NET.glob("decompiled/*.dem.c")):
    text = f.read_text(errors="replace")
    new, n = pat.subn(lambda m: mapping[m.group(0)], text)
    out = f.with_name(f.name.replace(".dem.c", ".ann.c"))
    out.write_text(new, encoding="utf-8")
    count += n
    print(f"{out.name}: {n} imports")
print("total replacements", count)
