# Inksplash2

Splatoon 2 running natively on Linux on top of the
[totk-recomp](https://github.com/Muhammad1259-sigma/totk-recomp) static-recompilation runtime
(the *Tears of the Kingdom* Linux / Steam Deck port). The target is the Steam Deck at
1280×720 and 60 fps.

The game's `main` module is lifted from AArch64 to C with the runtime's generator. The `sdk`
and `nv`/`nvn` modules are replaced by HLE, and NVN is rendered through the runtime's
NVN-on-Vulkan backend.

> **No game code, game data or keys are in this repository.** You need your own legally
> dumped Splatoon 2 (base NSP: ExeFS + RomFS) and console keys. Lifted C (`gen/`), extracted
> RomFS, NSO images and anything derived from the binary all stay outside git (see
> `.gitignore`).

## Status

- `main` lifts with **0 unhandled instructions** (114,172 functions).
- Boots through the 2D title/UI (720p60 on both the null and Vulkan backends), then the
  3D title scene, **PlayerMake** (the character creator), and on into the **tutorial 3D room**
  (Vulkan).
- Known issues: the 3D scenes render at ~34 fps instead of 60 (renderer-bound, not game
  logic), shadows render pure black, and some yes/no button labels are missing.
- PC input mapping (mouse aim, WASD, space/shift/F/LMB), SDL gamepad support, and a scripted
  input harness for headless runs.

The current state and the next steps are in [`notes/HANDOFF.md`](notes/HANDOFF.md).

## Layout

| Path | What |
|---|---|
| `baseline/totk-recomp/` | Vendored runtime, recompiler (`tools/recomp/gen.py`), launcher and build scripts. Upstream `a32f709`, plus the Splatoon 2 runtime and generator changes |
| `notes/` | Port plan, handoff, boot / UI-blocker / platform-layer investigation notes |
| `tools/input_sequencer.py`, `tools/scenarios/` | Host-side pad driver (`TOTK_PAD_FILE`) and input scripts |
| `tools/nso/`, `tools/static/` | NSO → ELF, NSO0 dynsym recovery, module import map (Node.js) |
| `net/` | Network stack research: Pia LAN protocol, Pia transport, NEX online, dedicated-server plan, plus Ghidra and LAN-dissector scripts |

## Building and running

Everything builds in Podman. The full commands, environment variables (`TOTK_LIFT_ALL`,
`TOTK_ROMFS`, `TOTK_IMG`, `TOTK_HEADLESS`, `TOTK_PAD_FILE`, …) and the expected
work-tree layout are in [`notes/HANDOFF.md`](notes/HANDOFF.md), under **Build** and **Run**.
In outline:

1. Extract ExeFS/RomFS from your dump and build the NSO images with `baseline/totk-recomp/tools/nso.py`.
2. Lift `main` with `baseline/totk-recomp/tools/recomp/gen.py`.
3. `tools/recomp/mkninja_linux.py` (`--null` for headless) → `ninja`.
4. Run `./totk` with the `TOTK_*` environment pointing at your RomFS and images.

## Credits and license

- **[sp2decomp](https://github.com/bangmcpe3321/sp2decomp)** by bangmcpe3321 (MIT): the
  Splatoon 2 reverse-engineering notes and NSO tooling this project started from. The
  `tools/nso` and `tools/static` scripts come from it and keep their history here.
- **[totk-recomp](https://github.com/Muhammad1259-sigma/totk-recomp)** by the totk-recomp
  contributors (MIT): the runtime vendored under `baseline/totk-recomp/`, with its own
  `LICENSE` and third-party notices.

This project is MIT-licensed. See [`LICENSE`](LICENSE).
Splatoon is a trademark of Nintendo. This project is not affiliated with or endorsed by Nintendo.
