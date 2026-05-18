#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"

write_complete_pcap_list() {
  local root="$1"
  local out="$2"
  if [[ ! -d "$root" ]]; then
    : > "$out"
    return 0
  fi
  find "$root" -type f \( -name '*.pcap' -o -name '*.pcapng' \) \
    ! -exec test -e '{}.aria2' ';' -print | sort > "$out"
}

if [[ "${SKIP_DOWNLOAD:-0}" != "1" ]]; then
  PYTHON="$PYTHON" bash scripts/00_download_sources.sh
fi
if [[ "${SKIP_UNPACK:-0}" != "1" ]]; then
  PYTHON="$PYTHON" bash scripts/01_unpack_sources.sh
fi

write_complete_pcap_list data/raw/mining/auto_capture_hf logs/auto_capture_pcap_files.txt
if [[ -s logs/auto_capture_pcap_files.txt ]]; then
  bash scripts/03_run_zeek.sh auto_capture_hf logs/auto_capture_pcap_files.txt
  "$PYTHON" scripts/04_extract_packet_sequences.py --source auto_capture_hf --pcap-list logs/auto_capture_pcap_files.txt
  "$PYTHON" scripts/05_parse_zeek_logs.py --source auto_capture_hf --label 1
fi

"$PYTHON" scripts/06_parse_cesnet.py

write_complete_pcap_list data/raw/mining/cj_sniffer logs/cj_sniffer_pcap_files.txt
if [[ -s logs/cj_sniffer_pcap_files.txt ]]; then
  "$PYTHON" scripts/filter_cj_encrypted.py --labels data/raw/mining/cj_sniffer/labels.csv --pcap-list logs/cj_sniffer_pcap_files.txt --out logs/cj_sniffer_encrypted_pcap_files.txt
  bash scripts/03_run_zeek.sh cj_sniffer logs/cj_sniffer_encrypted_pcap_files.txt
  "$PYTHON" scripts/04_extract_packet_sequences.py --source cj_sniffer --pcap-list logs/cj_sniffer_encrypted_pcap_files.txt
  "$PYTHON" scripts/05_parse_zeek_logs.py --source cj_sniffer --label 1
fi

"$PYTHON" scripts/07_parse_mineshark_artifact.py

write_complete_pcap_list data/raw/non_mining/hikari2021/pcap logs/hikari_pcap_files_downloaded.txt || true
write_complete_pcap_list data/raw/non_mining/hikari2021/extracted logs/hikari_pcap_files_extracted.txt || true
sort -u logs/hikari_pcap_files_downloaded.txt logs/hikari_pcap_files_extracted.txt > logs/hikari_pcap_files.txt
if [[ -s logs/hikari_pcap_files.txt ]]; then
  bash scripts/03_run_zeek.sh hikari2021 logs/hikari_pcap_files.txt
  "$PYTHON" scripts/04_extract_packet_sequences.py --source hikari2021 --pcap-list logs/hikari_pcap_files.txt
fi
"$PYTHON" scripts/08_parse_hikari.py
"$PYTHON" scripts/09_parse_iot23_mcfp.py

"$PYTHON" scripts/10_normalize_schema.py
"$PYTHON" scripts/11_merge_and_dedupe.py
"$PYTHON" scripts/12_validate_and_stats.py ${ALLOW_INCOMPLETE_COVERAGE:+--allow-incomplete-coverage}
"$PYTHON" scripts/13_export_final.py
