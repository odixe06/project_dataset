# Cross-source generalization benchmark

Output của contribution chính C1.

Sinh bởi `scripts/15_cross_source_benchmark.py`. Xem
`evaluation/BENCHMARK_REPORT.md` để biết bối cảnh và diễn giải.

## File

| File | Mục đích |
|---|---|
| `results.csv` | Per-experiment long format: `experiment, fold_id, heldout_source, feature_group, model, n_train, n_test, n_pos, n_neg, f1_pos, pr_auc, roc_auc, recall_pos, recall_neg, precision_pos, fpr, TN, FP, FN, TP, fit_seconds`. 28 rows = 4 in-source baselines + 24 cross-source (6 folds × 4 feature groups). |
| `summary_cross_source_matrix.csv` | Pivot `feature_group × heldout_source → f1_pos`. NaN cho folds mà test set chỉ có 1 class. |
| `summary_recall_pos_matrix_mining_holdouts.csv` | Pivot recall_pos cho 4 mining-source holdouts × 4 feature groups. Đây là metric chính cho C1. |
| `summary_fpr_matrix_benign_holdouts.csv` | Pivot FPR cho 2 benign-source holdouts (hikari, iot23) × 4 feature groups. |
| `summary_generalization_gap.csv` | Per feature_group: in-source recall_pos / FPR vs cross-source mean → gap. |
| `in_source_port_ablation.csv` | Counter-factual V3 (xem `BENCHMARK_REPORT.md` §6.3 + `VERIFICATION_LOG.md`): in-distribution baseline với vs không `dst_port`+`src_port`, 4 feature group. Trả lời "port có phải driver chính của baseline inflation không?" (không). |
| `iot23_tls_padding_ablation.csv` | Counter-factual V4 (xem `BENCHMARK_REPORT.md` §6.2 + `VERIFICATION_LOG.md`): FPR trên iot23 heldout với 3 cấu hình TLS exposure. Trả lời "TLS padding có phải driver chính của FPR=1.0 không?" (không — flow features là chính). |
| `_subsampled_cache.parquet` | Cache của non-mining subsample 100k để rerun nhanh. Xoá để rebuild. |

## Reproduce

```bash
source .venv/bin/activate

python scripts/15_cross_source_benchmark.py             # dùng cache nếu có
python scripts/15_cross_source_benchmark.py --rebuild-cache  # buộc resample
python scripts/18_verify_counter_factuals.py            # V3 + V4 counter-factuals
```

Seed = 42. Runtime: benchmark ~80s, counter-factuals ~30s, trên CPU 8-core.
