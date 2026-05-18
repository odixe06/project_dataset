# Data Dictionary

| column | dtype | group | padding | can_use_for_model_input |
|---|---:|---|---:|---:|
| sample_id | string | metadata |  | false |
| schema_version | string | metadata | mining_dataset_v1 | false |
| source | string | provenance |  | false |
| source_role | string | provenance |  | false |
| source_file | string | provenance |  | false |
| source_record_id | string | provenance |  | false |
| original_label | string | provenance |  | false |
| label | int8 | label | -1 | false |
| label_confidence | float32 | label | 1.0 | false |
| time_first | float64 | flow | 0.0 | true |
| time_last | float64 | flow | 0.0 | true |
| duration | float32 | flow | 0.0 | true |
| proto | string | flow | tcp | true |
| src_ip_hash64 | int64 | privacy | 0 | false |
| dst_ip_hash64 | int64 | privacy | 0 | false |
| src_port | int32 | flow | 0 | true |
| dst_port | int32 | flow | 0 | true |
| flow_key_hash64 | int64 | privacy | 0 | false |
| bytes_total | int64 | flow | 0 | true |
| bytes_fwd | int64 | flow | 0 | true |
| bytes_bwd | int64 | flow | 0 | true |
| packets_total | int32 | flow | 0 | true |
| packets_fwd | int32 | flow | 0 | true |
| packets_bwd | int32 | flow | 0 | true |
| byte_rate | float32 | flow | 0.0 | true |
| packet_rate | float32 | flow | 0.0 | true |
| bytes_ratio_fwd | float32 | flow | 0.0 | true |
| packets_ratio_fwd | float32 | flow | 0.0 | true |
| pkt_len_mean | float32 | timing | 0.0 | true |
| pkt_len_std | float32 | timing | 0.0 | true |
| pkt_len_min | float32 | timing | 0.0 | true |
| pkt_len_max | float32 | timing | 0.0 | true |
| pkt_len_p10 | float32 | timing | 0.0 | true |
| pkt_len_p50 | float32 | timing | 0.0 | true |
| pkt_len_p90 | float32 | timing | 0.0 | true |
| iat_mean | float32 | timing | 0.0 | true |
| iat_std | float32 | timing | 0.0 | true |
| iat_min | float32 | timing | 0.0 | true |
| iat_max | float32 | timing | 0.0 | true |
| iat_p10 | float32 | timing | 0.0 | true |
| iat_p50 | float32 | timing | 0.0 | true |
| iat_p90 | float32 | timing | 0.0 | true |
| iat_cv | float32 | timing | 0.0 | true |
| iat_entropy | float32 | timing | 0.0 | true |
| iat_zero_ratio | float32 | timing | 0.0 | true |
| iat_small_ratio_10ms | float32 | timing | 0.0 | true |
| fwd_iat_mean | float32 | timing | 0.0 | true |
| bwd_iat_mean | float32 | timing | 0.0 | true |
| fwd_bwd_iat_ratio | float32 | timing | 0.0 | true |
| burst_count | int32 | timing | 0 | true |
| burst_mean_packets | float32 | timing | 0.0 | true |
| burst_max_packets | int32 | timing | 0 | true |
| periodicity_autocorr_lag | int32 | timing | 0 | true |
| periodicity_autocorr_score | float32 | timing | 0.0 | true |
| periodicity_fft_peak | float32 | timing | 0.0 | true |
| has_tls | int8 | tls | 0 | true |
| tls_source | string | tls | none | true |
| tls_version_id | int32 | tls | 0 | true |
| tls_version_hash64 | int64 | tls | 0 | true |
| cipher_id | int32 | tls | 0 | true |
| cipher_hash64 | int64 | tls | 0 | true |
| sni_hash64 | int64 | tls | 0 | true |
| sni_len | int32 | tls | 0 | true |
| sni_num_labels | int32 | tls | 0 | true |
| sni_entropy | float32 | tls | 0.0 | true |
| sni_tld_hash64 | int64 | tls | 0 | true |
| alpn_id | int32 | tls | 0 | true |
| alpn_hash64 | int64 | tls | 0 | true |
| ja3_hash64 | int64 | tls | 0 | true |
| ja3s_hash64 | int64 | tls | 0 | true |
| tls_resumed | int8 | tls | 0 | true |
| tls_established | int8 | tls | 0 | true |
| tls_handshake_seen | int8 | tls | 0 | true |
| cert_observed | int8 | certificate | 0 | true |
| cert_subject_hash64 | int64 | certificate | 0 | true |
| cert_issuer_hash64 | int64 | certificate | 0 | true |
| cert_validity_days | float32 | certificate | 0.0 | true |
| cert_key_alg_id | int32 | certificate | 0 | true |
| cert_key_length | int32 | certificate | 0 | true |
| cert_sig_alg_id | int32 | certificate | 0 | true |
| cert_san_count | int32 | certificate | 0 | true |
| cert_self_signed | int8 | certificate | 0 | true |
| cert_chain_len | int32 | certificate | 0 | true |
| seq_len_stored | int32 | sequence | 0 | true |
| seq_pkt_len | list<int32> | sequence | [] | true |
| seq_signed_pkt_len | list<int32> | sequence | [] | true |
| seq_direction | list<int8> | sequence | [] | true |
| seq_iat | list<float32> | sequence | [] | true |
| packet_seq_available | int8 | quality | 0 | true |
| tls_metadata_available | int8 | quality | 0 | true |
| tls_full_available | int8 | quality | 0 | true |
| timing_full_available | int8 | quality | 0 | true |
| possible_tls_port | int8 | quality | 0 | true |
| extract_status | string | quality | ok | false |
| quality_notes | string | quality |  | false |
| hard_negative_type | string | provenance |  | false |
| sample_weight_suggested | float32 | training_hint | 1.0 | false |
