# Pia transport — framing, crypto, and what a relay must do

Splatoon 2 uses Pia 5.x. The packet format is publicly documented by the
NintendoClients **Pia Protocol** page; the decompiled module implements the same
primitives (`nn::pia::common::Packet`, `Crypto`, `Hmac`, `SignatureManager`,
`transport::PacketHandler`, `ProtocolMessageReader/Writer`).

## Packet framing

All Pia traffic is UDP. The first 4 bytes are the magic:

```
32 AB 98 64
```

For the 5.27-era header (version 9), the layout is:

| Offset | Size | Field |
|---:|---:|---|
| 0x00 | 4 | magic `32 AB 98 64` |
| 0x04 | 1 | `0x80` = encrypted, low 7 bits = header version (9) |
| 0x05 | 4 | destination variable id |
| 0x09 | 4 | source variable id |
| 0x0D | 2 | packet id |
| 0x0F | 1 | footer size |
| 0x10 | 8 | AES-GCM nonce |
| 0x18 | 8 | AES-GCM tag (first 8 bytes) |
| 0x20 | … | messages (encrypted when the flag is set) |

Later Pia versions shrink variable ids to 16 bits and move the header fields; see
`tools/lan_dissect.py` for the version table. The decompiled binary's
`Packet::Header::Deserialize` (`0x13359c8`) reads the smaller 12-byte
magic/encrypted/connection-id/packet-id/timers form, which is the pre-5.7 header;
the version-9 fields are handled by the crypto/header path.

## Message framing

A packet contains one or more messages. In the 5.27–6.30 format each message is:

| Field | Size | Notes |
|---|---:|---|
| flags | 1 | which of the following fields are present |
| message flags | 0/1 | optional |
| payload size | 0/2 | optional u16 |
| protocol type | 0/1 | optional |
| protocol port | 0/3 | optional |
| destination | 0/8 | optional |
| payload | … | protocol-specific |

Fields that are not present are copied from the previous message. Messages are
padded to 4 bytes in 5.x. The decompiled `ProtocolMessageReader::Attach`
(`0xcd4cc0`) and `ProtocolMessageAccessor::Header::Deserialize` (`0xcd4dcc`)
implement exactly this; the header is 0x14 bytes in the older fixed form.

The LAN host/session/keep-alive messages are Pia messages whose payload is the
LAN structure from `LAN_PROTOCOL.md`. Browse request/reply (types 0/1) are **not**
inside a Pia packet.

## Encryption

- AES-GCM with a 128-bit session key.
- 12-byte nonce = IP address of the source (4 bytes) + source variable id (1) +
  last 7 bytes of the header nonce.
- Authentication tag: first 8 bytes in the 5.27 header.

The LAN session key is derived from the challenge exchange:

```
session_key_param = challenge_key_reply || challenge_key_request
session_key       = HMAC-SHA256(session_key_param with last byte +1, game_key)[:16]
```

with the Splatoon 2 game key

```
ee182a63e216cdb1f51ad4bed8cf6508
```

The decompiled `LanProtocol` stores the session key param in `LanSessionInfo` and
`SignatureManager`/`Crypto` handle the per-packet encryption and signatures.

## Reliable / unreliable / broadcast

`nn::pia::transport` implements several protocols over the packet layer:

| Class | Purpose |
|---|---|
| `ReliableProtocol` | ordered, acked messages |
| `UnreliableProtocol` | fire-and-forget |
| `ReliableBroadcastProtocol` | broadcast with resend |
| `StationProtocolManager` | station-to-station handshake |
| `RelayRouteManager` | relay routes for NAT-restricted peers |
| `PacketHandler` | bundles messages into packets, assigns destinations |

`PacketHandler::AssignByStationIndex`, `AssignByStationBitmap`,
`AssignByStationAddress` (`0xcd27fc`, `0xcd2804`, `0xcd280c`) are the routing
points. A relay that understands the packet layer can use these identifiers; a
dumb UDP relay cannot.

## What a relay needs

Pia has two kinds of traffic:

1. **Identifiable traffic** — packets carry source/destination variable ids,
   connection ids and packet ids. A relay can map these to a pair of endpoints.
2. **Opaque probes** — the NAT-traversal probe is a 16-byte datagram with no
   identifier. It only makes sense to the peer that sent it; answering it from the
   relay is rejected by Pia, which expects the *peer* to answer.

Nextendo's `relaypair.go` documents this exact failure from a 2026-08-21 Splatoon 2
test: 914 probes received, none forwardable, so the relay answered them itself and
Pia refused the answer. Their solution is a **port per PID pair**:

- both peers are told a relay port derived from `(pidA, pidB)`;
- everything arriving on that port is forwarded to the other peer, regardless of
  content — probes, hole punching, session setup, game data;
- no protocol parsing is needed;
- a 2-minute idle TTL reclaims ports.

That is the practical design for an online Pia relay. For LAN mode the peers are
already on one broadcast domain (real LAN, VPN, or an L2 relay such as
`switch-lan-play`), so NAT traversal is not involved.

## Relevance to Splatoon 2 modes

Pia is the data plane for both LAN and online:

- **LAN mode:** Pia LAN session + direct UDP; no NEX.
- **Online:** NEX matchmaking returns station URLs/session key; Pia inet builds the
  mesh and runs NAT traversal. Ranked, league, fest and Salmon Run all use the same
  Pia mesh once matched.

A dedicated *game* server would have to be a Pia station (speak mesh/session/clone
and run the simulation). A dedicated *service* server only needs NEX + a relay,
which is enough for player-hosted matches.
