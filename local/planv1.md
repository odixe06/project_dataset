# plan xây dựng dataset mining / non-mining từ nguồn có sẵn

mục tiêu: tạo một bộ dữ liệu chuẩn hóa, chưa chia train/validation/test, gồm các mẫu đã có đặc trưng và label nhị phân:

- `label = 1`: cryptomining.
- `label = 0`: non-mining, gồm traffic bình thường và hard negative không liên quan đến mining.
- một phần mẫu có TLS metadata đầy đủ hoặc một phần.
- một phần mẫu không có TLS metadata, nhưng vẫn giữ cùng schema và padding nhất quán.
- output chính là flow-level dataset, không chuẩn bị input theo CNN của MineShark.

## 1. nguồn dữ liệu chốt dùng

không tự tạo traffic. không đề xuất thêm nguồn ngoài danh sách này.

| mã nguồn | vai trò | dạng dữ liệu | label dùng | đặc trưng có thể lấy |
|---|---:|---|---:|---|
| `auto_capture_hf` | mining TLS lõi | pcap | 1 | flow features, packet timing, TLS metadata từ `ssl.log`, `x509.log`, ja3 nếu zeek hỗ trợ |
| `cesnet_miner22` | scale flow mining và flow đối chứng theo nhãn gốc | csv flow đã trích sẵn | `Miner` -> 1, `Other` -> 0 | flow features, first 30 packet size/time/direction, sni nếu có |
| `cj_sniffer` | mining encrypted đa dạng phần mềm | pcap + labels.csv | 1, chỉ lấy mẫu `encrypted=yes` | flow features, packet timing, TLS metadata từ zeek |
| `mineshark_artifact` | mining obfuscated và perturbed | artifact của MineShark, có dữ liệu và code | 1 | timing/size sequence đã có hoặc trích từ pcap nếu artifact có pcap, TLS fields có thể thiếu |
| `hikari2021` | non-mining TLS đối chứng | pcap + ground truth + flow csv | 0, chỉ lấy benign | flow features, packet timing, TLS metadata từ HTTPS/TLS bình thường |
| `iot23_mcfp` | non-mining nền và hard negative | IoT-23 từ Stratosphere MCFP, pcap/log zeek | 0 | conn.log, ssl.log nếu có; nếu dùng pcap thì trích thêm packet timing và x509 |

ghi chú:
- `cesnet_miner22` có cả nhãn `Miner` và `Other`, nên trong v1 đưa cả hai vào để tăng quy mô và tránh chỉ dùng nguồn này cho label 1.
- `iot23_mcfp` được hiểu là dùng IoT-23 tải từ hạ tầng MCFP, không crawl toàn bộ MCFP.
- `mineshark_artifact` chỉ dùng phần obfuscated và perturbed để tăng robustness, không dùng để chuẩn bị input CNN.

## 2. nguyên tắc thiết kế dataset

### 2.1 đơn vị mẫu

mỗi dòng trong dataset cuối là một bidirectional flow.

một flow được xác định bằng:

```text
src_ip, dst_ip, src_port, dst_port, proto, time_first, time_last, source_file
```

để bảo vệ riêng tư, final dataset không lưu ip thô. lưu:

```text
src_ip_hash64
dst_ip_hash64
src_port
dst_port
proto
```

ip hash dùng salt cố định trong `configs/privacy.yaml`.

### 2.2 schema cố định cho mọi mẫu

mọi mẫu đều có đủ các nhóm cột:

1. metadata và provenance.
2. label.
3. flow features.
4. TLS metadata.
5. timing patterns.
6. sequence features dạng mảng.
7. quality flags.

với mẫu không có TLS:

```text
has_tls = 0
tls_source = "none"
tls_version_id = 0
cipher_id = 0
sni_hash64 = 0
ja3_hash64 = 0
ja3s_hash64 = 0
cert_* = 0
alpn_id = 0
```

với mẫu có TLS nhưng chỉ có SNI, ví dụ CESNET:

```text
has_tls = 1 nếu sni khác rỗng
tls_source = "sni_only"
sni_hash64 != 0
các trường cipher, ja3, x509 không có thì để 0
```

với mẫu có TLS đầy đủ từ pcap:

```text
has_tls = 1
tls_source = "zeek_ssl_x509"
điền ssl.log, x509.log, ja3/ja3s nếu có
```

### 2.3 không chuẩn hóa theo model tại bước này

không scale min-max, không z-score, không one-hot trong dataset gốc. lưu thêm id/hash ổn định cho categorical TLS để các model khác nhau có thể xử lý lại.

ví dụ:

```text
tls_version_raw = "TLSv12"
tls_version_id = 2
cipher_raw_hash64 = <hash>
cipher_id = <id trong vocab>
sni_hash64 = <hash>
```

### 2.4 không chia train/test

output không có `train.parquet`, `val.parquet`, `test.parquet`. chỉ có:

```text
samples.parquet
schema.json
feature_vocab.json
manifest.json
stats_report.md
stats.json
data_dictionary.md
```

việc chia dataset thực hiện sau, tùy model.

## 3. cấu trúc thư mục

tạo thư mục gốc:

```text
cryptomining_dataset_v1/
  configs/
    sources.yaml
    schema.yaml
    privacy.yaml
    build.yaml
  data/
    raw/
      mining/
        auto_capture_hf/
        cesnet_miner22/
        cj_sniffer/
        mineshark_artifact/
      non_mining/
        hikari2021/
        iot23_mcfp/
    staging/
      zeek/
        auto_capture_hf/
        cj_sniffer/
        hikari2021/
        iot23_mcfp/
      packets/
        auto_capture_hf/
        cj_sniffer/
        hikari2021/
        iot23_mcfp/
        mineshark_artifact/
      source_tables/
        cesnet_miner22/
        mineshark_artifact/
        iot23_mcfp/
      tls/
      flows/
    interim/
      canonical_by_source/
      rejected/
      audit/
    final/
      samples.parquet
      samples.csv.gz
      schema.json
      feature_vocab.json
      manifest.json
      provenance.parquet
      stats.json
      stats_report.md
      data_dictionary.md
  scripts/
    00_download_sources.sh
    01_unpack_sources.sh
    02_run_zeek.sh
    03_extract_packet_sequences.py
    04_parse_zeek_logs.py
    05_parse_cesnet.py
    06_parse_mineshark_artifact.py
    07_normalize_schema.py
    08_merge_and_dedupe.py
    09_validate_and_stats.py
    10_export_final.py
  logs/
```

## 4. file cấu hình chính

### 4.1 `configs/build.yaml`

```yaml
schema_version: "mining_dataset_v1"
random_seed: 42
tcp_only: true
min_packets_per_flow: 3

sequence:
  max_packets_store: 256
  store_signed_lengths: true
  store_iat: true
  store_direction: true

tls_padding:
  no_tls_numeric: 0
  no_tls_categorical: "unknown"
  no_tls_hash: 0

privacy:
  hash_ips: true
  hash_sni: true
  keep_raw_sni_in_final: false
  keep_raw_payload: false

label_policy:
  auto_capture_hf: 1
  cj_sniffer: 1
  mineshark_artifact: 1
  hikari2021: 0
  iot23_mcfp: 0
  cesnet_miner22:
    Miner: 1
    Other: 0

export:
  format: ["parquet", "csv.gz"]
  parquet_compression: "zstd"
  split_train_test: false
```

### 4.2 `configs/sources.yaml`

```yaml
auto_capture_hf:
  type: "huggingface_dataset"
  repo_id: "mdokl/Auto-capture-cryptomining-data"
  repo_type: "dataset"
  local_dir: "data/raw/mining/auto_capture_hf"

cesnet_miner22:
  type: "zenodo"
  url: "https://zenodo.org/records/7189293/files/DeCryptoDatasets.tar.gz?download=1"
  local_file: "data/raw/mining/cesnet_miner22/DeCryptoDatasets.tar.gz"

cj_sniffer:
  type: "git"
  url: "https://github.com/yebof/CJ-Sniffer-Dataset.git"
  local_dir: "data/raw/mining/cj_sniffer"

mineshark_artifact:
  type: "zenodo"
  url: "https://zenodo.org/records/13630503/files/MineShark_AE.tar.gz?download=1"
  local_file: "data/raw/mining/mineshark_artifact/MineShark_AE.tar.gz"

hikari2021:
  type: "zenodo"
  record: "https://zenodo.org/records/5199540"
  files:
    - "ALLFLOWMETER_HIKARI2021.csv.zip"
    - "ground-truth.zip"
    - "BRUTEFORCE_HTTPS/pcap/Friday_2021-04-16_2304.pcap"
    - "BRUTEFORCE_HTTPS/pcap/Sunday_2021-04-11_2154.pcap"
    - "BRUTEFORCE_XML/pcap/Monday_2021-04-12_0611.pcap"
    - "BRUTEFORCE_XML/pcap/Saturday_2021-04-17_0357.pcap"
    - "SCANCMS/pcap/Sunday_2021-05-02_1206.pcap"
    - "SCANCMS/pcap/Sunday_2021-05-02_1659.pcap"

iot23_mcfp:
  type: "tar"
  full_url: "https://mcfp.felk.cvut.cz/publicDatasets/IoT-23-Dataset/iot_23_datasets_full.tar.gz"
  small_url: "https://mcfp.felk.cvut.cz/publicDatasets/IoT-23-Dataset/iot_23_datasets_small.tar.gz"
  local_file: "data/raw/non_mining/iot23_mcfp/iot_23_datasets_full.tar.gz"
```

## 5. chuẩn bị môi trường

### 5.1 công cụ hệ thống

cài các công cụ sau:

```bash
sudo apt update
sudo apt install -y git wget curl unzip p7zip-full jq tshark zeek python3-venv
```

nếu zeek chưa có ja3:

```bash
zkg autoconfig
zkg install zeek/ja3
```

nếu không cài được package ja3, vẫn chạy pipeline bình thường, các trường `ja3_hash64`, `ja3s_hash64` sẽ bằng 0.

### 5.2 python environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install pandas pyarrow numpy scipy scikit-learn tqdm pyyaml xxhash dpkt scapy zeeklogs tldextract huggingface_hub
```

khuyến nghị dùng `pyarrow.dataset` và ghi parquet theo chunk để không cần load toàn bộ data vào ram.

## 6. tải dữ liệu

### 6.1 tạo thư mục

```bash
mkdir -p cryptomining_dataset_v1
cd cryptomining_dataset_v1

mkdir -p data/raw/mining/auto_capture_hf
mkdir -p data/raw/mining/cesnet_miner22
mkdir -p data/raw/mining/cj_sniffer
mkdir -p data/raw/mining/mineshark_artifact
mkdir -p data/raw/non_mining/hikari2021
mkdir -p data/raw/non_mining/iot23_mcfp
mkdir -p logs
```

### 6.2 tải Auto-capture-cryptomining-data

```bash
python - <<'PY'
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="mdokl/Auto-capture-cryptomining-data",
    repo_type="dataset",
    local_dir="data/raw/mining/auto_capture_hf",
    local_dir_use_symlinks=False
)
PY
```

kiểm tra:

```bash
find data/raw/mining/auto_capture_hf -type f -name "*.pcap" | sort > logs/auto_capture_pcap_files.txt
wc -l logs/auto_capture_pcap_files.txt
```

### 6.3 tải CESNET-MINER22

```bash
wget -c -O data/raw/mining/cesnet_miner22/DeCryptoDatasets.tar.gz \
  "https://zenodo.org/records/7189293/files/DeCryptoDatasets.tar.gz?download=1"
```

kiểm tra md5 nếu cần:

```bash
md5sum data/raw/mining/cesnet_miner22/DeCryptoDatasets.tar.gz > logs/cesnet_miner22.md5
```

### 6.4 tải CJ-Sniffer-Dataset

```bash
git clone https://github.com/yebof/CJ-Sniffer-Dataset.git data/raw/mining/cj_sniffer
```

kiểm tra:

```bash
test -f data/raw/mining/cj_sniffer/labels.csv
find data/raw/mining/cj_sniffer -type f -name "*.pcap" | sort > logs/cj_sniffer_pcap_files.txt
```

### 6.5 tải MineShark artifact

```bash
wget -c -O data/raw/mining/mineshark_artifact/MineShark_AE.tar.gz \
  "https://zenodo.org/records/13630503/files/MineShark_AE.tar.gz?download=1"
```

### 6.6 tải HIKARI-2021

tải metadata và flow csv trước:

```bash
wget -c -O data/raw/non_mining/hikari2021/ALLFLOWMETER_HIKARI2021.csv.zip \
  "https://zenodo.org/records/5199540/files/ALLFLOWMETER_HIKARI2021.csv.zip?download=1"

wget -c -O data/raw/non_mining/hikari2021/ground-truth.zip \
  "https://zenodo.org/records/5199540/files/ground-truth.zip?download=1"
```

tải các pcap có chứa traffic HTTPS/TLS. các pcap này lớn, xử lý theo file, không giải nén hoặc load toàn bộ vào ram.

```bash
mkdir -p data/raw/non_mining/hikari2021/pcap/BRUTEFORCE_HTTPS
mkdir -p data/raw/non_mining/hikari2021/pcap/BRUTEFORCE_XML
mkdir -p data/raw/non_mining/hikari2021/pcap/SCANCMS

wget -c -O data/raw/non_mining/hikari2021/pcap/BRUTEFORCE_HTTPS/Friday_2021-04-16_2304.pcap \
  "https://zenodo.org/records/5199540/files/BRUTEFORCE_HTTPS%2Fpcap%2FFriday_2021-04-16_2304.pcap?download=1"

wget -c -O data/raw/non_mining/hikari2021/pcap/BRUTEFORCE_HTTPS/Sunday_2021-04-11_2154.pcap \
  "https://zenodo.org/records/5199540/files/BRUTEFORCE_HTTPS%2Fpcap%2FSunday_2021-04-11_2154.pcap?download=1"

wget -c -O data/raw/non_mining/hikari2021/pcap/BRUTEFORCE_XML/Monday_2021-04-12_0611.pcap \
  "https://zenodo.org/records/5199540/files/BRUTEFORCE_XML%2Fpcap%2FMonday_2021-04-12_0611.pcap?download=1"

wget -c -O data/raw/non_mining/hikari2021/pcap/BRUTEFORCE_XML/Saturday_2021-04-17_0357.pcap \
  "https://zenodo.org/records/5199540/files/BRUTEFORCE_XML%2Fpcap%2FSaturday_2021-04-17_0357.pcap?download=1"

wget -c -O data/raw/non_mining/hikari2021/pcap/SCANCMS/Sunday_2021-05-02_1206.pcap \
  "https://zenodo.org/records/5199540/files/SCANCMS%2Fpcap%2FSunday_2021-05-02_1206.pcap?download=1"

wget -c -O data/raw/non_mining/hikari2021/pcap/SCANCMS/Sunday_2021-05-02_1659.pcap \
  "https://zenodo.org/records/5199540/files/SCANCMS%2Fpcap%2FSunday_2021-05-02_1659.pcap?download=1"
```

### 6.7 tải IoT-23 từ MCFP

nếu đủ đĩa, dùng bản full để có pcap và log:

```bash
wget -c -O data/raw/non_mining/iot23_mcfp/iot_23_datasets_full.tar.gz \
  "https://mcfp.felk.cvut.cz/publicDatasets/IoT-23-Dataset/iot_23_datasets_full.tar.gz"
```

nếu cần bản nhẹ để bắt đầu nhanh:

```bash
wget -c -O data/raw/non_mining/iot23_mcfp/iot_23_datasets_small.tar.gz \
  "https://mcfp.felk.cvut.cz/publicDatasets/IoT-23-Dataset/iot_23_datasets_small.tar.gz"
```

quy ước v1:
- nếu có full thì dùng full.
- nếu chỉ có small thì dùng các log sẵn có, đánh dấu `packet_seq_available=0` cho những mẫu không có pcap.

## 7. giải nén và lập manifest raw

### 7.1 giải nén

```bash
mkdir -p data/raw/mining/cesnet_miner22/extracted
tar -xzf data/raw/mining/cesnet_miner22/DeCryptoDatasets.tar.gz \
  -C data/raw/mining/cesnet_miner22/extracted

mkdir -p data/raw/mining/mineshark_artifact/extracted
tar -xzf data/raw/mining/mineshark_artifact/MineShark_AE.tar.gz \
  -C data/raw/mining/mineshark_artifact/extracted

mkdir -p data/raw/non_mining/hikari2021/extracted
unzip -n data/raw/non_mining/hikari2021/ALLFLOWMETER_HIKARI2021.csv.zip \
  -d data/raw/non_mining/hikari2021/extracted
unzip -n data/raw/non_mining/hikari2021/ground-truth.zip \
  -d data/raw/non_mining/hikari2021/extracted

mkdir -p data/raw/non_mining/iot23_mcfp/extracted
tar -xzf data/raw/non_mining/iot23_mcfp/iot_23_datasets_full.tar.gz \
  -C data/raw/non_mining/iot23_mcfp/extracted
```

### 7.2 lập manifest

script `scripts/build_manifest.py` quét toàn bộ `data/raw` và tạo:

```text
data/final/manifest.json
```

mỗi file có:

```json
{
  "source": "auto_capture_hf",
  "path": "data/raw/mining/auto_capture_hf/16G_12.pcap",
  "size_bytes": 448512,
  "sha256": "...",
  "file_type": "pcap",
  "downloaded_at": "2026-05-18"
}
```

manifest phải được tạo trước khi extract để có thể tái lập pipeline.

## 8. extract từ pcap bằng zeek

áp dụng cho:

```text
auto_capture_hf
cj_sniffer
hikari2021
iot23_mcfp nếu có pcap
mineshark_artifact nếu có pcap
```

### 8.1 chạy zeek

script `scripts/02_run_zeek.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SRC_NAME="$1"
PCAP_LIST="$2"
OUT_ROOT="data/staging/zeek/${SRC_NAME}"

mkdir -p "$OUT_ROOT"

while read -r PCAP; do
  BASE="$(basename "$PCAP")"
  OUT_DIR="${OUT_ROOT}/${BASE%.pcap}"
  mkdir -p "$OUT_DIR"

  (
    cd "$OUT_DIR"
    zeek -C -r "../../../${PCAP}" LogAscii::use_json=T || zeek -C -r "../../../${PCAP}"
  )
done < "$PCAP_LIST"
```

nếu ja3 hoạt động:

```bash
zeek -C -r file.pcap LogAscii::use_json=T policy/protocols/ssl/ja3.zeek
```

output cần có tối thiểu:

```text
conn.log
ssl.log nếu có TLS
x509.log nếu có certificate quan sát được
dns.log nếu có DNS
```

### 8.2 lưu ý với TLS 1.3

với TLS 1.3, certificate có thể không quan sát được trong `x509.log`. không loại bỏ mẫu này. ghi:

```text
has_tls = 1
cert_observed = 0
cert_* = 0
tls_cert_missing_reason = "tls13_or_not_seen"
```

## 9. extract packet sequence và timing từ pcap

zeek `conn.log` không đủ để có sequence packet theo thứ tự. cần thêm script parse pcap.

### 9.1 logic group flow

script `scripts/03_extract_packet_sequences.py`:

1. đọc pcap bằng `dpkt` hoặc `scapy`.
2. chỉ lấy TCP nếu `tcp_only=true`.
3. tạo canonical flow key:
   - so sánh 2 endpoint theo thứ tự `(ip, port)` để có key ổn định.
   - lưu hướng packet theo flow originator, originator là bên gửi packet đầu tiên.
4. với mỗi flow:
   - sort theo timestamp.
   - tính `pkt_len`.
   - tính `direction`: `1` originator -> responder, `-1` responder -> originator.
   - tính `iat`: timestamp hiện tại trừ timestamp trước đó trong cùng flow.
   - lưu tối đa `max_packets_store=256`.

### 9.2 output packet sequence

ghi parquet theo từng pcap:

```text
data/staging/packets/<source>/<pcap_name>.parquet
```

cột:

```text
source
source_file
flow_key_hash
time_first
time_last
packet_count_observed
seq_len_stored
seq_pkt_len
seq_signed_pkt_len
seq_direction
seq_iat
tcp_syn_count
tcp_ack_count
tcp_psh_count
tcp_rst_count
tcp_fin_count
```

### 9.3 timing patterns từ sequence

tính thêm các đặc trưng:

```text
iat_mean
iat_std
iat_min
iat_max
iat_p10
iat_p50
iat_p90
iat_cv
iat_entropy
iat_zero_ratio
iat_small_ratio_10ms
fwd_iat_mean
bwd_iat_mean
fwd_bwd_iat_ratio
burst_count
burst_mean_packets
burst_max_packets
periodicity_autocorr_lag
periodicity_autocorr_score
periodicity_fft_peak
```

định nghĩa burst đơn giản cho v1:

```text
một burst là chuỗi packet liên tiếp có iat <= 1 giây
```

định nghĩa periodicity v1:

```text
periodicity_autocorr_score = max autocorrelation của chuỗi iat sau khi bỏ lag 0
periodicity_autocorr_lag = lag tại điểm max
```

nếu flow có quá ít packet:

```text
periodicity_autocorr_score = 0
periodicity_autocorr_lag = 0
```

## 10. parse zeek logs và TLS metadata

script `scripts/04_parse_zeek_logs.py` đọc từng thư mục zeek output.

### 10.1 parse `conn.log`

lấy:

```text
uid
id.orig_h
id.orig_p
id.resp_h
id.resp_p
proto
service
duration
orig_bytes
resp_bytes
orig_pkts
resp_pkts
conn_state
history
local_orig
local_resp
missed_bytes
```

map sang flow features:

```text
duration
bytes_total = orig_bytes + resp_bytes
packets_total = orig_pkts + resp_pkts
bytes_fwd = orig_bytes
bytes_bwd = resp_bytes
packets_fwd = orig_pkts
packets_bwd = resp_pkts
bytes_ratio_fwd = orig_bytes / max(bytes_total, 1)
packets_ratio_fwd = orig_pkts / max(packets_total, 1)
byte_rate = bytes_total / max(duration, 1e-6)
packet_rate = packets_total / max(duration, 1e-6)
```

### 10.2 parse `ssl.log`

join theo `uid`.

cột raw cần đọc nếu có:

```text
version
cipher
curve
server_name
resumed
next_protocol
established
ja3
ja3s
cert_chain_fuids
client_cert_chain_fuids
subject
issuer
```

map sang TLS metadata:

```text
has_tls
tls_source
tls_version_raw
tls_version_id
cipher_hash64
cipher_id
sni_hash64
sni_len
sni_num_labels
sni_entropy
sni_tld_hash64
alpn_hash64
alpn_id
ja3_hash64
ja3s_hash64
tls_resumed
tls_established
tls_handshake_seen
```

không lưu `server_name` raw trong final. nếu cần debug, lưu riêng ở:

```text
data/interim/audit/private_sni.parquet
```

file này không dùng để train.

### 10.3 parse `x509.log`

join bằng `cert_chain_fuids`.

lấy certificate đầu tiên của server chain nếu có.

features:

```text
cert_observed
cert_subject_hash64
cert_issuer_hash64
cert_not_valid_before
cert_not_valid_after
cert_validity_days
cert_key_alg_id
cert_key_length
cert_sig_alg_id
cert_san_count
cert_self_signed
cert_chain_len
```

nếu không join được:

```text
cert_observed = 0
cert_* = 0
```

### 10.4 parse `dns.log`

không dùng DNS raw để label, chỉ dùng feature phụ tùy chọn:

```text
dns_query_hash64
dns_query_len
dns_qtype
dns_answer_count
```

v1 có thể bỏ DNS khỏi final nếu muốn giảm rủi ro leakage. nếu giữ, phải hash.

## 11. xử lý từng nguồn

### 11.1 `auto_capture_hf`

input:

```text
data/raw/mining/auto_capture_hf/*.pcap
```

bước:

1. chạy zeek trên từng pcap.
2. parse packet sequence.
3. parse conn, ssl, x509.
4. merge flow + sequence + TLS bằng 5-tuple và khoảng thời gian.
5. set label:

```text
label = 1
source = "auto_capture_hf"
source_role = "mining_tls"
original_label = "mining"
```

lọc:

```text
proto == tcp
packets_total >= 3
```

giữ cả mẫu có `has_tls=1` và mẫu không có TLS nếu có, nhưng kỳ vọng nguồn này chủ yếu là TLS.

### 11.2 `cesnet_miner22`

input sau giải nén thường có:

```text
decrypto_dataset_design.csv
decrypto_dataset_evaluation.csv
```

bước:

1. đọc csv theo chunk.
2. map label:

```text
LABEL == "Miner" -> label = 1
LABEL == "Other" -> label = 0
```

3. map flow features:

```text
BYTES -> bytes_fwd
BYTES_REV -> bytes_bwd
PACKETS -> packets_fwd
PACKETS_REV -> packets_bwd
TIME_LAST - TIME_FIRST -> duration
DST_PORT, SRC_PORT, PROTOCOL
```

4. map packet sequence từ PPI:

```text
PPI_PKT_DIRECTIONS -> seq_direction
PPI_PKT_LENGTHS -> seq_pkt_len
PPI_PKT_TIMES -> seq_time
diff(seq_time) -> seq_iat
```

5. map TLS:

```text
SNI hoặc SERVER_NAME nếu cột tồn tại -> sni_hash64
has_tls = 1 nếu sni không rỗng, ngược lại 0
tls_source = "sni_only" nếu có sni, ngược lại "none"
```

6. các trường không có:

```text
cipher_id = 0
ja3_hash64 = 0
x509 fields = 0
```

7. provenance:

```text
source = "cesnet_miner22"
source_role = "flow_scale"
original_label = LABEL
packet_seq_available = 1 nếu PPI arrays hợp lệ
tls_metadata_available = 1 nếu SNI hợp lệ
```

không dùng `payload first 100 bytes` làm feature, để tránh học payload trực tiếp và tránh rủi ro riêng tư.

### 11.3 `cj_sniffer`

input:

```text
data/raw/mining/cj_sniffer/labels.csv
data/raw/mining/cj_sniffer/Cryptomining_Traffic/**/*.pcap
```

bước:

1. đọc `labels.csv`.
2. chỉ chọn:

```text
encrypted == "yes"
```

3. map id trong labels với file pcap.
4. chạy zeek và packet sequence.
5. set:

```text
label = 1
source = "cj_sniffer"
source_role = "mining_encrypted"
original_label = "encrypted_mining"
```

6. giữ metadata phụ:

```text
coin_type
mining_software
algo
whether_cryptojacking
```

các cột phụ này lưu trong provenance, không đưa trực tiếp làm input model trừ khi dùng cho phân tích.

### 11.4 `mineshark_artifact`

input:

```text
data/raw/mining/mineshark_artifact/extracted/
```

bước:

1. quét artifact để tìm:
   - thư mục có tên chứa `obfuscated`
   - thư mục có tên chứa `perturbed`
   - file pcap hoặc file feature đã trích.
2. nếu có pcap:
   - chạy zeek.
   - trích packet sequence.
   - merge TLS nếu có.
3. nếu chỉ có feature:
   - đọc feature gốc.
   - map sang schema v1.
   - nếu chỉ có timestamps và size, tính flow/timing từ dữ liệu đó.
4. set:

```text
label = 1
source = "mineshark_artifact"
source_role = "mining_obfuscated_perturbed"
original_label = "obfuscated" hoặc "perturbed"
```

5. TLS padding:

```text
has_tls = 0 nếu không có ssl.log hoặc TLS metadata trong artifact
tls_source = "none"
TLS fields = 0
```

ghi rõ `tls_metadata_available=0` để model sau này không hiểu nhầm thiếu dữ liệu là non-mining.

### 11.5 `hikari2021`

input:

```text
ALLFLOWMETER_HIKARI2021.csv
ground-truth/
pcap/
```

mục tiêu: lấy non-mining TLS đối chứng.

bước:

1. đọc flow csv và ground truth.
2. chỉ lấy flow có nhãn benign.
3. chạy zeek trên pcap đã tải.
4. parse conn, ssl, x509.
5. merge với ground truth theo 5-tuple và thời gian.
6. set:

```text
label = 0
source = "hikari2021"
source_role = "non_mining_tls_benign"
original_label = "benign"
```

7. ưu tiên giữ các flow:

```text
has_tls = 1
service chứa ssl hoặc https nếu có
dst_port thuộc 443, 8443, 9443 hoặc có ssl.log
```

8. vẫn giữ một tỷ lệ nhỏ `has_tls=0` từ HIKARI để dataset có non-mining không TLS.

nếu merge ground truth không chắc chắn, đưa flow vào:

```text
data/interim/rejected/hikari_ambiguous.parquet
```

không đưa vào final.

### 11.6 `iot23_mcfp`

mục tiêu: traffic nền IoT benign và hard negative không mining.

bước với bản full:

1. quét từng scenario.
2. dùng `conn.log.labeled` nếu có để lấy label gốc.
3. nếu có `ssl.log` sẵn thì parse trực tiếp.
4. nếu có pcap và cần TLS đầy đủ thì chạy zeek cho scenario được chọn.
5. set label:

```text
label = 0
source = "iot23_mcfp"
source_role = "non_mining_iot_or_hard_negative"
```

6. giữ `original_label` từ log:

```text
Benign
C&C
DDoS
PartOfAHorizontalPortScan
Attack
...
```

7. chỉ loại bỏ nếu scenario hoặc label thể hiện cryptomining. nếu không có dấu hiệu mining thì giữ làm hard negative.

bước với bản small:

1. dùng log sẵn có.
2. tạo flow features từ `conn.log.labeled`.
3. nếu không có `ssl.log`, TLS fields padding 0.
4. packet sequence fields padding rỗng và:

```text
packet_seq_available = 0
timing_full_available = 0
```

## 12. merge và chuẩn hóa schema

### 12.1 key merge

với dữ liệu từ zeek:

```text
conn.uid -> ssl.uid
ssl.cert_chain_fuids -> x509.id
```

với packet sequence:

```text
source_file + canonical_5tuple + time overlap
```

nếu có mismatch thời gian do pcap/zeek rounding:

```text
tolerance_start <= 1 giây
tolerance_end <= 1 giây
```

nếu nhiều candidate:

1. chọn candidate có overlap thời gian lớn nhất.
2. nếu vẫn tie, chọn packet_count gần nhất với `orig_pkts + resp_pkts`.
3. nếu vẫn tie, reject vào `interim/rejected`.

### 12.2 chuẩn hóa tên cột

mọi nguồn phải xuất ra `data/interim/canonical_by_source/<source>.parquet` với schema giống nhau.

nhóm cột chính:

```text
sample_id
schema_version
source
source_role
source_file
source_record_id
original_label
label
label_confidence
time_first
time_last
duration
proto
src_ip_hash64
dst_ip_hash64
src_port
dst_port

bytes_total
bytes_fwd
bytes_bwd
packets_total
packets_fwd
packets_bwd
byte_rate
packet_rate
bytes_ratio_fwd
packets_ratio_fwd

pkt_len_mean
pkt_len_std
pkt_len_min
pkt_len_max
pkt_len_p10
pkt_len_p50
pkt_len_p90

iat_mean
iat_std
iat_min
iat_max
iat_p10
iat_p50
iat_p90
iat_cv
iat_entropy
iat_zero_ratio
iat_small_ratio_10ms
fwd_iat_mean
bwd_iat_mean
fwd_bwd_iat_ratio
burst_count
burst_mean_packets
burst_max_packets
periodicity_autocorr_lag
periodicity_autocorr_score
periodicity_fft_peak

has_tls
tls_source
tls_version_id
tls_version_hash64
cipher_id
cipher_hash64
sni_hash64
sni_len
sni_num_labels
sni_entropy
sni_tld_hash64
alpn_id
alpn_hash64
ja3_hash64
ja3s_hash64
tls_resumed
tls_established
tls_handshake_seen

cert_observed
cert_subject_hash64
cert_issuer_hash64
cert_validity_days
cert_key_alg_id
cert_key_length
cert_sig_alg_id
cert_san_count
cert_self_signed
cert_chain_len

seq_len_stored
seq_pkt_len
seq_signed_pkt_len
seq_direction
seq_iat

packet_seq_available
tls_metadata_available
tls_full_available
timing_full_available
extract_status
quality_notes
```

### 12.3 `sample_id`

tạo ổn định bằng:

```text
sha256(schema_version + source + source_file + source_record_id + canonical_5tuple + time_first + time_last + label)
```

không dùng index dòng vì sẽ thay đổi khi re-run.

### 12.4 vocabulary cho categorical

tạo `data/final/feature_vocab.json`:

```json
{
  "tls_version": {
    "unknown": 0,
    "SSLv3": 1,
    "TLSv10": 2,
    "TLSv11": 3,
    "TLSv12": 4,
    "TLSv13": 5
  },
  "cipher": {
    "unknown": 0,
    "TLS_AES_128_GCM_SHA256": 1
  },
  "alpn": {
    "unknown": 0,
    "http/1.1": 1,
    "h2": 2
  }
}
```

vocab được build từ toàn bộ dữ liệu final, nhưng id `0` luôn là unknown/no value.

## 13. quy tắc label

### 13.1 label 1

gán `label=1` cho:

```text
auto_capture_hf: toàn bộ pcap hợp lệ
cj_sniffer: pcap có encrypted=yes
mineshark_artifact: obfuscated và perturbed mining
cesnet_miner22: LABEL == Miner
```

### 13.2 label 0

gán `label=0` cho:

```text
hikari2021: flow benign sau khi match ground truth
iot23_mcfp: flow benign và malware không liên quan mining
cesnet_miner22: LABEL == Other
```

### 13.3 không đưa vào final

đưa vào `interim/rejected` nếu:

```text
label không rõ
pcap corrupt
flow không match được ground truth ở HIKARI
flow có ít hơn 3 packet
flow không có duration hợp lệ
packet timestamp lỗi
source label mâu thuẫn
```

## 14. xử lý thiếu dữ liệu

### 14.1 TLS thiếu

không drop flow chỉ vì thiếu TLS metadata. padding theo quy tắc:

```text
has_tls = 0
tls_metadata_available = 0
tls_full_available = 0
tls_source = "none"
all tls numeric/hash/id = 0
```

### 14.2 sequence thiếu

ví dụ IoT-23 small hoặc MineShark artifact chỉ có flow features.

```text
packet_seq_available = 0
seq_len_stored = 0
seq_pkt_len = []
seq_signed_pkt_len = []
seq_direction = []
seq_iat = []
timing_full_available = 0
```

flow features vẫn giữ nếu có.

### 14.3 TLS một phần

ví dụ CESNET có SNI nhưng không có cipher, ja3, x509.

```text
has_tls = 1
tls_metadata_available = 1
tls_full_available = 0
tls_source = "sni_only"
sni fields có giá trị
các TLS fields còn lại = 0
```

## 15. chống leakage và lệch nguồn

dataset từ nhiều nguồn có nguy cơ model học nguồn thay vì học mining. cần làm các bước sau trong stats, không nhất thiết loại bỏ ngay:

1. báo cáo phân bố `source` theo label.
2. báo cáo phân bố `has_tls` theo label.
3. báo cáo phân bố `tls_full_available` theo label.
4. báo cáo missing rate từng feature theo label.
5. kiểm tra feature nào gần như quyết định label vì chỉ xuất hiện ở một nguồn.
6. không đưa `source`, `source_role`, `source_file`, `original_label`, `extract_status` vào input model mặc định.
7. downstream split nên dùng group split theo `source` hoặc theo `source_file` để kiểm tra generalization.

## 16. validate dataset

script `scripts/09_validate_and_stats.py` chạy các kiểm tra:

### 16.1 kiểm tra schema

```text
mọi cột trong schema.yaml đều tồn tại
label chỉ thuộc {0,1}
sample_id không null
sample_id unique
duration >= 0
packets_total >= 3
bytes_total >= 0
has_tls thuộc {0,1}
tls ids >= 0
```

### 16.2 kiểm tra coverage

phải có:

```text
label 1 có has_tls=1
label 1 có has_tls=0 hoặc tls_full_available=0
label 0 có has_tls=1
label 0 có has_tls=0
```

nếu không đạt, không dừng pipeline nhưng ghi cảnh báo lớn trong `stats_report.md`.

### 16.3 kiểm tra mất cân bằng

tạo bảng:

```text
count by label
count by source
count by source and label
count by has_tls and label
count by tls_source and label
count by packet_seq_available and label
```

### 16.4 kiểm tra trùng

trùng chính xác:

```text
sample_id duplicate
```

trùng gần đúng:

```text
same source, same flow_key_hash, same time_first rounded, same time_last rounded
same label, same sequence hash
```

trùng gần đúng đưa vào `audit/possible_duplicates.parquet`.

## 17. thống kê cần xuất

### 17.1 `stats.json`

cấu trúc:

```json
{
  "total_samples": 0,
  "by_label": {"0": 0, "1": 0},
  "by_source": {},
  "by_source_label": {},
  "tls_coverage": {},
  "sequence_coverage": {},
  "missing_rate_by_feature": {},
  "duration_quantiles_by_label": {},
  "packet_count_quantiles_by_label": {},
  "tls_version_by_label": {},
  "top_cipher_hash_by_label": {},
  "top_ja3_hash_by_label": {},
  "rejected_counts": {}
}
```

### 17.2 `stats_report.md`

nội dung:

```text
1. tổng quan dataset
2. số mẫu theo label
3. số mẫu theo source và label
4. TLS coverage
5. sequence/timing coverage
6. missingness theo nhóm feature
7. phân phối duration, packet_count, bytes_total
8. phân phối TLS version, cipher, alpn, ja3
9. số flow bị reject và lý do
10. cảnh báo leakage/missingness
11. khuyến nghị khi train model sau này
```

### 17.3 `data_dictionary.md`

mô tả từng cột:

```text
column
dtype
group
meaning
padding value
available sources
can_use_for_model_input
```

các cột provenance như `source`, `source_file`, `original_label` có:

```text
can_use_for_model_input = false
```

## 18. export final

### 18.1 merge

script `scripts/08_merge_and_dedupe.py`:

1. đọc từng file `canonical_by_source/*.parquet`.
2. kiểm tra schema.
3. concat theo chunk.
4. tạo `sample_id`.
5. remove duplicate chính xác.
6. ghi:

```text
data/final/samples.parquet
data/final/provenance.parquet
```

### 18.2 parquet

khuyến nghị:

```python
df.to_parquet(
    "data/final/samples.parquet",
    engine="pyarrow",
    compression="zstd",
    index=False
)
```

nếu dữ liệu lớn, ghi partition:

```text
data/final/samples_parquet/
  label=0/part-000.parquet
  label=1/part-000.parquet
```

vẫn tạo symlink hoặc manifest chỉ rõ đường dẫn.

### 18.3 csv.gz

chỉ xuất bản rút gọn vì sequence array trong csv khó đọc:

```text
data/final/samples.csv.gz
```

csv giữ scalar features và bỏ `seq_*` arrays. parquet là output chính.

### 18.4 output bắt buộc

```text
data/final/samples.parquet
data/final/schema.json
data/final/feature_vocab.json
data/final/manifest.json
data/final/provenance.parquet
data/final/stats.json
data/final/stats_report.md
data/final/data_dictionary.md
```

## 19. pipeline chạy toàn bộ

thứ tự chạy:

```bash
bash scripts/00_download_sources.sh
bash scripts/01_unpack_sources.sh

find data/raw/mining/auto_capture_hf -type f -name "*.pcap" | sort > logs/auto_capture_pcap_files.txt
bash scripts/02_run_zeek.sh auto_capture_hf logs/auto_capture_pcap_files.txt
python scripts/03_extract_packet_sequences.py --source auto_capture_hf --pcap-list logs/auto_capture_pcap_files.txt
python scripts/04_parse_zeek_logs.py --source auto_capture_hf --label 1

python scripts/05_parse_cesnet.py \
  --input data/raw/mining/cesnet_miner22/extracted \
  --output data/interim/canonical_by_source/cesnet_miner22.parquet

find data/raw/mining/cj_sniffer -type f -name "*.pcap" | sort > logs/cj_sniffer_pcap_files.txt
python scripts/filter_cj_encrypted.py \
  --labels data/raw/mining/cj_sniffer/labels.csv \
  --pcap-list logs/cj_sniffer_pcap_files.txt \
  --out logs/cj_sniffer_encrypted_pcap_files.txt
bash scripts/02_run_zeek.sh cj_sniffer logs/cj_sniffer_encrypted_pcap_files.txt
python scripts/03_extract_packet_sequences.py --source cj_sniffer --pcap-list logs/cj_sniffer_encrypted_pcap_files.txt
python scripts/04_parse_zeek_logs.py --source cj_sniffer --label 1

python scripts/06_parse_mineshark_artifact.py \
  --input data/raw/mining/mineshark_artifact/extracted \
  --output data/interim/canonical_by_source/mineshark_artifact.parquet

find data/raw/non_mining/hikari2021/pcap -type f -name "*.pcap" | sort > logs/hikari_pcap_files.txt
bash scripts/02_run_zeek.sh hikari2021 logs/hikari_pcap_files.txt
python scripts/03_extract_packet_sequences.py --source hikari2021 --pcap-list logs/hikari_pcap_files.txt
python scripts/parse_hikari.py \
  --flowmeter data/raw/non_mining/hikari2021/extracted/ALLFLOWMETER_HIKARI2021.csv \
  --ground-truth data/raw/non_mining/hikari2021/extracted \
  --zeek data/staging/zeek/hikari2021 \
  --packets data/staging/packets/hikari2021 \
  --output data/interim/canonical_by_source/hikari2021.parquet

python scripts/parse_iot23_mcfp.py \
  --input data/raw/non_mining/iot23_mcfp/extracted \
  --output data/interim/canonical_by_source/iot23_mcfp.parquet

python scripts/07_normalize_schema.py \
  --input-root data/interim/canonical_by_source \
  --schema configs/schema.yaml

python scripts/08_merge_and_dedupe.py \
  --input-root data/interim/canonical_by_source \
  --output data/final/samples.parquet

python scripts/09_validate_and_stats.py \
  --input data/final/samples.parquet \
  --out-dir data/final

python scripts/10_export_final.py \
  --input data/final/samples.parquet \
  --out-dir data/final
```

## 20. tiêu chí hoàn thành v1

dataset v1 được xem là hoàn chỉnh khi đạt các điều kiện:

1. có `samples.parquet`.
2. tất cả row có `label` thuộc `{0,1}`.
3. tất cả row có cùng schema.
4. có ít nhất một nhóm label 1 với TLS đầy đủ từ pcap.
5. có ít nhất một nhóm label 0 với TLS đầy đủ từ HIKARI.
6. có mining obfuscated/perturbed từ MineShark artifact.
7. có flow-scale từ CESNET.
8. có hard negative từ IoT-23/MCFP.
9. có stats và manifest.
10. có padding TLS nhất quán cho flow không TLS.
11. không lưu payload raw trong final.
12. chưa chia train/test.

## 21. cấu trúc output mẫu

ví dụ một dòng có TLS:

```json
{
  "sample_id": "sha256...",
  "source": "auto_capture_hf",
  "label": 1,
  "duration": 123.4,
  "packets_total": 210,
  "bytes_total": 18420,
  "iat_mean": 0.93,
  "periodicity_autocorr_score": 0.71,
  "has_tls": 1,
  "tls_source": "zeek_ssl_x509",
  "tls_version_id": 5,
  "cipher_id": 14,
  "sni_hash64": 123456789,
  "ja3_hash64": 987654321,
  "cert_observed": 1,
  "cert_validity_days": 89,
  "seq_len_stored": 210,
  "seq_signed_pkt_len": [74, -1514, 66],
  "seq_iat": [0.0, 0.002, 1.31]
}
```

ví dụ một dòng không TLS:

```json
{
  "sample_id": "sha256...",
  "source": "mineshark_artifact",
  "label": 1,
  "duration": 84.2,
  "packets_total": 88,
  "bytes_total": 9201,
  "iat_mean": 1.12,
  "periodicity_autocorr_score": 0.64,
  "has_tls": 0,
  "tls_source": "none",
  "tls_version_id": 0,
  "cipher_id": 0,
  "sni_hash64": 0,
  "ja3_hash64": 0,
  "cert_observed": 0,
  "cert_validity_days": 0,
  "seq_len_stored": 88,
  "seq_signed_pkt_len": [302, -66, 217],
  "seq_iat": [0.0, 0.5, 1.6]
}
```

## 22. các lỗi thường gặp và cách xử lý

### 22.1 zeek không tạo `ssl.log`

nguyên nhân:
- flow không phải TLS.
- TLS handshake không nằm trong pcap.
- capture bắt đầu giữa phiên.
- traffic bị tunnel hoặc obfuscation.

xử lý:
- không drop flow.
- set `has_tls=0` nếu không có chứng cứ TLS.
- nếu port là 443 nhưng không có `ssl.log`, set `possible_tls_port=1` nhưng không coi là TLS metadata.

### 22.2 `x509.log` rỗng

nguyên nhân:
- TLS 1.3 encrypt certificate.
- handshake không đầy đủ.
- zeek không parse được cert.

xử lý:

```text
has_tls = 1 nếu ssl.log có
cert_observed = 0
cert_* = 0
```

### 22.3 HIKARI merge sai ground truth

xử lý:
- chỉ giữ flow có match chắc chắn.
- nếu 1 zeek conn match nhiều ground-truth row, chọn overlap cao nhất.
- nếu overlap thấp hoặc label khác nhau, reject.

### 22.4 IoT-23 chỉ có conn.log

xử lý:
- vẫn đưa vào final để tăng hard negative.
- `packet_seq_available=0`.
- `timing_full_available=0`.
- flow timing từ duration/rate vẫn có.

### 22.5 dataset bị mất cân bằng nguồn

không sửa bằng cách xóa dữ liệu ở final. thay vào đó:
- giữ full dataset.
- thêm `source`, `source_role`, `sample_weight_suggested`.
- downstream training tự sample theo source/label.

## 23. thứ tự ưu tiên nếu tài nguyên hạn chế

nếu không đủ đĩa hoặc thời gian, vẫn phải giữ đủ coverage như sau:

1. luôn xử lý `auto_capture_hf`.
2. luôn xử lý `cj_sniffer` encrypted.
3. luôn xử lý `hikari2021` ít nhất các pcap HTTPS để có non-mining TLS.
4. luôn xử lý `cesnet_miner22` vì đã là flow csv và rẻ.
5. xử lý `mineshark_artifact` obfuscated/perturbed.
6. xử lý `iot23_mcfp` bản small nếu full quá nặng.

không bỏ HIKARI, vì nếu thiếu non-mining TLS thì model dễ học sai rằng TLS là mining.

## 24. ghi chú về tính phù hợp với Deep Learning

dataset final không ép cấu trúc input CNN. tuy nhiên vẫn giữ đủ thông tin để tạo input cho nhiều loại model:

- tabular model: dùng scalar flow features + TLS numeric/hash features + timing aggregates.
- sequence model: dùng `seq_signed_pkt_len`, `seq_iat`, `seq_direction`.
- multimodal model: dùng scalar flow + TLS vector + sequence arrays.
- transformer/rnn: cắt hoặc pad sequence sau khi đọc parquet.
- graph hoặc contrastive model: dùng provenance/source để tạo group split, không dùng làm feature mặc định.

## 25. checklist cuối

trước khi dùng dataset để train, kiểm tra:

```text
[ ] samples.parquet đọc được bằng pandas/pyarrow
[ ] schema.json khớp với samples.parquet
[ ] sample_id unique
[ ] label có cả 0 và 1
[ ] label 0 có TLS
[ ] label 1 có TLS
[ ] có mẫu no TLS ở ít nhất một label
[ ] có MineShark obfuscated/perturbed
[ ] có CJ encrypted mining
[ ] có Auto-capture TLS mining
[ ] có HIKARI benign TLS
[ ] có IoT-23 hard negative
[ ] có CESNET flow-scale
[ ] stats_report.md đã tạo
[ ] manifest.json có sha256 của raw files
[ ] không lưu payload raw trong final
[ ] chưa chia train/test
```
