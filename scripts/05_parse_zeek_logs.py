#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from dataset_common import (
    bool_id,
    first_present,
    float_or_zero,
    flow_key_text,
    hmac_hash64,
    int_or_zero,
    load_build_config,
    load_privacy_config,
    load_yaml,
    normalize_dataframe,
    parser_with_root,
    read_zeek_log,
    rel,
    reject_rows,
    sequence_stats,
    string_entropy,
    tld,
    write_parquet,
)

import pandas as pd


TLS_VERSION_IDS = {"SSLv3": 1, "TLSv10": 2, "TLSv11": 3, "TLSv12": 4, "TLSv13": 5}


def log_path(directory: Path, name: str) -> Path:
    for candidate in (directory / f"{name}.log", directory / f"{name}.log.gz"):
        if candidate.exists():
            return candidate
    return directory / f"{name}.log"


def read_source_file(directory: Path) -> str:
    p = directory / "source_file.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return directory.name


def load_packet_rows(source: str) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    root = rel("data/staging/packets") / source
    if not root.exists():
        return out
    for path in root.glob("*.parquet"):
        df = pd.read_parquet(path)
        for row in df.to_dict(orient="records"):
            out.setdefault(int(row["flow_key_hash64"]), []).append(row)
    return out


def parse_vector(value) -> list[str]:
    text = str(value or "").strip()
    if not text or text in {"-", "(empty)"}:
        return []
    return [x for x in text.replace(",", " ").split() if x and x != "-"]


def parse_time(value) -> float:
    try:
        return pd.to_datetime(value, utc=True).timestamp()
    except Exception:
        return 0.0


def best_packet_match(candidates: list[dict], start: float, end: float, packets_total: int, tolerance: float) -> dict | None:
    if not candidates:
        return None
    scored = []
    for row in candidates:
        p_start = float_or_zero(row.get("time_first"))
        p_end = float_or_zero(row.get("time_last"))
        if abs(p_start - start) > tolerance and abs(p_end - end) > tolerance:
            continue
        overlap = max(0.0, min(end, p_end) - max(start, p_start))
        pkt_delta = abs(int_or_zero(row.get("packet_count_observed")) - packets_total)
        scored.append((overlap, -pkt_delta, row))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored[0][2]


def x509_features(x509: pd.DataFrame, ssl_row: dict, salt: str) -> dict:
    if x509.empty:
        return {"cert_observed": 0}
    ids = parse_vector(first_present(ssl_row, ["cert_chain_fuids", "cert_chain_fps"], ""))
    cert_row = None
    if ids and "id" in x509.columns:
        hit = x509[x509["id"].astype(str).isin(ids)]
        if not hit.empty:
            cert_row = hit.iloc[0].to_dict()
    if cert_row is None and not x509.empty:
        return {"cert_observed": 0}
    subject = first_present(cert_row, ["subject"], "")
    issuer = first_present(cert_row, ["issuer"], "")
    nb = first_present(cert_row, ["certificate.not_valid_before", "not_valid_before"], "")
    na = first_present(cert_row, ["certificate.not_valid_after", "not_valid_after"], "")
    validity = max(0.0, (parse_time(na) - parse_time(nb)) / 86400.0) if nb and na else 0.0
    san = first_present(cert_row, ["san.dns", "san_dns"], "")
    return {
        "cert_observed": 1,
        "cert_subject_hash64": hmac_hash64(subject, salt),
        "cert_issuer_hash64": hmac_hash64(issuer, salt),
        "cert_validity_days": validity,
        "cert_key_alg_id": 0,
        "cert_key_length": int_or_zero(first_present(cert_row, ["certificate.key_length", "key_length"], 0)),
        "cert_sig_alg_id": 0,
        "cert_san_count": len(parse_vector(san)),
        "cert_self_signed": 1 if subject and issuer and subject == issuer else 0,
        "cert_chain_len": len(ids),
    }


def flow_features(conn: dict, salt: str) -> dict:
    src_ip = str(first_present(conn, ["id.orig_h", "id_orig_h", "orig_h"], ""))
    dst_ip = str(first_present(conn, ["id.resp_h", "id_resp_h", "resp_h"], ""))
    src_port = int_or_zero(first_present(conn, ["id.orig_p", "id_orig_p", "orig_p"], 0))
    dst_port = int_or_zero(first_present(conn, ["id.resp_p", "id_resp_p", "resp_p"], 0))
    proto = str(first_present(conn, ["proto"], "tcp")).lower()
    duration = float_or_zero(first_present(conn, ["duration"], 0.0))
    orig_bytes = int_or_zero(first_present(conn, ["orig_bytes"], 0))
    resp_bytes = int_or_zero(first_present(conn, ["resp_bytes"], 0))
    orig_pkts = int_or_zero(first_present(conn, ["orig_pkts"], 0))
    resp_pkts = int_or_zero(first_present(conn, ["resp_pkts"], 0))
    ts = float_or_zero(first_present(conn, ["ts"], 0.0))
    bytes_total = orig_bytes + resp_bytes
    packets_total = orig_pkts + resp_pkts
    key_text = flow_key_text(src_ip, src_port, dst_ip, dst_port, proto)
    return {
        "time_first": ts,
        "time_last": ts + max(duration, 0.0),
        "duration": duration,
        "proto": proto,
        "src_ip_hash64": hmac_hash64(src_ip, salt),
        "dst_ip_hash64": hmac_hash64(dst_ip, salt),
        "src_port": src_port,
        "dst_port": dst_port,
        "flow_key_hash64": hmac_hash64(key_text, salt),
        "bytes_total": bytes_total,
        "bytes_fwd": orig_bytes,
        "bytes_bwd": resp_bytes,
        "packets_total": packets_total,
        "packets_fwd": orig_pkts,
        "packets_bwd": resp_pkts,
        "byte_rate": bytes_total / max(duration, 1e-6),
        "packet_rate": packets_total / max(duration, 1e-6),
        "bytes_ratio_fwd": orig_bytes / max(bytes_total, 1),
        "packets_ratio_fwd": orig_pkts / max(packets_total, 1),
    }


def tls_features(ssl_row: dict | None, x509: pd.DataFrame, salt: str) -> dict:
    if not ssl_row:
        return {
            "has_tls": 0,
            "tls_source": "none",
            "tls_metadata_available": 0,
            "tls_full_available": 0,
            "tls_handshake_seen": 0,
        }
    sni = str(first_present(ssl_row, ["server_name", "sni"], "") or "")
    version = str(first_present(ssl_row, ["version"], "") or "")
    cipher = str(first_present(ssl_row, ["cipher"], "") or "")
    alpn = str(first_present(ssl_row, ["next_protocol", "alpn"], "") or "")
    has_tls = 1
    cert = x509_features(x509, ssl_row, salt)
    full = 1 if (version or cipher or cert.get("cert_observed")) else 0
    return {
        "has_tls": has_tls,
        "tls_source": "zeek_ssl_x509" if full else "zeek_ssl",
        "tls_version_id": TLS_VERSION_IDS.get(version, 0),
        "tls_version_hash64": hmac_hash64(version, salt),
        "cipher_id": 0,
        "cipher_hash64": hmac_hash64(cipher, salt),
        "sni_hash64": hmac_hash64(sni, salt),
        "sni_len": len(sni),
        "sni_num_labels": len([p for p in sni.split(".") if p]) if sni else 0,
        "sni_entropy": string_entropy(sni),
        "sni_tld_hash64": hmac_hash64(tld(sni), salt),
        "alpn_id": 0,
        "alpn_hash64": hmac_hash64(alpn, salt),
        "ja3_hash64": hmac_hash64(first_present(ssl_row, ["ja3"], ""), salt),
        "ja3s_hash64": hmac_hash64(first_present(ssl_row, ["ja3s"], ""), salt),
        "tls_resumed": bool_id(first_present(ssl_row, ["resumed"], 0)),
        "tls_established": bool_id(first_present(ssl_row, ["established"], 0)),
        "tls_handshake_seen": 1,
        "tls_metadata_available": 1,
        "tls_full_available": full,
        **cert,
    }


def main() -> None:
    parser = parser_with_root("Parse Zeek logs into canonical source parquet.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--label", type=int, required=True)
    parser.add_argument("--zeek-root", default="data/staging/zeek")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    build = load_build_config()
    salt = load_privacy_config()["salt"]
    sources = load_yaml("configs/sources.yaml")
    source_role = sources.get(args.source, {}).get("source_role", "")
    min_packets = int(build.get("min_packets_per_flow", 3))
    tolerance = float(build.get("merge", {}).get("time_tolerance_seconds", 1.0))
    packet_rows = load_packet_rows(args.source)

    rows = []
    rejected = []
    for directory in sorted((rel(args.zeek_root) / args.source).glob("*")):
        if not directory.is_dir():
            continue
        conn = read_zeek_log(log_path(directory, "conn"))
        if conn.empty:
            continue
        ssl = read_zeek_log(log_path(directory, "ssl"))
        x509 = read_zeek_log(log_path(directory, "x509"))
        source_file = read_source_file(directory)
        ssl_by_uid = {}
        if not ssl.empty and "uid" in ssl.columns:
            ssl_by_uid = {str(r["uid"]): r for r in ssl.to_dict(orient="records")}
        for conn_row in conn.to_dict(orient="records"):
            base = flow_features(conn_row, salt)
            packets_total = base["packets_total"]
            if packets_total and packets_total < min_packets:
                rejected.append({**conn_row, "reject_reason": "too_few_packets"})
                continue
            uid = str(first_present(conn_row, ["uid"], ""))
            tls = tls_features(ssl_by_uid.get(uid), x509, salt)
            packet_match = best_packet_match(
                packet_rows.get(int(base["flow_key_hash64"]), []),
                base["time_first"],
                base["time_last"],
                packets_total,
                tolerance,
            )
            seq = {}
            if packet_match:
                seq_cols = [
                    "seq_len_stored",
                    "seq_pkt_len",
                    "seq_signed_pkt_len",
                    "seq_direction",
                    "seq_iat",
                    "pkt_len_mean",
                    "pkt_len_std",
                    "pkt_len_min",
                    "pkt_len_max",
                    "pkt_len_p10",
                    "pkt_len_p50",
                    "pkt_len_p90",
                    "iat_mean",
                    "iat_std",
                    "iat_min",
                    "iat_max",
                    "iat_p10",
                    "iat_p50",
                    "iat_p90",
                    "iat_cv",
                    "iat_entropy",
                    "iat_zero_ratio",
                    "iat_small_ratio_10ms",
                    "fwd_iat_mean",
                    "bwd_iat_mean",
                    "fwd_bwd_iat_ratio",
                    "burst_count",
                    "burst_mean_packets",
                    "burst_max_packets",
                    "periodicity_autocorr_lag",
                    "periodicity_autocorr_score",
                    "periodicity_fft_peak",
                ]
                seq = {c: packet_match.get(c) for c in seq_cols}
                seq.update({"packet_seq_available": 1, "timing_full_available": 1})
            row = {
                **base,
                **tls,
                **seq,
                "source": args.source,
                "source_role": source_role,
                "source_file": source_file,
                "source_record_id": uid,
                "original_label": "mining" if args.label == 1 else "benign",
                "label": args.label,
                "label_confidence": 1.0,
                "possible_tls_port": 1 if base["dst_port"] in {443, 8443, 9443} and not tls.get("has_tls") else 0,
                "extract_status": "ok",
            }
            rows.append(row)
    if rejected:
        reject_rows(rejected, args.source, "zeek_rejected")
    df = normalize_dataframe(pd.DataFrame(rows))
    output = args.output or f"data/interim/canonical_by_source/{args.source}.parquet"
    write_parquet(df, output)
    print(f"wrote {len(df)} canonical rows to {output}")


if __name__ == "__main__":
    main()

