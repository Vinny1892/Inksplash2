# Splatoon 2 network stack — decompilation and server notes

This directory contains a working decompilation of the **retail Splatoon 2 `main`
module's networking code** (game layer + PIA + NEX), plus the protocol notes needed
to build a LAN server and a replacement online service.

Work was done from the dumped NSO (`work/img/main.bin`) using its own dynamic
symbol table and RELA relocations, inside the local Podman image
`localhost/reva:12.1.3` (Ghidra 12.1.3 + PyGhidra).

## What is here

| Path | What |
|---|---|
| `NETWORK_STACK.md` | Architecture, layers, entry points, addresses, modes |
| `LAN_PROTOCOL.md` | Pia LAN wire protocol as implemented by Splatoon 2 (ports, messages, layout) |
| `PIA_TRANSPORT.md` | Pia packet/message framing, crypto, relay implications |
| `NEX_ONLINE.md` | NEX auth/matchmaking, endpoints, constants, protocol IDs, Nextendo fit |
| `DEDICATED_SERVER_PLAN.md` | LAN → online → dedicated server roadmap |
| `tools/` | LAN packet dissector, LAN browse probe, symbol indexer |
| `*.py` | ELF rebuilder, Ghidra import and batch-decompile scripts |

**Not in this repo:** the decompiled sources (`decompiled/`), `network_symbols.tsv`,
`symbols.json`, `strings_net.txt` and the reconstructed `main.elf`. They are derived
directly from the retail game binary. Regenerate them locally from your own dump with
`build_elf.py` → `import_elf.py` → `decompile_net.py` → `annotate_imports.py`
(`decompiled/index.tsv` comes from `tools/make_index.py`).

## Scale

- 119,169 function symbols in `main`; 111,648 function bodies recognised by Ghidra's
  ELF loader.
- 13,735 network functions decompiled: 0 decompiler failures.
  - `nn::pia` 5,223 symbols, `nn::nex` 7,512, `enl` 757, `Cnet` 647,
    `Lp::Net` 849, `Cstm` 129 (symbol counts; aliases and zero-size entries are
    deduplicated in the decompiled set).
- ~709,000 lines of pseudocode.
- 255,044 relocations applied to the reconstructed ELF.

## Reproduce

Everything is inside Podman; no host Ghidra install is needed.

```bash
cd work/net

# 1. Rebuild an ELF from the NSO memory image (symbols + RELA applied)
python3 build_elf.py

# 2. Import once (project lives in /tmp/opencode/ghproj/sp2)
podman run --rm --entrypoint bash \
  -v "$PWD:/work" -v /tmp/opencode/ghproj:/tmp/ghproj \
  localhost/reva:12.1.3 -lc 'cd /work && python3 import_elf.py'

# 3. Batch decompile (all categories, ~2 minutes)
podman run --rm --entrypoint bash \
  -v "$PWD:/work" -v /tmp/opencode/ghproj:/tmp/ghproj \
  localhost/reva:12.1.3 -lc 'cd /work && python3 decompile_net.py all'

# 4. Demangle + annotate PLT calls
for f in decompiled/*.c; do case "$f" in *.dem.c|*.ann.c) continue;; esac; \
  c++filt < "$f" > "${f%.c}.dem.c"; done
python3 annotate_imports.py
```

`decompile_net.py` accepts a category list, e.g. `pia_lan lan` or `nex`, so a
single subsystem can be regenerated without touching the rest.

## Caveats

- These are **decompiler outputs, not source**. Function prototypes are inferred;
  C++ `this` pointers, return-by-value structs and `nn::Result` often appear as
  `param_1` pointers. Use the demangled signature in the comment above each body.
- A handful of jump tables are not recovered (`Could not recover jumptable`); the
  control flow is still visible as indirect calls.
- The ELF is reconstructed from the memory image. Its entry point, sections and
  symbols are correct for analysis; it is not a runnable executable.
- The LAN/NEX protocol facts below were cross-checked against the public
  NintendoClients wiki and, for online, against Nextendo's implementation. Items
  that come from those sources rather than from this binary are marked.

## The short version

**LAN mode is fully implemented in PIA and does not touch NEX.**

- Browse request/reply: raw UDP on **port 30000**, types 0/1.
- Session/host/keep-alive: Pia-encapsulated UDP on **49152–49155**, types 3–7.
- A second direct socket binds **40000**.
- LAN crypto uses the Splatoon 2 Pia game key
  `ee182a63e216cdb1f51ad4bed8cf6508` (public wiki) and a challenge/response exchange.
- Pia LAN is the natural first server target: no Nintendo account, no Kerberos,
  no NEX.

**Online mode is NEX + Pia inet.**

- Retail game-server host: `g2df33d00-dd1.s.n.srv.nintendo.net`
  (`0x2df33d00` game-server id, `dd1` environment).
- Access key: `f25e0f69` (retail), dev key `4eb18d39`.
- NEX auth/matchmaking is WebSocket/TLS ("PRUDP Lite") on Switch; Nextendo uses
  auth `:443` and a per-game secure port (`:60004` for Splatoon 2).
- Nextendo already implements PRUDP/RMC/Kerberos/matchmaking/ranking/NAT-check and
  a per-pair P2P relay. Its documented gap is the Splatoon 2 **DataStore** layer.

## If you pivot to Splatoon 3

Splatoon 3 (`0100c2500fc20000`) uses **NPLN**, not NEX: gRPC/protobuf services under
`nn.npln.*`, with Splatoon 3-specific `nn.npln.toyohr.v1.*` services. Nextendo's
public service already lists Splatoon 3 and reports players online, but the public
`nextendo-nex` repository is only the **NEX** core. The Splatoon 3/NPLN server code
is not in Nextendo's public org list.

So:

- **As a player**, “connect to Nextendo” works today for Splatoon 3: use their
  Ryujinx/Citron build or the Switch CFW profile. No server build required.
- **As a self-hosted server**, the control plane is a different project: an NPLN
  gRPC server, not `nextendo-nex`. Public protocol material exists
  (`kinnay/NPLN-Protocols`, NintendoClients NPLN pages); the Nextendo NPLN server
  itself is not public.
- **LAN first is still viable**: Splatoon 3 uses Pia 6.x LAN (browse on 35000,
  `LanNetworkProperty`), not the Splatoon 2 layout. The decompilation pipeline in
  this directory is reusable; the protocol layouts and `build_elf.py` need the
  Splatoon 3 NSO.

See `NEX_ONLINE.md` and `DEDICATED_SERVER_PLAN.md` for the NPLN-specific notes.
