# Source-distribution drift

Output của contribution phụ C2.

Sinh bởi `scripts/16_source_drift.py` (drift) và
`scripts/17_drift_vs_gen.py` (correlation với generalization gap).
Xem `evaluation/BENCHMARK_REPORT.md` để biết bối cảnh và diễn giải.

## File

| File | Mục đích |
|---|---|
| `source_drift_jsd.csv` | Long format: `feature, group, source_a, source_b, jsd`. 1035 rows = 69 features × 15 source pairs. |
| `source_drift_by_group.csv` | Aggregated theo `(group, source_a, source_b)`: mean_jsd, median_jsd, max_jsd, n_features. |
| `source_drift_matrix_<group>.csv` | Pivot 6×6 symmetric matrix per feature group (`flow`, `timing`, `tls`, `certificate`). Diagonal = 0. |
| `top_drifting_features.csv` | Top 3 features có JSD cao nhất per source pair. |
| `drift_vs_generalization.csv` | Join với kết quả cross-source benchmark: `regime, heldout_source, feature_group, metric, in_source_value, cross_source_value, gap, mean_drift_over_group`. 24 rows. |
| `correlation_summary.csv` | Spearman ρ + Pearson r giữa drift và gap, per (regime, feature_group). |

## Phương pháp

- 50-bin quantile histogram trên các giá trị đã concatenate; thêm smoothing 1e-12 để tránh `log(0)`.
- `scipy.spatial.distance.jensenshannon(base=2.0)` — symmetric, bounded `[0,1]`.
- Loại các cột: `time_first`, `time_last` (leak source identity), feature thuộc group `metadata/provenance/label/privacy/quality/sequence/training_hint`, và mọi cột không có cờ `can_use_for_model_input=True`.

## Reproduce

```bash
source .venv/bin/activate

python scripts/16_source_drift.py
python scripts/17_drift_vs_gen.py
```

Runtime tổng < 5s.
