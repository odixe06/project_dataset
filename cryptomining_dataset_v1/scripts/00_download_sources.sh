#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
DRY_RUN="${DRY_RUN:-0}"
USER_AGENT="${USER_AGENT:-Mozilla/5.0 cryptomining-dataset-v1}"

download_file() {
  local url="$1"
  local out="$2"
  mkdir -p "$(dirname "$out")"
  if [[ -s "$out" && "${FORCE_DOWNLOAD:-0}" != "1" ]]; then
    printf 'skip existing %s\n' "$out"
    return 0
  fi
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[dry-run] download %s -> %s\n' "$url" "$out"
    return 0
  fi
  printf 'Downloading %s\n' "$url"
  if ! curl -L --fail --retry 5 --retry-delay 10 -C - -A "$USER_AGENT" -o "$out" "$url"; then
    printf '\nERROR: download failed for %s\n' "$url" >&2
    printf 'If this is a Zenodo 403, open the record URL in a browser, verify access, then retry or place the file at %s.\n' "$out" >&2
    return 1
  fi
}

if [[ "${SKIP_HF:-0}" != "1" ]]; then
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[dry-run] huggingface snapshot mdokl/Auto-capture-cryptomining-data\n'
  else
    "$PYTHON" - <<'PY'
from pathlib import Path
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="mdokl/Auto-capture-cryptomining-data",
    repo_type="dataset",
    local_dir=str(Path("data/raw/mining/auto_capture_hf")),
    local_dir_use_symlinks=False,
)
PY
  fi
fi

download_file "https://zenodo.org/records/7189293/files/DeCryptoDatasets.tar.gz?download=1" \
  "data/raw/mining/cesnet_miner22/DeCryptoDatasets.tar.gz"

if [[ ! -d data/raw/mining/cj_sniffer/.git ]]; then
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[dry-run] git clone CJ-Sniffer-Dataset\n'
  else
    rm -rf data/raw/mining/cj_sniffer
    git clone https://github.com/yebof/CJ-Sniffer-Dataset.git data/raw/mining/cj_sniffer
  fi
fi

download_file "https://zenodo.org/records/13630503/files/MineShark_AE.tar.gz?download=1" \
  "data/raw/mining/mineshark_artifact/MineShark_AE.tar.gz"

download_file "https://zenodo.org/records/5199540/files/ALLFLOWMETER_HIKARI2021.csv.zip?download=1" \
  "data/raw/non_mining/hikari2021/ALLFLOWMETER_HIKARI2021.csv.zip"
download_file "https://zenodo.org/records/5199540/files/ground-truth.zip?download=1" \
  "data/raw/non_mining/hikari2021/ground-truth.zip"

if [[ "${SKIP_HIKARI_PCAPS:-0}" != "1" ]]; then
  download_file "https://zenodo.org/records/5199540/files/BRUTEFORCE_HTTPS%2Fpcap%2FFriday_2021-04-16_2304.pcap?download=1" \
    "data/raw/non_mining/hikari2021/pcap/BRUTEFORCE_HTTPS/Friday_2021-04-16_2304.pcap"
  download_file "https://zenodo.org/records/5199540/files/BRUTEFORCE_HTTPS%2Fpcap%2FSunday_2021-04-11_2154.pcap?download=1" \
    "data/raw/non_mining/hikari2021/pcap/BRUTEFORCE_HTTPS/Sunday_2021-04-11_2154.pcap"
  download_file "https://zenodo.org/records/5199540/files/BRUTEFORCE_XML%2Fpcap%2FMonday_2021-04-12_0611.pcap?download=1" \
    "data/raw/non_mining/hikari2021/pcap/BRUTEFORCE_XML/Monday_2021-04-12_0611.pcap"
  download_file "https://zenodo.org/records/5199540/files/BRUTEFORCE_XML%2Fpcap%2FSaturday_2021-04-17_0357.pcap?download=1" \
    "data/raw/non_mining/hikari2021/pcap/BRUTEFORCE_XML/Saturday_2021-04-17_0357.pcap"
  download_file "https://zenodo.org/records/5199540/files/SCANCMS%2Fpcap%2FSunday_2021-05-02_1206.pcap?download=1" \
    "data/raw/non_mining/hikari2021/pcap/SCANCMS/Sunday_2021-05-02_1206.pcap"
  download_file "https://zenodo.org/records/5199540/files/SCANCMS%2Fpcap%2FSunday_2021-05-02_1659.pcap?download=1" \
    "data/raw/non_mining/hikari2021/pcap/SCANCMS/Sunday_2021-05-02_1659.pcap"
else
  printf 'skip HIKARI PCAP downloads because SKIP_HIKARI_PCAPS=1\n'
fi

if [[ "${IOT23_SMALL:-0}" == "1" ]]; then
  download_file "https://mcfp.felk.cvut.cz/publicDatasets/IoT-23-Dataset/iot_23_datasets_small.tar.gz" \
    "data/raw/non_mining/iot23_mcfp/iot_23_datasets_small.tar.gz"
else
  download_file "https://mcfp.felk.cvut.cz/publicDatasets/IoT-23-Dataset/iot_23_datasets_full.tar.gz" \
    "data/raw/non_mining/iot23_mcfp/iot_23_datasets_full.tar.gz"
fi

"$PYTHON" scripts/02_build_manifest.py --input-root data/raw --output data/final/manifest.json
