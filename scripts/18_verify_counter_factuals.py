"""Counter-factual experiments cited in BENCHMARK_REPORT.md §6.2 and §6.3.

These were originally run ad-hoc during the verification pass to test two
framings written in the threats-to-validity section:

  V3 (§6.3): Is dst_port/src_port the dominant driver of the inflated
             in-distribution baseline (~0.999 recall_pos)?
             Method: rerun in-source 80/20 baseline with vs without port
             columns, all 4 feature groups.
             Finding: port accounts for ~0.6 percentage point of inflation;
             flow features broadly separate mining from benign regardless.

  V4 (§6.2): Is the TLS-padding artifact the main driver of FPR=1.0 on the
             iot23 holdout for flow_tls?
             Method: train HGB on iot23-heldout fold with three
             configurations (flow_only, flow_only+has_tls, flow_tls full),
             measure FPR on iot23 test (which has 0 mining flows, so any
             positive prediction is a false positive).
             Finding: flow_only alone already gives FPR=0.998. has_tls flag
             pushes to 1.000. Full TLS cols add nothing on top of has_tls.

Outputs under data/final/evaluation/05_cross_source_benchmark/:
  - in_source_port_ablation.csv (V3)
  - iot23_tls_padding_ablation.csv (V4)
"""

import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split

warnings.filterwarnings("ignore")

SEED = 42
ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "data/final/evaluation/05_cross_source_benchmark/_subsampled_cache.parquet"
FEATURE_CFG = ROOT / "data/final/evaluation/04_feature_group_ablations/feature_columns.json"
SPLIT_PATH = ROOT / "data/final/evaluation/01_source_file_group_holdout/source_holdout_membership.csv.gz"
OUT_DIR = ROOT / "data/final/evaluation/05_cross_source_benchmark"

TIME_LEAKAGE = {"time_first", "time_last"}
PORT_COLS = {"dst_port", "src_port"}


def coerce(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    X = df[cols].copy()
    for c in X.columns:
        if X[c].dtype == object or str(X[c].dtype).startswith("string"):
            X[c] = pd.Categorical(X[c].astype(str)).codes.astype(np.int32)
        else:
            X[c] = pd.to_numeric(X[c], errors="coerce").astype(np.float32)
    return X.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def build_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.05,
        max_leaf_nodes=63,
        min_samples_leaf=50,
        l2_regularization=0.1,
        class_weight="balanced",
        random_state=SEED,
    )


def load_inputs():
    if not CACHE_PATH.exists():
        raise SystemExit(
            f"Missing {CACHE_PATH}. Run scripts/15_cross_source_benchmark.py first."
        )
    cache = pd.read_parquet(CACHE_PATH)
    with open(FEATURE_CFG) as f:
        feature_sets = json.load(f)["feature_sets"]
    return cache, feature_sets


def v3_in_source_port_ablation(cache: pd.DataFrame, feature_sets: dict) -> pd.DataFrame:
    """V3 — in-distribution baseline with vs without port columns."""
    rows = []
    y = cache["label"].astype(int).values
    for fg_name, fg_cols in feature_sets.items():
        cols_full = [c for c in fg_cols if c in cache.columns and c not in TIME_LEAKAGE]
        cols_no_ports = [c for c in cols_full if c not in PORT_COLS]
        for variant_name, cols in [("with_ports", cols_full), ("without_ports", cols_no_ports)]:
            X = coerce(cache, cols)
            X_tr, X_te, y_tr, y_te = train_test_split(
                X, y, test_size=0.2, stratify=y, random_state=SEED
            )
            m = build_model()
            m.fit(X_tr, y_tr)
            proba = m.predict_proba(X_te)[:, 1]
            pred = (proba >= 0.5).astype(int)
            rows.append({
                "feature_group": fg_name,
                "variant": variant_name,
                "n_features": int(len(cols)),
                "f1_pos": round(float(f1_score(y_te, pred, zero_division=0)), 4),
                "recall_pos": round(float(recall_score(y_te, pred, zero_division=0)), 4),
                "precision_pos": round(float(precision_score(y_te, pred, zero_division=0)), 4),
            })
    return pd.DataFrame(rows)


def v4_iot23_tls_padding_ablation(cache: pd.DataFrame, feature_sets: dict) -> pd.DataFrame:
    """V4 — FPR on iot23 heldout with 3 incremental TLS exposures."""
    split = pd.read_csv(SPLIT_PATH)
    fold = split[split["heldout_source"] == "iot23_mcfp"]
    sid_set = set(cache["sample_id"])
    tr_ids = [s for s in fold[fold["split"] == "train"]["sample_id"] if s in sid_set]
    te_ids = [s for s in fold[fold["split"] == "test"]["sample_id"] if s in sid_set]
    ci = cache.set_index("sample_id")
    d_tr, d_te = ci.loc[tr_ids], ci.loc[te_ids]

    flow_only_cols = [c for c in feature_sets["flow_only"]
                      if c in cache.columns and c not in TIME_LEAKAGE]
    flow_tls_cols = [c for c in feature_sets["flow_tls"]
                     if c in cache.columns and c not in TIME_LEAKAGE]

    configs = [
        ("flow_only_no_tls", flow_only_cols),
        ("flow_only_plus_has_tls", flow_only_cols + ["has_tls"]),
        ("flow_tls_full", flow_tls_cols),
    ]
    rows = []
    y_tr = d_tr["label"].astype(int).values
    y_te = d_te["label"].astype(int).values
    n_te = len(y_te)
    n_pos_te = int((y_te == 1).sum())
    for variant_name, cols in configs:
        X_tr = coerce(d_tr, cols)
        X_te = coerce(d_te, cols)
        m = build_model()
        m.fit(X_tr, y_tr)
        proba = m.predict_proba(X_te)[:, 1]
        pred = (proba >= 0.5).astype(int)
        # iot23 test set has 0 mining flows; every positive prediction is FP.
        fpr = float((pred == 1).sum() / max(n_te, 1)) if n_pos_te == 0 else float("nan")
        rows.append({
            "config": variant_name,
            "n_features": int(len(cols)),
            "n_train": int(len(y_tr)),
            "n_test": int(n_te),
            "n_pos_test": n_pos_te,
            "fpr_iot23": round(fpr, 4),
        })
    return pd.DataFrame(rows)


def main():
    cache, feature_sets = load_inputs()
    print(f"[load] cache: {len(cache):,} rows, sources={sorted(cache['source'].unique())}")

    print("\n=== V3: in-source baseline with vs without port columns ===")
    v3 = v3_in_source_port_ablation(cache, feature_sets)
    print(v3.to_string(index=False))
    v3.to_csv(OUT_DIR / "in_source_port_ablation.csv", index=False)
    print(f"[write] {OUT_DIR / 'in_source_port_ablation.csv'}")

    print("\n=== V4: FPR on iot23 heldout with 3 TLS exposure configs ===")
    v4 = v4_iot23_tls_padding_ablation(cache, feature_sets)
    print(v4.to_string(index=False))
    v4.to_csv(OUT_DIR / "iot23_tls_padding_ablation.csv", index=False)
    print(f"[write] {OUT_DIR / 'iot23_tls_padding_ablation.csv'}")


if __name__ == "__main__":
    main()
