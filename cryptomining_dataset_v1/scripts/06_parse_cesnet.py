#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from dataset_common import (
    first_present,
    float_or_zero,
    flow_key_text,
    hmac_hash64,
    int_or_zero,
    load_privacy_config,
    normalize_dataframe,
    parse_sequence,
    parser_with_root,
    rel,
    sequence_stats,
    string_entropy,
    tld,
    write_parquet,
)

import pandas as pd


def csv_files(root: Path) -> list[Path]:
    return sorted([p for p in root.rglob("*") if "".join(p.suffixes).lower().endswith((".csv", ".csv.gz"))])


def row_to_canonical(row: dict, path: Path, salt: str) -> dict | None:
    label_raw = str(first_present(row, ["LABEL", "Label", "label"], "")).strip()
    if label_raw not in {"Miner", "Other"}:
        return None
    label = 1 if label_raw == "Miner" else 0
    src_ip = str(first_present(row, ["SRC_IP", "src_ip"], ""))
    dst_ip = str(first_present(row, ["DST_IP", "dst_ip"], ""))
    src_port = int_or_zero(first_present(row, ["SRC_PORT", "src_port"], 0))
    dst_port = int_or_zero(first_present(row, ["DST_PORT", "dst_port"], 0))
    proto = str(first_present(row, ["PROTOCOL", "proto"], "tcp")).lower()
    t_first = float_or_zero(first_present(row, ["TIME_FIRST", "time_first", "START_TIME"], 0))
    t_last = float_or_zero(first_present(row, ["TIME_LAST", "time_last", "END_TIME"], 0))
    duration = max(0.0, t_last - t_first) if t_last else float_or_zero(first_present(row, ["DURATION", "duration"], 0))
    bytes_fwd = int_or_zero(first_present(row, ["BYTES", "bytes", "BYTES_FWD"], 0))
    bytes_bwd = int_or_zero(first_present(row, ["BYTES_REV", "bytes_rev", "BYTES_BWD"], 0))
    packets_fwd = int_or_zero(first_present(row, ["PACKETS", "packets", "PACKETS_FWD"], 0))
    packets_bwd = int_or_zero(first_present(row, ["PACKETS_REV", "packets_rev", "PACKETS_BWD"], 0))
    directions = [int_or_zero(x) for x in parse_sequence(first_present(row, ["PPI_PKT_DIRECTIONS", "PPI_DIRECTIONS"], []))]
    pkt_len = [int_or_zero(x) for x in parse_sequence(first_present(row, ["PPI_PKT_LENGTHS", "PPI_LENGTHS"], []))]
    times = parse_sequence(first_present(row, ["PPI_PKT_TIMES", "PPI_TIMES"], []))
    iat = [0.0] + [max(0.0, b - a) for a, b in zip(times, times[1:])] if times else []
    if not directions and pkt_len:
        directions = [1] * len(pkt_len)
    signed = [int(l) * (1 if int_or_zero(d) >= 0 else -1) for l, d in zip(pkt_len, directions)]
    seq = sequence_stats(pkt_len, signed, directions, iat) if pkt_len else {}
    sni = str(first_present(row, ["SNI", "SERVER_NAME", "server_name"], "") or "")
    has_tls = 1 if sni else 0
    key = flow_key_text(src_ip, src_port, dst_ip, dst_port, proto)
    bytes_total = bytes_fwd + bytes_bwd
    packets_total = packets_fwd + packets_bwd
    return {
        "source": "cesnet_miner22",
        "source_role": "flow_scale",
        "source_file": str(path),
        "source_record_id": str(first_present(row, ["ID", "id", "FLOW_ID", "flow_id"], "")),
        "original_label": label_raw,
        "label": label,
        "label_confidence": 1.0,
        "time_first": t_first,
        "time_last": t_last or (t_first + duration),
        "duration": duration,
        "proto": proto,
        "src_ip_hash64": hmac_hash64(src_ip, salt),
        "dst_ip_hash64": hmac_hash64(dst_ip, salt),
        "src_port": src_port,
        "dst_port": dst_port,
        "flow_key_hash64": hmac_hash64(key, salt),
        "bytes_total": bytes_total,
        "bytes_fwd": bytes_fwd,
        "bytes_bwd": bytes_bwd,
        "packets_total": packets_total,
        "packets_fwd": packets_fwd,
        "packets_bwd": packets_bwd,
        "byte_rate": bytes_total / max(duration, 1e-6),
        "packet_rate": packets_total / max(duration, 1e-6),
        "bytes_ratio_fwd": bytes_fwd / max(bytes_total, 1),
        "packets_ratio_fwd": packets_fwd / max(packets_total, 1),
        "has_tls": has_tls,
        "tls_source": "sni_only" if has_tls else "none",
        "sni_hash64": hmac_hash64(sni, salt),
        "sni_len": len(sni),
        "sni_num_labels": len([p for p in sni.split(".") if p]) if sni else 0,
        "sni_entropy": string_entropy(sni),
        "sni_tld_hash64": hmac_hash64(tld(sni), salt),
        "tls_metadata_available": has_tls,
        "tls_full_available": 0,
        "seq_len_stored": len(pkt_len),
        "seq_pkt_len": pkt_len,
        "seq_signed_pkt_len": signed,
        "seq_direction": directions,
        "seq_iat": iat,
        "packet_seq_available": 1 if pkt_len else 0,
        "timing_full_available": 1 if pkt_len else 0,
        "extract_status": "ok",
        **seq,
    }


def main() -> None:
    parser = parser_with_root("Parse CESNET-MINER22 CSV files into canonical parquet.")
    parser.add_argument("--input", default="data/raw/mining/cesnet_miner22/extracted")
    parser.add_argument("--output", default="data/interim/canonical_by_source/cesnet_miner22.parquet")
    parser.add_argument("--chunksize", type=int, default=100000)
    args = parser.parse_args()
    salt = load_privacy_config()["salt"]
    rows = []
    for path in csv_files(rel(args.input)):
        for chunk in pd.read_csv(path, chunksize=args.chunksize, low_memory=False):
            for row in chunk.to_dict(orient="records"):
                out = row_to_canonical(row, path, salt)
                if out is not None:
                    rows.append(out)
    df = normalize_dataframe(pd.DataFrame(rows))
    write_parquet(df, args.output)
    print(f"wrote {len(df)} CESNET rows to {args.output}")


if __name__ == "__main__":
    main()
