#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import csv
import sys


FIELDNAMES = [
    "id",
    "timestamp",
    "mining_device_config",
    "is_complete",
    "encrypted",
    "hash_rate_1",
    "hash_rate_2",
    "hash_rate_3",
    "submission_number",
    "coin_type",
    "mining_software",
    "algo",
    "whether_cryptojacking",
    "length",
]


def read_label_rows(path: str) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
        sample = f.readline()
        f.seek(0)
        first_cell = sample.split(",", 1)[0].strip().lower()
        if first_cell in {"id", "pcap_id"}:
            return list(csv.DictReader(f))
        return list(csv.DictReader(f, fieldnames=FIELDNAMES))


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter CJ-Sniffer PCAP list to labels with encrypted=yes.")
    parser.add_argument("--labels", required=True)
    parser.add_argument("--pcap-list", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    encrypted_ids = set()
    for row in read_label_rows(args.labels):
        lower = {str(k).lower().strip(): v for k, v in row.items()}
        if str(lower.get("encrypted", "")).strip().lower() == "yes":
            encrypted_ids.add(str(lower.get("id", "")).strip())
    fallback_all = not encrypted_ids
    if fallback_all:
        print("WARNING: no CJ labels have encrypted=yes; keeping all CJ PCAPs as mining source coverage.", file=sys.stderr)
    kept = []
    with open(args.pcap_list, "r", encoding="utf-8") as f:
        for line in f:
            path = line.strip()
            if not path:
                continue
            if fallback_all or Path(path).stem in encrypted_ids:
                kept.append(path)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    print(f"kept {len(kept)} encrypted CJ pcaps")


if __name__ == "__main__":
    main()
