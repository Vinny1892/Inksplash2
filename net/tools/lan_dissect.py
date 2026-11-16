#!/usr/bin/env python3
"""Splatoon 2 / Pia LAN packet dissector.

The LAN protocol is documented publicly (kinnay/NintendoClients wiki, LAN Protocol)
and the implementation in the retail module matches that documentation.  This tool
decodes the pieces we care about when bringing up a LAN server:

  * raw browse request/reply (UDP 30000)       types 0, 1
  * Pia-encapsulated LAN messages (49152-55)   types 3,4,5,6,7
  * the Pia packet/message framing itself

It does not decrypt Pia payloads.  The session key is derived from the LAN
challenge and the game-specific key; once you have it, the payload can be fed to
an AES-GCM implementation separately (the framing parser below still works on the
ciphertext and tells you where the ciphertext starts).

Usage:
  python3 lan_dissect.py --hex 00000000023a...
  python3 lan_dissect.py --file capture.bin
  python3 lan_dissect.py --udp            # listen on the LAN ports and decode

The --udp mode is deliberately read-only: it does not answer anything.
"""
from __future__ import annotations

import argparse
import binascii
import socket
import struct
import sys
import time

PIA_MAGIC = 0x32AB9864
SPLATOON2_PIA_KEY = bytes.fromhex("ee182a63e216cdb1f51ad4bed8cf6508")

TYPE_NAMES = {
    0: "browse-request",
    1: "browse-reply",
    3: "host-request",
    4: "host-message",
    5: "session-request",
    6: "session-message",
    7: "self-keepalive",
}


def u8(b, o=0):
    return b[o]


def u16(b, o=0):
    return struct.unpack_from(">H", b, o)[0]


def u32(b, o=0):
    return struct.unpack_from(">I", b, o)[0]


def u64(b, o=0):
    return struct.unpack_from(">Q", b, o)[0]


def hexdump(b, indent="    "):
    for i in range(0, len(b), 16):
        chunk = b[i:i + 16]
        print(indent + f"{i:04x}  " + binascii.hexlify(chunk).decode() +
              "  " + "".join(chr(c) if 32 <= c < 127 else "." for c in chunk))


# --------------------------------------------------------------------------- LAN

def parse_challenge(b):
    """Pia 5.9-6.33 challenge/response block (0x12A bytes)."""
    if len(b) < 0x2A:
        return {"error": f"challenge too short ({len(b)})"}
    d = {
        "version": b[0],
        "crypto_enabled": b[1],
        "counter": u64(b, 2),
        "challenge_key": b[10:26].hex(),
        "auth_tag": b[26:42].hex(),
        "payload_len": len(b) - 42,
        "payload": b[42:].hex(),
    }
    if d["payload_len"] == 256:
        d["kind"] = "challenge (256 bytes)"
    elif d["payload_len"] == 16:
        d["kind"] = "response (16 bytes)"
    else:
        d["kind"] = "unknown"
    return d


def parse_criteria(b):
    """LanSessionSearchCriteria, Pia <= 5.45 (0x23A bytes)."""
    if len(b) < 0x23A:
        return {"error": f"criteria too short ({len(b)})"}
    attrs = []
    for li in range(6):
        attrs.append([u32(b, 0x1A + li * 0x50 + i * 4) for i in range(20)])
    return {
        "min_participants_range": (u16(b, 0), u16(b, 2)),
        "max_participants_range": (u16(b, 4), u16(b, 6)),
        "opened_only": bool(b[8]),
        "vacant_only": bool(b[9]),
        "result_range": (u32(b, 0x0A), u32(b, 0x0E)),
        "game_mode": u32(b, 0x12),
        "session_type": u32(b, 0x16),
        "attributes": attrs,
        "attribute_counts": list(b[0x1FA:0x200]),
        "attribute_range_min": [u32(b, 0x200 + i * 4) for i in range(6)],
        "attribute_range_max": [u32(b, 0x218 + i * 4) for i in range(6)],
        "attribute_range_used": list(b[0x230:0x236]),
        "search_flags": f"{u32(b, 0x236):#x}",
    }


def parse_station_info(b, o):
    return {
        "role": b[o],
        "name_encoding": b[o + 1],
        "name": b[o + 2:o + 0x2A].split(b"\0", 1)[0].decode("utf-8", "replace"),
        "constant_id": u64(b, o + 0x2A),
    }


def parse_session_info(b):
    """LanSessionInfo, Pia 5.10-5.45 layout as implemented by Splatoon 2."""
    if len(b) < 0x1AF:
        return {"error": f"session info too short ({len(b)})"}
    d = {
        "game_mode": u32(b, 0),
        "network_id": f"{u32(b, 4):#010x}",
        "attributes": [u32(b, 8 + i * 4) for i in range(6)],
        "participants": (u16(b, 0x20), u16(b, 0x22), u16(b, 0x24)),
        "system_comm_version": b[0x26],
        "app_comm_version": b[0x27],
        "session_type": u16(b, 0x28),
        "application_data_size": u32(b, 0x1AA),
        "is_open": bool(b[0x1AE]),
    }
    d["application_data"] = b[0x2A:0x2A + min(d["application_data_size"], 0x180)].hex()
    # The host block runs from 0x1AF to the 16 station records at the tail.
    stations_off = len(b) - 16 * 0x32
    if stations_off >= 0x1AF:
        d["host_block"] = b[0x1AF:stations_off].hex()
        d["stations"] = [parse_station_info(b, stations_off + i * 0x32)
                         for i in range(16)]
        d["stations"] = [s for s in d["stations"]
                         if s["role"] or s["name"] or s["constant_id"]]
    return d


def parse_lan_payload(payload):
    """Decode a raw LAN message (after Pia framing, or a raw browse packet)."""
    if not payload:
        return {"error": "empty"}
    t = payload[0]
    d = {"type": t, "type_name": TYPE_NAMES.get(t, "unknown")}
    if t in (0, 1):
        # [type][u32 size][body][challenge]
        if len(payload) < 5:
            return {**d, "error": "short"}
        size = u32(payload, 1)
        body = payload[5:5 + size]
        d["declared_size"] = size
        if t == 0:
            d["criteria"] = parse_criteria(body)
        else:
            d["session_info"] = parse_session_info(body)
        rest = payload[5 + size:]
        if rest:
            d["challenge"] = parse_challenge(rest)
        return d
    if t in (3, 4, 5, 6, 7):
        # [type][11 bytes base][u32 network id][...]
        if len(payload) < 0x0C:
            return {**d, "error": "short"}
        d["base"] = payload[1:0xC].hex()
        d["network_id"] = f"{u32(payload, 0xC):#010x}"
        if t == 6:
            if len(payload) < 0x18:
                return {**d, "error": "short session message"}
            d["session_message"] = {
                "random": f"{u32(payload, 0xC):#010x}",
                "sequence": u16(payload, 0x10),
                "fragment_index": payload[0x12],
                "fragment_count": payload[0x13],
                "fragment_size": u32(payload, 0x14),
                "fragment": payload[0x18:0x18 + u32(payload, 0x14)].hex(),
            }
        elif t == 4:
            d["host_station"] = payload[0x10:].hex()
        return d
    return d


# --------------------------------------------------------------------------- Pia
# Header lengths for the Pia versions relevant to LAN mode.  Splatoon 2 is on the
# 5.x line (header version 9, 32-byte header).  See Pia Protocol wiki.
PIA_HEADER_LEN = {
    1: 0x0C,  # <= 5.6
    3: 0x20,  # 5.11-5.17 (nonce+tag)
    4: 0x20,
    5: 0x1C,  # 5.23-5.26
    9: 0x20,  # 5.27-5.45
    11: 0x1C,  # 6.16-6.30
    12: 0x1C,
    13: 0x1C,
    15: 0x1D,  # 6.32+
    16: 0x1D,
}


def parse_pia_packet(b):
    if len(b) < 4 or u32(b, 0) != PIA_MAGIC:
        return None
    raw = b[4]
    encrypted = bool(raw & 0x80)
    version = raw & 0x7F
    d = {
        "kind": "pia-packet",
        "version": version,
        "encrypted": encrypted,
        "length": len(b),
    }
    if version == 9:
        # 5.27-5.45
        d.update({
            "dest_variable_id": u32(b, 5),
            "src_variable_id": u32(b, 9),
            "packet_id": u16(b, 0x0D),
            "footer_size": b[0x0F],
            "nonce": b[0x10:0x18].hex(),
            "auth_tag": b[0x18:0x20].hex(),
        })
        body_off = 0x20
    elif version in (15, 16):
        # 6.32+
        d.update({
            "padding": raw >> 4,
            "flags": raw & 0x0F,
            "dest_variable_id": u16(b, 6),
            "src_variable_id": u16(b, 8),
            "packet_id": u16(b, 0x0A),
            "footer_size": b[0x0C],
            "nonce": b[0x0D:0x15].hex(),
            "auth_tag": b[0x15:0x1D].hex(),
        })
        body_off = 0x1D
    else:
        body_off = PIA_HEADER_LEN.get(version, 0x20)
        d["body_offset_guess"] = body_off
    d["body_offset"] = body_off
    d["body"] = b[body_off:].hex()
    if not encrypted:
        d["plain_body_hex"] = b[body_off:].hex()
    return d


def parse_pia_messages(body, version=9):
    """Best-effort parse of the Pia message stream (unencrypted only)."""
    out = []
    o = 0
    while o < len(body):
        start = o
        flags = body[o]
        o += 1
        if flags == 0 and o >= len(body):
            break
        mflags = None
        size = None
        proto = None
        port = None
        dest = None
        if flags & 1:
            mflags = body[o]
            o += 1
        if flags & 2:
            size = u16(body, o)
            o += 2
        if flags & 4:
            proto = body[o]
            o += 1
            if version >= 11:
                port = body[o]
                o += 1
            else:
                port = int.from_bytes(body[o:o + 3], "big")
                o += 3
        if flags & 8:
            dest = u64(body, o)
            o += 8
        if size is None:
            # No size: remainder is the payload (final message).
            size = len(body) - o
        payload = body[o:o + size]
        o += size
        # 4-byte alignment in 5.x
        if version < 11:
            o = (o + 3) & ~3
        out.append({
            "offset": start,
            "flags": flags,
            "msg_flags": mflags,
            "size": size,
            "protocol": proto,
            "port": port,
            "destination": dest,
            "payload": payload,
        })
        if o <= start:
            break
    return out


# --------------------------------------------------------------------------- CLI

def decode(data, note=""):
    print(f"--- {len(data)} bytes {note}")
    pia = parse_pia_packet(data)
    if pia:
        print(f"  Pia packet v{pia['version']} encrypted={pia['encrypted']} "
              f"len={pia['length']}")
        for k, v in pia.items():
            if k in ("kind", "version", "encrypted", "length", "body"):
                continue
            print(f"    {k}: {v}")
        if not pia["encrypted"]:
            body = bytes.fromhex(pia["body"])
            msgs = parse_pia_messages(body, pia["version"])
            for m in msgs:
                print(f"    message @{m['offset']:#x} proto={m['protocol']} "
                      f"port={m['port']} size={m['size']} flags={m['flags']:#x}")
                if m["payload"]:
                    lan = parse_lan_payload(m["payload"])
                    print(f"      lan: {lan}")
        return
    lan = parse_lan_payload(data)
    print(f"  LAN {lan.get('type_name', '?')}")
    for k, v in lan.items():
        print(f"    {k}: {v}")


def udp_listen(ports):
    socks = []
    for p in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            s.bind(("0.0.0.0", p))
        except OSError as e:
            print(f"bind {p}: {e}", file=sys.stderr)
            continue
        s.setblocking(False)
        socks.append((p, s))
    print(f"listening on {[p for p, _ in socks]} (Ctrl-C to stop)")
    try:
        while True:
            for p, s in socks:
                try:
                    data, addr = s.recvfrom(65535)
                except BlockingIOError:
                    continue
                print(f"\n[{time.strftime('%H:%M:%S')}] {addr[0]}:{addr[1]} -> :{p}")
                decode(data, f"from {addr[0]}:{addr[1]}")
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hex")
    ap.add_argument("--file")
    ap.add_argument("--udp", action="store_true")
    ap.add_argument("--ports", default="30000,49152,49153,49154,49155,40000")
    args = ap.parse_args()
    if args.hex:
        decode(bytes.fromhex(args.hex.replace(" ", "")))
    elif args.file:
        decode(open(args.file, "rb").read())
    elif args.udp:
        udp_listen([int(x) for x in args.ports.split(",") if x])
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
