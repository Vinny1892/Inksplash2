#!/usr/bin/env python3
"""Reconstruct a Ghidra/revng-loadable AArch64 ELF from the Splatoon 2 NSO
memory image (work/img/main.bin), using the dynamic symbol table and RELA
relocations that are present in the module itself.

Input : work/img/main.bin      (exact memory image, base 0)
        work/net/symbols.json  (address,size,info,shndx,name)
Output: work/net/main.elf
"""
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
IMG = ROOT / "img" / "main.bin"
SYMS = HERE / "symbols.json"
OUT = HERE / "main.elf"

BASE = 0x100000  # keep virtual address 0 unmapped

TEXT_OFF, TEXT_SZ = 0, 21057640
RO_OFF, RO_SZ = 21061632, 26526899
DATA_OFF, DATA_SZ = 47591424, 2589104
BSS_OFF = 50180528
BSS_END = 57249696
IMAGE_SZ = 50180528

RELA_OFF = 21061704
RELA_SZ = 6121056

SHT_PROGBITS, SHT_SYMTAB, SHT_STRTAB, SHT_NOBITS = 1, 2, 3, 8
PT_LOAD = 1
SHF_WRITE, SHF_ALLOC, SHF_EXECINSTR = 1, 2, 4
STT_FUNC = 2
SHN_ABS = 0xFFF1


def main() -> None:
    image = bytearray(IMG.read_bytes())
    assert len(image) == IMAGE_SZ, len(image)
    syms = json.loads(SYMS.read_text())

    # ---------------------------------------------------------------- relocs
    # NSO RELA entries: r_offset, r_info (sym<<32 | type), r_addend.
    # The module is ET_DYN-ish; all pointers are image-relative.
    nrel = RELA_SZ // 24
    applied = 0
    for i in range(nrel):
        off, info, add = struct.unpack_from("<QQq", image, RELA_OFF + i * 24)
        symidx, rtype = info >> 32, info & 0xFFFFFFFF
        if rtype == 1027:  # R_AARCH64_RELATIVE
            val = add
        elif rtype in (257, 1025, 1026):  # ABS64 / JUMP_SLOT / GLOB_DAT
            sv = syms[symidx][0] if symidx < len(syms) else 0
            val = sv + add
        else:
            continue
        # pointers are 8-byte, all in the data segment
        if not (DATA_OFF <= off < IMAGE_SZ):
            continue
        struct.pack_into("<Q", image, off, (val + BASE) & 0xFFFFFFFFFFFFFFFF)
        applied += 1

    # --------------------------------------------------------------- symbols
    strtab = bytearray(b"\x00")
    sym_entries = []  # (name_off, info, other, shndx, value, size)
    for value, size, info, shndx, name in syms:
        if not name:
            continue
        b = name.encode("latin1", "replace")
        noff = len(strtab)
        strtab += b + b"\x00"
        if value < TEXT_OFF + TEXT_SZ:
            sec = 1
        elif value < RO_OFF + RO_SZ:
            sec = 2
        elif value < DATA_OFF + DATA_SZ:
            sec = 3
        elif value < BSS_END:
            sec = 4
        else:
            sec = SHN_ABS
        sym_entries.append((noff, info, 0, sec, value + BASE, size))

    # ------------------------------------------------------------- sections
    # Layout: ELF header | pad | text | ro | data | [bss is NOBITS] |
    #         symtab | strtab | shstrtab | section headers
    def align(x, a):
        return (x + a - 1) & ~(a - 1)

    # Keep file offset == BASE + virtual address so the copied memory image
    # (which contains the original inter-segment gaps) is byte-exact.
    text_fo = BASE + TEXT_OFF
    ro_fo = BASE + RO_OFF
    data_fo = BASE + DATA_OFF
    off = BASE + IMAGE_SZ
    symtab_fo = align(off, 8)

    symtab = bytearray()
    for e in sym_entries:
        symtab += struct.pack("<IBBHQQ", *e)
    strtab_fo = align(symtab_fo + len(symtab), 8)
    shstrtab_fo = align(strtab_fo + len(strtab), 8)
    shstr = b"\x00.text\x00.rodata\x00.data\x00.bss\x00.symtab\x00.strtab\x00.shstrtab\x00"

    shoff = align(shstrtab_fo + len(shstr), 8)
    shnum = 8

    # section header: name, type, flags, addr, offset, size, link, info,
    #                 addralign, entsize
    shdrs = [struct.pack("<IIQQQQIIQQ", *([0] * 10))]
    shdrs.append(struct.pack("<IIQQQQIIQQ", 1, SHT_PROGBITS, SHF_ALLOC | SHF_EXECINSTR,
                             BASE + TEXT_OFF, text_fo, TEXT_SZ, 0, 0, 16, 0))
    shdrs.append(struct.pack("<IIQQQQIIQQ", 7, SHT_PROGBITS, SHF_ALLOC,
                             BASE + RO_OFF, ro_fo, RO_SZ, 0, 0, 16, 0))
    shdrs.append(struct.pack("<IIQQQQIIQQ", 15, SHT_PROGBITS, SHF_ALLOC | SHF_WRITE,
                             BASE + DATA_OFF, data_fo, DATA_SZ, 0, 0, 16, 0))
    shdrs.append(struct.pack("<IIQQQQIIQQ", 21, SHT_NOBITS, SHF_ALLOC | SHF_WRITE,
                             BASE + BSS_OFF, data_fo + DATA_SZ, BSS_END - BSS_OFF,
                             0, 0, 16, 0))
    shdrs.append(struct.pack("<IIQQQQIIQQ", 26, SHT_SYMTAB, 0, 0, symtab_fo,
                             len(symtab), 6, 1, 8, 24))
    shdrs.append(struct.pack("<IIQQQQIIQQ", 34, SHT_STRTAB, 0, 0, strtab_fo,
                             len(strtab), 0, 0, 1, 0))
    shdrs.append(struct.pack("<IIQQQQIIQQ", 42, SHT_STRTAB, 0, 0, shstrtab_fo,
                             len(shstr), 0, 0, 1, 0))

    # ------------------------------------------------------------- phdrs
    # three PT_LOADs: text RX, ro R, data RW (+bss)
    phdrs = [
        struct.pack("<IIQQQQQQ", PT_LOAD, 5, text_fo, BASE + TEXT_OFF,
                    BASE + TEXT_OFF, TEXT_SZ, TEXT_SZ, 0x1000),
        struct.pack("<IIQQQQQQ", PT_LOAD, 4, ro_fo, BASE + RO_OFF,
                    BASE + RO_OFF, RO_SZ, RO_SZ, 0x1000),
        struct.pack("<IIQQQQQQ", PT_LOAD, 6, data_fo, BASE + DATA_OFF,
                    BASE + DATA_OFF, DATA_SZ, BSS_END - DATA_OFF, 0x1000),
    ]

    ehsize, phentsize, phnum = 64, 56, len(phdrs)
    shentsize = 64
    phoff = ehsize
    ident = b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\x00" * 8
    ehdr = ident + struct.pack(
        "<HHIQQQIHHHHHH",
        2,  # ET_EXEC
        183,  # EM_AARCH64
        1,
        BASE + 0x24,  # entry (module _init-ish; game entry is +0x24)
        phoff,
        shoff,
        0,
        ehsize,
        phentsize,
        phnum,
        shentsize,
        shnum,
        7,  # shstrndx
    )
    assert len(ehdr) == 64

    out = bytearray(shoff + shnum * shentsize)
    out[0:64] = ehdr
    out[phoff:phoff + len(phdrs) * 56] = b"".join(phdrs)
    # copy the (relocated) memory image so file offset == BASE + vaddr
    out[BASE:BASE + IMAGE_SZ] = image
    out[symtab_fo:symtab_fo + len(symtab)] = symtab
    out[strtab_fo:strtab_fo + len(strtab)] = strtab
    out[shstrtab_fo:shstrtab_fo + len(shstr)] = shstr
    out[shoff:shoff + shnum * shentsize] = b"".join(shdrs)
    OUT.write_bytes(out)

    print(f"wrote {OUT} ({len(out)/1e6:.1f} MB)")
    print(f"  symbols {len(sym_entries)}, relocs applied {applied}/{nrel}")


if __name__ == "__main__":
    main()
