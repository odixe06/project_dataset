#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from dataset_common import export_json, load_build_config, load_schema, parser_with_root, read_table, rel

import pandas as pd


FORBIDDEN_COLUMNS = {"src_ip", "dst_ip", "server_name", "server_name_raw", "raw_sni", "payload", "raw_payload"}


def counts(df: pd.DataFrame, cols: list[str]) -> dict:
    if df.empty:
        return {}
    if len(cols) == 1:
        return {str(k): int(v) for k, v in df[cols[0]].value_counts(dropna=False).to_dict().items()}
    out = {}
    grouped = df.groupby(cols, dropna=False).size()
    for idx, value in grouped.items():
        key = "|".join(str(x) for x in (idx if isinstance(idx, tuple) else (idx,)))
        out[key] = int(value)
    return out


def quantiles(df: pd.DataFrame, col: str) -> dict:
    if df.empty or col not in df:
        return {}
    return {str(q): float(df[col].quantile(q)) for q in [0.1, 0.5, 0.9, 0.99]}


def main() -> None:
    parser = parser_with_root("Validate final dataset and write stats.")
    parser.add_argument("--input", default="data/final/samples.parquet")
    parser.add_argument("--out-dir", default="data/final")
    parser.add_argument("--allow-incomplete-coverage", action="store_true")
    args = parser.parse_args()

    input_path = rel(args.input)
    if not input_path.exists():
        raise SystemExit(f"missing final dataset: {input_path}")
    df = read_table(input_path)
    _, columns = load_schema()
    expected = [c["name"] for c in columns]
    errors = []
    warnings = []
    if list(df.columns) != expected:
        missing = [c for c in expected if c not in df.columns]
        extra = [c for c in df.columns if c not in expected]
        errors.append(f"schema mismatch missing={missing} extra={extra}")
    if df.empty:
        errors.append("dataset is empty")
    if "sample_id" in df and (df["sample_id"].isna().any() or df["sample_id"].duplicated().any()):
        errors.append("sample_id must be non-null and unique")
    labels = set(df["label"].dropna().astype(int).tolist()) if "label" in df else set()
    if labels - {0, 1}:
        errors.append(f"label outside {{0,1}}: {sorted(labels)}")
    if not {0, 1}.issubset(labels):
        errors.append(f"dataset must contain both labels 0 and 1; found {sorted(labels)}")
    bad_cols = sorted(FORBIDDEN_COLUMNS.intersection(df.columns))
    if bad_cols:
        errors.append(f"forbidden raw/private columns in final dataset: {bad_cols}")
    if "duration" in df and (df["duration"].fillna(0) < 0).any():
        errors.append("duration must be >= 0")
    if "packets_total" in df and (df["packets_total"].fillna(0) < 0).any():
        errors.append("packets_total must be >= 0")
    if "has_tls" in df and not set(df["has_tls"].dropna().astype(int).unique()).issubset({0, 1}):
        errors.append("has_tls must be binary")

    build = load_build_config()
    qg = build.get("quality_gates", {})
    coverage_failures = []
    if qg.get("require_label1_tls_full", True):
        ok = ((df.get("label") == 1) & (df.get("tls_full_available") == 1)).any()
        if not ok:
            coverage_failures.append("missing label=1 with full TLS metadata")
    if qg.get("require_label0_hikari_tls_full", True):
        ok = ((df.get("label") == 0) & (df.get("source") == "hikari2021") & (df.get("tls_full_available") == 1)).any()
        if not ok:
            coverage_failures.append("missing HIKARI label=0 with full TLS metadata")
    for source in qg.get("require_sources", []):
        if source not in set(df.get("source", pd.Series(dtype=str)).dropna().astype(str)):
            coverage_failures.append(f"missing required source {source}")
    if coverage_failures:
        message = "; ".join(coverage_failures)
        if args.allow_incomplete_coverage:
            warnings.append(message)
        else:
            errors.append(message)

    stats = {
        "total_samples": int(len(df)),
        "by_label": counts(df, ["label"]),
        "by_source": counts(df, ["source"]),
        "by_source_label": counts(df, ["source", "label"]),
        "tls_coverage": counts(df, ["label", "has_tls"]),
        "sequence_coverage": counts(df, ["label", "packet_seq_available"]),
        "missing_rate_by_feature": {c: float(df[c].isna().mean()) for c in df.columns},
        "duration_quantiles_by_label": {str(k): quantiles(g, "duration") for k, g in df.groupby("label")} if "label" in df else {},
        "packet_count_quantiles_by_label": {str(k): quantiles(g, "packets_total") for k, g in df.groupby("label")} if "label" in df else {},
        "tls_version_by_label": counts(df, ["label", "tls_version_id"]),
        "top_cipher_hash_by_label": counts(df, ["label", "cipher_hash64"]),
        "top_ja3_hash_by_label": counts(df, ["label", "ja3_hash64"]),
        "warnings": warnings,
        "errors": errors,
    }
    export_json(stats, Path(args.out_dir) / "stats.json")
    report = [
        "# Dataset Stats Report",
        "",
        f"Total samples: {len(df)}",
        "",
        "## Counts By Label",
        str(stats["by_label"]),
        "",
        "## Counts By Source And Label",
        str(stats["by_source_label"]),
        "",
        "## TLS Coverage",
        str(stats["tls_coverage"]),
        "",
        "## Sequence Coverage",
        str(stats["sequence_coverage"]),
        "",
        "## Warnings",
        "\n".join(f"- {w}" for w in warnings) or "- none",
        "",
        "## Errors",
        "\n".join(f"- {e}" for e in errors) or "- none",
        "",
        "## Training Notes",
        "- Do not use provenance columns as default model inputs.",
        "- Prefer source/file group splits for downstream generalization checks.",
    ]
    out_report = rel(Path(args.out_dir) / "stats_report.md")
    out_report.write_text("\n".join(report) + "\n", encoding="utf-8")
    if errors:
        raise SystemExit("validation failed: " + "; ".join(errors))
    print(f"validation passed for {len(df)} rows")


if __name__ == "__main__":
    main()

