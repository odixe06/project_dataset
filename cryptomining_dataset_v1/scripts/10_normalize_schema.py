#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from dataset_common import normalize_dataframe, parser_with_root, read_table, rel, write_parquet


def main() -> None:
    parser = parser_with_root("Normalize canonical source parquet files to configs/schema.yaml.")
    parser.add_argument("--input-root", default="data/interim/canonical_by_source")
    parser.add_argument("--schema", default="configs/schema.yaml")
    args = parser.parse_args()
    for path in sorted(rel(args.input_root).glob("*.parquet")):
        df = read_table(path)
        out = normalize_dataframe(df, args.schema)
        write_parquet(out, path)
        print(f"normalized {path} ({len(out)} rows)")


if __name__ == "__main__":
    main()

