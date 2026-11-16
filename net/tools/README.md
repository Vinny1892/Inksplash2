# Tools

All commands assume `cd work/net`.

## `build_elf.py`

Rebuilds `main.elf` from `work/img/main.bin`:

- reads the NSO memory image;
- applies all 255,044 RELA relocations (RELATIVE, ABS64, JUMP_SLOT);
- emits `.text`/`.rodata`/`.data`/`.bss` plus `.symtab` and `.strtab`;
- rebases to `0x100000` so virtual address 0 stays unmapped.

Output: `main.elf` (63.6 MB), loadable by Ghidra, revng, objdump, etc.

## `decompile_net.py`

Batch decompiler. Run inside the REA container:

```bash
podman run --rm --entrypoint bash \
  -v "$PWD:/work" -v /tmp/opencode/ghproj:/tmp/ghproj \
  localhost/reva:12.1.3 -lc 'cd /work && python3 decompile_net.py all'
```

Categories: `pia_lan`, `pia_local`, `pia_inet`, `pia_session`, `pia_transport`,
`pia_nat`, `pia_common`, `pia_clone`, `pia_chat`, `enl`, `cnet`, `lpnet`, `cstm`,
`nex`. Pass one or more, or `all`.

It:

- opens the saved Ghidra project (`/tmp/ghproj/sp2`);
- disassembles each symbol's exact address range;
- creates a function with that body;
- decompiles with a 60 s timeout;
- writes `decompiled/<category>.c` and appends to `decompiled/index.tsv`.

## `annotate_imports.py`

Replaces Ghidra's `func_0x…` PLT stubs with the demangled import name from
`gen-totk/main/report.json` (`plt_map`). Produces `*.ann.c`.

Typical flow:

```bash
for f in decompiled/*.c; do case "$f" in *.dem.c|*.ann.c) continue;; esac; \
  c++filt < "$f" > "${f%.c}.dem.c"; done
python3 annotate_imports.py
```

## `make_index.py`

Builds `network_symbols.tsv` from `symbols.json`:

```
category  address  size  demangled  mangled
```

15,177 symbols across PIA, NEX, ENL, Cnet, Lp::Net, Cstm and the platform
imports (`nn::nifm`, `nn::socket`, `nn::ssl`, `nn::ldn`).

## `show_func.py`

Print decompiled functions by name substring:

```bash
python3 show_func.py decompiled "LanProtocol::(Dispatch|Bind)" 5
python3 show_func.py decompiled "MatchMakingClient::MatchMakingClient" 2
```

It reads `*.dem.c` (or `*.ann.c` if you point it there) and prints the matching
function bodies with their address/size headers.

## `lan_dissect.py`

Splatoon 2 / Pia LAN packet dissector.

```bash
# decode a hex packet
python3 tools/lan_dissect.py --hex 00000000023a...

# decode a file
python3 tools/lan_dissect.py --file capture.bin

# listen on the LAN ports (read-only)
sudo python3 tools/lan_dissect.py --udp
```

It decodes:

- raw browse request/reply (types 0/1, UDP 30000);
- `LanSessionSearchCriteria` and `LanSessionInfo`;
- Pia packet headers (v9 and later), message framing, and LAN payloads 3–7;
- session fragments.

It does **not** decrypt Pia payloads. The challenge format and crypto notes are in
`LAN_PROTOCOL.md`.
