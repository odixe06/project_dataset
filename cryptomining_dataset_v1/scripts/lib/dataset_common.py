#!/usr/bin/env python3
"""Shared utilities for the cryptomining dataset build pipeline."""

from __future__ import annotations

import argparse
import ast
import csv
import gzip
import hashlib
import hmac
import json
import math
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised only before requirements are installed.
    np = None

try:
    import pandas as pd
except ImportError:  # pragma: no cover - exercised only before requirements are installed.
    pd = None


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_VERSION = "mining_dataset_v1"
PRIVATE_RAW_TOKENS = ("raw_payload", "payload", "raw_sni", "server_name_raw", "src_ip", "dst_ip")
ARRAY_COLUMNS = {"seq_pkt_len", "seq_signed_pkt_len", "seq_direction", "seq_iat"}
PROVENANCE_COLUMNS = {
    "source",
    "source_role",
    "source_file",
    "source_record_id",
    "original_label",
    "extract_status",
    "quality_notes",
    "hard_negative_type",
}


def rel(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def load_yaml(path: str | Path) -> dict[str, Any]:
    with rel(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_build_config() -> dict[str, Any]:
    return load_yaml("configs/build.yaml")


def load_privacy_config() -> dict[str, Any]:
    cfg = load_yaml("configs/privacy.yaml")
    local_path = rel("configs/privacy.local.yaml")
    if local_path.exists():
        cfg.update(load_yaml(local_path))
    salt = str(cfg.get("salt", "")).strip()
    if not salt or salt in {"CHANGE_ME_LOCAL_ONLY", "replace-with-local-secret"}:
        env_salt = os.environ.get("DATASET_PRIVACY_SALT", "").strip()
        if env_salt:
            cfg["salt"] = env_salt
        else:
            raise RuntimeError(
                "Missing privacy salt. Set DATASET_PRIVACY_SALT or edit configs/privacy.yaml locally."
            )
    return cfg


def load_schema(path: str | Path = "configs/schema.yaml") -> tuple[str, list[dict[str, Any]]]:
    cfg = load_yaml(path)
    return cfg.get("schema_version", SCHEMA_VERSION), cfg.get("columns", [])


def schema_column_names(path: str | Path = "configs/schema.yaml") -> list[str]:
    _, columns = load_schema(path)
    return [c["name"] for c in columns]


def schema_padding(path: str | Path = "configs/schema.yaml") -> dict[str, Any]:
    _, columns = load_schema(path)
    return {c["name"]: c.get("padding") for c in columns}


def hmac_hash64(value: Any, salt: str) -> int:
    if value is None:
        return 0
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null", "unknown", "-"}:
        return 0
    digest = hmac.new(salt.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big") & ((1 << 63) - 1)


def sample_id(row: dict[str, Any]) -> str:
    parts = [
        str(row.get("schema_version", SCHEMA_VERSION)),
        str(row.get("source", "")),
        str(row.get("source_file", "")),
        str(row.get("source_record_id", "")),
        str(row.get("proto", "")),
        str(row.get("src_ip_hash64", "")),
        str(row.get("dst_ip_hash64", "")),
        str(row.get("src_port", "")),
        str(row.get("dst_port", "")),
        f"{float_or_zero(row.get('time_first')):.6f}",
        f"{float_or_zero(row.get('time_last')):.6f}",
        str(row.get("label", "")),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def detect_file_type(path: Path) -> str:
    suffixes = "".join(path.suffixes).lower()
    if suffixes.endswith((".pcap", ".pcapng", ".cap")):
        return "pcap"
    if suffixes.endswith((".csv", ".csv.gz", ".csv.zip")):
        return "csv"
    if suffixes.endswith((".parquet", ".pq")):
        return "parquet"
    if suffixes.endswith((".log", ".log.gz", ".labeled")):
        return "zeek_log"
    if suffixes.endswith((".tar.gz", ".tgz", ".zip", ".7z")):
        return "archive"
    return path.suffix.lower().lstrip(".") or "unknown"


def float_or_zero(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        out = float(value)
        if math.isnan(out) or math.isinf(out):
            return 0.0
        return out
    except Exception:
        return 0.0


def int_or_zero(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        if isinstance(value, str) and value.strip().lower() in {"-", "nan", "none", "null"}:
            return 0
        return int(float(value))
    except Exception:
        return 0


def bool_id(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y", "established"}:
        return 1
    if text in {"0", "false", "f", "no", "n", "", "-", "none", "nan"}:
        return 0
    return 0


def first_present(row: Any, names: Iterable[str], default: Any = None) -> Any:
    lower_map = {str(k).lower(): k for k in row.keys()}
    for name in names:
        key = lower_map.get(name.lower())
        if key is not None:
            val = row[key]
            if val is not None and str(val).strip() != "":
                return val
    return default


def parse_sequence(value: Any) -> list[float]:
    if value is None:
        return []
    array_types = [list, tuple]
    if np is not None:
        array_types.append(np.ndarray)
    if pd is not None:
        array_types.append(pd.Series)
    if isinstance(value, tuple(array_types)):
        return [float_or_zero(v) for v in value]
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "[]"}:
        return []
    if "|" in text:
        text = text.strip("[]()")
        return [float_or_zero(p) for p in text.split("|") if p != ""]
    try:
        parsed = ast.literal_eval(text)
        if isinstance(parsed, (list, tuple)):
            return [float_or_zero(v) for v in parsed]
    except Exception:
        pass
    text = text.strip("[]()")
    parts = re.split(r"[\s,;|]+", text)
    return [float_or_zero(p) for p in parts if p != ""]


def string_entropy(text: Any) -> float:
    if text is None:
        return 0.0
    s = str(text)
    if not s:
        return 0.0
    counts = Counter(s)
    total = len(s)
    return float(-sum((n / total) * math.log2(n / total) for n in counts.values()))


def tld(value: Any) -> str:
    text = str(value or "").strip().strip(".").lower()
    if "." not in text:
        return ""
    return text.rsplit(".", 1)[-1]


def canonical_tuple(src_ip: str, src_port: Any, dst_ip: str, dst_port: Any, proto: Any) -> tuple[str, int, str, int, str]:
    left = (str(src_ip), int_or_zero(src_port))
    right = (str(dst_ip), int_or_zero(dst_port))
    proto_s = str(proto or "tcp").lower()
    if left <= right:
        return left[0], left[1], right[0], right[1], proto_s
    return right[0], right[1], left[0], left[1], proto_s


def flow_key_text(src_ip: str, src_port: Any, dst_ip: str, dst_port: Any, proto: Any) -> str:
    a_ip, a_port, b_ip, b_port, proto_s = canonical_tuple(src_ip, src_port, dst_ip, dst_port, proto)
    return f"{a_ip}:{a_port}-{b_ip}:{b_port}-{proto_s}"


def quantile(values: list[float], q: float) -> float:
    require_numpy()
    if not values:
        return 0.0
    return float(np.quantile(np.asarray(values, dtype=float), q))


def sequence_stats(pkt_len: list[float], signed_len: list[float], direction: list[float], iat: list[float]) -> dict[str, Any]:
    require_numpy()
    abs_lengths = [abs(float_or_zero(v)) for v in (pkt_len or signed_len)]
    iats = [max(0.0, float_or_zero(v)) for v in iat]
    dirs = [int_or_zero(v) for v in direction]
    out: dict[str, Any] = {
        "pkt_len_mean": float(np.mean(abs_lengths)) if abs_lengths else 0.0,
        "pkt_len_std": float(np.std(abs_lengths)) if len(abs_lengths) > 1 else 0.0,
        "pkt_len_min": float(min(abs_lengths)) if abs_lengths else 0.0,
        "pkt_len_max": float(max(abs_lengths)) if abs_lengths else 0.0,
        "pkt_len_p10": quantile(abs_lengths, 0.10),
        "pkt_len_p50": quantile(abs_lengths, 0.50),
        "pkt_len_p90": quantile(abs_lengths, 0.90),
        "iat_mean": float(np.mean(iats)) if iats else 0.0,
        "iat_std": float(np.std(iats)) if len(iats) > 1 else 0.0,
        "iat_min": float(min(iats)) if iats else 0.0,
        "iat_max": float(max(iats)) if iats else 0.0,
        "iat_p10": quantile(iats, 0.10),
        "iat_p50": quantile(iats, 0.50),
        "iat_p90": quantile(iats, 0.90),
        "iat_zero_ratio": float(sum(1 for x in iats if x == 0) / len(iats)) if iats else 0.0,
        "iat_small_ratio_10ms": float(sum(1 for x in iats if x <= 0.010) / len(iats)) if iats else 0.0,
    }
    out["iat_cv"] = out["iat_std"] / out["iat_mean"] if out["iat_mean"] > 0 else 0.0
    out["iat_entropy"] = entropy_numeric(iats)
    fwd = [x for x, d in zip(iats, dirs) if d == 1]
    bwd = [x for x, d in zip(iats, dirs) if d == -1]
    out["fwd_iat_mean"] = float(np.mean(fwd)) if fwd else 0.0
    out["bwd_iat_mean"] = float(np.mean(bwd)) if bwd else 0.0
    out["fwd_bwd_iat_ratio"] = out["fwd_iat_mean"] / out["bwd_iat_mean"] if out["bwd_iat_mean"] > 0 else 0.0
    bursts = burst_lengths(iats)
    out["burst_count"] = len(bursts)
    out["burst_mean_packets"] = float(np.mean(bursts)) if bursts else 0.0
    out["burst_max_packets"] = int(max(bursts)) if bursts else 0
    lag, score = autocorr_peak(iats)
    out["periodicity_autocorr_lag"] = lag
    out["periodicity_autocorr_score"] = score
    out["periodicity_fft_peak"] = fft_peak(iats)
    return out


def entropy_numeric(values: list[float], bins: int = 10) -> float:
    require_numpy()
    if len(values) < 2:
        return 0.0
    hist, _ = np.histogram(np.asarray(values, dtype=float), bins=bins)
    total = hist.sum()
    if total == 0:
        return 0.0
    probs = hist[hist > 0] / total
    return float(-(probs * np.log2(probs)).sum())


def burst_lengths(iats: list[float], threshold: float = 1.0) -> list[int]:
    if not iats:
        return []
    bursts: list[int] = []
    cur = 1
    for x in iats[1:]:
        if x <= threshold:
            cur += 1
        else:
            bursts.append(cur)
            cur = 1
    bursts.append(cur)
    return bursts


def autocorr_peak(values: list[float]) -> tuple[int, float]:
    require_numpy()
    if len(values) < 4:
        return 0, 0.0
    arr = np.asarray(values, dtype=float)
    arr = arr - arr.mean()
    denom = float(np.dot(arr, arr))
    if denom <= 0:
        return 0, 0.0
    scores = []
    max_lag = min(len(arr) - 1, 64)
    for lag in range(1, max_lag + 1):
        score = float(np.dot(arr[:-lag], arr[lag:]) / denom)
        scores.append((lag, score))
    return max(scores, key=lambda x: x[1])


def fft_peak(values: list[float]) -> float:
    require_numpy()
    if len(values) < 4:
        return 0.0
    arr = np.asarray(values, dtype=float)
    arr = arr - arr.mean()
    mag = np.abs(np.fft.rfft(arr))
    if len(mag) <= 1:
        return 0.0
    return float(mag[1:].max())


def normalize_row(
    row: dict[str, Any],
    schema_path: str | Path = "configs/schema.yaml",
    schema_cache: tuple[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    schema_version, columns = schema_cache or load_schema(schema_path)
    out: dict[str, Any] = {}
    row = dict(row)
    row.setdefault("schema_version", schema_version)
    for col in columns:
        name = col["name"]
        value = row.get(name, col.get("padding"))
        if name in ARRAY_COLUMNS:
            out[name] = value if isinstance(value, list) else parse_sequence(value)
        else:
            out[name] = value
    if not out.get("sample_id"):
        out["sample_id"] = sample_id(out)
    return out


def normalize_dataframe(df: pd.DataFrame, schema_path: str | Path = "configs/schema.yaml") -> pd.DataFrame:
    require_pandas()
    schema_cache = load_schema(schema_path)
    rows = [normalize_row(r, schema_path, schema_cache) for r in df.to_dict(orient="records")]
    cols = [c["name"] for c in schema_cache[1]]
    return pd.DataFrame(rows, columns=cols)


def write_parquet(df: pd.DataFrame, path: str | Path) -> None:
    require_pandas()
    path = rel(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, engine="pyarrow", compression="zstd", index=False)


def read_table(path: str | Path) -> pd.DataFrame:
    require_pandas()
    path = rel(path)
    suffixes = "".join(path.suffixes).lower()
    if suffixes.endswith(".parquet") or suffixes.endswith(".pq"):
        return pd.read_parquet(path)
    if suffixes.endswith(".csv.gz"):
        return pd.read_csv(path, compression="gzip")
    if suffixes.endswith(".csv"):
        return pd.read_csv(path)
    raise ValueError(f"Unsupported table file: {path}")


def read_zeek_log(path: Path) -> pd.DataFrame:
    require_pandas()
    if not path.exists():
        return pd.DataFrame()
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        first_data = ""
        pos_lines = []
        for line in f:
            if line.strip():
                first_data = line.strip()
                pos_lines.append(line)
                break
        if not first_data:
            return pd.DataFrame()
        rest = f.readlines()
    lines = pos_lines + rest
    if first_data.startswith("{"):
        return pd.DataFrame(json.loads(line) for line in lines if line.strip() and not line.startswith("#"))
    fields: list[str] | None = None
    rows: list[dict[str, Any]] = []
    for line in lines:
        line = line.rstrip("\n")
        if not line:
            continue
        if line.startswith("#fields"):
            fields = line.split("\t")[1:]
            continue
        if line.startswith("#"):
            continue
        if fields is None:
            continue
        parts = line.split("\t")
        rows.append({k: (parts[i] if i < len(parts) else "") for i, k in enumerate(fields)})
    return pd.DataFrame(rows)


def reject_rows(rows: list[dict[str, Any]], source: str, reason: str) -> None:
    require_pandas()
    if not rows:
        return
    path = rel(f"data/interim/rejected/{source}_{reason}.parquet")
    write_parquet(pd.DataFrame(rows), path)


def export_json(obj: Any, path: str | Path) -> None:
    path = rel(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def scalar_csv_export(df: pd.DataFrame, path: str | Path) -> None:
    path = rel(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    scalar_cols = [c for c in df.columns if c not in ARRAY_COLUMNS]
    with gzip.open(path, "wt", encoding="utf-8", newline="") as f:
        df[scalar_cols].to_csv(f, index=False, quoting=csv.QUOTE_MINIMAL)


def parser_with_root(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--root", default=str(ROOT), help="Dataset root. Defaults to this project directory.")
    return parser


def require_pandas() -> None:
    if pd is None:
        raise RuntimeError("pandas is required for this step. Install dependencies with: pip install -r requirements.txt")


def require_numpy() -> None:
    if np is None:
        raise RuntimeError("numpy is required for this step. Install dependencies with: pip install -r requirements.txt")
