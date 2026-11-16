# Dedicated server roadmap

## First: decide what “dedicated server” means

There are two different products behind that phrase:

1. **Dedicated service server** — replaces Nintendo's matchmaking/relay. It does
   not simulate Splatoon 2. Players still host the match on their own console
   (as Nintendo's P2P design intends). This is enough for **quickplay, ranked,
   league, Splatfest and Salmon Run**, because all of them use the same
   NEX-matchmaking + Pia-mesh pattern.
2. **Authoritative game server** — runs the simulation itself and clients connect
   to it. This requires the game engine (or a reimplementation), not just the
   network stack. It is a much larger project and is not required to restore
   online play.

The roadmap below delivers (1) first, with LAN as the stepping stone, and leaves
(2) as an optional final phase.

## Backend options: self-hosted, Nextendo public, or LAN-only

Nextendo Network is a **public, free replacement service** for Switch online play,
including Splatoon 2 and Splatoon 3. It is not a federation you join from a
third-party server; it is a client-facing service. That gives three deployment
shapes:

| Shape | Who runs the backend | Client setup | Best for |
|---|---|---|---|
| **LAN only** | nobody | LAN mode; no DNS/account | offline events, protocol work, stepping stone |
| **Nextendo public** | Nextendo | their Ryujinx/Citron build, or a Switch CFW profile | playing online now, with no server maintenance |
| **Self-hosted** | you | your DNS + CA + account | full control, custom rules, research |
| **Hybrid** | you for LAN, Nextendo for online | switch profile/DNS per mode | LAN server plus public online fallback |

For **Splatoon 3** the split is sharper:

- Nextendo public works today (`0100c2500fc20000` is live in their status API).
- Splatoon 3's control plane is **NPLN** (gRPC/protobuf), not NEX. Nextendo's
  public `nextendo-nex` repo is the NEX core; their Splatoon 3/NPLN server is not
  in the public org list.
- Self-hosting Splatoon 3 therefore means writing an NPLN server
  (`kinnay/NPLN-Protocols` + Splatoon 3 `nn.npln.toyohr.v1.*` services), not
  reusing `nextendo-nex`.
- LAN remains Pia 6.x; the LAN/relay work is still valid.

There is **no documented server-to-server federation API** in Nextendo's public
repos: a game server is a client-facing auth/secure endpoint, and the account
service issues `nx2.` tokens to clients. So "our server connects to Nextendo" is
not a supported topology. What is supported is:

1. **Use Nextendo as the online backend for players** — point the console/emulator
   at Nextendo using their profile. This is a client-side choice, not something
   our server can transparently proxy without their account/TLS stack.
2. **Self-host the Nextendo stack (Splatoon 2)** — run `nextendo-account`,
   `nx-dauth`, `nextendo-nex` and a Splatoon 2 game server yourself. This is "your
   own Nextendo network", not "Nextendo's network".
3. **Self-host an NPLN stack (Splatoon 3)** — a separate codebase. It can follow
   the public NPLN protocol docs, but it is not `nextendo-nex`.
4. **Hybrid UX** — our server can expose a mode switch: `lan` (local only),
   `self` (our backend), `nextendo` (documentation/profile that points clients at
   Nextendo's public service). The `nextendo` mode is a deployment/documentation
   path, not a proxy.

If the goal is "let players use Nextendo when they want, and our LAN/dedicated
server when they don't", the clean design is a **client-side profile switch** plus
clear docs, not a transparent relay. Trying to proxy Nextendo's TLS/auth traffic
would require their CA/account model and would likely violate their terms.

Nextendo's code is source-available under PolyForm Shield 1.0.0: self-hosting is
allowed; running a competing public service is not. The public service's uptime,
rules and account policy are theirs.

## Phase 0 — capture and baseline (days)

Goal: see the real traffic and confirm the decompiled constants.

- Put a PC on the same LAN as two Switches, run `switch-lan-play` or a mirrored
  switch port, and capture UDP 30000, 49152–49155 and 40000.
- Run `tools/lan_dissect.py --udp` on the capture host. It decodes browse
  requests/replies, session fragments, host messages and the Pia framing.
- Confirm: browse on 30000, session/host/keepalive on 49152–49155, second socket
  40000, session key param in `LanSessionInfo`.
- This also gives a golden trace to test a synthetic host against.

Deliverable: `captures/lan-*.pcap` + decoded logs.

## Phase 1 — LAN play over the internet (weeks)

The fastest path to “LAN works with friends” is not a new protocol: it is a
virtual LAN.

### Option A — reuse `switch-lan-play`

`spacemeowx2/switch-lan-play` already relays Ethernet/IPv4 between a PC helper and
a server (default UDP 11451). The Switch gets a static IP in `10.13.x.x/16`, the
PC bridges ARP/IPv4 to the server, and the server forwards frames between rooms.
This is proven and gets LAN mode working immediately.

Use it to validate:
- all LAN modes (Turf War, Ranked, League, Private, Salmon Run),
- the number of players and NAT behavior,
- whether your target modes are available in LAN mode at all (they should be;
  the game's `MatchingSeqBase` treats LAN as a first-class mode).

### Option B — native Pia LAN relay / host

A native server can speak the protocol from `LAN_PROTOCOL.md`:

1. **Discovery responder**: listen on UDP 30000, parse type 0, answer type 1 with a
   synthetic `LanSessionInfo`, including the crypto challenge response.
2. **Broker**: listen on 49152–49155 and hand out a real player-host's
   `StationLocation` (type 4) so clients join a real console's mesh.
3. **Relay**: assign a per-pair UDP port and forward everything between the pair
   (the Nextendo `relaypair.go` design). This avoids parsing Pia probes.
4. **Optional authoritative host**: speak Pia station/session/clone and run the
   game. Only do this once (2) is solved.

The discovery responder requires the challenge/response implementation
(`LAN_PROTOCOL.md`). The relay does not.

### Phase 1 acceptance

- Two consoles on different networks see each other in the LAN room list.
- A full 4v4 Turf War and a Salmon Run run complete.
- No NEX/account is involved.
- Packet loss/latency comparable to `switch-lan-play`.

## Phase 2 — online service (weeks to months)

Use `NextendoNetwork/nextendo-nex` as the NEX core. It already has PRUDP Lite,
RMC, Kerberos, matchmaking, ranking, notifications, NAT traversal, NAT-check and
the pair relay.

### Components

```
                DNS / TLS
 clients ─────────────────► sni-router :443 ──► splatoon-2 auth :443
    │                                              │
    │                                              ▼
    │                                        nextendo-account
    │                                         (nx2. tokens)
    │
    ├──────────► splatoon-2 secure :60004 ──► matchmaking / ranking /
    │              (PRUDP Lite over WSS)        utility / datastore
    │
    ├──────────► nextendo-nncs (two IPs)  ──► NAT check (10025/10125)
    │
    └──────────► Pia mesh / pair relay ─────► gameplay (P2P)
```

### Configuration

- `Settings = NewSwitchSettings("f25e0f69", 40000)`.
- Auth endpoint: insecure, `AuthConfig` with the secure station URL and account
  token resolver.
- Secure endpoint: `Secure=true`, `SetSecureAccount(password, pid)`, register
  `0x0B`, `0x15`, `0x32`, `0x6D`, `0x6E`, `0x70`, `0x73`, `0x03`, `0x0E`, `0x64`.
- `LegacyPiaConfig` (`type=0x03`, no `Pa`) for Splatoon 2.
- DNS: `g2df33d00-dd1.s.n.srv.nintendo.net`, `nncs1/2-…`.
- Secure port `60004` (or any port returned by auth).
- `nextendo-nncs` on two distinct public addresses.
- Pair relay enabled on a UDP port range.

### Phase 2 acceptance

- Login, lobby, friends/presence, quickplay and private rooms.
- A complete Turf War and Ranked match with Pia mesh established through the
  relay/NAT traversal.
- Result uploads do not stall the client.

## Phase 3 — all modes

The remaining work is game-service coverage, not transport:

| Feature | Work |
|---|---|
| Quickplay / Turf War | matchmaking already in Nextendo |
| Ranked (Gachi) | matchmaking attributes + `UploadGachiMatchResult` (DataStore 52) |
| League | `UploadLeagueMatchResult` (53), Ranking 16/17 |
| Splatfest | `UploadFesMatchResult` (54/59/64/68), Ranking 18–21 |
| X Rank | `UploadXMatchResult` (60/65), Ranking 22/23 |
| Salmon Run | matchmaking coop + `UploadCoopResult` (69), `UpdateMatchmakeSessionPart` |
| Gear shop | DataStore 55/56 |
| Posts / replays | DataStore 47–50, 58, 66/67 |
| SplatNet | optional REST API, not required for gameplay |

Nextendo's comments show it already handles the Splatoon 2-specific matchmaking
quirks (host attribute updates, Salmon Run end transition, team merging). The
DataStore is the documented stub; implement it with the public structures and use
`Cnet::NexDataStoreMgr` / `NexExtraServiceMgr` decompiled call sites as the
checklist for when each method is called.

## Phase 4 — authoritative game server (optional, very large)

A true dedicated server needs the simulation:

- **Option A — headless recompiled game.** The repo already has a static
  recompilation route (`Splat2-ReTotK`, `work/totk-linux`). Boot the recompiled
  game headless, force LAN mode, and let it act as the Pia host. This still needs
  the renderer/audio/input to be stubbed and a headless game loop.
- **Option B — clean-room simulation.** Reimplement Splatoon 2's movement,
  weapons, maps, physics and game rules. This is a fan-project-scale engine, not a
  networking task.

Until one of these exists, “dedicated server” should mean the service server in
Phase 2/3.

## Test matrix

| Test | Expected |
|---|---|
| LAN, same switch, 2 consoles | room visible, join, match |
| LAN over VPN (WireGuard/ZeroTier) | same |
| LAN over `switch-lan-play` | same, higher RTT |
| Online auth with a fresh account | `nx2.` token accepted |
| Quickplay 8 players | match starts, results upload |
| Ranked 8 players | same, rank updates |
| Salmon Run 4 players | waves start, `UploadCoopResult` |
| Host disconnects | migration or clean error |
| NAT-restricted peer | relay pair used |
| Packet loss 5% | match continues |

## Risks and constraints

- **Legal / ToS.** Reverse engineering for interoperability and self-hosting is
  one thing; distributing Nintendo code, keys, or assets is another. Keep the
  server clean-room and require users to dump their own game.
- **TLS trust.** A real console needs a CA in its trust store (CFW) or an
  emulator with a cert layer. This is the main deployment friction.
- **Account tokens.** Nextendo's `nx2.` token model depends on its account/DAuth
  stack; a real console's Nintendo Account token cannot be used against a private
  server without redirecting the account services too.
- **Pia is proprietary and versioned.** The LAN layout is stable for Splatoon 2,
  but online Pia has more state (mesh, clone, NAT) and the relay must be tested
  against real traffic.
- **No game simulation.** The service server cannot replace a player host. If the
  goal is “server runs the match with no player host”, Phase 4 is mandatory.

## Recommended order

1. Capture LAN traffic; decode with `tools/lan_dissect.py`.
2. Get LAN working over the internet with `switch-lan-play` (fastest win).
3. Stand up Nextendo with Splatoon 2 settings; get login + quickplay.
4. Add Splatoon 2 DataStore/Ranking; test ranked, league, fest, Salmon Run.
5. Only then consider a native Pia LAN host or a headless recompiled game server.
