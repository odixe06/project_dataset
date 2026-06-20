# Evaluation Artifacts

Thư mục này chứa các artifact phục vụ chia dữ liệu, chống leakage, chạy feature ablation và báo cáo kết quả đánh giá cho dataset
`cryptomining_dataset_v1/data/final`.

Các file được sinh từ `samples.csv.gz`. Hầu hết artifact chỉ chứa `sample_id`, metadata split hoặc subset feature, không copy toàn bộ `samples.parquet`. Khi cần train/evaluate trên đầy đủ dữ liệu, join các file này với `samples.csv.gz` hoặc `samples.parquet` bằng khóa `sample_id`.

**Báo cáo benchmark tổng hợp:** [`BENCHMARK_REPORT.md`](BENCHMARK_REPORT.md) —
kết quả của hai contribution chính của dataset (cross-source generalization
benchmark + source-distribution drift report). Output của benchmark đặt dưới
[`05_cross_source_benchmark/`](05_cross_source_benchmark/) và
[`06_source_drift/`](06_source_drift/). Khuyến nghị đọc trước khi đi sâu vào
các artifact chia split bên dưới.

## Cách dùng nhanh

1. Dùng `01_source_file_group_holdout/source_holdout_membership.csv.gz` nếu
   muốn đánh giá khả năng generalize sang từng nguồn dữ liệu chưa thấy.
2. Dùng `01_source_file_group_holdout/source_file_group_split.csv.gz` nếu muốn
   có một split train/validation/test tránh trộn cùng `source_file` giữa các
   split.
3. Dùng `03_deduplicated_feature_groups/dedup_group_split.csv.gz` cho final
   evaluation chống leakage từ các vector feature giống hoặc gần giống nhau.
4. Dùng các file trong `04_feature_group_ablations/` để train model với từng
   nhóm feature: flow only, flow + timing, flow + TLS, flow + timing + TLS.
5. Sau khi có prediction, dùng `02_performance_slices/reporting_slices.csv.gz`
   để report metric theo source, TLS/non-TLS và sequence availability.

## File gốc và script

| File | Mục đích |
|---|---|
| `README.md` | Tài liệu tổng quan về các artifact evaluation. |
| `build_evaluation_artifacts.py` | Script sinh lại toàn bộ nội dung trong thư mục `evaluation` từ `samples.csv.gz` và `schema.json`. Dùng khi dataset final thay đổi hoặc muốn regenerate artifact. |

## `01_source_file_group_holdout/`

Nhóm file này phục vụ đánh giá theo nguồn dữ liệu và split theo nhóm file gốc.
Mục tiêu là hạn chế source leakage, vì random split đơn giản có thể làm model
học đặc trưng riêng của capture/source thay vì hành vi cryptomining.

| File | Sử dụng làm gì |
|---|---|
| `README.md` | Ghi chú ngắn cho nhóm artifact source/file-group holdout. |
| `source_holdout_membership.csv.gz` | File membership cho leave-one-source-out evaluation. Mỗi `fold_id` tương ứng một `heldout_source`; các dòng thuộc source đó có `split=test`, các source còn lại có `split=train`. Dùng file này để train trên tất cả source trừ một source, rồi test riêng trên source bị holdout. |
| `source_holdout_summary.csv` | Bảng tóm tắt từng fold source-holdout: source nào bị holdout, số mẫu train/test, số label 0/1 và ghi chú nếu test chỉ có một class. Dùng để kiểm tra nhanh fold có phù hợp với metric đang tính hay không. |
| `source_file_group_split.csv.gz` | Một split train/validation/test duy nhất, giữ toàn bộ mẫu có cùng `(source, source_file)` trong cùng một split. Dùng khi cần split ổn định theo file gốc để giảm leakage giữa train và test. |
| `source_file_group_summary.csv` | Thống kê từng group `(source, source_file)`: group id, split, source, source file, count và phân bố label. Dùng để audit split và kiểm tra source/file nào nằm ở train, validation hoặc test. |

Lưu ý: một số source chỉ có một `source_file`, nên không thể chia nội bộ source
đó sang nhiều split mà vẫn giữ ràng buộc group theo file.

## `02_performance_slices/`

Nhóm file này không dùng để chia train/test trực tiếp. Nó dùng để gắn thêm nhãn
slice khi báo cáo kết quả, sau khi model đã tạo prediction.

| File | Sử dụng làm gì |
|---|---|
| `README.md` | Ghi chú ngắn cho nhóm artifact reporting slice. |
| `reporting_slices.csv.gz` | Mapping từ `sample_id` sang các slice báo cáo: `source`, `tls_slice` (`tls` hoặc `non_tls`), `sequence_slice` (`sequence_available` hoặc `sequence_unavailable`) và slice kết hợp `source_tls_sequence_slice`. Join prediction với file này để tính metric theo từng lát cắt. |
| `slice_counts.csv` | Số mẫu và phân bố label 0/1 cho từng slice. Dùng để biết slice nào đủ lớn, slice nào chỉ có một class, và để diễn giải metric cẩn thận. |
| `metrics_template.csv` | Template trống để điền kết quả model theo từng slice, gồm các cột như TP, FP, TN, FN, accuracy, precision, recall, F1, ROC-AUC, PR-AUC. Dùng như format thống nhất cho báo cáo. |

## `03_deduplicated_feature_groups/`

Nhóm file này phục vụ deduplicate hoặc group near-identical feature vectors
trước final evaluation. Các dòng được group theo scalar model-input features
sau khi áp dụng padding từ schema và làm tròn float tới 6 chữ số có nghĩa.

| File | Sử dụng làm gì |
|---|---|
| `README.md` | Ghi chú ngắn cho nhóm artifact dedup/near-duplicate. |
| `dedup_group_split.csv.gz` | Mapping từng `sample_id` sang `dedup_group_id`, kích thước group, cờ representative và split train/validation/test. Dùng file này cho final split chống leakage: mọi sample trong cùng một near-identical group luôn nằm cùng một split. |
| `dedup_group_summary.csv.gz` | Thống kê ở cấp group: fingerprint, split, count, label_0, label_1, group có mixed label hay không, và `representative_sample_id`. Dùng để audit duplicate group hoặc chỉ giữ representative khi muốn train/evaluate trên bản deduplicated. |
| `dedup_summary.json` | Metadata của quá trình dedup: danh sách feature dùng để tạo fingerprint, quy tắc near-identical, tổng số mẫu, số group unique, số mẫu thuộc group duplicate, max group size và split ratio. Dùng để mô tả phương pháp trong báo cáo/thí nghiệm. |

Nếu muốn tạo bản deduplicated thật sự, có thể lấy các dòng
`is_group_representative=1` từ `dedup_group_split.csv.gz`, rồi join lại với
`samples.csv.gz` hoặc `samples.parquet`.

## `04_feature_group_ablations/`

Nhóm file này chứa các CSV scalar đã được lọc sẵn theo nhóm feature để chạy
ablation. Mỗi file có `sample_id`, `label` và các feature tương ứng. Các file
này không chứa sequence arrays vì sequence chỉ có trong `samples.parquet`.

| File | Sử dụng làm gì |
|---|---|
| `README.md` | Ghi chú ngắn cho nhóm artifact feature ablation. |
| `feature_columns.json` | Danh sách cột chính xác cho từng ablation set. Dùng để kiểm tra model đang nhận feature nào và để reproduce thí nghiệm. |
| `flow_only.csv.gz` | Dataset scalar chỉ gồm flow features như duration, proto, ports, bytes, packets, byte rate, packet rate và ratio forward. Dùng làm baseline tối giản. |
| `flow_timing.csv.gz` | Flow features cộng timing/statistical packet features như packet length stats, IAT stats, burst và periodicity. Dùng để đo đóng góp của timing patterns. |
| `flow_tls.csv.gz` | Flow features cộng TLS và certificate metadata. TLS variants bao gồm cả schema group `tls` và `certificate`. Dùng để đo đóng góp của TLS/certificate metadata khi không dùng timing. |
| `flow_timing_tls.csv.gz` | Flow + timing + TLS/certificate. Đây là bộ scalar đầy đủ nhất trong 4 ablation và dùng để so sánh với các subset nhỏ hơn. |

## Gợi ý join với split

Các ablation CSV không tự chứa cột `split`. Khi train/evaluate, hãy join một
file ablation với một file split bằng `sample_id`, ví dụ:

```python
import pandas as pd

features = pd.read_csv("04_feature_group_ablations/flow_timing_tls.csv.gz")
split = pd.read_csv("03_deduplicated_feature_groups/dedup_group_split.csv.gz")
df = features.merge(split[["sample_id", "split"]], on="sample_id", how="inner")

train = df[df["split"] == "train"]
validation = df[df["split"] == "validation"]
test = df[df["split"] == "test"]
```

Sau khi model sinh prediction theo `sample_id`, join prediction với
`02_performance_slices/reporting_slices.csv.gz` để tính metric theo từng slice.
