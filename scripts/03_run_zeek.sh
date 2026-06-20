#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ $# -lt 2 ]]; then
  printf 'usage: %s <source> <pcap_list>\n' "$0" >&2
  exit 2
fi

SOURCE="$1"
PCAP_LIST="$2"
OUT_ROOT="$ROOT/data/staging/zeek/$SOURCE"
mkdir -p "$OUT_ROOT"

if ! command -v zeek >/dev/null 2>&1; then
  printf 'ERROR: zeek is not installed or not on PATH.\n' >&2
  exit 1
fi

while IFS= read -r PCAP || [[ -n "$PCAP" ]]; do
  [[ -z "$PCAP" ]] && continue
  if [[ "$PCAP" = /* ]]; then
    ABS_PCAP="$PCAP"
  else
    ABS_PCAP="$ROOT/$PCAP"
  fi
  if [[ ! -f "$ABS_PCAP" ]]; then
    printf 'skip missing pcap: %s\n' "$ABS_PCAP" >&2
    continue
  fi
  BASE="$(basename "$ABS_PCAP")"
  HASH="$(printf '%s' "$ABS_PCAP" | sha1sum | awk '{print substr($1,1,10)}')"
  OUT_DIR="$OUT_ROOT/${BASE%.*}_${HASH}"
  mkdir -p "$OUT_DIR"
  printf '%s\n' "$ABS_PCAP" > "$OUT_DIR/source_file.txt"
  (
    cd "$OUT_DIR"
    if ! zeek -C -r "$ABS_PCAP" LogAscii::use_json=T; then
      rm -f ./*.log
      zeek -C -r "$ABS_PCAP"
    fi
  )
done < "$PCAP_LIST"

