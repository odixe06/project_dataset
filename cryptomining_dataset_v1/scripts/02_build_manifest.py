#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from dataset_common import detect_file_type, export_json, load_yaml, now_iso, parser_with_root, rel, sha256_file


def source_for(path: Path) -> str:
    parts = path.parts
    known = {
        "auto_capture_hf",
        "cesnet_miner22",
        "cj_sniffer",
        "mineshark_artifact",
        "hikari2021",
        "iot23_mcfp",
    }
    for part in parts:
        if part in known:
            return part
    return "unknown"


def main() -> None:
    parser = parser_with_root("Build raw file manifest with sha256 checksums.")
    parser.add_argument("--input-root", default="data/raw")
    parser.add_argument("--output", default="data/final/manifest.json")
    args = parser.parse_args()

    src_cfg = load_yaml("configs/sources.yaml")
    input_root = rel(args.input_root)
    records = []
    for path in sorted(p for p in input_root.rglob("*") if p.is_file() and p.suffix != ".aria2"):
        source = source_for(path)
        cfg = src_cfg.get(source, {})
        try:
            size_bytes = path.stat().st_size
            sha256 = sha256_file(path)
        except FileNotFoundError:
            continue
        records.append(
            {
                "source": source,
                "path": str(path.relative_to(rel("."))),
                "size_bytes": size_bytes,
                "sha256": sha256,
                "file_type": detect_file_type(path),
                "downloaded_at": now_iso(),
                "record_url": cfg.get("record_url", ""),
                "license_or_rights": cfg.get("license_or_rights", "see_source_record"),
            }
        )
    export_json({"created_at": now_iso(), "files": records}, args.output)
    print(f"wrote {len(records)} manifest entries to {args.output}")


if __name__ == "__main__":
    main()
