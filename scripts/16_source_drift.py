"""Source-distribution drift report (contribution C2).

For every numeric model-input feature, computes pairwise Jensen-Shannon
divergence between sources. Aggregates by schema feature group (flow,
timing, tls, certificate). Sequence list-typed columns and provenance
columns are excluded.

Outputs under data/final/evaluation/06_source_drift/:
  - source_drift_jsd.csv: long format (feature, group, source_a, source_b, jsd)
  - source_drift_by_group.csv: per (group, source_a, source_b) aggregated jsd
  - source_drift_matrix_<group>.csv: pivot per feature group
"""

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.spatial.distance import jensenshannon

SEED = 42
N_BINS = 50
ROOT = Path(__file__).resolve().parents[1]
SAMPLES_PATH = ROOT / "data/final/samples.parquet"
SCHEMA_YAML = ROOT / "configs/schema.yaml"
OUT_DIR = ROOT / "data/final/evaluation/06_source_drift"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Same as benchmark: absolute timestamps leak source -> exclude.
EXCLUDE_COLS = {"time_first", "time_last"}
EXCLUDE_GROUPS = {"sequence", "metadata", "provenance", "label", "privacy",
                  "quality", "training_hint"}


def load_schema() -> list:
    with open(SCHEMA_YAML) as f:
        s = yaml.safe_load(f)
    return s["columns"]


def select_features(schema_cols: list) -> list:
    keep = []
    for col in schema_cols:
        name = col["name"]
        grp = col.get("group", "")
        if name in EXCLUDE_COLS:
            continue
        if grp in EXCLUDE_GROUPS:
            continue
        if not col.get("can_use_for_model_input", False):
            continue
        dtype = col.get("dtype", "")
        if dtype.startswith("list"):
            continue
        keep.append({"name": name, "group": grp, "dtype": dtype})
    return keep


def jsd_pair(a: np.ndarray, b: np.ndarray, n_bins: int = N_BINS) -> float:
    """Symmetric Jensen-Shannon divergence between two empirical distributions."""
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if len(a) == 0 or len(b) == 0:
        return float("nan")
    combined = np.concatenate([a, b])
    if np.allclose(combined.max(), combined.min()):
        return 0.0
    edges = np.quantile(combined, np.linspace(0, 1, n_bins + 1))
    edges = np.unique(edges)
    if len(edges) < 2:
        return 0.0
    hist_a, _ = np.histogram(a, bins=edges)
    hist_b, _ = np.histogram(b, bins=edges)
    pa = hist_a.astype(float) + 1e-12
    pb = hist_b.astype(float) + 1e-12
    pa /= pa.sum()
    pb /= pb.sum()
    return float(jensenshannon(pa, pb, base=2.0))


def main():
    t0 = time.time()
    df = pd.read_parquet(SAMPLES_PATH)
    print(f"[load] {len(df):,} rows")
    # Match benchmark: exclude rows the parser flagged as partial. See
    # scripts/15_cross_source_benchmark.py load_dataset() for rationale.
    n_before = len(df)
    df = df[df["extract_status"] == "ok"].reset_index(drop=True)
    if len(df) < n_before:
        print(f"[load] dropped {n_before - len(df):,} non-ok rows")
    schema_cols = load_schema()
    feats = select_features(schema_cols)
    print(f"[load] {len(feats)} features after filter")

    # Categorical strings -> codes
    for f in feats:
        col = f["name"]
        if df[col].dtype == object or str(df[col].dtype).startswith("string"):
            df[col] = pd.Categorical(df[col].astype(str)).codes.astype(np.int32)
        else:
            df[col] = pd.to_numeric(df[col], errors="coerce").astype(np.float32)

    sources = sorted(df["source"].unique())
    print(f"[load] sources={sources}")

    rows = []
    for f in feats:
        col = f["name"]
        per_source = {s: df.loc[df["source"] == s, col].dropna().to_numpy(dtype=np.float64)
                      for s in sources}
        for i, sa in enumerate(sources):
            for sb in sources[i + 1:]:
                jsd = jsd_pair(per_source[sa], per_source[sb])
                rows.append({
                    "feature": col,
                    "group": f["group"],
                    "source_a": sa,
                    "source_b": sb,
                    "jsd": round(jsd, 6),
                })
        if len(rows) % 200 == 0:
            print(f"  ... {col} done ({len(rows)} rows)")
    long_df = pd.DataFrame(rows)
    long_df.to_csv(OUT_DIR / "source_drift_jsd.csv", index=False)
    print(f"[write] source_drift_jsd.csv ({len(long_df)} rows)")

    # Aggregate by group
    agg = (long_df.groupby(["group", "source_a", "source_b"], as_index=False)
           .agg(mean_jsd=("jsd", "mean"),
                median_jsd=("jsd", "median"),
                max_jsd=("jsd", "max"),
                n_features=("jsd", "count")))
    agg["mean_jsd"] = agg["mean_jsd"].round(4)
    agg["median_jsd"] = agg["median_jsd"].round(4)
    agg["max_jsd"] = agg["max_jsd"].round(4)
    agg.to_csv(OUT_DIR / "source_drift_by_group.csv", index=False)
    print(f"[write] source_drift_by_group.csv")

    # Pivot per group: symmetric source x source matrix
    for grp, sub in agg.groupby("group"):
        sym = sub.copy()
        rev = sym.rename(columns={"source_a": "source_b", "source_b": "source_a"})
        all_pairs = pd.concat([sym, rev], ignore_index=True)
        mat = all_pairs.pivot_table(index="source_a", columns="source_b",
                                    values="mean_jsd", aggfunc="mean")
        for s in sources:
            if s in mat.index and s in mat.columns:
                mat.loc[s, s] = 0.0
        mat = mat.round(4)
        mat.to_csv(OUT_DIR / f"source_drift_matrix_{grp}.csv")
    print(f"[write] source_drift_matrix_<group>.csv x {long_df['group'].nunique()}")

    # Top drifting features per source pair (overall)
    top = (long_df.sort_values("jsd", ascending=False)
           .groupby(["source_a", "source_b"], as_index=False)
           .head(3))
    top.to_csv(OUT_DIR / "top_drifting_features.csv", index=False)
    print(f"[write] top_drifting_features.csv")

    print(f"\n[total] {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
