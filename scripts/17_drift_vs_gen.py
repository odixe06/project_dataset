"""Correlate source-distribution drift with cross-source generalization gap.

For each (heldout_source, feature_group) pair:
  drift = mean JSD between heldout_source and each training source on features
          belonging to feature_group
  gap   = in_source_metric - cross_source_metric, where the metric is
          recall_pos for mining-source holdouts (test is mining-only) and
          fpr for non-mining-source holdouts (test is benign-only)

Computes Spearman correlation between drift and gap, per metric regime.

Outputs under data/final/evaluation/06_source_drift/:
  - drift_vs_generalization.csv: per (heldout_source, feature_group) row
  - correlation_summary.csv: Spearman/Pearson rho + p-value per regime
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import pearsonr, spearmanr

ROOT = Path(__file__).resolve().parents[1]
BENCH_DIR = ROOT / "data/final/evaluation/05_cross_source_benchmark"
DRIFT_DIR = ROOT / "data/final/evaluation/06_source_drift"
SCHEMA_YAML = ROOT / "configs/schema.yaml"
FEATURE_CFG_PATH = ROOT / "data/final/evaluation/04_feature_group_ablations/feature_columns.json"
OUT_DIR = DRIFT_DIR

# Same exclusion list as drift script
EXCLUDE_COLS = {"time_first", "time_last"}


def feature_set_columns() -> dict:
    with open(FEATURE_CFG_PATH) as f:
        cfg = json.load(f)
    return {k: [c for c in v if c not in EXCLUDE_COLS]
            for k, v in cfg["feature_sets"].items()}


def main():
    bench = pd.read_csv(BENCH_DIR / "results.csv")
    drift = pd.read_csv(DRIFT_DIR / "source_drift_jsd.csv")
    fsets = feature_set_columns()

    mining_folds = {"holdout_source__auto_capture_hf", "holdout_source__cesnet_miner22",
                    "holdout_source__cj_sniffer", "holdout_source__mineshark_artifact"}
    non_mining_folds = {"holdout_source__hikari2021", "holdout_source__iot23_mcfp"}

    # In-source baseline metrics per feature_group
    is_base = bench[bench["experiment"] == "in_source_random"].set_index("feature_group")

    rows = []
    cs = bench[bench["experiment"] == "cross_source"]
    for _, r in cs.iterrows():
        fg = r["feature_group"]
        heldout = r["heldout_source"]
        fg_cols = fsets.get(fg, [])
        # Drift restricted to features in this feature group
        d_sub = drift[(drift["feature"].isin(fg_cols)) &
                      ((drift["source_a"] == heldout) | (drift["source_b"] == heldout))]
        if d_sub.empty:
            mean_drift = float("nan")
        else:
            mean_drift = float(d_sub["jsd"].mean())

        if r["fold_id"] in mining_folds:
            metric_name = "recall_pos"
            cs_val = float(r["recall_pos"])
            is_val = float(is_base.loc[fg, "recall_pos"]) if fg in is_base.index else float("nan")
            gap = is_val - cs_val
            regime = "mining_holdout"
        elif r["fold_id"] in non_mining_folds:
            metric_name = "fpr"
            cs_val = float(r["fpr"])
            is_val = float(is_base.loc[fg, "fpr"]) if fg in is_base.index else float("nan")
            gap = cs_val - is_val
            regime = "benign_holdout"
        else:
            continue

        rows.append({
            "regime": regime,
            "heldout_source": heldout,
            "feature_group": fg,
            "metric": metric_name,
            "in_source_value": round(is_val, 4),
            "cross_source_value": round(cs_val, 4),
            "gap": round(gap, 4),
            "mean_drift_over_group": round(mean_drift, 4),
            "n_drift_features": int(d_sub["feature"].nunique()) if not d_sub.empty else 0,
        })
    out = pd.DataFrame(rows)
    out.to_csv(OUT_DIR / "drift_vs_generalization.csv", index=False)
    print(f"[write] drift_vs_generalization.csv ({len(out)} rows)")

    # Correlation per (regime, feature_group)
    corr_rows = []
    for (regime, fg), sub in out.groupby(["regime", "feature_group"]):
        sub = sub.dropna(subset=["gap", "mean_drift_over_group"])
        if len(sub) < 3:
            corr_rows.append({"regime": regime, "feature_group": fg, "n": len(sub),
                              "spearman_rho": float("nan"), "spearman_p": float("nan"),
                              "pearson_r": float("nan"), "pearson_p": float("nan")})
            continue
        sr, sp = spearmanr(sub["mean_drift_over_group"], sub["gap"])
        pr, pp = pearsonr(sub["mean_drift_over_group"], sub["gap"])
        corr_rows.append({"regime": regime, "feature_group": fg, "n": int(len(sub)),
                          "spearman_rho": round(sr, 3), "spearman_p": round(sp, 3),
                          "pearson_r": round(pr, 3), "pearson_p": round(pp, 3)})
    # Also aggregate across all feature_groups per regime
    for regime, sub in out.groupby("regime"):
        sub = sub.dropna(subset=["gap", "mean_drift_over_group"])
        if len(sub) < 3:
            continue
        sr, sp = spearmanr(sub["mean_drift_over_group"], sub["gap"])
        pr, pp = pearsonr(sub["mean_drift_over_group"], sub["gap"])
        corr_rows.append({"regime": regime, "feature_group": "ALL", "n": int(len(sub)),
                          "spearman_rho": round(sr, 3), "spearman_p": round(sp, 3),
                          "pearson_r": round(pr, 3), "pearson_p": round(pp, 3)})
    pd.DataFrame(corr_rows).to_csv(OUT_DIR / "correlation_summary.csv", index=False)
    print(f"[write] correlation_summary.csv ({len(corr_rows)} rows)")


if __name__ == "__main__":
    main()
