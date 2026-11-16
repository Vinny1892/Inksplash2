# NEX online — auth, matchmaking, endpoints, and the Nextendo fit

Splatoon 2's online mode is **NEX + Pia inet**:

- NEX provides login, matchmaking, rankings, DataStore and notifications.
- Pia provides the peer-to-peer mesh and NAT traversal once a session exists.
- The game server never carries gameplay traffic; it only introduces peers.

## Transport on Switch

Switch NEX is **PRUDP "Lite" over WebSocket + TLS**, not raw UDP. Evidence in the
retail module:

- `nn::nex::WebSocketClient` and `nn::nex::ClientWebSocketDriver` classes;
- `WSClientHandShake` strings and `prudp:/`, `prudps:/`, `ws://`, `wss://`;
- `nn::nex::BerkeleySocketDriver` exists for fallback/UDP paths, but the Switch
  profile uses the WebSocket transport.

Nextendo's `Settings` describes the same profile:

```go
NexVersion: 40000
StructHeader: true
PIDSize: 8
PrudpVersion: 2       // "Lite"
Transport: TransportWebSocket
Compression: CompressionNone
Encryption: EncryptionNone   // TLS/WSS provides confidentiality
KerberosKeyDerivation: KeyDerivationNew
```

The auth server is reached on `:443`; the secure server port is chosen by the
server and returned in `RVConnectionData`. Nextendo's example deployment uses
`60004` for Splatoon 2.

## Retail endpoints and constants (from `main`)

| Item | Value | Source |
|---|---|---|
| Retail game-server host | `g2df33d00-dd1.s.n.srv.nintendo.net` | string at `0x2891e10` |
| Game-server id in config | `0x2df33d01` | `Cstm::EnlTask::settingTaskConfig` (`0x19a4a4`) |
| Retail access key | **`f25e0f69`** | string `0x280153d` |
| Dev access key | `4eb18d39` | string `0x2801546` |
| Dev game-server id | `0x24e30d00` | `settingTaskConfig` (`RomType==4`) |
| Debug server name | `59a7cc00` | `settingDebugServerInfo` (`0x19bd60`) |
| Debug user format | `user%06d` / `usr%06d` | strings `0x280154f`, `0x2891e3c` |
| Debug password | `password` | string `0x2801588` |
| NAT-check hosts | `nncs1-%.n.n.srv.nintendo.net`, `nncs2-%.n.n.srv.nintendo.net` | `RootTransport::SetUpDefaultNATCheckServerInternal` (`0xd56218`) |
| NAT-check ports | `0x2729` = 10025, `0x278d` = 10125 | same |
| SplatNet host | `app.splatoon2.nintendo.net` | string `0x27f8ffe` |
| Pia game key | `ee182a63e216cdb1f51ad4bed8cf6508` | public NintendoClients wiki |

`settingTaskConfig` also writes the retail `EnlTaskConfig` values:

```c
param[2]  = 0x01003c700009c000;   // two u32: 0x0009c000, 0x01003c70
param[4]  = 0x2df33d01;           // game-server id / environment
param[8]  = "f25e0f69";           // access key
param[0x24] = 0x0000000a00000002; // 2, 10
param[0x28] = 3;
```

The exact meaning of `param[2]`/`param[0x24]` is PIA/NEX sizing, not a port. The
secure port is server-chosen and returned during auth.

## NEX protocol ids

Confirmed by the decompiled constructors and by Nextendo's constants:

| Id | Protocol | Decompiled client |
|---:|---|---|
| 0x03 | NAT Traversal | `NATTraversalProtocolClient` (`0x1173fc8`) |
| 0x0A | Ticket Granting / Authentication | `TicketGrantingProtocolClient` (`0xda8558`) |
| 0x0B | Secure Connection | `SecureConnectionProtocolClient` (`0xda3ccc`) |
| 0x0E | Notification | `NotificationProtocolClient` (`0xd9f258`) |
| 0x15 | Match Making | `MatchMakingProtocolClient` (`0x11656dc`) |
| 0x32 | Match Making Ext | registered by `MatchMakingClient` (`0x115b538`) |
| 0x64 | Nintendo Notification | `NintendoNotificationEventProtocolClient` (`0xd9afd4`) |
| 0x6D | Matchmake Extension | `MatchmakeExtensionProtocolClient` (`0x11490d4`) |
| 0x6E | Utility | `UtilityProtocolClient` (`0x11d4da4`) |
| 0x70 | Ranking (Splatoon 2 = 112) | `RankingProtocolClient` (`0x11cb198`) |
| 0x73 | DataStore (115) | `DataStoreProtocolClient` (`0x11a89d0`) |

`MatchMakingClient::MatchMakingClient` explicitly registers `0x15` and `0x32`;
`AuthenticationClient` registers `0x0A`; `BackEndServices` registers `0x0E` and
`0x64`.

## Login flow

```
RendezVous::Login(ctx, host, user, pass, port, ...)        0xdd4040
  └─ BackEndServices::LoginImpl                            0xdc42d0
       └─ JobBackEndServicesLogin
            ├─ ConnectToAuthenticationService              0xdc9120
            │    station URL: prudps:/address=<host>;port=<port>;...
            │    WebSocket/TLS handshake, PRUDP CONNECT
            ├─ Authenticate                                0xdc9b1c
            │    TicketGranting LoginEx / Kerberos ticket
            ├─ ConnectToSecureConnectionService            0xdc9dd4
            │    RVConnectionData gives the secure station URL
            ├─ RegisterURLs                                0xdca9a8
            └─ CompleteLogin                               0xdca3ac
```

The secure server then handles `SecureConnection` (`0x0B`) and the game protocols.
Splatoon 2 uses the **Legacy Pia config** (`type=0x03`, no `Pa` attribute), as
Nextendo documents in `secureconnection.go`. This matters for NAT traversal: the
game builds its probes from the legacy fields.

## What Splatoon 2 asks the server to do

Nextendo's `nextendo-nex` already implements the hard parts:

- PRUDP v2 Lite over WebSocket, RMC, fragmentation, acks.
- Kerberos-style ticket granting and secure connection.
- Matchmaking (0x15, 0x32, 0x6D) with Splatoon 2-specific behaviour:
  - `ModifyCurrentGameAttribute` (host updates attributes),
  - `UpdateMatchmakeSessionPart` (Salmon Run end-of-session),
  - 8-player normal / 10-player private / Salmon Run sizing,
  - host migration, participation notifications, session URLs,
  - Splatfest team merging.
- Ranking (0x70), Utility (0x6E), Notification (0x0E), Nintendo Notification (0x64).
- NAT traversal (0x03), NAT-check responder (`nextendo-nncs`), and per-pair P2P
  relay (`relaypair.go`).
- Switch `Settings` profile and `LegacyPiaConfig`.

The documented gap is **DataStore (0x73)** for Splatoon 2. Nextendo ships an SMM2
DataStore (`datastore_smm2.go`), not a Splatoon 2 one. The retail game's
`Cnet::NexDataStoreMgr` (`0x...`, see `network_symbols.tsv`) and the public
Splatoon 2 DataStore page list the methods:

| Method | Name | Needed for |
|---:|---|---|
| 47 | `CoconutRegisterMeta` | user posts / replays |
| 48 | `CoconutRatePost` | post ratings |
| 49 | `CoconutGetObjectInfos` | post feed |
| 50 | `CoconutReportViolation` | report post |
| 51 | `UploadRegularMatchResult` | Turf War results |
| 52 | `UploadGachiMatchResult` | Ranked results |
| 53 | `UploadLeagueMatchResult` | League results |
| 54 | `UploadFesMatchResult` | Splatfest results |
| 55 | `GetOrderedGear` | gear shop |
| 56 | `PurchaseGear` | gear shop |
| 57 | `UploadTimeAttack` | single-player time attack |
| 58 | `CoconutRegisterMetaByParam` | posts |
| 59 | `UploadFesMatchResultV2` | Splatfest |
| 60–65 | `UploadXMatchResult`, V2 variants | Ranked X / fest |
| 66 | `PreparePostPlayLog` | replay upload |
| 67 | `PrepareGetPlayLog` | replay download |
| 68 | `UploadFesMatchResultV4` | Splatfest |
| 69 | `UploadCoopResult` | **Salmon Run** |

For “all modes work”, at minimum implement 51–54, 68 and 69 (result uploads), plus
55/56 (gear) and 47–50/58 (Coconut) if the lobby/social features are in scope.
The request/response structures are public on the NintendoClients wiki. A
no-op success for uploads is usually enough to get past the result screen; a
`GetOrderedGear` that returns an empty or plausible `OrderedInfo` avoids shop
stalls.

Ranking (0x70) methods 16–26 are also Splatoon 2-specific (League, Festival,
X Power). Nextendo's `ranking.go`/`ranking2.go` provide the framework; the
Splatoon 2 method bodies need to be added or stubbed.

## DNS / TLS / deployment

A real console (or emulator) must resolve the retail hostnames to your server:

```
g2df33d00-dd1.s.n.srv.nintendo.net   -> your secure/auth IP
nncs1-<...>.n.n.srv.nintendo.net     -> NAT_IP (one vantage point)
nncs2-<...>.n.n.srv.nintendo.net     -> NAT_IP (second vantage point)
app.splatoon2.nintendo.net           -> optional SplatNet
```

Nextendo uses:

- `sni-router` on `:443` to route auth TLS by SNI;
- a per-game secure port (`:60004` for Splatoon 2);
- `nextendo-account` for `nx2.` tokens;
- `nx-dauth` for device/application auth;
- `nextendo-nncs` on two distinct addresses for the NAT check;
- a CA installed in the client trust store (or the emulator's cert layer).

The secure station URL returned by auth is what tells the client where to connect,
so the port is configurable without patching the game.

## Using Nextendo public as an option

Nextendo runs a public service at <https://nextendo.network> with an account,
friends, presence and matchmaking, and lists Splatoon 2 among its supported games.
For a player this is the lowest-effort way to “connect to Nextendo”:

1. create a Nextendo account;
2. use the Nextendo Ryujinx/Citron build, or enable the Nextendo profile on a
   Switch with CFW;
3. sign in and launch Splatoon 2 online.

That path does **not** use this decompilation or a self-hosted server. It is a
client-side DNS/account/cert profile. If you want a server-side option in your own
project, expose it as a documented **backend choice**, not as a proxy:

- `lan` — LAN mode only (this decompilation's LAN protocol).
- `self` — your own Nextendo-stack server (the rest of this document).
- `nextendo` — instruct the user to use Nextendo's client profile; do not try to
  relay their TLS/auth traffic.

There is no public federation/registration API for a third-party server to join
Nextendo's matchmaking as a node. Their per-game servers are client-facing
endpoints. If you want to operate a game server inside their network, ask the
Nextendo maintainers; do not assume it is supported.

## Splatoon 3 is NPLN, not NEX

If you pivot the project to Splatoon 3, the control plane changes completely:

- Splatoon 3 title id: `0100c2500fc20000`.
- Matchmaking/auth/friends/leaderboards/datastore use **NPLN**: gRPC over HTTP/2 +
  protobuf, not PRUDP/RMC.
- NPLN tenant / server id: `dce9377b` (from the NintendoClients NPLN page).
- Splatoon 3-specific services: `nn.npln.toyohr.v1.Canola`, `CloudSave`,
  `CoopScenario`, `FestService`, `GameRecord`, `LobbyMessaging`, `Locker`,
  `Replay`, `Schedule`, `UserScreening`.
- P2P is still Pia (6.x), so LAN/NAT/relay work is still relevant, but the packet
  versions and LAN layout differ from Splatoon 2.

Nextendo's status API currently reports Splatoon 3 as a live game:

```json
{"0100c2500fc20000": 51}
```

and its website lists Splatoon 3. So **connecting to Nextendo as a player works
today** for Splatoon 3. What is not public is the server implementation:

- `nextendo-nex` is the **NEX/PRUDP** core. It cannot serve NPLN.
- Nextendo's org repo list has no public NPLN/Splatoon 3 server. Their deployed
  Splatoon 3 backend exists, but it is not a library you can self-host.
- There is no documented federation API for a third-party server to join
  Nextendo's matchmaking as a node.

To self-host Splatoon 3 you need an **NPLN server**:

1. Implement the gRPC services from `kinnay/NPLN-Protocols` (`nn.npln.auth.v1`,
   `nn.npln.matchmaking.v1`, friends, messaging, hydro, leaderboard, plus the
   `toyohr` services).
2. Terminate TLS for the NPLN host (`<tenant>.lp1.t.npln.srv.nintendo.net`) and
   issue the client an NPLN access token / uid (the client uses metadata
   `npln-tenant-id`, `authorization: bearer …`, `uid: u-…`).
3. Implement the Splatoon 3 service methods the client calls. Public protobuf
   definitions exist; the game-specific semantics still need reverse engineering
   (this is where a Splatoon 3 decompilation would help).
4. Keep Pia 6.x for the actual match; reuse the relay/NAT ideas.

If Nextendo publishes their NPLN server later, the same “backend choice” model
applies: `nextendo` (their public service), `self` (your NPLN), `lan` (Pia LAN).
Until then, the realistic options are Nextendo public or a from-scratch NPLN
server.

## Using Nextendo with this decompilation

1. Clone `NextendoNetwork/nextendo-nex` and use `NewSwitchSettings("f25e0f69", 40000)`.
2. Register the protocols above on an insecure auth endpoint and a secure endpoint.
3. Use `AuthConfig` with the secure station URL, secure PID/password, and a
   `ResolveUser` that validates the `nx2.` token from `nextendo-account`.
4. Implement the Splatoon 2 DataStore and Ranking method bodies using the public
   structures and the decompiled `Cnet::NexDataStoreMgr` / `NexExtraServiceMgr`
   call sites as a checklist.
5. Run `nextendo-nncs` and the pair relay; set `LegacyPiaConfig`.
6. Point DNS at the server and test with a real console or emulator.

The decompilation is useful here for **what the client actually calls and in what
order**: `Cnet::NetworkReadyExe` states, `NexDataStoreMgr` jobs, `NexExtraServiceMgr`,
`NexMaintenanceChecker`, `NexCoralMgr`, and the matchmake state machine. When a
Nextendo handler is missing, the decompiled call site tells you the expected
request shape and timing.

## Licensing and deployment note

`nextendo-nex` is source-available under the **PolyForm Shield 1.0.0** license:
you may read, use, modify and self-host it, but not use it to provide a product
that competes with Nextendo Network. Check the license before shipping a public
service. The protocol documentation and this decompilation are separate; the
server code you write around Nextendo is yours.

The secure port (`60004`) and the `nextendo-*` service names are Nextendo's
example deployment, not values extracted from the game. The client learns the
secure address from `RVConnectionData`, so any port works.
