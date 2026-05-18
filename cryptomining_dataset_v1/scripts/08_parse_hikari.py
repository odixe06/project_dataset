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
    load_build_config,
    load_privacy_config,
    normalize_dataframe,
    parser_with_root,
    read_zeek_log,
    rel,
    write_parquet,
)

import pandas as pd

import importlib.util


def load_zeek_helpers():
    path = Path(__file__).resolve().parent / "05_parse_zeek_logs.py"
    spec = importlib.util.spec_from_file_location("parse_zeek_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def is_benign(row: dict) -> bool:
    category = str(first_present(row, ["traffic_category", "traffic_type", "category"], "")).strip().lower()
    label = str(first_present(row, ["Label", "label"], "")).strip().lower()
    return category == "benign" and label in {"0", "0.0", "benign"}


def main() -> None:
    parser = parser_with_root("Parse HIKARI-2021 benign flow CSV into canonical parquet.")
    parser.add_argument("--flowmeter", default="data/raw/non_mining/hikari2021/extracted/ALLFLOWMETER_HIKARI2021.csv")
    parser.add_argument("--ground-truth", default="data/raw/non_mining/hikari2021/extracted")
    parser.add_argument("--zeek", default="data/staging/zeek/hikari2021")
    parser.add_argument("--output", default="data/interim/canonical_by_source/hikari2021.parquet")
    parser.add_argument("--chunksize", type=int, default=100000)
    args = parser.parse_args()
    salt = load_privacy_config()["salt"]
    limit = int(load_build_config().get("source_row_limits", {}).get("hikari2021") or 0)
    flowmeter = rel(args.flowmeter)
    candidates = [flowmeter] if flowmeter.exists() else sorted(rel("data/raw/non_mining/hikari2021/extracted").rglob("*.csv"))
    rows = []
    benign_flow_keys = set()
    for path in candidates:
        for chunk in pd.read_csv(path, chunksize=args.chunksize, low_memory=False):
            for row in chunk.to_dict(orient="records"):
                if not is_benign(row):
                    continue
                src_ip = str(first_present(row, ["originh", "src_ip", "Source IP", "Src IP", "SRC_IP"], ""))
                dst_ip = str(first_present(row, ["responh", "dst_ip", "Destination IP", "Dst IP", "DST_IP"], ""))
                src_port = int_or_zero(first_present(row, ["originp", "src_port", "Source Port", "Src Port", "SRC_PORT"], 0))
                dst_port = int_or_zero(first_present(row, ["responp", "dst_port", "Destination Port", "Dst Port", "DST_PORT"], 0))
                proto = str(first_present(row, ["Protocol", "proto", "PROTOCOL"], "tcp")).lower()
                duration = float_or_zero(first_present(row, ["flow_duration", "Flow Duration", "duration", "DURATION"], 0))
                packets_fwd = int_or_zero(first_present(row, ["fwd_pkts_tot", "Tot Fwd Pkts", "packets_fwd", "PACKETS"], 0))
                packets_bwd = int_or_zero(first_present(row, ["bwd_pkts_tot", "Tot Bwd Pkts", "packets_bwd", "PACKETS_REV"], 0))
                bytes_fwd = int_or_zero(first_present(row, ["fwd_pkts_payload.tot", "TotLen Fwd Pkts", "bytes_fwd", "BYTES"], 0))
                bytes_bwd = int_or_zero(first_present(row, ["bwd_pkts_payload.tot", "TotLen Bwd Pkts", "bytes_bwd", "BYTES_REV"], 0))
                has_tls = 1 if dst_port in {443, 8443, 9443} else 0
                if not has_tls:
                    continue
                bytes_total = bytes_fwd + bytes_bwd
                packets_total = packets_fwd + packets_bwd
                key = flow_key_text(src_ip, src_port, dst_ip, dst_port, proto)
                key_hash = hmac_hash64(key, salt)
                benign_flow_keys.add(key_hash)
                record_id = str(first_present(row, ["uid", "ID", "id", "Flow ID", "flow_id"], "")) or f"{path.name}:{len(rows)}"
                rows.append(
                    {
                        "source": "hikari2021",
                        "source_role": "non_mining_tls_benign",
                        "source_file": str(path),
                        "source_record_id": record_id,
                        "original_label": "benign",
                        "label": 0,
                        "label_confidence": 1.0,
                        "duration": duration,
                        "proto": proto,
                        "src_ip_hash64": hmac_hash64(src_ip, salt),
                        "dst_ip_hash64": hmac_hash64(dst_ip, salt),
                        "src_port": src_port,
                        "dst_port": dst_port,
                        "flow_key_hash64": key_hash,
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
                        "tls_source": "port_heuristic" if has_tls else "none",
                        "tls_metadata_available": 0,
                        "tls_full_available": 0,
                        "possible_tls_port": has_tls,
                        "extract_status": "ok",
                        "quality_notes": "HIKARI flowmeter row filtered to benign; run Zeek parser for full TLS metadata when PCAP is available.",
                    }
                )
                if limit and len(rows) >= limit:
                    break
            if limit and len(rows) >= limit:
                break
        if limit and len(rows) >= limit:
            break
    zeek_root = rel(args.zeek)
    if zeek_root.exists() and benign_flow_keys:
        helpers = load_zeek_helpers()
        for directory in sorted(p for p in zeek_root.glob("*") if p.is_dir()):
            conn = read_zeek_log(helpers.log_path(directory, "conn"))
            ssl = read_zeek_log(helpers.log_path(directory, "ssl"))
            x509 = read_zeek_log(helpers.log_path(directory, "x509"))
            if conn.empty or ssl.empty or "uid" not in ssl.columns:
                continue
            ssl_by_uid = {str(r["uid"]): r for r in ssl.to_dict(orient="records")}
            for conn_row in conn.to_dict(orient="records"):
                base = helpers.flow_features(conn_row, salt)
                if int(base["flow_key_hash64"]) not in benign_flow_keys:
                    continue
                uid = str(first_present(conn_row, ["uid"], ""))
                tls = helpers.tls_features(ssl_by_uid.get(uid), x509, salt)
                if not tls.get("has_tls"):
                    continue
                rows.append(
                    {
                        **base,
                        **tls,
                        "source": "hikari2021",
                        "source_role": "non_mining_tls_benign",
                        "source_file": helpers.read_source_file(directory),
                        "source_record_id": uid,
                        "original_label": "benign",
                        "label": 0,
                        "label_confidence": 1.0,
                        "packet_seq_available": 0,
                        "timing_full_available": 0,
                        "extract_status": "ok",
                        "quality_notes": "Zeek TLS metadata matched to a benign HIKARI flow key.",
                    }
                )
    df = normalize_dataframe(pd.DataFrame(rows))
    write_parquet(df, args.output)
    print(f"wrote {len(df)} HIKARI rows to {args.output}")


if __name__ == "__main__":
    main()
