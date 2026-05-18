# Dataset Description

## 1. Tổng quan

`cryptomining_dataset_v1` là bộ dữ liệu flow-level nhị phân cho bài toán phát hiện cryptomining trên lưu lượng mạng. Mỗi mẫu là một bidirectional flow đã được chuẩn hóa về cùng schema, có nhãn `label=1` cho cryptomining và `label=0` cho non-mining hoặc hard negative không liên quan đến mining.

Dataset này được xây dựng theo hướng giữ schema cố định cho mọi mẫu, đồng thời bảo toàn thông tin đủ dùng cho huấn luyện mô hình nhưng không lưu các dữ liệu nhạy cảm như IP thô, SNI thô hoặc payload thô trong phần final.

## 2. Nguồn dữ liệu và quy trình xây dựng

### Nguồn dữ liệu chính

Dataset cuối cùng được tổng hợp từ các nguồn công khai sau:

- `auto_capture_hf`: PCAP cryptomining TLS từ Hugging Face.
- `cesnet_miner22`: flow CSV từ DeCryptoDatasets/CESNET-MINER22, có cả nhãn `Miner` và `Other`.
- `cj_sniffer`: PCAP từ CJ-Sniffer-Dataset, chỉ lấy mẫu `encrypted=yes`.
- `mineshark_artifact`: artifact của MineShark, chỉ dùng phần `obfuscated` và `perturbed`.
- `hikari2021`: PCAP và flow ground truth cho lưu lượng non-mining.
- `iot23_mcfp`: dữ liệu IoT-23 tải qua MCFP, dùng làm non-mining nền và hard negative.

### Quy trình trích xuất và chuẩn hóa

Pipeline xây dựng đi theo các bước chính sau:

1. Tải và giải nén nguồn dữ liệu vào `data/raw/`.
2. Tạo manifest thô để ghi lại đường dẫn, kích thước, hash, loại file và nguồn gốc.
3. Với các nguồn PCAP, chạy Zeek để sinh `conn.log`, `ssl.log`, `x509.log` và các log liên quan nếu có.
4. Trích packet sequence từ PCAP, sau đó ghép với flow đã parse bằng canonical bidirectional 5-tuple và khoảng giao thời gian phù hợp.
5. Với các nguồn CSV/artifact, đọc trực tiếp flow features hoặc sequence đã có sẵn, rồi map về cùng schema.
6. Chuẩn hóa cột, padding giá trị thiếu, hash các trường nhạy cảm bằng HMAC-SHA256 truncated 63-bit, và loại bỏ mọi trường raw không được phép xuất hiện ở final.
7. Hợp nhất, loại trùng, kiểm tra chất lượng và xuất bộ final.

### Kết quả cuối cùng

Toàn bộ pipeline tạo ra 415,670 mẫu, trong đó:

- `label=0`: 402,203 mẫu.
- `label=1`: 13,467 mẫu.

Theo nguồn:

- `hikari2021`: 229,089 mẫu.
- `iot23_mcfp`: 173,114 mẫu.
- `cesnet_miner22`: 10,000 mẫu.
- `mineshark_artifact`: 2,716 mẫu.
- `auto_capture_hf`: 533 mẫu.
- `cj_sniffer`: 218 mẫu.

## 3. Mô tả chung về dữ liệu thu được

Mỗi dòng dữ liệu biểu diễn một flow hai chiều và có các nhóm thông tin chính:

- metadata và provenance.
- nhãn và độ tin cậy của nhãn.
- đặc trưng flow cơ bản.
- đặc trưng timing và burst/periodicity.
- metadata TLS và certificate.
- sequence packet-level đã cắt ngắn/padding.
- cờ chất lượng mô tả mức độ đầy đủ của từng nhóm đặc trưng.

Một số lưu ý quan trọng:

- Dataset không chia sẵn train/validation/test.
- Dataset final không chứa raw IP, raw SNI hoặc raw payload.
- Các cột provenance như `source`, `source_file`, `source_record_id`, `original_label` được giữ để truy vết, nhưng không nên dùng làm input mặc định cho mô hình.
- Dữ liệu có cả mẫu đầy đủ TLS lẫn mẫu thiếu TLS; schema vẫn thống nhất nhờ padding.

### Phân bố TLS và sequence

Theo thống kê hiện tại, TLS metadata không xuất hiện đồng đều ở mọi nguồn. Dataset có cả mẫu có TLS và mẫu không có TLS để mô hình học được hai chế độ quan sát khác nhau.

Sequence packet-level cũng không đầy đủ cho mọi mẫu. Những nguồn từ CSV hoặc artifact có thể không có packet sequence đầy đủ, nên các cờ `packet_seq_available`, `timing_full_available` và `tls_metadata_available` cần được dùng để hiểu mức độ đầy đủ của từng mẫu.

## 4. Các đặc trưng sử dụng và ý nghĩa

### 4.1 Flow features

Đây là nhóm đặc trưng mô tả tổng quan một flow và là phần nền cho hầu hết mô hình tabular.

Các biến chính gồm:

- `time_first`, `time_last`, `duration`: thời điểm bắt đầu/kết thúc và thời lượng flow.
- `proto`: giao thức vận chuyển, hiện chủ yếu là `tcp`.
- `src_port`, `dst_port`: cổng nguồn và đích.
- `bytes_total`, `bytes_fwd`, `bytes_bwd`: tổng byte và phân rã theo chiều.
- `packets_total`, `packets_fwd`, `packets_bwd`: tổng packet và phân rã theo chiều.
- `byte_rate`, `packet_rate`: tốc độ truyền tải trung bình.
- `bytes_ratio_fwd`, `packets_ratio_fwd`: tỷ lệ hướng thuận trong flow.

Ý nghĩa thực tế:

- Cryptomining thường có flow dài hơn, nhịp đều hơn và nhiều phiên lặp lại hơn so với non-mining.
- Các tỷ lệ forward/backward và tốc độ truyền có thể giúp phân biệt giữa traffic handshake ngắn với session mining kéo dài.

### 4.2 Timing patterns

Nhóm timing mô tả nhịp điệu packet trong flow và là phần quan trọng để phân biệt cryptomining với lưu lượng TLS bình thường.

Các biến chính gồm:

- Thống kê độ dài packet: `pkt_len_mean`, `pkt_len_std`, `pkt_len_min`, `pkt_len_max`, `pkt_len_p10`, `pkt_len_p50`, `pkt_len_p90`.
- Thống kê inter-arrival time: `iat_mean`, `iat_std`, `iat_min`, `iat_max`, `iat_p10`, `iat_p50`, `iat_p90`.
- Đặc trưng biến thiên và phân bố: `iat_cv`, `iat_entropy`, `iat_zero_ratio`, `iat_small_ratio_10ms`.
- Đặc trưng theo chiều: `fwd_iat_mean`, `bwd_iat_mean`, `fwd_bwd_iat_ratio`.
- Burst và periodicity: `burst_count`, `burst_mean_packets`, `burst_max_packets`, `periodicity_autocorr_lag`, `periodicity_autocorr_score`, `periodicity_fft_peak`.

Ý nghĩa thực tế:

- Traffic cryptomining thường có nhịp lặp ổn định, burst đều và khoảng cách giữa các packet tương đối có cấu trúc.
- `iat_*` và các chỉ số periodicity hữu ích khi phát hiện hành vi mining chạy kéo dài và đều đặn.
- `burst_*` hỗ trợ nhận ra các pha trao đổi packet ngắn nhưng lặp đi lặp lại.

### 4.3 TLS Metadata

Nhóm TLS mô tả lớp bảo mật và dấu vân tay giao thức, là phần rất hữu ích khi phân tích cryptomining qua HTTPS/TLS.

Các biến chính gồm:

- `has_tls`, `tls_source`: cờ và kiểu nguồn TLS.
- `tls_version_id`, `tls_version_hash64`: phiên bản TLS đã chuẩn hóa và hash tương ứng.
- `cipher_id`, `cipher_hash64`: bộ mã hóa được dùng trong handshake.
- `sni_hash64`, `sni_len`, `sni_num_labels`, `sni_entropy`, `sni_tld_hash64`: đặc trưng từ SNI, nhưng chỉ giữ dưới dạng hash/đặc trưng suy diễn, không lưu chuỗi thô.
- `alpn_id`, `alpn_hash64`: ứng dụng lớp giao vận được quảng bá trong TLS.
- `ja3_hash64`, `ja3s_hash64`: fingerprint của client và server hello khi có thể trích xuất.
- `tls_resumed`, `tls_established`, `tls_handshake_seen`: trạng thái handshake và resumption.
- `cert_observed`, `cert_subject_hash64`, `cert_issuer_hash64`, `cert_validity_days`, `cert_key_alg_id`, `cert_key_length`, `cert_sig_alg_id`, `cert_san_count`, `cert_self_signed`, `cert_chain_len`: nhóm đặc trưng certificate.

Các giá trị categorical như TLS version, cipher, ALPN, certificate key algorithm và certificate signature algorithm được mã hóa bằng vocabulary trong `feature_vocab.json`. Giá trị `0` luôn đại diện cho `unknown`.

Ý nghĩa thực tế:

- Nhiều mẫu mining dùng TLS ẩn danh, nên fingerprint TLS có thể rất giàu tín hiệu.
- `tls_version_id`, `cipher_id`, `ja3_hash64`, `ja3s_hash64` và các đặc trưng certificate thường giúp mô hình phân biệt traffic mining với TLS hợp lệ khác.
- Với mẫu thiếu TLS, các trường này được padding về 0 để giữ schema ổn định.

### 4.4 Sequence features

Nhóm này lưu chuỗi packet-level đã cắt ngắn và chuẩn hóa, phục vụ các mô hình có thể học từ trình tự.

Các biến chính gồm:

- `seq_len_stored`: số packet thật sự được giữ lại trong sequence.
- `seq_pkt_len`: độ dài packet theo trị tuyệt đối.
- `seq_signed_pkt_len`: độ dài packet có dấu để biểu diễn chiều.
- `seq_direction`: chiều packet theo flow.
- `seq_iat`: inter-arrival time giữa các packet liên tiếp.

Các chuỗi đều được cắt ngắn/padding nhất quán, nên phù hợp cho mô hình sequence hoặc deep learning. Nếu một nguồn không có packet sequence đầy đủ, các cờ chất lượng sẽ phản ánh điều đó thay vì làm schema bị lệch.

## 5. Hướng dẫn sử dụng file trong dữ liệu cuối cùng

Các file chính trong `data/final/` hiện gồm:

- `samples.parquet`: file chính, chứa toàn bộ cột và sequence arrays.
- `samples.csv.gz`: bản xuất chỉ gồm các đặc trưng scalar, không gồm mảng sequence.
- `schema.json`: mô tả schema, kiểu dữ liệu và giá trị padding của từng cột.
- `feature_vocab.json`: mapping cho các categorical TLS values như TLS version, cipher, ALPN, certificate algorithms.
- `manifest.json`: provenance tổng hợp của các file nguồn đã được sử dụng.
- `provenance.parquet`: bảng truy vết chi tiết theo mẫu hoặc theo file nguồn.
- `stats.json`: thống kê machine-readable cho dataset.
- `stats_report.md`: bản tóm tắt thống kê và các cảnh báo/ghi chú.
- `data_dictionary.md`: bảng mô tả cột theo dtype, group và khả năng dùng làm input.

Khuyến nghị sử dụng:

- Dùng `samples.parquet` nếu cần sequence arrays hoặc muốn đọc đầy đủ schema.
- Dùng `samples.csv.gz` nếu chỉ train mô hình tabular trên các đặc trưng scalar.
- Dùng `schema.json` để kiểm tra kiểu cột và padding trước khi load dữ liệu vào pipeline.
- Dùng `feature_vocab.json` để encode các trường categorical nhất quán giữa train và inference.
- Dùng `provenance.parquet` khi cần debug, audit hoặc phân tích lỗi theo nguồn.

## 6. Gợi ý sử dụng bộ data để train mô hình

### 6.1 Nên và không nên dùng gì làm input

Nên dùng:

- flow features.
- timing patterns.
- TLS metadata đã hash/mã hóa.
- sequence features nếu mô hình có khả năng xử lý chuỗi.

Không nên dùng mặc định:

- `source`, `source_file`, `source_record_id`, `original_label`.
- mọi trường provenance và audit.
- bất kỳ trường raw nào không nằm trong final schema.

### 6.2 Cách chia train/validation/test

Dataset này chưa có split sẵn. Khi tạo split, nên ưu tiên:

- group split theo source hoặc source_file để tránh leakage.
- kiểm tra cân bằng label sau khi split.
- tách riêng đánh giá theo nguồn để đo khả năng tổng quát hóa.

### 6.3 Lưu ý về mất cân bằng và coverage

Dataset hiện khá lệch về label `0`, nên khi train cần cân nhắc:

- class weighting hoặc focal loss.
- downsampling/upsampling có kiểm soát trên train set בלבד.
- đo thêm PR-AUC, F1 và recall cho label `1`, không chỉ accuracy.

Ngoài ra, coverage TLS và sequence không đồng đều giữa các nguồn. Vì vậy:

- mô hình tabular nên học tốt cả trường hợp không có TLS.
- mô hình sequence nên xử lý được missing sequence một cách rõ ràng.
- nên dùng các cờ `has_tls`, `packet_seq_available`, `tls_metadata_available` như feature phụ hoặc như mask logic trong pipeline.

### 6.4 Gợi ý thực nghiệm

- Bắt đầu bằng mô hình tabular trên các feature scalar để có baseline ổn định.
- Sau đó thử kết hợp thêm sequence features để khai thác nhịp packet và burst pattern.
- Nếu dùng model học sâu, giữ chuẩn hóa và padding nhất quán giữa train và inference.
- Khi báo cáo kết quả, nên có thêm đánh giá theo từng nguồn để tránh mô hình học quá mạnh vào đặc trưng của một dataset cụ thể.

## 7. Ghi chú cuối

- Dataset này là bản V1 và ưu tiên tính nhất quán schema, truy vết nguồn và khả năng huấn luyện hơn là tối ưu hóa một model cụ thể.
- Các giá trị thiếu được padding nhất quán để cùng một schema có thể dùng cho nhiều kiểu mô hình khác nhau.
- Nếu cần phân tích sâu theo nguồn hoặc theo mức độ đầy đủ của TLS/sequence, hãy dùng thêm `stats.json`, `stats_report.md` và `provenance.parquet`.