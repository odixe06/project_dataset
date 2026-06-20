#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys
import re

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from dataset_common import (
    first_present,
    float_or_zero,
    flow_key_text,
    hmac_hash64,
    int_or_zero,
    load_build_config,
    load_privacy_config,
    normalize_dataframe,
    parser_with_root,
    rel,
    write_parquet,
)

import pandas as pd


MINING_TERMS = ("miner", "mining", "cryptomining", "stratum", "xmr", "monero")


def label_allowed(label: str) -> bool:
    text = label.lower()
    return bool(text) and not any(term in text for term in MINING_TERMS)


def iter_iot_rows(path: Path):
    fields = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            if line.startswith("#fields"):
                fields = line.split("\t")[1:]
                if fields and "   " in fields[-1]:
                    fields = fields[:-1] + re.split(r"\s{2,}", fields[-1].strip())
                continue
            if line.startswith("#"):
                continue
            parts = line.split("\t")
            if fields and len(parts) == len(fields) - 2 and "   " in parts[-1]:
                parts = parts[:-1] + re.split(r"\s{2,}", parts[-1].strip())
            if not fields or len(parts) != len(fields):
                continue
            yield dict(zip(fields, parts))


def main() -> None:
    parser = parser_with_root("Parse IoT-23 MCFP conn.log.labeled files into label=0 canonical parquet.")
    parser.add_argument("--input", default="data/raw/non_mining/iot23_mcfp/extracted")
    parser.add_argument("--output", default="data/interim/canonical_by_source/iot23_mcfp.parquet")
    args = parser.parse_args()
    salt = load_privacy_config()["salt"]
    limits = load_build_config().get("source_row_limits", {})
    max_rows = int(limits.get("iot23_mcfp") or 0)
    max_per_file = int(limits.get("iot23_mcfp_per_file") or 0)
    rows = []
    paths = list(rel(args.input).rglob("conn.log.labeled")) + list(rel(args.input).rglob("conn.log"))
    for path in sorted(set(paths)):
        kept_for_file = 0
        for row in iter_iot_rows(path):
            original_label = str(first_present(row, ["label", "detailed-label", "tunnel_parents"], "unknown"))
            if not label_allowed(original_label):
                continue
            src_ip = str(first_present(row, ["id.orig_h", "id_orig_h"], ""))
            dst_ip = str(first_present(row, ["id.resp_h", "id_resp_h"], ""))
            src_port = int_or_zero(first_present(row, ["id.orig_p", "id_orig_p"], 0))
            dst_port = int_or_zero(first_present(row, ["id.resp_p", "id_resp_p"], 0))
            proto = str(first_present(row, ["proto"], "tcp")).lower()
            duration = float_or_zero(first_present(row, ["duration"], 0))
            bytes_fwd = int_or_zero(first_present(row, ["orig_bytes"], 0))
            bytes_bwd = int_or_zero(first_present(row, ["resp_bytes"], 0))
            packets_fwd = int_or_zero(first_present(row, ["orig_pkts"], 0))
            packets_bwd = int_or_zero(first_present(row, ["resp_pkts"], 0))
            bytes_total = bytes_fwd + bytes_bwd
            packets_total = packets_fwd + packets_bwd
            key = flow_key_text(src_ip, src_port, dst_ip, dst_port, proto)
            hard_type = "benign" if "benign" in original_label.lower() else "non_mining_malware_or_attack"
            rows.append(
                {
                    "source": "iot23_mcfp",
                    "source_role": "non_mining_iot_or_hard_negative",
                    "source_file": str(path),
                    "source_record_id": str(first_present(row, ["uid"], "")),
                    "original_label": original_label,
                    "label": 0,
                    "label_confidence": 1.0,
                    "hard_negative_type": hard_type,
                    "time_first": float_or_zero(first_present(row, ["ts"], 0)),
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
                    "has_tls": 0,
                    "tls_source": "none",
                    "packet_seq_available": 0,
                    "timing_full_available": 0,
                    "extract_status": "ok",
                }
            )
            kept_for_file += 1
            if (max_per_file and kept_for_file >= max_per_file) or (max_rows and len(rows) >= max_rows):
                break
        if max_rows and len(rows) >= max_rows:
            break
    df = normalize_dataframe(pd.DataFrame(rows))
    write_parquet(df, args.output)
    print(f"wrote {len(df)} IoT-23 rows to {args.output}")


if __name__ == "__main__":
    main()
