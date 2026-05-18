#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from dataset_common import ARRAY_COLUMNS, export_json, load_schema, parser_with_root, read_table, rel, scalar_csv_export


def main() -> None:
    parser = parser_with_root("Export final schema, vocab, data dictionary, and scalar CSV.")
    parser.add_argument("--input", default="data/final/samples.parquet")
    parser.add_argument("--out-dir", default="data/final")
    args = parser.parse_args()
    df = read_table(args.input)
    schema_version, columns = load_schema()
    out_dir = rel(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    export_json({"schema_version": schema_version, "columns": columns}, out_dir / "schema.json")
    vocab = {
        "tls_version": {"unknown": 0, "SSLv3": 1, "TLSv10": 2, "TLSv11": 3, "TLSv12": 4, "TLSv13": 5},
        "cipher": {"unknown": 0},
        "alpn": {"unknown": 0},
        "cert_key_alg": {"unknown": 0},
        "cert_sig_alg": {"unknown": 0},
    }
    export_json(vocab, out_dir / "feature_vocab.json")

    lines = ["# Data Dictionary", "", "| column | dtype | group | padding | can_use_for_model_input |", "|---|---:|---|---:|---:|"]
    for col in columns:
        lines.append(
            f"| {col['name']} | {col.get('dtype','')} | {col.get('group','')} | {col.get('padding','')} | {str(col.get('can_use_for_model_input', False)).lower()} |"
        )
    (out_dir / "data_dictionary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    scalar_csv_export(df, out_dir / "samples.csv.gz")
    print(f"exported final artifacts in {out_dir}; sequence columns kept only in parquet: {sorted(ARRAY_COLUMNS)}")


if __name__ == "__main__":
    main()

