# Verification Log

Đối chứng các fix áp dụng cho `BENCHMARK_REPORT.md`. Mỗi check trả lời "nếu fix sai/giả thuyết sai thì sẽ phát hiện như thế nào".

## V1 — Clean-state reproducibility ✅ PASS

**Câu hỏi:** Script chạy từ trạng thái sạch (xoá cache) có cho cùng số liệu không?

**Cách làm:** Snapshot 4 file output, xoá `_subsampled_cache.parquet`, rerun cả 3 script với `--rebuild-cache`, diff với snapshot.

**Kết quả:** Mọi metric scientific (F1, recall_pos, FPR, JSD, Spearman ρ, Pearson r) khớp **bit-exact**. Chỉ `fit_seconds` khác do wall-clock — không phải số liệu khoa học. Reproducibility xác nhận với `random_state=42`.

## V2 — Filter assertion (mineshark loại trừ) ✅ PASS

**Câu hỏi:** Fix `extract_status == 'ok'` có thực sự loại mineshark_artifact khỏi mọi downstream output không?

**Cách làm:** Assert `'mineshark_artifact' not in source` ở 3 nơi: subsample cache, benchmark results.csv, drift source_drift_jsd.csv.

**Kết quả:**
- Cache sources: `[auto_capture_hf, cesnet_miner22, cj_sniffer, hikari2021, iot23_mcfp]` — không có mineshark ✓
- Results folds: `[holdout_source__{auto_capture_hf, cesnet, cj, hikari, iot23}, in_source_random_80_20]` — không có mineshark fold ✓
- Drift sources: 5 sources, không có mineshark ✓

## V3 — In-source inflation counter-factual ⚠ HYPOTHESIS REFINED

**Câu hỏi:** Báo cáo claim `dst_port`/`src_port` là driver chính của baseline 0.999 inflate. Đúng không?

**Cách làm:** Rerun in-distribution random 80/20 baseline với và không `dst_port + src_port`, cả 4 feature group.

**Kết quả:**

| Feature group | F1 với port | F1 không port | Δ |
|---|---:|---:|---:|
| flow_only | 0.9972 | 0.9942 | −0.003 |
| flow_timing | 0.9995 | 0.9995 | 0.000 |
| flow_tls | 0.9984 | 0.9974 | −0.001 |
| flow_timing_tls | 0.9995 | 0.9995 | 0.000 |

(Số chính thức được chốt lại với hyperparams khớp 100% benchmark engine — `l2_regularization=0.1`. Output: [`05_cross_source_benchmark/in_source_port_ablation.csv`](05_cross_source_benchmark/in_source_port_ablation.csv). Reproduce: `python scripts/18_verify_counter_factuals.py`.)

**Hypothesis FALSIFIED:** Port chỉ chiếm ~0.3 percentage point của inflation; `flow_timing` không thay đổi gì. Nguyên nhân thật sâu hơn — **toàn bộ phân bố flow features (bytes, packets, rates) giữa mining và benign trong dataset hiện tại tách trivially**. Đây là tính chất composition của dataset, không phải artifact của một feature cụ thể.

**Đã cập nhật BENCHMARK_REPORT.md §6.3** để phản ánh finding mới này.

## V4 — TLS padding semantics ⚠ HYPOTHESIS REFINED

**Câu hỏi:** Báo cáo claim padding (TLS feature pad bằng 0 khi `has_tls=0`) là driver chính của FPR=1.0 trên iot23 với `flow_tls`. Đúng không?

**Cách làm:** Train 3 cấu hình trên fold heldout iot23, so FPR.

**Kết quả:**

| Cấu hình | #features | FPR trên iot23 |
|---|---:|---:|
| flow_only (KHÔNG có TLS) | 14 | 0.998 |
| flow_only + has_tls (chỉ flag) | 15 | 1.000 |
| flow_tls full (42 TLS cols) | 42 | 1.000 |

(Output: [`05_cross_source_benchmark/iot23_tls_padding_ablation.csv`](05_cross_source_benchmark/iot23_tls_padding_ablation.csv). Reproduce: `python scripts/18_verify_counter_factuals.py`.)

**Hypothesis PARTIALLY FALSIFIED:**
- flow features đã đẩy FPR lên 0.998 *mà không cần TLS feature nào*. Flow là driver chính.
- Thêm `has_tls` flag cộng thêm 0.002 → có padding artifact thật nhưng nhỏ.
- Thêm 41 TLS columns nữa không cộng thêm gì so với `has_tls` đơn lẻ → các TLS columns gần như duy nhất mang signal "có/không có TLS" trong dataset hiện tại (xác nhận padding-driven, vì mining có TLS coverage 0.6%).

**Đã cập nhật BENCHMARK_REPORT.md §6.2** để phản ánh: padding artifact tồn tại nhưng KHÔNG phải nguyên nhân chính của FPR cao; flow features là.

## V5 — Independent re-derivation ✅ PASS

**Câu hỏi:** Logic của `15_cross_source_benchmark.py` có bug không?

**Cách làm:** Re-train 1 fold (cesnet_miner22 heldout, flow_timing) bằng tay từ samples.parquet với code numpy/sklearn thuần, không qua harness. So recall_pos với số trong `results.csv`.

**Kết quả:**
- Hand-computed recall_pos = 1.0000
- Script-reported recall_pos = 1.0000
- Diff < 1e-6 ✓

Logic harness khớp với re-derivation độc lập.

---

## Tổng kết

| Check | Mục đích | Kết quả |
|---|---|---|
| V1 | Reproducibility | ✅ PASS bit-exact |
| V2 | Mineshark filter | ✅ PASS, vắng khắp nơi |
| V3 | Port = inflator? | ⚠ REFINED, port chỉ là một phần nhỏ; cấu trúc phân bố mới là chính |
| V4 | TLS padding = FPR driver? | ⚠ REFINED, padding artifact thật nhưng nhỏ; flow features là chính |
| V5 | Script logic | ✅ PASS, khớp re-derivation manual |

**3 PASS + 2 REFINEMENT.** Refinement là kết quả tích cực của verification — bắt được 2 chỗ framing chưa chính xác và đã sửa trong BENCHMARK_REPORT.md (§6.2, §6.3). Không có failure thật sự ở fix nào; phương pháp + filter đều đúng.

## Reproduce verification

```bash
source .venv/bin/activate


# V1
rm -f data/final/evaluation/05_cross_source_benchmark/_subsampled_cache.parquet
python scripts/15_cross_source_benchmark.py --rebuild-cache
python scripts/16_source_drift.py
python scripts/17_drift_vs_gen.py

# V3 + V4 counter-factuals (chốt lại bằng script reproducible)
python scripts/18_verify_counter_factuals.py
# Output:
#   data/final/evaluation/05_cross_source_benchmark/in_source_port_ablation.csv (V3)
#   data/final/evaluation/05_cross_source_benchmark/iot23_tls_padding_ablation.csv (V4)

# V2 + V5 vẫn dùng inline python; nội dung mô tả trong các mục trên.
```
