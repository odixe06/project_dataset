#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import csv
import re


def main() -> None:
    parser = argparse.ArgumentParser(description="Filter CJ-Sniffer PCAP list to labels with encrypted=yes.")
    parser.add_argument("--labels", required=True)
    parser.add_argument("--pcap-list", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    encrypted_ids = set()
    with open(args.labels, "r", encoding="utf-8", errors="replace", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lower = {k.lower().strip(): v for k, v in row.items()}
            if str(lower.get("encrypted", "")).strip().lower() == "yes":
                encrypted_ids.add(str(lower.get("id", lower.get("ID", ""))).strip())
    kept = []
    with open(args.pcap_list, "r", encoding="utf-8") as f:
        for line in f:
            path = line.strip()
            if not path:
                continue
            stem = Path(path).stem
            ids = set(re.findall(r"\d+", stem))
            if ids & encrypted_ids:
                kept.append(path)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    print(f"kept {len(kept)} encrypted CJ pcaps")


if __name__ == "__main__":
    main()

