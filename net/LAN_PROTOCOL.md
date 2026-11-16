# Pia LAN protocol — as implemented by Splatoon 2

Sources: decompiled `nn::pia::lan` in `decompiled/pia_lan.ann.c`, cross-checked with
the public NintendoClients **LAN Protocol** and **Pia Protocol** pages.

The retail module's behaviour matches the wiki's **Pia 5.x** tables. In particular
the LAN keep-alive is still broadcast (Pia 5.28+ sends it to localhost), so this is
the 5.27-era LAN implementation.

## Ports and encapsulation

| Traffic | Transport | Port |
|---|---|---|
| Browse request (type 0) | raw UDP, **not** in a Pia packet | **30000** |
| Browse reply (type 1) | raw UDP, **not** in a Pia packet | unicast to requester |
| Host / session / keep-alive (3–7) | Pia packet + Pia message | **49152–49155** (0xC000–0xC003) |
| Second/direct socket | raw UDP | **40000** |

Decompiled evidence:

- `LanMatchmakeUpdateJob::SendBrowseMessage` (`0xc8c3fc`) builds
  `[type=0][u32 size][criteria][challenge]` and calls `Socket::SendTo` with
  `InetAddress(broadcast_address, 30000)`.
- `LanMatchmakeUpdateJob::SendBrowseReplyMessage` (`0xc8c540`) builds
  `[type=1][u32 size][LanSessionInfo][challenge reply]` and sends it **three times**
  to the requester.
- `LanProtocol::Dispatch` (`0xc8151c`) calls `SendSessionMessage` for
  `broadcast:49152`, `:49153`, `:49154`, `:49155`; `SendSelfKeepAliveMessage`
  (`0xc81b60`) sends to `broadcast:49152`.
- `LanProtocol::BindRandomPort` (`0xc81de8`) binds a socket in
  `49152..49155` (wrapping at 0xC004) and a second socket to `40000`.

`LanFacade::Bind` (`0xc7eb3c`) stores the subnet broadcast address at `+0x30`:

```c
local_ip  = setting.ip;
mask      = setting.mask;
broadcast = local_ip | ~mask;
```

## Message types

Types 0 and 1 are raw. Types 3–7 are carried inside a Pia packet/message (see
`PIA_TRANSPORT.md`), and the LAN payload begins at the Pia message payload.

| Type | Name | Direction | Shape |
|---:|---|---|---|
| 0 | Browse request | client → broadcast:30000 | `u8 type` + `u32 size` + criteria (0x23A) + challenge (0x12A) |
| 1 | Browse reply | host → requester | `u8 type` + `u32 size` + session info + challenge reply |
| 3 | Host request | client → broadcast:49152–55 | `u8 type` + 11 bytes + `u32 network_id` |
| 4 | Host message | host → client | `u8 type` + 11 bytes + `u32 network_id` + host `StationLocation` |
| 5 | Session request | client → broadcast:49152–55 | `u8 type` + 11 bytes + `u32 network_id` |
| 6 | Session message | host → broadcast or requester | `u8 type` + 11 bytes + `u32 random` + `u16 sequence` + `u8 fragment_index` + `u8 fragment_count` + `u32 fragment_size` + fragment |
| 7 | Keep-alive | every 2 s → broadcast:49152 | `u8 type` + 11 bytes |

The 11-byte field after the type is zero padding in this implementation. The base
`LanMessage::Deserialize` (`0xc8dc44`) reads the type from byte 0 and copies bytes
1..11 into `this+0xc`.

### Browse request — `LanSessionSearchCriteria` (0x23A)

`LanSessionSearchCriteria::Deserialize` (`0xc85468`) matches the wiki 5.45 layout:

| Offset | Size | Field |
|---:|---:|---|
| 0x00 | 4 | min-participants range `{max:u16, min:u16}` |
| 0x04 | 4 | max-participants range `{max:u16, min:u16}` |
| 0x08 | 1 | opened only |
| 0x09 | 1 | vacant only |
| 0x0A | 4 | result range offset |
| 0x0E | 4 | result range size |
| 0x12 | 4 | game mode |
| 0x16 | 4 | session type |
| 0x1A | 0x1E0 | 6 attribute lists × 20 × u32 |
| 0x1FA | 6 | number of attributes per list |
| 0x200 | 24 | attribute range min (6 × u32) |
| 0x218 | 24 | attribute range max (6 × u32) |
| 0x230 | 6 | attribute-range-used flags |
| 0x236 | 4 | search flags |

### Browse reply / session message — `LanSessionInfo`

`LanSessionInfo::Deserialize` (`0xc84038`) reads the Pia 5.10–5.45 layout. The
fixed prefix:

| Offset | Size | Field |
|---:|---:|---|
| 0x000 | 4 | game mode |
| 0x004 | 4 | network id |
| 0x008 | 24 | 6 session attributes (u32) |
| 0x020 | 2 | current participants |
| 0x022 | 2 | minimum participants |
| 0x024 | 2 | maximum participants |
| 0x026 | 1 | system communication version |
| 0x027 | 1 | application communication version |
| 0x028 | 2 | session type |
| 0x02A | 0x180 | application data |
| 0x1AA | 4 | application data size |
| 0x1AE | 1 | is open |
| 0x1AF | var | host `StationAddress` |
| … | 8 | host constant id (PID in NEX; IP/port-derived in LAN) |
| … | 4 | host variable id |
| … | 4 | host service variable id |
| … | 7 | URL type / sid / stream / flags |
| … | 6 | host `InetAddress` (IPv4 + port) |
| tail | 16 × 0x32 | 16 × `LanStationInfo` |

`LanStationInfo::GetSerializedSize` (`0xc85c8c`) is
`SessionStationInfo::GetSerializedSize() + 0x31 == 0x32`:

| Offset | Size | Field |
|---:|---:|---|
| 0x00 | 1 | role (1 host, 2 player) |
| 0x01 | 1 | name encoding (1 UTF-8, 2 UTF-16) |
| 0x02 | 40 | player name |
| 0x2A | 8 | constant id |

The parser in `tools/lan_dissect.py` uses the tail-relative station offset, so it
does not need to know whether the host `StationAddress` is the 6-byte IPv4 or the
18-byte form.

### Session fragmentation

`LanProtocol::SendSessionMessage` (`0xc8193c`) serializes `LanSessionInfo` with a
maximum of `0x5D8` bytes, then splits it into **800-byte fragments**. Every fragment
is sent three times. Fields:

- `random`: a fresh `pead::Random::getU32()` shared by all fragments of one reply.
  Used to tell replies apart.
- `sequence`: `u16` incremented for each session message (`proto+0x1220`), starting
  at 0.
- `fragment_index` / `fragment_count`.
- `fragment_size` (last fragment is smaller).

The receiver reassembles fragments in `LanProtocol::ReceivedFragmentData::Receive`
(`0xc80fa8`) and accepts the result only when the fragment bitmap is full, then
deserializes `LanSessionInfo` into the session object.

## Crypto

The public wiki documents the algorithm; the decompiled binary contains the
primitives (`nn::pia::common::Crypto::Encrypt/Decrypt`, `Hmac::Calc`,
`SignatureManager`). Splatoon 2's game-specific key is public:

```
ee182a63e216cdb1f51ad4bed8cf6508
```

- Browse request challenge: 256 random bytes, AES-GCM encrypted with a key derived
  from the 16-byte random challenge key and the game key.
- Browse reply: first 16 bytes of `HMAC-SHA256(decrypted_challenge, game_key)`,
  encrypted with a response key derived from the **session key param**.
- Session key param = `challenge_key_from_reply || challenge_key_from_request`.
- Pia session key = first 16 bytes of
  `HMAC-SHA256(session_key_param with last byte incremented, game_key)`.

Because the challenge/response is required before the host is listed, a synthetic
LAN host must implement this exchange. A pure **relay** does not: it forwards
already-encrypted UDP between real consoles.

## Observed LAN flow

```
client                                    host / server
  |-- type 0 browse (broadcast:30000) ------->|
  |<-- type 1 reply (unicast, ×3) -------------|   LanSessionInfo
  |-- type 5 session request (bcast:49152) --->|
  |<-- type 6 session message (fragments) -----|
  |-- type 3 host request (bcast:49152) ------>|
  |<-- type 4 host message (StationLocation) --|
  |                                           |
  |====== Pia transport / mesh (UDP) =========|
  |-- type 7 keep-alive (bcast:49152, 2 s) --->|
```

Once the client has the host `StationLocation`, Pia's `transport`/`session` layer
takes over: mesh creation, station connections, reliable/unreliable protocols,
clone replication. That traffic is ordinary Pia packets on the bound sockets.

## What this means for a server

Three levels are possible:

1. **Opaque LAN relay.** Forward UDP between consoles on 30000/49152–49155/40000.
   No crypto, no game logic. This is what `switch-lan-play` does at L2; a native
   Pia relay can do it at UDP level if the peers share an address space (VPN/TAP).
2. **LAN matchmaking host.** Answer browse requests with a synthetic session and
   host messages, so the room appears in the LAN list. Clients then try to join a
   Pia mesh that has no real host unless the server also speaks the Pia station
   protocol. Useful for protocol testing and for redirecting clients to a real
   player-host.
3. **Authoritative LAN host.** Speak Pia transport + session + clone and run the
   game simulation. This is a dedicated game server; it needs either the recompiled
   game engine or a reimplementation of Splatoon 2's simulation.

See `DEDICATED_SERVER_PLAN.md` for the recommended order.
