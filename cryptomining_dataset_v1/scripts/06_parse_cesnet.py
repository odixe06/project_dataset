#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
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


def logical_row(row: dict) -> dict:
    out = {}
    for key, value in row.items():
        logical = str(key).strip().split()[-1].lower()
        out[logical] = value
    return out


NEEDED_LOGICAL_COLUMNS = {
    "bytes",
    "bytes_rev",
    "time_first",
    "time_last",
    "packets",
    "packets_rev",
    "dst_port",
    "src_port",
    "protocol",
    "label",
    "ppi_pkt_directions",
    "ppi_pkt_lengths",
    "ppi_pkt_times",
}


def use_cesnet_column(name: str) -> bool:
    return str(name).strip().split()[-1].lower() in NEEDED_LOGICAL_COLUMNS


def timestamp_or_zero(value) -> float:
    if value is None or str(value).strip() == "":
        return 0.0
    numeric = float_or_zero(value)
    if numeric:
        return numeric
    try:
        dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return float(dt.timestamp())
    except ValueError:
        return 0.0


def parse_time_sequence(value) -> list[float]:
    if value is None:
        return []
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "[]"}:
        return []
    parts = [p for p in text.strip("[]()").split("|") if p != ""]
    return [timestamp_or_zero(p) for p in parts]


def seconds_of_day(value: str) -> float:
    text = str(value).strip()
    try:
        time_part = text.split("T", 1)[1] if "T" in text else text
        time_part = time_part.rstrip("Z")
        hh = int(time_part[0:2])
        mm = int(time_part[3:5])
        ss = int(time_part[6:8])
        frac = 0.0
        if len(time_part) > 8 and time_part[8] == ".":
            digits = []
            for ch in time_part[9:]:
                if not ch.isdigit():
                    break
                digits.append(ch)
            if digits:
                frac = float("0." + "".join(digits))
        return hh * 3600.0 + mm * 60.0 + ss + frac
    except Exception:
        return timestamp_or_zero(text)


def parse_iat_sequence(value, target_len: int) -> list[float]:
    if target_len <= 0:
        return []
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null", "[]"}:
        return [0.0] * target_len
    parts = [p for p in text.strip("[]()").split("|") if p != ""]
    if not parts:
        return [0.0] * target_len
    times = [seconds_of_day(p) for p in parts]
    iat = [0.0]
    for prev, cur in zip(times, times[1:]):
        delta = cur - prev
        if delta < 0:
            delta += 86400.0
        iat.append(max(0.0, delta))
    if len(iat) < target_len:
        iat.extend([0.0] * (target_len - len(iat)))
    return iat[:target_len]


def row_to_canonical(row: dict, path: Path, salt: str) -> dict | None:
    row = logical_row(row)
    label_raw = str(first_present(row, ["label"], "")).strip()
    if label_raw not in {"Miner", "Other"}:
        return None
    label = 1 if label_raw == "Miner" else 0
    src_ip = str(first_present(row, ["src_ip"], ""))
    dst_ip = str(first_present(row, ["dst_ip"], ""))
    src_port = int_or_zero(first_present(row, ["src_port"], 0))
    dst_port = int_or_zero(first_present(row, ["dst_port"], 0))
    proto_raw = str(first_present(row, ["protocol", "proto"], "tcp")).lower()
    proto = "tcp" if proto_raw in {"6", "6.0", "tcp"} else proto_raw
    t_first = timestamp_or_zero(first_present(row, ["time_first", "start_time"], 0))
    t_last = timestamp_or_zero(first_present(row, ["time_last", "end_time"], 0))
    duration = max(0.0, t_last - t_first) if t_last else float_or_zero(first_present(row, ["duration"], 0))
    bytes_fwd = int_or_zero(first_present(row, ["bytes", "bytes_fwd"], 0))
    bytes_bwd = int_or_zero(first_present(row, ["bytes_rev", "bytes_bwd"], 0))
    packets_fwd = int_or_zero(first_present(row, ["packets", "packets_fwd"], 0))
    packets_bwd = int_or_zero(first_present(row, ["packets_rev", "packets_bwd"], 0))
    directions = [int_or_zero(x) for x in parse_sequence(first_present(row, ["ppi_pkt_directions", "ppi_directions"], []))]
    pkt_len = [int_or_zero(x) for x in parse_sequence(first_present(row, ["ppi_pkt_lengths", "ppi_lengths"], []))]
    iat = parse_iat_sequence(first_present(row, ["ppi_pkt_times", "ppi_times"], []), len(pkt_len))
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
        "source_record_id": str(first_present(row, ["__row_index", "id", "flow_id"], "")),
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
        "timing_full_available": 1 if pkt_len and any(x > 0 for x in iat) else 0,
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
    limit = int(load_build_config().get("source_row_limits", {}).get("cesnet_miner22") or 0)
    rows = []
    for path in csv_files(rel(args.input)):
        chunk_size = min(args.chunksize, limit) if limit else args.chunksize
        for chunk_index, chunk in enumerate(
            pd.read_csv(path, chunksize=chunk_size, low_memory=False, usecols=use_cesnet_column)
        ):
            chunk = chunk.reset_index().rename(columns={"index": "__row_index"})
            chunk["__row_index"] = chunk["__row_index"] + (chunk_index * args.chunksize)
            for row in chunk.to_dict(orient="records"):
                out = row_to_canonical(row, path, salt)
                if out is not None:
                    rows.append(out)
                    if limit and len(rows) >= limit:
                        break
            if limit and len(rows) >= limit:
                break
        if limit and len(rows) >= limit:
            break
    df = normalize_dataframe(pd.DataFrame(rows))
    write_parquet(df, args.output)
    print(f"wrote {len(df)} CESNET rows to {args.output}")


if __name__ == "__main__":
    main()
