# Sources and prior art

## This decompilation

- Retail Splatoon 2 `main` NSO (`work/base-nsp/exefs/main`, dumped memory image
  `work/img/main.bin`).
- The module's own dynamic symbol table (146,622 entries) and RELA relocations.
- Ghidra 12.1.3 via PyGhidra in the local `localhost/reva:12.1.3` Podman image.
- `decompiled/*.ann.c` — 13,735 network functions, demangled and annotated.

## Public protocol documentation

These were used to cross-check the decompiled layouts. Where a fact comes from
these pages rather than the binary, it is marked in the docs.

- NintendoClients wiki — Pia Protocol:
  <https://github.com/kinnay/NintendoClients/wiki/Pia-Protocol>
- NintendoClients wiki — LAN Protocol:
  <https://github.com/kinnay/NintendoClients/wiki/LAN-Protocol>
- NintendoClients wiki — Pia Types:
  <https://github.com/kinnay/NintendoClients/wiki/Pia-Types>
- NintendoClients wiki — Pia Game Keys:
  <https://github.com/kinnay/NintendoClients/wiki/Pia-Game-Keys>
- NintendoClients wiki — NEX Overview (Game Servers):
  <https://github.com/kinnay/NintendoClients/wiki/NEX-Overview-(Game-Servers)>
- NintendoClients wiki — PRUDP Protocol:
  <https://github.com/kinnay/NintendoClients/wiki/PRUDP-Protocol>
- NintendoClients wiki — Data Store Protocol (Splatoon 2):
  <https://github.com/kinnay/NintendoClients/wiki/Data-Store-Protocol-(Splatoon-2)>
- NintendoClients wiki — Ranking Protocol (Splatoon 2):
  <https://github.com/kinnay/NintendoClients/wiki/Ranking-Protocol-(Splatoon-2)>

## Prior art / reusable implementations

- **Nextendo Network** — from-scratch NEX/PRUDP server core, Kerberos, matchmaking,
  ranking, NAT traversal, NAT-check responder, per-pair P2P relay:
  <https://github.com/NextendoNetwork>
  - `nextendo-nex`: <https://github.com/NextendoNetwork/nextendo-nex>
  - `nextendo-nncs`: <https://github.com/NextendoNetwork/nextendo-nncs>
  - `nextendo-docs`: architecture/deployment.
  - License: PolyForm Shield 1.0.0 (source-available; self-hosting allowed, do not
    use it to provide a competing product).
- **switch-lan-play** — Ethernet/IPv4 LAN relay for Switch LAN mode:
  <https://github.com/spacemeowx2/switch-lan-play>
- **NintendoClients** — protocol documentation and tooling:
  <https://github.com/kinnay/NintendoClients>
- **revng** — binary analysis/decompilation framework (not needed for this run,
  but a useful second opinion if you want an independent decompiler):
  <https://github.com/revng/revng>
- **REA** — Ghidra-based reverse-engineering MCP used by the Podman image:
  <https://github.com/morluto/rea>

## Note on the game version

The dump is the retail `main` for title id `01003bc0000a0000` (Splatoon 2), with
the `NintendoSDK-NEX-for_NX-4_1_1` strings. The LAN behaviour (browse on 30000,
session on 49152–49155, broadcast keep-alive) matches the Pia 5.27-era tables.
