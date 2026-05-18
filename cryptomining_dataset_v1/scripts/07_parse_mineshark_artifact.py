#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from dataset_common import normalize_dataframe, parser_with_root, read_table, rel, write_parquet

import pandas as pd


def interesting(path: Path) -> bool:
    text = str(path).lower()
    return "obfuscated" in text or "perturbed" in text


def main() -> None:
    parser = parser_with_root("Parse MineShark obfuscated/perturbed artifact tables into canonical parquet.")
    parser.add_argument("--input", default="data/raw/mining/mineshark_artifact/extracted")
    parser.add_argument("--output", default="data/interim/canonical_by_source/mineshark_artifact.parquet")
    args = parser.parse_args()

    rows = []
    for path in sorted(rel(args.input).rglob("*")):
        if not path.is_file() or not interesting(path):
            continue
        suffixes = "".join(path.suffixes).lower()
        if not suffixes.endswith((".csv", ".csv.gz", ".parquet", ".pq")):
            continue
        try:
            df = read_table(path)
        except Exception as exc:
            print(f"skip unreadable MineShark table {path}: {exc}", file=sys.stderr)
            continue
        kind = "obfuscated" if "obfuscated" in str(path).lower() else "perturbed"
        for i, _ in enumerate(df.to_dict(orient="records")):
            rows.append(
                {
                    "source": "mineshark_artifact",
                    "source_role": "mining_obfuscated_perturbed",
                    "source_file": str(path),
                    "source_record_id": f"{path.name}:{i}",
                    "original_label": kind,
                    "label": 1,
                    "label_confidence": 1.0,
                    "has_tls": 0,
                    "tls_source": "none",
                    "tls_metadata_available": 0,
                    "tls_full_available": 0,
                    "packet_seq_available": 0,
                    "timing_full_available": 0,
                    "extract_status": "partial_feature_table",
                    "quality_notes": "MineShark feature layout is artifact-dependent; raw feature columns are not copied unless mapped explicitly.",
                }
            )
    df = normalize_dataframe(pd.DataFrame(rows))
    write_parquet(df, args.output)
    print(f"wrote {len(df)} MineShark rows to {args.output}")


if __name__ == "__main__":
    main()

