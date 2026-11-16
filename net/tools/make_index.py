#!/usr/bin/env python3
"""Build a demangled, category-tagged symbol index for the network stack."""
import json
import subprocess
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent.parent
ROOT = HERE.parent
SYMS = HERE / "symbols.json"
OUT = HERE / "network_symbols.tsv"

CATEGORIES = {
    "pia_lan": "_ZN2nn3pia3lan",
    "pia_local": "_ZN2nn3pia5local",
    "pia_inet": "_ZN2nn3pia4inet",
    "pia_session": "_ZN2nn3pia7session",
    "pia_transport": "_ZN2nn3pia9transport",
    "pia_nat": "_ZN2nn3pia3nat",
    "pia_common": "_ZN2nn3pia6common",
    "pia_clone": "_ZN2nn3pia5clone",
    "pia_chat": "_ZN2nn3pia4chat",
    "enl": "_ZN3enl",
    "cnet": "_ZN4Cnet",
    "lpnet": "_ZN2Lp3Net",
    "cstm": "_ZN4Cstm",
    "nex": "_ZN2nn3nex",
    "nifm": "_ZN2nn4nifm",
    "socket": "_ZN2nn6socket",
    "ssl": "_ZN2nn3ssl",
    "ldn": "_ZN2nn3ldn",
}


def cat(name):
    for c, p in CATEGORIES.items():
        if name.startswith(p):
            return c
    return None


syms = json.loads(SYMS.read_text())
rows = []
for value, size, info, shndx, name in syms:
    if (info & 0xF) != 2 or not name:
        continue
    c = cat(name)
    if c is None:
        continue
    rows.append((c, value, size, name))

rows.sort(key=lambda r: (r[0], r[1]))
names = [r[3] for r in rows]
dem = subprocess.run(["c++filt"], input="\n".join(names), capture_output=True,
                     text=True).stdout.splitlines()
if len(dem) != len(names):
    dem = names

with OUT.open("w") as f:
    f.write("category\taddress\tsize\tdemangled\tmangled\n")
    for (c, v, s, n), d in zip(rows, dem):
        f.write(f"{c}\t{v:#x}\t{s}\t{d}\t{n}\n")
print(f"{len(rows)} symbols -> {OUT}")
