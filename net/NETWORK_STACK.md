# Splatoon 2 network stack — map

All addresses are **original module virtual addresses** (image base 0). To get the
address in the reconstructed `main.elf`, add `0x100000`.

## Layers

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ Game modes / UI                                                              │
│   Match::VersusSeq, Match::CoopSeq, Lobby::Seq*, Game::...                   │
│   Lp::Net::DefaultMatchingSeq  (state machine: sleep → connect → login →      │
│   match → fix → share → scene)                                               │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────────┐
│ Cnet — Splatoon 2's network game layer                                       │
│   NetworkReadyExe, *MatchmakeExe, *SharingExe, SystemCloneObjMgr,            │
│   NexDataStoreMgr, NexCoralMgr, NexExtraServiceMgr, NexMaintenanceChecker,   │
│   OnlinePlayPenaltyMgr, ErrorCallback, Packet* (clone payloads)              │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────────┐
│ enl — Nintendo's "ENL" wrapper around PIA/NEX                                │
│   NinPiaFramework, PiaFramework, PiaInetMatchingManager,                     │
│   PiaLanMatchingManager, PiaLocalMatchingManager, NinPiaLanMatchingManager,  │
│   TransportManager, SendManager, P2PManager, PeerManager, TaskThread         │
│   NinLanMatchingManagerPlatformImpl  → nn::nifm / nn::socket                 │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────────┐
│ nn::pia — Nintendo's peer-to-peer library (statically linked)                │
│   common · session · transport · lan · local (LDN) · inet (NEX) · nat ·      │
│   clone · chat                                                              │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────────┐
│ nn::nex — Quazal/NEX client (statically linked)                              │
│   PRUDP · RMC · Kerberos/TicketGranting · SecureConnection · MatchMaking ·   │
│   MatchmakeExtension · NATTraversal · DataStore · Ranking · Utility · Coral  │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────────────┐
│ Platform imports (resolved by the Switch OS)                                 │
│   nn::socket (BSD sockets) · nn::nifm (network interface) · nn::ssl ·        │
│   nn::ldn (local wireless) · nn::os · nn::account                            │
└──────────────────────────────────────────────────────────────────────────────┘
```

The network stack is **inside `main`**, not in `sdk` or a system module. The symbol
table contains 5,223 `nn::pia` and 7,512 `nn::nex` entries, and the LAN/NEX code
is ordinary statically linked C++.

## Component counts (function symbols)

| Namespace | Functions | Role |
|---|---:|---|
| `nn::pia::lan` | 520 | LAN discovery/session (49152–49155, 30000) |
| `nn::pia::local` | 760 | LDN / local wireless |
| `nn::pia::inet` | 971 | NEX-backed P2P sessions |
| `nn::pia::session` | 882 | session/mesh/matchmake state machines |
| `nn::pia::transport` | 824 | reliable/unreliable/broadcast protocols |
| `nn::pia::nat` | 194 | NAT traversal |
| `nn::pia::common` | 392 | packets, sockets, crypto, HMAC, signatures |
| `nn::pia::clone` | 557 | state replication (clone protocol) |
| `nn::pia::chat` | 116 | voice chat |
| `nn::nex` | 7,512 | NEX client + protocols |
| `enl` | 757 | PIA/NEX wrapper used by the game |
| `Cnet` | 647 | Splatoon 2 game networking |
| `Lp::Net` | 849 | game matching sequence, clone objects, chat |
| `Cstm` | 129 | game-specific ENL configuration |

## Four network modes

`Cnet::NetworkReadyExe::stateCheckNetworkMode` (`0x17b31c`) reads a mode value at
`this+0x50` and selects one of four paths:

| Case | Test | Meaning |
|---:|---|---|
| 0 | `Lp::Utl::Matching::isInetMode()` | online / NEX |
| 1 | `isInetMode()` then `isLogIn()` | online already logged in |
| 2 | `isLocalMode()` / `isLocalInit()` | local wireless (LDN) |
| 3 | `isLanMode()` then `isLogIn()` | **LAN mode** |

`Cnet::NetworkReadyExe::stateChangeNetworkMode` (`0x17b518`) then calls
`Lp::Net::MatchingSeqBase::setMode` (`0x11ea7e4`) with mode 0 (inet), 1 (local),
or 2 (LAN). The game therefore handles LAN as a first-class matching mode, not a
hack.

## LAN call path

```
Cstm::EnlTask (game config)
  └─ Lp::Net::EnlTask::readyNetwork                  0x11e6930
       ├─ enl::NinPiaFramework::createInstance       0x132d830
       ├─ enl::NetworkConfig setup (heaps, timeouts, player count)
       └─ enl::NinPiaFramework::applyConfig_         0x132db4c
            └─ enl::PiaLanMatchingManager            0xc1b58c / initialize 0xc1b788
                 ├─ enl::PiaUtil::PrepareLan         0xc08b24
                 │    ├─ nn::pia::lan::Initialize     0xc7e39c
                 │    ├─ nn::pia::lan::BeginSetup
                 │    ├─ nn::pia::lan::LanFacade::CreateInstance  0xc7e998
                 │    └─ nn::pia::lan::EndSetup
                 ├─ enl::PiaUtil::BindLan             0xc08bf0
                 │    ├─ get local IP / subnet mask
                 │    └─ LanFacade::Bind               0xc7eb3c
                 │         └─ LanProtocol::Bind        0xc81c50
                 │              broadcast = ip | ~mask
                 └─ LanFacade::StartLanSession         0xc7eb7c
                      ├─ LanProtocol::BindRandomPort   0xc81de8
                      │    socket A: 49152..49155
                      │    socket B: 40000
                      └─ LanProtocol::Dispatch         0xc8151c
                           ├─ ReceiveMessages          0xc81854
                           ├─ SendSessionMessage       0xc8193c  (broadcast 49152..55)
                           └─ SendSelfKeepAliveMessage 0xc81b60  (broadcast 49152)
```

`enl::PiaUtil::BindLan` reads the local address from
`PiaLanMatchingManager::getLocalAddress()` and the mask from `getSubnetMask()`, and
passes a third field (`manager+0x20`) through. `LanProtocol::Bind` computes the
subnet broadcast address:

```c
*(u32 *)(proto + 0x2c) = local_ip;          // source address
*(u32 *)(proto + 0x30) = local_ip | ~mask;  // broadcast address
*(u32 *)(proto + 0x38) = gateway_or_zero;
```

The local addresses ultimately come from `nn::nifm` through
`enl::NinLanMatchingManagerPlatformImpl::networkInitialize` (`0x1332e88`), which
calls `nn::nifm::Initialize`, `SetLocalNetworkMode`, `SubmitNetworkRequestAndWait`,
`IsNetworkAvailable`, and `nn::socket::Initialize(heap, 0x600000, 0x20000, 0xe)`.

## Online (NEX) call path

```
Cnet::MatchmakeExeBase / VersusMatchmakeExe / CoopMatchmakeExe / ...
  └─ enl::PiaInetMatchingManager
       └─ nn::pia::inet  (NexMatchmakeSession, NexMatchMeshLayerController, …)
            └─ nn::nex
                 ├─ RendezVous::Login                    0xdd4040
                 │    └─ BackEndServices::LoginImpl      0xdc42d0
                 │         └─ JobBackEndServicesLogin
                 │              ├─ ConnectToAuthenticationService  0xdc9120
                 │              ├─ Authenticate                    0xdc9b1c
                 │              ├─ ConnectToSecureConnectionService 0xdc9dd4
                 │              └─ RegisterURLs / CompleteLogin
                 ├─ MatchMakingClient                     0x115b538
                 │    protocol 0x15 (MatchMaking)
                 │    protocol 0x32 (MatchMakingExt)
                 ├─ MatchmakeExtensionClient              (protocol 0x6D)
                 ├─ SecureConnectionProtocolClient       0xda3ccc
                 ├─ NATTraversalEngine                   0xd4ab0c
                 └─ PRUDPStream / RootTransport          0xd7150c / 0xd5524c
```

On Switch, NEX runs over **WebSocket + TLS** ("PRUDP Lite"), not raw UDP. The
decompiled `nn::nex::WebSocketClient` and `ClientWebSocketDriver` classes, and the
`WSClientHandShake` strings in `main`, match Nextendo's `TransportWebSocket`
profile. See `NEX_ONLINE.md`.

## Game configuration constants (from `Cstm::EnlTask::settingTaskConfig`, `0x19a4a4`)

`settingTaskConfig(Lp::Net::EnlTaskConfig *)` writes the retail NEX parameters:

| Field | Retail | Dev (`Cmn::Def::getRomType()==4`) |
|---|---|---|
| Game-server id (`param[4]`) | `0x2df33d01` | `0x24e30d00` |
| Access key (`param[8]`, string) | **`f25e0f69`** | `4eb18d39` |
| `param[2]` | `0x01003c700009c000` | same |
| `param[0x24]` | `0x0000000a00000002` | same |
| `param[0x28]` | `3` | same |

The hard-coded retail URL string is:

```
https://g2df33d00-dd1.s.n.srv.nintendo.net/
```

so the game-server id is `0x2df33d00`, and `0x2df33d01` in the config is the same
id with a low-byte environment/type marker. `settingDebugServerInfo` (`0x19bd60`)
overrides the username (`user%06d`), password (`password`) and a debug server name
(`59a7cc00`) when the debug path is enabled.

## Where the decompiled code lives

| Category | File | Start of range |
|---|---|---:|
| PIA LAN | `decompiled/pia_lan.ann.c` | `0xc7e39c` |
| PIA local/LDN | `decompiled/pia_local.ann.c` | `0xc088a4` |
| PIA inet | `decompiled/pia_inet.ann.c` | `0xc42a14` |
| PIA session | `decompiled/pia_session.ann.c` | |
| PIA transport | `decompiled/pia_transport.ann.c` | `0xc4a354` |
| PIA NAT | `decompiled/pia_nat.ann.c` | `0xc76248` |
| PIA common | `decompiled/pia_common.ann.c` | |
| PIA clone | `decompiled/pia_clone.ann.c` | |
| ENL | `decompiled/enl.ann.c` | `0x17ac58` |
| Cnet | `decompiled/cnet.ann.c` | `0x16b668` |
| Lp::Net | `decompiled/lpnet.ann.c` | `0x11dee5c` |
| NEX | `decompiled/nex.ann.c` | `0xd0cae4` |

`network_symbols.tsv` is the searchable index: category, original address, size,
demangled name, mangled name.
