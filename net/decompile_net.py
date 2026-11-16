#!/usr/bin/env python3
"""Batch-decompile the Splatoon 2 network stack from the reconstructed ELF.

Run inside the localhost/reva:12.1.3 container (Ghidra 12.1.3 + pyghidra).
Each function is disassembled from its exact symbol range and decompiled with
the module's own C++ symbols, so output carries real class/namespace names.

Usage:
  python3 decompile_net.py pia_lan
  python3 decompile_net.py all
"""
import json
import os
import re
import sys
import time
from pathlib import Path

import pyghidra

pyghidra.start()

from ghidra.util.task import ConsoleTaskMonitor
from ghidra.app.cmd.disassemble import DisassembleCommand
from ghidra.app.cmd.function import CreateFunctionCmd
from ghidra.program.model.address import AddressSet
from ghidra.program.model.symbol import SourceType

BASE = 0x100000
HERE = Path("/work")
SYMS = HERE / "symbols.json"
OUT = HERE / "decompiled"
PROJECT_LOC = "/tmp/ghproj/sp2"
PROJECT_NAME = "sp2"

# category -> list of mangled prefixes
CATEGORIES = {
    "pia_lan":       ["_ZN2nn3pia3lan"],
    "pia_local":     ["_ZN2nn3pia5local"],
    "pia_inet":      ["_ZN2nn3pia4inet"],
    "pia_session":   ["_ZN2nn3pia7session"],
    "pia_transport": ["_ZN2nn3pia9transport"],
    "pia_nat":       ["_ZN2nn3pia3nat"],
    "pia_common":    ["_ZN2nn3pia6common"],
    "pia_clone":     ["_ZN2nn3pia5clone"],
    "pia_chat":      ["_ZN2nn3pia4chat"],
    "enl":           ["_ZN3enl"],
    "cnet":          ["_ZN4Cnet"],
    "lpnet":         ["_ZN2Lp3Net"],
    "cstm":          ["_ZN4Cstm"],
    "nex":           ["_ZN2nn3nex"],
}


def categorize(name):
    for cat, prefixes in CATEGORIES.items():
        for p in prefixes:
            if name.startswith(p):
                return cat
    return None


def load_targets(cats):
    syms = json.loads(SYMS.read_text())
    by_addr = {}
    for value, size, info, shndx, name in syms:
        if (info & 0xF) != 2 or not name:
            continue
        cat = categorize(name)
        if cat is None or cat not in cats:
            continue
        # keep one symbol per address; prefer the longest/real name
        old = by_addr.get(value)
        if old is None or (old[1] == 0 and size > 0):
            by_addr[value] = (name, size, cat)
    # fill zero sizes from the next function start
    starts = sorted(by_addr)
    out = []
    for av in starts:
        name, size, cat = by_addr[av]
        if size == 0:
            j = starts.index(av)
            if j + 1 < len(starts):
                size = starts[j + 1] - av
        if size <= 0 or size > 200000:
            continue
        out.append((av, size, name, cat))
    return out


def main():
    cats = sys.argv[1:] or ["all"]
    if cats == ["all"]:
        cats = list(CATEGORIES)
    bad = [c for c in cats if c not in CATEGORIES]
    if bad:
        sys.exit("unknown categories: " + ", ".join(bad))

    targets = load_targets(set(cats))
    print(f"targets: {len(targets)} functions in {len(cats)} categories", flush=True)

    OUT.mkdir(exist_ok=True)
    proj = pyghidra.open_project(PROJECT_LOC, PROJECT_NAME)
    mon = ConsoleTaskMonitor()

    with pyghidra.program_context(proj, "/main.elf") as prog:
        af = prog.getAddressFactory().getDefaultAddressSpace()
        fm = prog.getFunctionManager()
        listing = prog.getListing()
        from ghidra.app.decompiler import DecompInterface

        di = DecompInterface()
        di.openProgram(prog)

        index_path = OUT / "index.tsv"
        index_new = not index_path.exists()
        index = open(index_path, "a", encoding="utf-8")
        if index_new:
            index.write("category\taddress\tsize\tmangled\n")

        from ghidra.app.util.demangler import DemanglerUtil

        handles = {}
        for cat in cats:
            handles[cat] = open(OUT / f"{cat}.c", "w", encoding="utf-8")
            handles[cat].write(
                f"/* Splatoon 2 network stack - {cat}\n"
                f" * Reconstructed from main NSO symbols; Ghidra 12.1.3 decompiler.\n"
                f" * Addresses are original module addresses (image base 0).\n */\n\n")

        t0 = time.time()
        done = 0
        failed = 0
        for i, (av, size, mangled, cat) in enumerate(targets):
            va = av + BASE
            a = af.getAddress(va)
            end = af.getAddress(va + size - 1)
            body = AddressSet(a, end)
            try:
                tid = prog.startTransaction("decompile")
                try:
                    f = fm.getFunctionAt(a)
                    if f is not None and f.getBody().getNumAddresses() < size:
                        fm.removeFunction(a)
                        f = None
                    if f is None:
                        DisassembleCommand(a, body, True).applyTo(prog, mon)
                        CreateFunctionCmd(mangled, a, body, SourceType.USER_DEFINED,
                                          False, False).applyTo(prog, mon)
                        f = fm.getFunctionAt(a)
                finally:
                    prog.endTransaction(tid, True)
                if f is None:
                    failed += 1
                    continue
                res = di.decompileFunction(f, 60, mon)
                if res is None or not res.decompileCompleted():
                    failed += 1
                    continue
                code = res.getDecompiledFunction().getC()
                try:
                    dm = DemanglerUtil.demangle(prog, mangled)
                    disp = dm.getSignature() if dm else mangled
                except Exception:
                    disp = mangled
                h = handles[cat]
                h.write(f"/* {av:#x}  size {size}  {disp} */\n")
                h.write(code.rstrip() + "\n\n")
                index.write(f"{cat}\t{av:#x}\t{size}\t{mangled}\n")
            except Exception as e:
                failed += 1
                if failed < 20:
                    print("ERR", hex(av), mangled, repr(e), flush=True)
            done += 1
            if done % 100 == 0:
                dt = time.time() - t0
                print(f"  {done}/{len(targets)}  {dt:.0f}s  fail={failed}", flush=True)

        for h in handles.values():
            h.close()
        index.close()
        print(f"done: {done} decompiled, {failed} failed, {time.time()-t0:.0f}s",
              flush=True)
    proj.close()


if __name__ == "__main__":
    main()
