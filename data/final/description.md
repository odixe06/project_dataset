# Mô Tả Dataset Cryptomining / Non-Mining V1

## 0. Contributions

Bản V1 của dataset đi kèm hai contribution có thể defend khoa học:

1. **(Chính) Cross-source generalization benchmark.** Đánh giá đầu tiên trên public multi-source data cho cryptomining detection: 4 feature group ablations × 5 leave-one-source-out folds (mineshark_artifact bị loại do parser hiện không map raw features — xem report §6.1). Lượng hoá generalization gap mà MineShark và các công trình trước chưa đo. Kết luận định tính: timing features là yếu tố then chốt — chuyển mean cross-source recall_pos từ 0.52 (flow_only) lên 0.98 (flow_timing), đồng thời triệt tiêu FPR trên hikari/iot23 benign (0.80 → 0.019). TLS features không cải thiện cross-source khi đã có timing, và độc lập làm tệ hơn (caveat: TLS coverage ở mining chỉ 0.6% nên kết luận về TLS bị confound bởi padding semantics).
2. **(Phụ trợ) Source-distribution drift report.** Đo Jensen-Shannon divergence pairwise giữa các source theo feature group, đối chiếu với generalization gap. Trên 3 mining-source folds defendable, quan hệ drift→gap đơn điệu hoàn hảo cho `flow_only` (gợi ý drift flow là nguyên nhân chính của generalization failure) nhưng không có chiều hướng cho `flow_timing` (gợi ý timing robust bất kể drift). Đây là *evidence-of-direction* định tính, không phải kết luận thống kê — n nhỏ.

Báo cáo tổng hợp + threats-to-validity: [`evaluation/BENCHMARK_REPORT.md`](evaluation/BENCHMARK_REPORT.md).
Code reproduce: `scripts/15_cross_source_benchmark.py`, `16_source_drift.py`, `17_drift_vs_gen.py`.

## 1. Tổng Quan

`cryptomining_dataset_v1` là bộ dữ liệu flow-level cho bài toán phát hiện lưu lượng cryptomining trong traffic mạng. Mỗi dòng trong file chính tương ứng với một bidirectional network flow đã được chuẩn hóa về cùng schema.

Nhãn của dataset:

- `label=1`: cryptomining.
- `label=0`: non-mining, benign hoặc hard negative không liên quan đến mining.

Mục tiêu của bản V1 là tạo một dataset thống nhất, có provenance rõ ràng, có thể dùng cho cả mô hình tabular và mô hình sequence, đồng thời không xuất dữ liệu nhạy cảm trong thư mục final. Các giá trị như IP thô, SNI thô và raw payload không nằm trong output cuối cùng.

Kích thước bản final hiện tại:

| Nhóm | Số mẫu |
|---|---:|
| Tổng số mẫu | 415,670 |
| `label=0` | 402,203 |
| `label=1` | 13,467 |

Phân bố theo nguồn:

| Source | Số mẫu |
|---|---:|
| `hikari2021` | 229,089 |
| `iot23_mcfp` | 173,114 |
| `cesnet_miner22` | 10,000 |
| `mineshark_artifact` | 2,716 |
| `auto_capture_hf` | 533 |
| `cj_sniffer` | 218 |

## 2. Nguồn Dữ Liệu

Dataset được xây dựng từ các nguồn công khai sau.

### `auto_capture_hf`

Nguồn: Hugging Face `mdokl/Auto-capture-cryptomining-data`.

Vai trò trong dataset:

- Đóng góp mẫu cryptomining từ PCAP.
- Được xử lý bằng Zeek để lấy flow và TLS metadata.
- Được trích packet sequence từ PCAP.

### `cesnet_miner22`

Nguồn: CESNET-MINER22 / DeCryptoDatasets từ Zenodo.

Vai trò trong dataset:

- Đóng góp flow-scale samples có nhãn `Miner` và `Other`.
- `Miner` được map thành `label=1`.
- `Other` được map thành `label=0`.
- Bản local V1 hiện lấy 10,000 dòng để giữ thời gian build phù hợp với tài nguyên máy hiện tại.
- PPI arrays được dùng để tạo packet length, direction và timing patterns.

Lưu ý quan trọng: `seq_iat` của CESNET được tính từ `PPI_PKT_TIMES` bằng parser ISO nhẹ theo giây trong ngày, không dùng `pd.to_datetime` từng phần tử. Vì vậy CESNET vẫn giữ được time patterns trong sequence.

### `cj_sniffer`

Nguồn: GitHub `yebof/CJ-Sniffer-Dataset`.

Vai trò trong dataset:

- Đóng góp PCAP cryptomining.
- Được chạy Zeek và trích packet sequence.

Lưu ý về nhãn `encrypted`: file `labels.csv` trong bản repo hiện tại có `encrypted=no` cho toàn bộ 64 PCAP. Do đó pipeline fallback giữ toàn bộ PCAP CJ-Sniffer như một nguồn cryptomining packet-level, thay vì loại bỏ cả nguồn. Khi sử dụng dataset, nên xem `cj_sniffer` là mining PCAP coverage, không nên diễn giải nó là coverage encrypted-only.

### `mineshark_artifact`

Nguồn: MineShark artifact từ Zenodo.

Vai trò trong dataset:

- Đóng góp mẫu cryptomining đã obfuscated hoặc perturbed.
- Dùng các artifact/feature có sẵn khi không có PCAP đầy đủ.
- Một số mẫu có thể không có TLS metadata hoặc packet sequence đầy đủ.

### `hikari2021`

Nguồn: HIKARI-2021 từ Zenodo.

Vai trò trong dataset:

- Đóng góp non-mining/benign TLS traffic.
- Dùng cả flowmeter CSV và PCAP.
- PCAP được chạy Zeek để lấy `conn.log`, `ssl.log`, `x509.log`.
- Packet sequence được trích từ các PCAP HIKARI đã tải và các PCAP anonymized trong ground truth.

### `iot23_mcfp`

Nguồn: IoT-23 từ MCFP.

Vai trò trong dataset:

- Đóng góp non-mining IoT và hard negative không liên quan đến mining.
- Các label/scenario có dấu hiệu mining, miner, cryptomining, stratum, xmr hoặc monero được loại bỏ.
- Bản local V1 dùng parser streaming và giới hạn số dòng để tránh đọc toàn bộ hàng trăm triệu dòng vào RAM.

## 3. Quy Trình Xây Dựng Dataset

Pipeline được tổ chức theo các stage trong thư mục `scripts/`.

Các bước chính:

1. Tải nguồn dữ liệu vào `data/raw/`.
2. Giải nén archive vào vùng raw tương ứng.
3. Tạo `manifest.json` gồm đường dẫn, kích thước, SHA256, loại file, thời điểm tải, record URL và quyền/licensing.
4. Với nguồn PCAP, chạy Zeek bằng absolute PCAP path để sinh log flow/TLS.
5. Parse `conn.log`, `ssl.log`, `x509.log` và optional `dns.log`.
6. Trích packet sequence bằng parser PCAP, canonical hóa flow key theo bidirectional 5-tuple.
7. Với nguồn CSV/artifact, map các feature có sẵn về schema chung.
8. Hash các trường nhạy cảm bằng HMAC-SHA256 truncated 63-bit.
9. Chuẩn hóa schema, padding giá trị thiếu, merge các nguồn và deduplicate theo `sample_id`.
10. Validate quality gates và export final artifacts.

Các output cuối cùng nằm trong `data/final/`.

## 4. Mô Tả Chung Về Dữ Liệu Thu Được

Mỗi mẫu là một flow hai chiều, gồm các nhóm thông tin:

- Metadata và provenance.
- Label.
- Flow features.
- Timing patterns.
- TLS metadata.
- Certificate metadata.
- Packet sequence arrays.
- Quality flags.
- Training hints.

Một số điểm cần chú ý:

- Dataset chưa chia train/validation/test.
- Dataset không cân bằng label; `label=0` nhiều hơn `label=1`.
- TLS metadata không có ở mọi mẫu.
- Packet sequence không có ở mọi mẫu.
- Các cột provenance được giữ để audit, nhưng không nên đưa vào model input mặc định.
- Một số nguồn là PCAP đầy đủ, một số nguồn là flow CSV hoặc artifact, nên mức độ đầy đủ của feature khác nhau theo nguồn.

Coverage hiện tại:

| Coverage | Số mẫu |
|---|---:|
| `label=0`, không TLS | 173,114 |
| `label=0`, có TLS | 229,089 |
| `label=1`, không TLS | 13,383 |
| `label=1`, có TLS | 84 |

TLS full metadata:

| Label | Số mẫu `tls_full_available=1` |
|---|---:|
| `label=0` | 112,771 |
| `label=1` | 84 |

CESNET timing check:

- `cesnet_miner22`: 10,000 mẫu.
- 10,000/10,000 mẫu CESNET có `seq_iat` khác 0.
- `timing_full_available=1` khi sequence timing được trích xuất từ PPI times.

## 5. Quy Tắc Privacy Và Provenance

Dataset final không lưu:

- IP thô.
- SNI thô.
- Payload thô.

Các giá trị nhạy cảm được hash bằng HMAC-SHA256 với salt local, sau đó truncate về 63-bit để lưu an toàn trong `int64`.

Các cột hash/privacy:

- `src_ip_hash64`
- `dst_ip_hash64`
- `flow_key_hash64`
- `sni_hash64`
- `sni_tld_hash64`
- `tls_version_hash64`
- `cipher_hash64`
- `alpn_hash64`
- `ja3_hash64`
- `ja3s_hash64`
- `cert_subject_hash64`
- `cert_issuer_hash64`

Các cột provenance như `source`, `source_role`, `source_file`, `source_record_id`, `original_label`, `hard_negative_type` giúp truy vết nguồn và debug. Không nên dùng các cột này làm feature mặc định vì dễ gây source leakage.

## 6. Các Nhóm Đặc Trưng Và Ý Nghĩa

Schema final có 97 cột. Danh sách đầy đủ kiểu dữ liệu và group nằm trong `schema.json` và `data_dictionary.md`.

### 6.1 Metadata Và Label

| Feature | Ý nghĩa | Dùng cho model mặc định |
|---|---|---:|
| `sample_id` | ID ổn định của mẫu, sinh từ schema/source/flow/label. | Không |
| `schema_version` | Version schema. | Không |
| `source` | Tên nguồn dữ liệu. | Không |
| `source_role` | Vai trò nguồn trong dataset. | Không |
| `source_file` | File gốc sinh ra mẫu. | Không |
| `source_record_id` | ID record trong nguồn gốc nếu có. | Không |
| `original_label` | Label gốc trước khi map về 0/1. | Không |
| `label` | Nhãn nhị phân: 1 mining, 0 non-mining. | Target |
| `label_confidence` | Độ tin cậy nhãn, hiện chủ yếu là 1.0. | Không |

### 6.2 Flow Features

Flow features mô tả tổng quan hành vi truyền dữ liệu của một flow.

| Feature | Ý nghĩa |
|---|---|
| `time_first` | Thời điểm bắt đầu flow, dạng epoch nếu nguồn có thời gian. |
| `time_last` | Thời điểm kết thúc flow, dạng epoch nếu nguồn có thời gian. |
| `duration` | Thời lượng flow. |
| `proto` | Giao thức vận chuyển, ví dụ `tcp` hoặc `udp`. |
| `src_port` | Cổng nguồn. |
| `dst_port` | Cổng đích. |
| `bytes_total` | Tổng số byte của flow. |
| `bytes_fwd` | Byte chiều originator -> responder. |
| `bytes_bwd` | Byte chiều responder -> originator. |
| `packets_total` | Tổng số packet của flow. |
| `packets_fwd` | Packet chiều originator -> responder. |
| `packets_bwd` | Packet chiều responder -> originator. |
| `byte_rate` | Byte trung bình trên giây. |
| `packet_rate` | Packet trung bình trên giây. |
| `bytes_ratio_fwd` | Tỷ lệ byte theo chiều forward. |
| `packets_ratio_fwd` | Tỷ lệ packet theo chiều forward. |

Ý nghĩa khi train mô hình:

- Cryptomining thường có flow dài, lặp lại và duy trì kết nối ổn định.
- `duration`, `packet_rate`, `byte_rate`, `bytes_ratio_fwd` và `packets_ratio_fwd` là baseline tốt cho mô hình tabular.
- Không nên dùng raw IP, nhưng có thể dùng port và flow statistics.

### 6.3 Timing Patterns

Timing patterns mô tả nhịp truyền packet. Đây là nhóm feature quan trọng vì cryptomining thường tạo traffic có nhịp đều, burst lặp lại và các khoảng cách packet có cấu trúc.

#### Packet Length Statistics

| Feature | Ý nghĩa |
|---|---|
| `pkt_len_mean` | Độ dài packet trung bình. |
| `pkt_len_std` | Độ lệch chuẩn độ dài packet. |
| `pkt_len_min` | Độ dài packet nhỏ nhất. |
| `pkt_len_max` | Độ dài packet lớn nhất. |
| `pkt_len_p10` | Percentile 10 của độ dài packet. |
| `pkt_len_p50` | Median độ dài packet. |
| `pkt_len_p90` | Percentile 90 của độ dài packet. |

#### Inter-Arrival Time Statistics

| Feature | Ý nghĩa |
|---|---|
| `iat_mean` | Inter-arrival time trung bình. |
| `iat_std` | Độ lệch chuẩn inter-arrival time. |
| `iat_min` | IAT nhỏ nhất. |
| `iat_max` | IAT lớn nhất. |
| `iat_p10` | Percentile 10 của IAT. |
| `iat_p50` | Median của IAT. |
| `iat_p90` | Percentile 90 của IAT. |
| `iat_cv` | Coefficient of variation của IAT. |
| `iat_entropy` | Entropy của phân bố IAT. |
| `iat_zero_ratio` | Tỷ lệ IAT bằng 0 hoặc gần 0 theo parser. |
| `iat_small_ratio_10ms` | Tỷ lệ IAT nhỏ hơn 10 ms. |

#### Directional Timing

| Feature | Ý nghĩa |
|---|---|
| `fwd_iat_mean` | IAT trung bình theo chiều forward. |
| `bwd_iat_mean` | IAT trung bình theo chiều backward. |
| `fwd_bwd_iat_ratio` | Tỷ lệ nhịp forward/backward. |

#### Burst Và Periodicity

| Feature | Ý nghĩa |
|---|---|
| `burst_count` | Số burst phát hiện trong flow. |
| `burst_mean_packets` | Số packet trung bình trong mỗi burst. |
| `burst_max_packets` | Số packet lớn nhất trong một burst. |
| `periodicity_autocorr_lag` | Lag có autocorrelation cao nhất. |
| `periodicity_autocorr_score` | Điểm autocorrelation tại lag tốt nhất. |
| `periodicity_fft_peak` | Peak trong miền tần số từ chuỗi timing. |

Gợi ý sử dụng:

- Với mô hình tabular, các feature `iat_*`, `burst_*`, `periodicity_*` thường là nhóm rất đáng thử.
- Với mô hình sequence, nên dùng trực tiếp `seq_iat`, `seq_direction`, `seq_pkt_len`, `seq_signed_pkt_len`.
- Luôn kiểm tra `timing_full_available` và `packet_seq_available` trước khi diễn giải timing.

### 6.4 TLS Metadata

TLS metadata mô tả handshake, SNI đã ẩn danh, fingerprint và trạng thái TLS. Nhóm này hữu ích khi traffic mining được che bằng TLS hoặc HTTPS-like transport.

| Feature | Ý nghĩa |
|---|---|
| `has_tls` | Flow có TLS metadata hoặc có thể được nhận diện là TLS. |
| `tls_source` | Nguồn phát hiện TLS, ví dụ Zeek SSL log, heuristic port hoặc none. |
| `tls_version_id` | ID phiên bản TLS theo vocabulary. |
| `tls_version_hash64` | Hash của TLS version gốc. |
| `cipher_id` | ID cipher suite theo vocabulary nếu map được. |
| `cipher_hash64` | Hash của cipher suite. |
| `sni_hash64` | HMAC hash của SNI, không lưu SNI thô. |
| `sni_len` | Độ dài SNI. |
| `sni_num_labels` | Số label/domain parts trong SNI. |
| `sni_entropy` | Entropy của chuỗi SNI. |
| `sni_tld_hash64` | Hash của TLD trong SNI. |
| `alpn_id` | ID ALPN nếu có. |
| `alpn_hash64` | Hash ALPN. |
| `ja3_hash64` | Hash JA3 client fingerprint. |
| `ja3s_hash64` | Hash JA3S server fingerprint. |
| `tls_resumed` | TLS session có resumed hay không. |
| `tls_established` | TLS session đã established hay không. |
| `tls_handshake_seen` | Có quan sát được handshake hay không. |

Gợi ý sử dụng:

- `tls_version_id`, `cipher_hash64`, `ja3_hash64`, `ja3s_hash64` là các fingerprint mạnh, nhưng cần cẩn thận với overfitting theo nguồn.
- `sni_len`, `sni_num_labels`, `sni_entropy` là feature suy diễn từ SNI mà không lộ SNI thô.
- Với flow không TLS, các cột TLS được padding về 0 hoặc `unknown`.
- Khi train nên dùng thêm `has_tls`, `tls_metadata_available`, `tls_full_available` như mask hoặc feature phụ.

### 6.5 Certificate Metadata

| Feature | Ý nghĩa |
|---|---|
| `cert_observed` | Có certificate được quan sát hay không. |
| `cert_subject_hash64` | Hash subject certificate. |
| `cert_issuer_hash64` | Hash issuer certificate. |
| `cert_validity_days` | Số ngày hiệu lực certificate. |
| `cert_key_alg_id` | ID thuật toán key của certificate. |
| `cert_key_length` | Độ dài key. |
| `cert_sig_alg_id` | ID thuật toán chữ ký. |
| `cert_san_count` | Số SAN entries. |
| `cert_self_signed` | Certificate self-signed hay không. |
| `cert_chain_len` | Độ dài chain nếu có. |

Certificate metadata có thể giúp phân biệt traffic TLS hợp lệ phổ biến với một số TLS endpoint bất thường. Tuy nhiên nhiều TLS 1.3 session hoặc capture giữa phiên có thể thiếu x509 đầy đủ.

### 6.6 Packet Sequence Features

Các cột sequence được giữ trong `samples.parquet`, không có trong `samples.csv.gz`.

| Feature | Ý nghĩa |
|---|---|
| `seq_len_stored` | Số packet được giữ trong sequence. |
| `seq_pkt_len` | List độ dài packet. |
| `seq_signed_pkt_len` | List độ dài packet có dấu theo chiều. |
| `seq_direction` | List chiều packet. |
| `seq_iat` | List inter-arrival time giữa các packet. |

Quy ước:

- Sequence được cắt ngắn theo `max_packets_store`.
- Khi thiếu sequence, các list được padding rỗng/0 theo schema.
- `seq_signed_pkt_len` giúp mô hình học đồng thời độ dài và hướng.
- `seq_iat` là feature chính để học timing patterns dạng chuỗi.

### 6.7 Quality Flags Và Training Hints

| Feature | Ý nghĩa |
|---|---|
| `packet_seq_available` | Có packet sequence hay không. |
| `tls_metadata_available` | Có TLS metadata hay không. |
| `tls_full_available` | Có TLS metadata đầy đủ hơn, thường từ Zeek SSL/X509. |
| `timing_full_available` | Timing sequence/statistics có đủ tin cậy hay không. |
| `possible_tls_port` | Port có khả năng là TLS dù không có metadata đầy đủ. |
| `extract_status` | Trạng thái extract. |
| `quality_notes` | Ghi chú chất lượng, nếu có. |
| `hard_negative_type` | Loại hard negative, dùng cho provenance/audit. |
| `sample_weight_suggested` | Trọng số gợi ý nếu muốn dùng trong training. |

## 7. Hướng Dẫn Sử Dụng Các File Final

Các file trong `data/final/`:

| File | Mục đích |
|---|---|
| `samples.parquet` | File chính, chứa toàn bộ feature, bao gồm sequence arrays. |
| `samples.csv.gz` | Bản CSV nén chỉ chứa scalar features, bỏ sequence arrays. |
| `schema.json` | Schema machine-readable: dtype, padding, group và cờ model input. |
| `feature_vocab.json` | Vocabulary cho các categorical TLS/certificate IDs. |
| `manifest.json` | Manifest của raw files: path, size, SHA256, source, record URL. |
| `provenance.parquet` | Bảng truy vết source/source_file/original_label theo sample. |
| `stats.json` | Thống kê dataset dạng JSON. |
| `stats_report.md` | Báo cáo thống kê ngắn dạng Markdown. |
| `data_dictionary.md` | Data dictionary dạng bảng từ schema. |
| `description.md` | File mô tả tổng quan này. |

Ví dụ đọc dữ liệu:

```python
import pandas as pd

df = pd.read_parquet("data/final/samples.parquet")
print(df.shape)
print(df["label"].value_counts())
```

Nếu chỉ dùng mô hình tabular:

```python
import pandas as pd

df = pd.read_csv("data/final/samples.csv.gz")
```

Nếu muốn chọn feature mặc định theo schema:

```python
import json
import pandas as pd

with open("data/final/schema.json", "r", encoding="utf-8") as f:
    schema = json.load(f)

feature_cols = [
    c["name"]
    for c in schema["columns"]
    if c.get("can_use_for_model_input") is True
]

df = pd.read_parquet("data/final/samples.parquet")
X = df[feature_cols]
y = df["label"]
```

Khi dùng `samples.csv.gz`, cần loại các feature list khỏi `feature_cols` nếu chúng không có trong CSV.

## 8. Gợi Ý Train Mô Hình

### 8.1 Baseline Nên Thử Trước

Nên bắt đầu với mô hình tabular:

- Logistic Regression hoặc Linear SVM cho baseline đơn giản.
- Random Forest, XGBoost, LightGBM hoặc CatBoost cho baseline mạnh hơn.
- Feature groups nên thử: flow + timing + TLS scalar + certificate scalar + quality flags.

Sau đó mới thử mô hình sequence:

- 1D CNN trên `seq_signed_pkt_len`, `seq_direction`, `seq_iat`.
- GRU/LSTM/Transformer nhỏ cho packet sequence.
- Hybrid model: tabular branch + sequence branch.

### 8.2 Split Dữ Liệu

Không nên random split đơn giản toàn bộ dataset nếu mục tiêu là đánh giá khả năng tổng quát hóa. Nên dùng:

- Group split theo `source_file`.
- Hoặc leave-one-source-out evaluation.
- Hoặc train trên nhiều source và test riêng theo từng source.

Lý do: nếu random split, mô hình có thể học đặc trưng riêng của capture/source thay vì học hành vi cryptomining thật.

### 8.3 Xử Lý Mất Cân Bằng

Dataset hiện lệch mạnh về `label=0`. Khi train nên cân nhắc:

- `class_weight`.
- Focal loss nếu dùng neural network.
- Downsample `label=0` trong train set, không downsample validation/test.
- Báo cáo thêm PR-AUC, recall, precision, F1 cho `label=1`, không chỉ accuracy.

### 8.4 Dùng TLS Và Timing Một Cách Cẩn Thận

TLS metadata rất hữu ích nhưng dễ overfit theo endpoint, JA3 hoặc source. Timing patterns có thể tổng quát hóa tốt hơn trong một số bối cảnh, nhưng cũng phụ thuộc capture environment.

Khuyến nghị:

- Train/evaluate riêng các ablation:
  - Flow only.
  - Flow + timing.
  - Flow + TLS.
  - Flow + timing + TLS.
  - Sequence only.
  - Hybrid scalar + sequence.
- Luôn báo cáo performance theo `source`.
- Kiểm tra performance riêng trên mẫu `has_tls=1` và `has_tls=0`.

### 8.5 Các Cột Không Nên Dùng Làm Feature Mặc Định

Không nên đưa trực tiếp vào model:

- `sample_id`
- `schema_version`
- `source`
- `source_role`
- `source_file`
- `source_record_id`
- `original_label`
- `hard_negative_type`
- `extract_status`
- `quality_notes`
- `sample_weight_suggested`

Những cột này hữu ích cho audit, split, debugging hoặc weighting, nhưng có nguy cơ leakage nếu dùng trực tiếp làm feature.

## 9. Lưu Ý Về Phiên Bản V1

Bản V1 ưu tiên:

- Schema ổn định.
- Không lộ raw private fields.
- Có đủ coverage từ nhiều nguồn.
- Có cả flow features, TLS metadata và timing/sequence patterns.
- Có provenance để audit.

Các giới hạn hiện tại:

- Dataset chưa được cân bằng lại.
- Chưa có train/validation/test split chính thức.
- Một số nguồn có metadata không đầy đủ.
- `cj_sniffer` không đạt điều kiện encrypted-only vì label gốc hiện là `encrypted=no` toàn bộ.
- `cesnet_miner22` và `iot23_mcfp` đang dùng local row cap để build được trên máy hiện tại; raw data vẫn còn trong `data/raw` để mở rộng khi cần.

Khi dùng cho nghiên cứu hoặc training production-like, nên tạo split theo group/source, chạy ablation và kiểm tra khả năng tổng quát hóa theo từng nguồn.
