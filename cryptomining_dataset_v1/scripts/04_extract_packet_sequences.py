#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from dataset_common import (
    flow_key_text,
    hmac_hash64,
    int_or_zero,
    load_build_config,
    load_privacy_config,
    parser_with_root,
    rel,
    sequence_stats,
    write_parquet,
)

import pandas as pd


def inet_to_str(raw: bytes) -> str:
    if len(raw) == 4:
        return socket.inet_ntop(socket.AF_INET, raw)
    if len(raw) == 16:
        return socket.inet_ntop(socket.AF_INET6, raw)
    return ""


def iter_tcp_packets(path: Path):
    try:
        import dpkt
    except ImportError as exc:
        raise RuntimeError("dpkt is required for PCAP extraction. Install requirements.txt first.") from exc

    with path.open("rb") as f:
        try:
            reader = dpkt.pcap.Reader(f)
        except (ValueError, dpkt.dpkt.NeedData):
            f.seek(0)
            reader = dpkt.pcapng.Reader(f)
        for ts, buf in reader:
            try:
                eth = dpkt.ethernet.Ethernet(buf)
                ip = eth.data
                if not isinstance(ip, (dpkt.ip.IP, dpkt.ip6.IP6)):
                    continue
                tcp = ip.data
                if not isinstance(tcp, dpkt.tcp.TCP):
                    continue
                src_ip = inet_to_str(ip.src)
                dst_ip = inet_to_str(ip.dst)
                yield {
                    "ts": float(ts),
                    "src_ip": src_ip,
                    "dst_ip": dst_ip,
                    "src_port": int(tcp.sport),
                    "dst_port": int(tcp.dport),
                    "proto": "tcp",
                    "pkt_len": int(len(buf)),
                    "flags": int(tcp.flags),
                }
            except Exception:
                continue


def process_pcap(path: Path, source: str, salt: str, max_packets: int) -> pd.DataFrame:
    flows: dict[str, list[dict]] = defaultdict(list)
    for pkt in iter_tcp_packets(path):
        key = flow_key_text(pkt["src_ip"], pkt["src_port"], pkt["dst_ip"], pkt["dst_port"], pkt["proto"])
        flows[key].append(pkt)

    rows = []
    for key, packets in flows.items():
        packets.sort(key=lambda p: p["ts"])
        if not packets:
            continue
        first = packets[0]
        origin = (first["src_ip"], first["src_port"])
        seq_len = min(len(packets), max_packets)
        stored = packets[:seq_len]
        directions = [1 if (p["src_ip"], p["src_port"]) == origin else -1 for p in stored]
        pkt_len = [int(p["pkt_len"]) for p in stored]
        signed = [l * d for l, d in zip(pkt_len, directions)]
        iats = [0.0]
        for prev, cur in zip(stored, stored[1:]):
            iats.append(max(0.0, float(cur["ts"]) - float(prev["ts"])))
        flags = [int_or_zero(p["flags"]) for p in packets]
        stats = sequence_stats(pkt_len, signed, directions, iats)
        rows.append(
            {
                "source": source,
                "source_file": str(path.resolve()),
                "flow_key_hash64": hmac_hash64(key, salt),
                "time_first": float(packets[0]["ts"]),
                "time_last": float(packets[-1]["ts"]),
                "packet_count_observed": len(packets),
                "seq_len_stored": seq_len,
                "seq_pkt_len": pkt_len,
                "seq_signed_pkt_len": signed,
                "seq_direction": directions,
                "seq_iat": iats,
                "tcp_syn_count": sum(1 for x in flags if x & 0x02),
                "tcp_ack_count": sum(1 for x in flags if x & 0x10),
                "tcp_psh_count": sum(1 for x in flags if x & 0x08),
                "tcp_rst_count": sum(1 for x in flags if x & 0x04),
                "tcp_fin_count": sum(1 for x in flags if x & 0x01),
                **stats,
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    parser = parser_with_root("Extract packet sequences and timing features from PCAP files.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--pcap-list", required=True)
    parser.add_argument("--output-root", default="data/staging/packets")
    args = parser.parse_args()

    build = load_build_config()
    salt = load_privacy_config()["salt"]
    max_packets = int(build.get("sequence", {}).get("max_packets_store", 256))
    output_dir = rel(args.output_root) / args.source
    output_dir.mkdir(parents=True, exist_ok=True)

    with rel(args.pcap_list).open("r", encoding="utf-8") as f:
        pcaps = [line.strip() for line in f if line.strip()]

    for pcap in pcaps:
        path = Path(pcap)
        if not path.is_absolute():
            path = rel(path)
        if not path.exists():
            print(f"skip missing pcap {path}", file=sys.stderr)
            continue
        df = process_pcap(path, args.source, salt, max_packets)
        out = output_dir / f"{path.stem}_{hmac_hash64(str(path.resolve()), salt)}.parquet"
        write_parquet(df, out)
        print(f"wrote {len(df)} packet-flow rows to {out}")


if __name__ == "__main__":
    main()

