#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from dataset_common import PROVENANCE_COLUMNS, normalize_dataframe, parser_with_root, read_table, rel, write_parquet

import pandas as pd


def main() -> None:
    parser = parser_with_root("Merge canonical per-source parquet files and deduplicate sample_id.")
    parser.add_argument("--input-root", default="data/interim/canonical_by_source")
    parser.add_argument("--output", default="data/final/samples.parquet")
    args = parser.parse_args()
    frames = []
    for path in sorted(rel(args.input_root).glob("*.parquet")):
        df = normalize_dataframe(read_table(path))
        if len(df):
            frames.append(df)
            print(f"loaded {len(df)} rows from {path}")
    merged = pd.concat(frames, ignore_index=True) if frames else normalize_dataframe(pd.DataFrame())
    before = len(merged)
    if "sample_id" in merged.columns:
        merged = merged.drop_duplicates(subset=["sample_id"], keep="first")
    print(f"dedupe: {before} -> {len(merged)} rows")
    write_parquet(merged, args.output)
    prov_cols = [c for c in merged.columns if c in PROVENANCE_COLUMNS or c in {"sample_id", "label"}]
    write_parquet(merged[prov_cols], "data/final/provenance.parquet")


if __name__ == "__main__":
    main()

