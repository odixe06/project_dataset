#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${SKIP_DOWNLOAD:-0}" != "1" ]]; then
  bash scripts/00_download_sources.sh
fi
if [[ "${SKIP_UNPACK:-0}" != "1" ]]; then
  bash scripts/01_unpack_sources.sh
fi

find data/raw/mining/auto_capture_hf -type f \( -name '*.pcap' -o -name '*.pcapng' \) | sort > logs/auto_capture_pcap_files.txt
if [[ -s logs/auto_capture_pcap_files.txt ]]; then
  bash scripts/03_run_zeek.sh auto_capture_hf logs/auto_capture_pcap_files.txt
  python3 scripts/04_extract_packet_sequences.py --source auto_capture_hf --pcap-list logs/auto_capture_pcap_files.txt
  python3 scripts/05_parse_zeek_logs.py --source auto_capture_hf --label 1
fi

python3 scripts/06_parse_cesnet.py

find data/raw/mining/cj_sniffer -type f \( -name '*.pcap' -o -name '*.pcapng' \) | sort > logs/cj_sniffer_pcap_files.txt
if [[ -s logs/cj_sniffer_pcap_files.txt ]]; then
  python3 scripts/filter_cj_encrypted.py --labels data/raw/mining/cj_sniffer/labels.csv --pcap-list logs/cj_sniffer_pcap_files.txt --out logs/cj_sniffer_encrypted_pcap_files.txt
  bash scripts/03_run_zeek.sh cj_sniffer logs/cj_sniffer_encrypted_pcap_files.txt
  python3 scripts/04_extract_packet_sequences.py --source cj_sniffer --pcap-list logs/cj_sniffer_encrypted_pcap_files.txt
  python3 scripts/05_parse_zeek_logs.py --source cj_sniffer --label 1
fi

python3 scripts/07_parse_mineshark_artifact.py

find data/raw/non_mining/hikari2021/pcap -type f \( -name '*.pcap' -o -name '*.pcapng' \) | sort > logs/hikari_pcap_files.txt || true
if [[ -s logs/hikari_pcap_files.txt ]]; then
  bash scripts/03_run_zeek.sh hikari2021 logs/hikari_pcap_files.txt
  python3 scripts/04_extract_packet_sequences.py --source hikari2021 --pcap-list logs/hikari_pcap_files.txt
fi
python3 scripts/08_parse_hikari.py
python3 scripts/09_parse_iot23_mcfp.py

python3 scripts/10_normalize_schema.py
python3 scripts/11_merge_and_dedupe.py
python3 scripts/12_validate_and_stats.py ${ALLOW_INCOMPLETE_COVERAGE:+--allow-incomplete-coverage}
python3 scripts/13_export_final.py

