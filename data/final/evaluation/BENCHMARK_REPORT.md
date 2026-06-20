# Benchmark Report — Cross-Source Generalization + Source Drift

Bản báo cáo tổng hợp hai đóng góp của project (V1):

- **C1 (chính):** Benchmark cross-source generalization cho cryptomining traffic detection trên dataset đa nguồn công khai, ablate theo nhóm feature, lượng hoá generalization gap mà MineShark và các công trình trước chưa đo trên public multi-source data.
- **C2 (phụ trợ):** Báo cáo source-distribution drift: đo Jensen-Shannon divergence pairwise giữa các source theo feature group, đối chiếu với generalization gap để xác định nhóm feature nào robust nhất khi cross-source.

Tất cả artifact đều regenerate được bằng script trong `scripts/`.

> **Đọc trước threats-to-validity ở §6.** Một số kết quả nhìn ấn tượng nhưng chịu giới hạn của n nhỏ, dataset composition và padding semantics. Báo cáo phân biệt rõ phát hiện *định tính* (đáng tin) khỏi số *định lượng* (gợi ý).

---

## 1. Setup

| Hạng mục | Giá trị |
|---|---|
| Dataset version | `mining_dataset_v1` (415,670 flows tổng) |
| **Loại trừ** | 2,716 rows từ `mineshark_artifact` có `extract_status='partial_feature_table'` (xem §6.1) |
| Sau loại trừ | 412,954 rows (mining 10,751 / non-mining 402,203) |
| Subsample dùng cho benchmark | mining giữ nguyên 10,751; non-mining stratified xuống 100,000 → 110,751 rows |
| Model | `sklearn.ensemble.HistGradientBoostingClassifier`, `class_weight="balanced"`, `max_iter=300`, `learning_rate=0.05`, `max_leaf_nodes=63`, `min_samples_leaf=50`, `random_state=42` |
| Feature groups | `flow_only` (14), `flow_timing` (41), `flow_tls` (42), `flow_timing_tls` (69), sau khi loại `time_first`/`time_last` (leak source identity) |
| Splits | 5 leave-one-source-out folds + 1 in-distribution random 80/20 baseline per feature group |
| Drift metric | Jensen-Shannon divergence, 50-bin quantile histogram, pairwise giữa 5 sources, 67 numeric model-input features |
| Seed | 42 cố định ở subsample, split, model |
| Reproduce | `python scripts/15_cross_source_benchmark.py && python scripts/16_source_drift.py && python scripts/17_drift_vs_gen.py` |

**Quyết định loại bỏ `time_first` / `time_last`.** Mỗi source được capture ở thời điểm khác nhau. Để nguyên các cột timestamp tuyệt đối, model trivially shortcut "captured in 2018 → label=0". Đã document.

**Quyết định loại bỏ `mineshark_artifact` rows.** Parser `07_parse_mineshark_artifact.py` không map raw features (kèm cờ `extract_status='partial_feature_table'` và `quality_notes` giải thích), khiến cả 2,716 rows có giá trị 0 trên mọi cột numeric (verify bằng `df.groupby('source')[numeric_cols].agg(['mean','std'])`). Nếu để nguyên, model sẽ trả recall=0 trên mineshark fold không phải vì obfuscation mà vì input rỗng — một parser issue, không phải finding. Đã được filter trong cả hai script benchmark. Xem §6.1.

---

## 2. Cross-source generalization (C1)

### 2.1 Mining-source holdout — recall_pos

Khi held-out source là mining-only (test set có 0 negatives), metric ý nghĩa duy nhất là `recall_pos`.

| feature_group | auto_capture_hf | cesnet_miner22 | cj_sniffer | mean |
|---|---:|---:|---:|---:|
| flow_only | 0.159 | 0.502 | 0.899 | **0.520** |
| flow_timing | 0.957 | 1.000 | 0.986 | **0.981** |
| flow_tls | 0.023 | 0.545 | 0.917 | **0.495** |
| flow_timing_tls | 0.957 | 1.000 | 0.986 | **0.981** |

### 2.2 Benign-source holdout — FPR

| feature_group | hikari2021 | iot23_mcfp |
|---|---:|---:|
| flow_only | 0.608 | 0.998 |
| flow_timing | **0.000** | **0.038** |
| flow_tls | 0.647 | 1.000 |
| flow_timing_tls | **0.000** | 1.000 |

### 2.3 In-distribution upper bound vs cross-source

| feature_group | in-dist recall_pos | cross-source recall_pos mean | recall_gap | in-dist FPR | cross-source FPR mean | fpr_gap |
|---|---:|---:|---:|---:|---:|---:|
| flow_only | 0.998 | 0.520 | 0.478 | 0.0004 | 0.803 | 0.803 |
| flow_timing | 0.999 | **0.981** | **0.018** | 0.000 | **0.019** | **0.019** |
| flow_tls | 0.999 | 0.495 | 0.504 | 0.0003 | 0.824 | 0.823 |
| flow_timing_tls | 0.999 | 0.981 | 0.018 | 0.000 | 0.500 | 0.500 |

**Lưu ý quan trọng về baseline:** "in-distribution recall_pos = 0.999" KHÔNG đại diện cho performance thực tế của mining detection trong deployment. Đây là *upper bound* khi train và test cùng phân bố, và bị inflate bởi việc `dst_port` của mining (3333/4444/14444) tách hoàn toàn khỏi `dst_port` của hikari (80/443) và iot23 (23, IoT C&C ports) — model có thể đạt 0.999 mà không học mining behavior nào. Trong báo cáo này, ý nghĩa của baseline là một *reference* để đo gap, không phải claim về accuracy thực tế.

### 2.4 Findings chính

1. **Timing features đóng cross-source gap gần như hoàn toàn.** Thêm timing vào flow features đẩy mean cross-source recall_pos từ 0.52 → 0.98 (gap giảm từ 0.48 → 0.018), đồng thời triệt tiêu FPR trên cả hikari và iot23 (0.80 → 0.019). Phát hiện này **support trực tiếp claim của MineShark paper** (Section V-D, line 161 và 288–290) rằng các temporal patterns trên size+timing là content-agnostic và robust — paper claim qualitative; ở đây lần đầu lượng hoá trên public multi-source data.
2. **TLS features không cải thiện cross-source khi đã có timing**, và độc lập làm cross-source TỆ HƠN flow. `flow_timing_tls` ≡ `flow_timing` về recall, nhưng FPR trên iot23 nhảy từ 0.038 lên 1.000 — model nhầm toàn bộ benign iot23 thành mining khi có TLS features. **⚠ Caveat quan trọng:** kết luận này không phải về TLS metadata thực; nó về cách TLS được encode trong dataset hiện tại (mining có TLS coverage chỉ 0.6% — 84/13,467 — vs paper deployment ~17.6%). Phần lớn cột TLS chứa padding value (0/`unknown`) cho hầu hết rows; "TLS features" thực chất gần giống biến `has_tls` flag. Xem §6.2.
3. **`flow_only` cho FPR cực cao bất hợp lý.** 60% hikari và 100% iot23 benign bị flag thành mining → flow features đơn thuần (port, byte rate, ratio) không tách mining khỏi benign khi distribution thay đổi.
4. **Per-source variation lớn.** `auto_capture_hf` recall jump 0.16 → 0.96 khi thêm timing — minh hoạ rõ giá trị timing features. `cesnet_miner22` reach 1.000 với mọi cấu hình timing-aware.

---

## 3. Feature group ablation summary

| feature_group | điểm chính | khuyến nghị |
|---|---|---|
| `flow_only` | Recall cross-source thấp (0.52); FPR cực cao (0.80) | Không đủ cho deployment |
| `flow_timing` | Recall cao nhất (0.98); FPR thấp nhất (0.019); generalization gap nhỏ nhất | **Khuyến nghị dùng** |
| `flow_tls` | Recall thấp (0.50); FPR rất cao (0.82); ⚠ kết quả bị chi phối bởi padding semantics | Không khuyến nghị, và conclusion về TLS metadata thực cần dataset có TLS coverage tốt hơn |
| `flow_timing_tls` | Recall ≡ `flow_timing`, FPR tệ hơn trên iot23 | Không thêm gì so với `flow_timing` |

Khuyến nghị tổng quát cho người dùng dataset này: **dùng `flow_timing` (41 features), bỏ TLS features.** Kết luận này chỉ rõ sau khi đo cross-source — random 80/20 split sẽ không cho thấy điều này.

---

## 4. Source-distribution drift (C2)

### 4.1 Mean JSD theo feature group (cao = phân bố khác xa)

Sau khi loại mineshark, các cặp source pairwise:

| group | min mean_JSD pair | max mean_JSD pair | overall observation |
|---|---|---|---|
| flow | cj_sniffer–hikari2021: 0.71 | hikari2021–iot23_mcfp: 0.88 | drift rất cao đều — chứng tỏ port/size phân bố tách rời cho từng capture |
| timing | cj_sniffer–cesnet: 0.74 | cesnet–hikari2021: 0.83 | nhiều cặp = 0 do thiếu sequence-derived timing |
| tls | hầu hết = 0 (không có TLS) | hikari–others: 0.46–0.47 | drift chủ yếu là "có TLS vs không TLS" |
| certificate | tất cả = 0 | n/a | non-finding (certificate gần như không có ở mọi source) |

Drift cao nhất ở **flow group** — đặc biệt `dst_port`, `bytes_total`, `packets_total` JSD ≈ 0.95–1.0 giữa nhiều cặp source. Điều này giải thích vì sao `flow_only` fails cross-source.

### 4.2 Top drifting features

`06_source_drift/top_drifting_features.csv` chứa top 3 per pair. Tóm tắt qua các group:
- **flow:** `dst_port`, `packets_total`, `bytes_total`, `bytes_fwd` thường JSD ~0.95–1.00.
- **timing:** `iat_zero_ratio`, `iat_small_ratio_10ms`, `pkt_len_min`, `pkt_len_p10` JSD cao ở các cặp cesnet ↔ hikari/iot.
- **tls:** `tls_version_hash64`, `cipher_hash64` JSD = 1.0 — nhưng do source không có TLS, phân bố là dirac ở padding value. ⚠ Drift này không phản ánh "TLS handshake content khác nhau" mà phản ánh "có/không có TLS".

---

## 5. Drift × generalization (synthesis)

Đối với mỗi (heldout_source, feature_group), tính mean JSD giữa heldout source và các source train (giới hạn vào features của feature_group đó), rồi tương quan với generalization gap.

| regime | feature_group | n | Spearman ρ | Spearman p | Pearson r | Pearson p |
|---|---|---:|---:|---:|---:|---:|
| mining_holdout | flow_only | 3 | 1.000 | 0.000 | 0.985 | 0.110 |
| mining_holdout | flow_timing | 3 | -0.500 | 0.667 | -0.690 | 0.515 |
| mining_holdout | flow_tls | 3 | -0.500 | 0.667 | -0.198 | 0.873 |
| mining_holdout | flow_timing_tls | 3 | -0.500 | 0.667 | -0.730 | 0.479 |
| benign_holdout | * | 2 | n/a (n too small) |

### 5.1 Cảnh báo về thống kê

**Mỗi correlation tính trên n=3 mining sources** (auto_capture_hf, cesnet_miner22, cj_sniffer). Với n=3, ρ=1.0 không phải bằng chứng thống kê — bất kỳ ba điểm có thứ tự đơn điệu đều cho ρ=1.0. Spearman p-value hiển thị 0.000 là artifact của scipy với mẫu siêu nhỏ; Pearson p-value 0.11 phản ánh đúng độ không chắc chắn hơn. **Đọc các số này như chỉ báo gợi ý (monotone tendencies), không phải kết luận tin cậy.**

### 5.2 Diễn giải định tính (chứng cứ định tính, không phải chứng minh thống kê)

- **`flow_only`: quan hệ drift→gap đơn điệu hoàn hảo trên 3 sources được kiểm tra.** Source nào càng xa phân bố flow của tập train, gap càng lớn. Gợi ý rằng drift trong flow feature là yếu tố chính gây generalization failure khi model chỉ học flow.
- **`flow_timing`: ρ âm yếu (-0.5).** Không có chiều hướng "drift cao → gap lớn". Tương thích với observation §2: timing features generalize well bất kể drift quan sát được. Lưu ý vì gap đã rất nhỏ (0.018) nên correlation không meaningful kể cả nếu n lớn — bottom-effect.
- **`flow_tls`: ρ âm yếu.** Tương tự không có chiều rõ ràng; finding bị nhiễu bởi vấn đề padding semantics (§6.2).

### 5.3 Hệ quả thực tế

Kết quả §4 + §5 gợi ý: **timing-based mining detection chịu shift phân bố cross-source tốt hơn flow-based hoặc TLS-based** — phù hợp với MineShark claim về content-agnostic timing features. Tuy nhiên với n=3 sources defendable, đây là *evidence-of-direction*, không phải kết luận đóng băng. Để strong-defensible cần ≥6 sources hoặc bootstrap CI; xem §7.

---

## 6. Threats to validity

### 6.1 mineshark_artifact placeholder rows

Parser `07_parse_mineshark_artifact.py` không map raw feature columns từ artifact CSV (do format artifact-dependent), kết quả là 2,716 mineshark rows có ALL feature numeric = 0 và `seq_pkt_len` = `[]`. Trước fix, recall_pos của fold mineshark = 0 trên mọi feature group — chúng tôi từng diễn giải nhầm thành finding về obfuscation, sau khi inspect mới phát hiện là parser issue.

**Hệ quả thực:** benchmark hiện tại đo cross-source generalization trên 5 sources, không bao gồm bất kỳ obfuscated mining data nào. Claim "model fails on obfuscated mining" KHÔNG được test trong V1 — phải re-parse mineshark_artifact với feature mapping đầy đủ trước khi đưa kết luận về obfuscation defeat learning detection.

**Khắc phục đề xuất:** sửa `07_parse_mineshark_artifact.py` map các cột raw từ `detect_obfuscated.csv` (artifact MineShark có schema cụ thể trong code paper), hoặc dùng PCAP của mineshark artifact thay vì CSV, qua pipeline 03-04-05 chuẩn.

### 6.2 TLS findings bị confound với padding semantics — nhưng KHÔNG phải driver chính

Mining sources có TLS coverage rất thấp (0.6% — chỉ 84/13,467 flows), trong khi hikari ~100% TLS, iot23 0% TLS. Cột TLS được pad bằng 0/`"unknown"` cho rows không có TLS, nên model dùng TLS features có thể học `has_tls=1 vs 0` chứ không phải handshake content.

**Counter-factual test (V4 trong verification log; reproduce bằng `scripts/18_verify_counter_factuals.py`, output `iot23_tls_padding_ablation.csv`):** trên fold heldout iot23, FPR với 3 cấu hình:

| Cấu hình | FPR trên iot23 |
|---|---:|
| `flow_only` (KHÔNG có TLS feature) | 0.998 |
| `flow_only + has_tls` (chỉ flag) | 1.000 |
| `flow_tls` (full 42 TLS cols) | 1.000 |

Kết luận: **flow features đã đẩy FPR lên 0.998** kể cả khi không có TLS. Thêm chỉ `has_tls` cộng thêm 0.002. Thêm full TLS cols không cộng thêm gì so với `has_tls` đơn lẻ → xác nhận TLS columns chủ yếu mang signal "có/không có TLS", không phải handshake content (padding artifact thật). Nhưng padding artifact KHÔNG phải nguyên nhân chính của FPR cao — flow features là. Caveat TLS-confound trong §2.4 finding #2 đúng về mặt mechanism nhưng không phải explanation chính cho `flow_tls` FPR.

Để test TLS metadata thực, vẫn cần (a) dataset có balanced TLS coverage hoặc (b) mask TLS cột bằng NaN khi `has_tls=0`.

### 6.3 In-distribution baseline là upper bound, không phải accuracy thực

In-dist recall_pos ~0.999 cao bất thường so với benchmark mining detection thực (paper MineShark deployment: precision/recall ~80–95%).

**Counter-factual test (V3 trong verification log; reproduce bằng `scripts/18_verify_counter_factuals.py`, output `in_source_port_ablation.csv`):** chúng tôi từng giả thuyết `dst_port`/`src_port` là thủ phạm chính (mining dùng 3333/4444 vs benign dùng 80/443/23). Rerun in-distribution baseline KHÔNG có `dst_port` + `src_port`:

| Feature group | F1 với port | F1 không port | Δ |
|---|---:|---:|---:|
| flow_only | 0.9972 | 0.9942 | −0.003 |
| flow_timing | 0.9995 | 0.9995 | 0.000 |
| flow_tls | 0.9984 | 0.9974 | −0.001 |
| flow_timing_tls | 0.9995 | 0.9995 | 0.000 |

→ Port không phải driver chính. Inflation đến từ việc *toàn bộ phân bố flow features* (bytes, packets, rate, ratio) giữa mining và benign trong dataset hiện tại trùng nhau đủ ít để model tách trivially. Đây là tính chất composition của dataset (mining: cesnet + cj_sniffer + auto_capture; benign: hikari + iot23), không phải artifact đơn lẻ. Baseline 0.999 do đó vẫn là *upper bound* không thực tế, nhưng lý do sâu hơn là phân bố overall separable, không chỉ một feature gây leak.

### 6.4 Statistical power thấp

n = 3 mining-source folds và 2 benign-source folds → mọi correlation/p-value cần đọc thận trọng. ρ=1.0 trên flow_only ấn tượng nhưng không phải chứng cứ kết luận. Cần ≥6 mining sources để Spearman p-value có ý nghĩa.

### 6.5 Sequence features không dùng trong baseline

Paper MineShark dùng 1D-CNN trên ma trận 4×N gồm bidirectional packet sizes và IATs. Baseline ở đây dùng aggregate statistics (mean, std, percentile) của packet length và IAT. Kết luận "timing features robust" áp dụng cho aggregated timing, không phải sequence-level timing. Sequence-based formulation có thể cho cross-source kết quả khác.

### 6.6 Threshold cố định 0.5

Mọi metric tính tại threshold 0.5. Với imbalance, threshold tối ưu F1 thường thấp hơn — số FPR/recall có thể thay đổi đáng kể nếu tune threshold per fold. Chưa có report tại operating point tối ưu.

### 6.7 No confidence intervals

Mọi số là point estimate. Recall trên cj_sniffer (218 mining flows) đặc biệt dễ biến động ±0.05. Bootstrap CIs nên được thêm cho version sau.

### 6.8 iot23 benign vs mining confound

iot23_mcfp gồm cả benign baseline lẫn IoT malware C&C traffic (Mirai, Okiru, Torii). Hiện cả hai được gán label=0. Model train trên hikari (web/scan benign) test trên iot23 → FPR cao có thể là do iot23 có pattern malware giống mining hơn benign hikari, không chỉ do domain shift của "benign". Đã document từ phase ban đầu nhưng chưa filter trong V1.

---

## 7. Đề xuất cho version sau

| Việc | Ước lượng | Tác động |
|---|---|---|
| Re-parse mineshark_artifact với feature mapping đầy đủ | ~4 giờ | Unblock obfuscation findings |
| Mask TLS cột bằng NaN khi `has_tls=0`, rerun | ~30 phút | TLS conclusion thực có ý nghĩa |
| Bootstrap CI cho mọi metric chính | ~15 phút | Defend statistical claims |
| Threshold tuning per fold cho F1 tối ưu | ~15 phút | Operating point chính xác |
| Thêm sources (ví dụ self-capture TLS mining) lên ≥6 | ~1 ngày | Statistical power cho correlation |
| Baseline sequence CNN trên seq_pkt_len + seq_iat | ~2 giờ | Test claim với formulation đúng như paper |
| Hard-negative filter trên iot23 (benign-only) | ~1 giờ | Loại confound malware/benign |

---

## 8. Reproduction

```bash
source .venv/bin/activate


# C1 — cross-source benchmark (~60s sau khi đã có cache; ~80s nếu rebuild)
python scripts/15_cross_source_benchmark.py

# C2 — source-distribution drift (~2s)
python scripts/16_source_drift.py

# Synthesis — drift × generalization correlation (~1s)
python scripts/17_drift_vs_gen.py
```

Tất cả output ghi vào `data/final/evaluation/05_cross_source_benchmark/` và `data/final/evaluation/06_source_drift/`. Seed cố định ở `random_state=42` toàn bộ pipeline; rerun trên cùng dataset cho cùng số liệu.

Để buộc resample (xoá cache subsample):

```bash
python scripts/15_cross_source_benchmark.py --rebuild-cache
```

---

## 9. Output files

```
05_cross_source_benchmark/
├── results.csv                                    # 24 rows: per-experiment metrics
├── summary_cross_source_matrix.csv                # F1 matrix (mostly NaN ở single-class folds)
├── summary_recall_pos_matrix_mining_holdouts.csv  # 4 feature groups × 3 mining sources
├── summary_fpr_matrix_benign_holdouts.csv         # 4 feature groups × 2 benign sources
├── summary_generalization_gap.csv                 # gap per feature_group
└── _subsampled_cache.parquet                      # cache non-mining subsample (xoá để rebuild)

06_source_drift/
├── source_drift_jsd.csv                # 690 rows: feature × source-pair JSD
├── source_drift_by_group.csv           # aggregated per (group, pair)
├── source_drift_matrix_{flow,timing,tls,certificate}.csv
├── top_drifting_features.csv           # top 3 features per pair
├── drift_vs_generalization.csv         # 20 rows: drift + gap joined
└── correlation_summary.csv             # Spearman/Pearson per regime
```

---

## 10. Honest summary (đề xuất framing khi defend)

> *Đây là benchmark sơ bộ trên dataset đa nguồn công khai, không phải tuyên bố cuối cùng. Phát hiện **định tính** — `flow_timing` features robust hơn `flow_only` và `flow_tls` cross-source — phù hợp với MineShark paper claim và được lượng hoá lần đầu trên public data với 5 sources. Phát hiện **định lượng** (gap = 0.018, ρ = 1.0 trên flow_only) là gợi ý mạnh nhưng cần xác nhận: (a) baseline "in-distribution" bị inflate bởi port-leakage trong cùng phân bố; (b) n = 3 mining sources không đủ statistical power; (c) TLS findings bị confound với padding semantics. Mineshark_artifact bị loại khỏi benchmark vì parser hiện không map raw features — cần re-parse trước khi kết luận về obfuscation. Sequence-based model như paper chính (CNN trên 4×N matrix) chưa được test ở đây.*
