"""Cross-source generalization benchmark (contribution C1).

Trains HistGradientBoostingClassifier with class_weight='balanced' on:
  - 4 feature group ablations (flow_only, flow_timing, flow_tls, flow_timing_tls)
  - 6 leave-one-source-out folds
  - + 1 in-source random 80/20 baseline per feature group (for generalization gap)

Non-mining is subsampled to 100k (stratified by source) to keep total fits under
the 5-hour budget. Mining (label=1) is kept at full 13,467 samples.

Outputs under data/final/evaluation/05_cross_source_benchmark/:
  - results.csv: long-format per-fold metrics
  - summary_cross_source_matrix.csv: F1 matrix (feature_group x heldout_source)
  - summary_generalization_gap.csv: in-source vs cross-source F1 per feature_group
  - README.md: short interpretation
"""

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split

warnings.filterwarnings("ignore")

SEED = 42
NON_MINING_TARGET = 100_000

# Absolute-timestamp columns leak source identity (each source captured at a
# different epoch). They inflate in-source F1 to ~1.0 and make cross-source
# results meaningless. We drop them from every feature group. Duration is kept
# as it's a relative quantity carrying mining-relevant signal.
TIME_LEAKAGE_COLS = {"time_first", "time_last"}
ROOT = Path(__file__).resolve().parents[1]
SAMPLES_PATH = ROOT / "data/final/samples.parquet"
FEATURE_CFG_PATH = ROOT / "data/final/evaluation/04_feature_group_ablations/feature_columns.json"
SPLIT_PATH = ROOT / "data/final/evaluation/01_source_file_group_holdout/source_holdout_membership.csv.gz"
OUT_DIR = ROOT / "data/final/evaluation/05_cross_source_benchmark"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CACHE_PATH = OUT_DIR / "_subsampled_cache.parquet"


def load_dataset(use_cache: bool = True) -> pd.DataFrame:
    if use_cache and CACHE_PATH.exists():
        print(f"[load] cache hit: {CACHE_PATH}")
        return pd.read_parquet(CACHE_PATH)
    print(f"[load] reading {SAMPLES_PATH}")
    df = pd.read_parquet(SAMPLES_PATH)
    print(f"[load] full: {len(df):,} rows, labels {df['label'].value_counts().to_dict()}")
    # Filter out rows the parser flagged as not fully extracted. As of V1, the
    # mineshark_artifact parser writes extract_status='partial_feature_table'
    # for all rows because the raw CSV layout is artifact-dependent and the
    # parser does not map feature columns. Including these rows in the
    # benchmark would make the model see all-zero feature vectors for the
    # mineshark fold (recall_pos collapses to 0), which is a parser issue, not
    # a generalization finding. They are dropped here and documented in
    # BENCHMARK_REPORT.md.
    n_before = len(df)
    df = df[df["extract_status"] == "ok"].reset_index(drop=True)
    n_dropped = n_before - len(df)
    if n_dropped:
        dropped_sources = sorted(set(pd.read_parquet(SAMPLES_PATH).loc[
            pd.read_parquet(SAMPLES_PATH)["extract_status"] != "ok", "source"].unique()))
        print(f"[load] dropped {n_dropped:,} rows with extract_status != ok "
              f"(sources: {dropped_sources})")
    mining = df[df["label"] == 1]
    non_mining = df[df["label"] == 0]
    rng = np.random.RandomState(SEED)
    sampled_parts = []
    for src, sub in non_mining.groupby("source"):
        share = len(sub) / len(non_mining)
        take = int(round(NON_MINING_TARGET * share))
        take = min(take, len(sub))
        sampled_parts.append(sub.sample(n=take, random_state=rng.randint(0, 1_000_000)))
    non_mining_sampled = pd.concat(sampled_parts, ignore_index=True)
    out = pd.concat([mining, non_mining_sampled], ignore_index=True)
    out = out.sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    print(
        f"[load] subsampled: {len(out):,} rows, "
        f"labels {out['label'].value_counts().to_dict()}, "
        f"sources {out['source'].value_counts().to_dict()}"
    )
    out.to_parquet(CACHE_PATH, compression="zstd")
    print(f"[load] cached -> {CACHE_PATH}")
    return out


def load_feature_groups() -> dict:
    with open(FEATURE_CFG_PATH) as f:
        cfg = json.load(f)
    return cfg["feature_sets"]


def coerce_features(df: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
    X = df[feature_cols].copy()
    for col in X.columns:
        if X[col].dtype == object or str(X[col].dtype).startswith("string"):
            X[col] = pd.Categorical(X[col].astype(str)).codes.astype(np.int32)
        else:
            X[col] = pd.to_numeric(X[col], errors="coerce").astype(np.float32)
    X = X.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return X


def compute_metrics(y_true, y_pred, y_proba) -> dict:
    out = {
        "n_test": int(len(y_true)),
        "n_pos": int((y_true == 1).sum()),
        "n_neg": int((y_true == 0).sum()),
    }
    has_pos = out["n_pos"] > 0
    has_neg = out["n_neg"] > 0
    if has_pos and has_neg:
        out["f1_pos"] = float(f1_score(y_true, y_pred, pos_label=1, zero_division=0))
        out["pr_auc"] = float(average_precision_score(y_true, y_proba))
        out["roc_auc"] = float(roc_auc_score(y_true, y_proba))
    else:
        out["f1_pos"] = float("nan")
        out["pr_auc"] = float("nan")
        out["roc_auc"] = float("nan")
    out["recall_pos"] = (
        float(recall_score(y_true, y_pred, pos_label=1, zero_division=0)) if has_pos else float("nan")
    )
    out["recall_neg"] = (
        float(recall_score(y_true, y_pred, pos_label=0, zero_division=0)) if has_neg else float("nan")
    )
    out["precision_pos"] = (
        float(precision_score(y_true, y_pred, pos_label=1, zero_division=0)) if has_pos else float("nan")
    )
    if has_neg:
        out["fpr"] = float(((y_pred == 1) & (y_true == 0)).sum() / max(out["n_neg"], 1))
    else:
        out["fpr"] = float("nan")
    if has_pos and has_neg:
        cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
        out["TN"], out["FP"], out["FN"], out["TP"] = (int(v) for v in cm.ravel())
    else:
        out["TN"] = out["FP"] = out["FN"] = out["TP"] = -1
    return out


def fit_eval(X_tr, y_tr, X_te, y_te) -> tuple:
    model = HistGradientBoostingClassifier(
        max_iter=300,
        learning_rate=0.05,
        max_leaf_nodes=63,
        min_samples_leaf=50,
        l2_regularization=0.1,
        class_weight="balanced",
        random_state=SEED,
    )
    model.fit(X_tr, y_tr)
    y_proba = model.predict_proba(X_te)[:, 1]
    y_pred = (y_proba >= 0.5).astype(int)
    return y_pred, y_proba


def run():
    t0 = time.time()
    df = load_dataset()
    feature_sets = load_feature_groups()
    split_df = pd.read_csv(SPLIT_PATH)

    sid_to_row = {sid: i for i, sid in enumerate(df["sample_id"].values)}
    rows = []

    # In-source baseline: stratified random 80/20 of the (subsampled) full dataset
    for fg_name, fg_cols in feature_sets.items():
        present = [c for c in fg_cols if c in df.columns and c not in TIME_LEAKAGE_COLS]
        print(f"\n[baseline:{fg_name}] features={len(present)}")
        X_all = coerce_features(df, present)
        y_all = df["label"].astype(int).values
        X_tr, X_te, y_tr, y_te = train_test_split(
            X_all, y_all, test_size=0.2, stratify=y_all, random_state=SEED
        )
        t = time.time()
        y_pred, y_proba = fit_eval(X_tr, y_tr, X_te, y_te)
        m = compute_metrics(y_te, y_pred, y_proba)
        m.update(
            {
                "experiment": "in_source_random",
                "fold_id": "in_source_random_80_20",
                "heldout_source": "none",
                "feature_group": fg_name,
                "slice": "all",
                "model": "hgb",
                "n_train": int(len(y_tr)),
                "fit_seconds": round(time.time() - t, 2),
            }
        )
        rows.append(m)
        print(f"  done in {m['fit_seconds']}s F1={m['f1_pos']:.3f} PR-AUC={m['pr_auc']:.3f}")

    # Leave-one-source-out cross-source folds
    df_indexed = df.set_index("sample_id")
    for fold_id, sub in split_df.groupby("fold_id"):
        heldout = sub["heldout_source"].iloc[0]
        train_ids = sub.loc[sub["split"] == "train", "sample_id"].values
        test_ids = sub.loc[sub["split"] == "test", "sample_id"].values
        train_ids = [s for s in train_ids if s in sid_to_row]
        test_ids = [s for s in test_ids if s in sid_to_row]
        if not train_ids or not test_ids:
            print(f"[skip:{fold_id}] empty after subsample restriction")
            continue
        df_tr = df_indexed.loc[train_ids]
        df_te = df_indexed.loc[test_ids]
        for fg_name, fg_cols in feature_sets.items():
            present = [c for c in fg_cols if c in df.columns and c not in TIME_LEAKAGE_COLS]
            print(
                f"\n[fold:{heldout}][{fg_name}] train={len(df_tr):,} "
                f"test={len(df_te):,} pos_test={int((df_te['label']==1).sum())}"
            )
            X_tr = coerce_features(df_tr, present)
            X_te = coerce_features(df_te, present)
            y_tr = df_tr["label"].astype(int).values
            y_te = df_te["label"].astype(int).values
            if len(np.unique(y_tr)) < 2:
                print(f"  skip: training set has single class")
                continue
            t = time.time()
            y_pred, y_proba = fit_eval(X_tr, y_tr, X_te, y_te)
            m_all = compute_metrics(y_te, y_pred, y_proba)
            m_all.update(
                {
                    "experiment": "cross_source",
                    "fold_id": fold_id,
                    "heldout_source": heldout,
                    "feature_group": fg_name,
                    "slice": "all",
                    "model": "hgb",
                    "n_train": int(len(y_tr)),
                    "fit_seconds": round(time.time() - t, 2),
                }
            )
            rows.append(m_all)
            print(
                f"  done in {m_all['fit_seconds']}s "
                f"F1={m_all['f1_pos']:.3f} recall_pos={m_all['recall_pos']:.3f} "
                f"FPR={m_all['fpr']:.4f}"
            )

    results = pd.DataFrame(rows)
    results.to_csv(OUT_DIR / "results.csv", index=False)
    print(f"\n[write] {OUT_DIR / 'results.csv'} ({len(results)} rows)")

    # Cross-source F1 matrix
    pivot = results[results["experiment"] == "cross_source"].pivot_table(
        index="feature_group", columns="heldout_source", values="f1_pos"
    )
    pivot.to_csv(OUT_DIR / "summary_cross_source_matrix.csv")
    print(f"[write] summary_cross_source_matrix.csv")

    # Generalization gap. Cross-source folds split into two metric regimes:
    #   - mining-source holdouts: test set is mining-only -> measure recall_pos
    #   - non-mining-source holdouts: test set is benign-only -> measure FPR
    # In-source baseline gives both metrics on a mixed test set.
    mining_folds = {"holdout_source__auto_capture_hf", "holdout_source__cesnet_miner22",
                    "holdout_source__cj_sniffer", "holdout_source__mineshark_artifact"}
    non_mining_folds = {"holdout_source__hikari2021", "holdout_source__iot23_mcfp"}
    gap_rows = []
    for fg in results["feature_group"].unique():
        in_src = results[(results["experiment"] == "in_source_random") & (results["feature_group"] == fg)]
        cs_mining = results[(results["experiment"] == "cross_source") & (results["feature_group"] == fg)
                            & (results["fold_id"].isin(mining_folds))]
        cs_benign = results[(results["experiment"] == "cross_source") & (results["feature_group"] == fg)
                            & (results["fold_id"].isin(non_mining_folds))]
        rec_is = float(in_src["recall_pos"].mean()) if len(in_src) else float("nan")
        rec_cs = float(cs_mining["recall_pos"].mean()) if len(cs_mining) else float("nan")
        fpr_is = float(in_src["fpr"].mean()) if len(in_src) else float("nan")
        fpr_cs = float(cs_benign["fpr"].mean()) if len(cs_benign) else float("nan")
        gap_rows.append({
            "feature_group": fg,
            "in_source_recall_pos": round(rec_is, 4),
            "cross_source_recall_pos_mean": round(rec_cs, 4),
            "recall_gap": round(rec_is - rec_cs, 4) if not (np.isnan(rec_is) or np.isnan(rec_cs)) else float("nan"),
            "in_source_fpr": round(fpr_is, 4),
            "cross_source_fpr_mean": round(fpr_cs, 4),
            "fpr_gap": round(fpr_cs - fpr_is, 4) if not (np.isnan(fpr_is) or np.isnan(fpr_cs)) else float("nan"),
            "n_mining_folds": int(len(cs_mining)),
            "n_benign_folds": int(len(cs_benign)),
        })
    pd.DataFrame(gap_rows).to_csv(OUT_DIR / "summary_generalization_gap.csv", index=False)
    print(f"[write] summary_generalization_gap.csv")

    # Cross-source recall_pos matrix (mining folds) + FPR matrix (benign folds)
    cs = results[results["experiment"] == "cross_source"].copy()
    cs_mining_pivot = cs[cs["fold_id"].isin(mining_folds)].pivot_table(
        index="feature_group", columns="heldout_source", values="recall_pos"
    )
    cs_mining_pivot.to_csv(OUT_DIR / "summary_recall_pos_matrix_mining_holdouts.csv")
    cs_benign_pivot = cs[cs["fold_id"].isin(non_mining_folds)].pivot_table(
        index="feature_group", columns="heldout_source", values="fpr"
    )
    cs_benign_pivot.to_csv(OUT_DIR / "summary_fpr_matrix_benign_holdouts.csv")
    print(f"[write] summary_recall_pos_matrix_mining_holdouts.csv + summary_fpr_matrix_benign_holdouts.csv")

    print(f"\n[total] {time.time() - t0:.0f}s")
    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild-cache", action="store_true")
    args = ap.parse_args()
    if args.rebuild_cache and CACHE_PATH.exists():
        CACHE_PATH.unlink()
    run()
