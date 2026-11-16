#!/usr/bin/env python3
"""Import main.elf into the Ghidra project used by decompile_net.py (idempotent)."""
import pathlib
import pyghidra

pyghidra.start()

LOC = "/tmp/ghproj"
NAME = "sp2"
ELF = "/work/main.elf"

try:
    proj = pyghidra.open_project(f"{LOC}/{NAME}", NAME)
    print(f"project already exists: {LOC}/{NAME}")
    proj.close()
except FileNotFoundError:
    with pyghidra.open_program(ELF, project_location=LOC, project_name=NAME,
                               analyze=False, language="AARCH64:LE:64:v8A"):
        print(f"imported {ELF} into {LOC}/{NAME}")
