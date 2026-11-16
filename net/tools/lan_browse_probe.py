#!/usr/bin/env python3
"""Send a Pia LAN browse request (type 0) and decode the replies.

This is the same request a console sends when it scans for LAN rooms.  It uses an
unencrypted challenge (crypto_enabled=0), which is legal in the protocol; some
hosts may still only answer encrypted requests.  If so, the reply parser will
show the session and the challenge, and you can add the AES-GCM exchange from
LAN_PROTOCOL.md.

Usage:
  python3 lan_browse_probe.py                 # broadcast 255.255.255.255:30000
  python3 lan_browse_probe.py --dest 10.13.37.255
  python3 lan_browse_probe.py --wait 5
"""
from __future__ import annotations

import argparse
import os
import socket
import struct
import time

from lan_dissect import parse_session_info, parse_challenge, TYPE_NAMES


def build_criteria(min_players=1, max_players=8, opened_only=True,
                   vacant_only=True, game_mode=0, session_type=0,
                   search_flags=0x3F):
    b = bytearray(0x23A)
    # range = {max:u16, min:u16}
    struct.pack_into(">HH", b, 0x00, max_players, min_players)
    struct.pack_into(">HH", b, 0x04, max_players, min_players)
    b[0x08] = 1 if opened_only else 0
    b[0x09] = 1 if vacant_only else 0
    struct.pack_into(">II", b, 0x0A, 0, 32)       # result offset / size
    struct.pack_into(">II", b, 0x12, game_mode, session_type)
    struct.pack_into(">I", b, 0x236, search_flags)
    return bytes(b)


def build_challenge(crypto=False, counter=None):
    version = 2
    key = os.urandom(16)
    tag = os.urandom(16)
    payload = os.urandom(256)
    if counter is None:
        counter = int(time.time() * 1000) & 0xFFFFFFFFFFFFFFFF
    return (bytes([version, 1 if crypto else 0]) +
            struct.pack(">Q", counter) + key + tag + payload)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default="255.255.255.255",
                    help="broadcast or host address (default 255.255.255.255)")
    ap.add_argument("--port", type=int, default=30000)
    ap.add_argument("--wait", type=float, default=3.0)
    ap.add_argument("--min", type=int, default=1)
    ap.add_argument("--max", type=int, default=8)
    ap.add_argument("--game-mode", type=int, default=0)
    ap.add_argument("--session-type", type=int, default=0)
    ap.add_argument("--crypto", action="store_true",
                    help="set the crypto flag (payload is still random)")
    args = ap.parse_args()

    criteria = build_criteria(args.min, args.max, game_mode=args.game_mode,
                              session_type=args.session_type)
    challenge = build_challenge(args.crypto)
    body = criteria + challenge
    pkt = bytes([0]) + struct.pack(">I", len(body)) + body

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", 0))
    s.settimeout(0.2)

    print(f"sending browse request to {args.dest}:{args.port} "
          f"({len(pkt)} bytes, crypto={args.crypto})")
    s.sendto(pkt, (args.dest, args.port))

    end = time.time() + args.wait
    seen = set()
    while time.time() < end:
        try:
            data, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        if not data or data[0] != 1:
            continue
        key = (addr[0], data[:16])
        if key in seen:
            continue
        seen.add(key)
        print(f"\nreply from {addr[0]}:{addr[1]} ({len(data)} bytes)")
        if len(data) < 5:
            continue
        size = struct.unpack_from(">I", data, 1)[0]
        info = data[5:5 + size]
        print("  session info:")
        for k, v in parse_session_info(info).items():
            if k == "stations":
                print(f"    stations: {len(v)}")
                for st in v:
                    print(f"      {st}")
            elif k != "application_data":
                print(f"    {k}: {v}")
        rest = data[5 + size:]
        if rest:
            print("  challenge reply:")
            for k, v in parse_challenge(rest).items():
                if k != "payload":
                    print(f"    {k}: {v}")


if __name__ == "__main__":
    main()
