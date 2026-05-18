# Plan Hoàn Chỉnh Xây Dựng Dataset Cryptomining / Non-Mining V1

## Summary
- Xây dựng dataset flow-level nhị phân: `label=1` cryptomining, `label=0` non-mining/hard negative, chưa chia train/validation/test.
- Giữ schema cố định cho mọi mẫu, padding nhất quán khi thiếu TLS hoặc packet sequence.
- Không lưu IP thô, SNI thô, payload raw trong final; raw PCAP chỉ nằm ở vùng `data/raw`.
- Nguồn giữ đúng định hướng trong `plan.md`: [Auto-capture HF](https://huggingface.co/datasets/mdokl/Auto-capture-cryptomining-data), [CESNET-MINER22](https://zenodo.org/records/7189293), [CJ-Sniffer](https://github.com/yebof/CJ-Sniffer-Dataset), [MineShark](https://zenodo.org/records/13630503), [HIKARI-2021](https://zenodo.org/records/5199540), [IoT-23 MCFP](https://mcfp.felk.cvut.cz/publicDatasets/IoT-23-Dataset/).
- Điểm cần sửa so với plan hiện tại: đồng bộ lại tên scripts, dùng absolute path khi chạy Zeek, dùng HMAC-SHA256 thay vì xxhash thường cho dữ liệu riêng tư, và thêm quality gate bắt buộc cho coverage TLS/non-TLS.

## Interfaces Và Outputs
- Project root: `/home/odixe/project_dataset/cryptomining_dataset_v1`.
- Config chính:
  - `configs/sources.yaml`: URL, local path, checksum nếu có, size estimate, source role.
  - `configs/build.yaml`: TCP-only, `min_packets_per_flow=3`, `max_packets_store=256`, export parquet/csv, fallback IoT-23 small nếu thiếu disk.
  - `configs/privacy.yaml`: secret salt local-only, `hash_method=hmac_sha256_truncated_63bit`, không commit salt thật.
  - `configs/schema.yaml`: dtype, padding value, feature group, `can_use_for_model_input`.
- CLI/pipeline chuẩn hóa thành:
  - `00_download_sources.sh`, `01_unpack_sources.sh`, `02_build_manifest.py`, `03_run_zeek.sh`, `04_extract_packet_sequences.py`, `05_parse_zeek_logs.py`, `06_parse_cesnet.py`, `07_parse_mineshark_artifact.py`, `08_parse_hikari.py`, `09_parse_iot23_mcfp.py`, `10_normalize_schema.py`, `11_merge_and_dedupe.py`, `12_validate_and_stats.py`, `13_export_final.py`, `run_pipeline.sh`.
- Output bắt buộc:
  - `data/final/samples.parquet` là output chính.
  - `samples.csv.gz` chỉ chứa scalar features, bỏ sequence arrays.
  - `schema.json`, `feature_vocab.json`, `manifest.json`, `provenance.parquet`, `stats.json`, `stats_report.md`, `data_dictionary.md`.

## Implementation Changes
- Bootstrap thư mục theo `plan.md`, nhưng thêm `data/interim/audit/private_debug/` để chứa SNI/IP debug đã hạn chế truy cập, không dùng train và không export.
- Download theo source cố định; với Zenodo, script phải hỗ trợ retry, user-agent, checksum/md5 từ trang record, và báo lỗi rõ nếu server trả `403` cho request tự động.
- Tạo raw manifest ngay sau download/unpack, gồm `source`, `path`, `size_bytes`, `sha256`, `file_type`, `downloaded_at`, `record_url`, `license_or_rights`.
- PCAP sources dùng chung pipeline:
  - Chạy Zeek bằng absolute PCAP path, output JSON nếu có thể.
  - Parse `conn.log`, `ssl.log`, `x509.log`, optional `dns.log`.
  - Extract packet sequence bằng `dpkt`/`scapy`, canonical bidirectional 5-tuple, originator là packet đầu tiên.
  - Join Zeek flow với packet sequence bằng `source_file + canonical_5tuple + time overlap`, tolerance 1 giây, reject nếu tie không giải được.
- CSV/artifact sources:
  - CESNET đọc chunk, map `Miner -> 1`, `Other -> 0`, map PPI arrays sang sequence; bỏ payload bytes nếu có.
  - MineShark chỉ lấy `obfuscated` và `perturbed`; nếu không có PCAP thì map feature sẵn có và đặt `tls_metadata_available=0` khi thiếu TLS.
  - HIKARI chỉ giữ flow benign match chắc chắn với ground truth; ưu tiên TLS/HTTPS, reject ambiguous match.
  - IoT-23 giữ benign và malware không liên quan mining làm `label=0`, lưu `hard_negative_type`, loại mọi scenario/label có dấu hiệu cryptomining.
- Privacy/schema:
  - IP, SNI, issuer/subject/cipher raw hash bằng HMAC-SHA256 với salt local; lấy 63 bit để lưu an toàn dưới `int64`, padding `0`.
  - Không lưu raw SNI/IP trong final. `source`, `source_file`, `original_label` được giữ cho provenance/audit nhưng `can_use_for_model_input=false`.
  - Sequence dtypes: `seq_pkt_len=list<int32>`, `seq_signed_pkt_len=list<int32>`, `seq_direction=list<int8>`, `seq_iat=list<float32>`.
- Validation:
  - Fail hard nếu thiếu `samples.parquet`, schema không khớp, `sample_id` trùng/null, label ngoài `{0,1}`, hoặc final có raw payload/SNI/IP.
  - Fail hard nếu không có label 1 TLS đầy đủ, label 0 TLS đầy đủ từ HIKARI, CESNET flow-scale, CJ encrypted, MineShark obfuscated/perturbed, và IoT-23 hard negative.
  - Warn không fail nếu mất cân bằng source/label, thiếu JA3, thiếu x509 do TLS 1.3 hoặc capture giữa phiên.

## Test Plan
- Unit tests cho hash privacy, canonical flow key, sequence truncation/padding, TLS padding, CESNET PPI parsing, sample_id stability.
- Integration smoke test bằng 1 PCAP nhỏ/source hoặc sample subset: Zeek parse → packet sequence → canonical parquet → merge → validate.
- Schema test đọc `samples.parquet` bằng `pyarrow` và so với `schema.json`.
- Data quality tests:
  - `label` có cả 0 và 1.
  - `has_tls` có cả 0 và 1 ở dataset tổng.
  - `packet_seq_available` đúng với nguồn có/không có PCAP.
  - `source`, `source_role`, `source_file`, `original_label` không nằm trong default model feature list.
- Reproducibility test: rerun cùng input tạo cùng `sample_id`, cùng manifest hash, cùng vocab IDs với `unknown=0`.

## Assumptions
- V1 là local batch pipeline, chưa cần orchestration bằng Airflow/DVC.
- Không thêm nguồn ngoài danh sách trong `plan.md`.
- Nếu disk dưới ngưỡng cấu hình, dùng IoT-23 small nhưng vẫn phải đạt quality gate; nếu không đạt thì pipeline fail rõ lý do.
- HIKARI giữ record/version đã nêu trong plan để tái lập, không tự động đổi sang newer Zenodo version.
- Final dataset không cân bằng lại bằng sampling; cân bằng và group split để downstream training xử lý sau.
