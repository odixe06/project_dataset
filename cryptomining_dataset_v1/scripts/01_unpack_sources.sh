#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"

unpack_tar() {
  local file="$1"
  local out="$2"
  if [[ -f "$file" ]]; then
    mkdir -p "$out"
    tar -xzf "$file" -C "$out"
  else
    printf 'skip missing archive %s\n' "$file"
  fi
}

unpack_zip() {
  local file="$1"
  local out="$2"
  if [[ -f "$file" ]]; then
    mkdir -p "$out"
    unzip -n "$file" -d "$out"
  else
    printf 'skip missing zip %s\n' "$file"
  fi
}

unpack_tar data/raw/mining/cesnet_miner22/DeCryptoDatasets.tar.gz data/raw/mining/cesnet_miner22/extracted
unpack_tar data/raw/mining/mineshark_artifact/MineShark_AE.tar.gz data/raw/mining/mineshark_artifact/extracted
unpack_zip data/raw/non_mining/hikari2021/ALLFLOWMETER_HIKARI2021.csv.zip data/raw/non_mining/hikari2021/extracted
unpack_zip data/raw/non_mining/hikari2021/ground-truth.zip data/raw/non_mining/hikari2021/extracted

if [[ -f data/raw/non_mining/iot23_mcfp/iot_23_datasets_full.tar.gz ]]; then
  unpack_tar data/raw/non_mining/iot23_mcfp/iot_23_datasets_full.tar.gz data/raw/non_mining/iot23_mcfp/extracted
elif [[ -f data/raw/non_mining/iot23_mcfp/iot_23_datasets_small.tar.gz ]]; then
  unpack_tar data/raw/non_mining/iot23_mcfp/iot_23_datasets_small.tar.gz data/raw/non_mining/iot23_mcfp/extracted
else
  printf 'skip missing IoT-23 archive\n'
fi

"$PYTHON" scripts/02_build_manifest.py --input-root data/raw --output data/final/manifest.json
