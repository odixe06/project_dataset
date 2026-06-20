# MineShark Reproduction — Cryptomining Traffic Dataset and Cross-Source Benchmark

A reproduction study of *MineShark — Cryptomining traffic detection at scale*
([reference paper](2025-402-paper.md), included in this repository as Markdown).
The project rebuilds the dataset pipeline at a smaller, locally-runnable scale
and contributes two original analyses that the original paper did not perform
on public multi-source data.

## What this repository contains

```
.
├── 2025-402-paper.md              # The reference paper (Markdown, local only)
├── CLAUDE.md                       # Project methodology (local only)
├── samplepaper.tex                 # LaTeX skeleton for the final write-up
├── README.md                       # This file
├── requirements.txt                # Pipeline dependencies
├── configs/                        # build / schema / sources / privacy YAML
├── scripts/                        # numbered pipeline + benchmark scripts
├── data/final/                     # processed dataset and evaluation artifacts
└── tests/                          # pytest entry point
```

Raw and intermediate data are not tracked; everything under `data/final/` is
regenerable from `data/raw/` via the numbered scripts.

## Contributions

This project goes beyond pure reproduction in two ways. Both are reproducible
end-to-end from the processed dataset.

### C1 — Cross-source generalization benchmark (primary)

The first systematic evaluation of cryptomining traffic detection across
multiple public datasets. We run leave-one-source-out folds on the
HistGradientBoosting model, ablate four feature groups
(`flow_only`, `flow_timing`, `flow_tls`, `flow_timing_tls`), and quantify the
generalization gap between in-distribution and cross-source performance —
something MineShark and prior work did not measure on public multi-source data.

Headline finding (full numbers in
[`BENCHMARK_REPORT.md`](data/final/evaluation/BENCHMARK_REPORT.md)):
adding aggregate timing features lifts mean cross-source mining-recall from
0.52 (flow-only) to 0.98, and reduces benign-source FPR from 0.80 to 0.019.
TLS features, on the other hand, do not improve cross-source recall once
timing is present and increase FPR on the iot23 benign holdout. This
empirically supports MineShark's qualitative claim that timing patterns are
content-agnostic.

### C2 — Source-distribution drift report (auxiliary)

We compute pairwise Jensen–Shannon divergence between sources for every
numeric model-input feature, aggregate by feature group, and correlate the
resulting drift with the cross-source generalization gap from C1. The drift
report explains *why* certain feature groups generalize and others do not:
on the three mining-source folds, drift in flow features tracks the gap
perfectly monotonically (ρ = 1.0), while drift in timing features does not
predict the gap at all (ρ = −0.5), consistent with timing being robust under
covariate shift.

We are explicit that with only three mining sources these correlations are
*evidence-of-direction*, not statistical conclusions; see §6 of the benchmark
report.

## Quick start

### 1. Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install scikit-learn scipy   # benchmark dependencies, not in core requirements
```

### 2. Get the processed dataset

The repository tracks `samples.parquet` (the primary dataset) and a few
summary artifacts under `data/final/`. To regenerate everything from raw,
follow the pipeline section below. To run only the benchmark, the tracked
files are sufficient.

If the bulk evaluation join tables are needed (some are git-ignored due to
size), regenerate them:

```bash
python data/final/evaluation/build_evaluation_artifacts.py
```

### 3. Run the contributions

```bash
# C1 — cross-source benchmark (~80 s on an 8-core laptop CPU)
python scripts/15_cross_source_benchmark.py

# C2 — source-distribution drift (~2 s)
python scripts/16_source_drift.py

# C2 synthesis — correlate drift with generalization gap (~1 s)
python scripts/17_drift_vs_gen.py

# Verification — counter-factuals cited in the report §6.2 and §6.3
python scripts/18_verify_counter_factuals.py
```

All scripts use `random_state=42`. Reproducibility is bit-exact (verified;
see [`VERIFICATION_LOG.md`](data/final/evaluation/VERIFICATION_LOG.md)).

Outputs land under
[`data/final/evaluation/05_cross_source_benchmark/`](data/final/evaluation/05_cross_source_benchmark/)
and
[`data/final/evaluation/06_source_drift/`](data/final/evaluation/06_source_drift/).

## Rebuilding the dataset from raw sources

The processing pipeline is a sequence of numbered scripts under
`scripts/`. They consume the public sources listed in
`configs/sources.yaml` and produce the final artifacts under
`data/final/`.

```bash
# Optional: a private salt for HMAC-SHA256 hashing of IP/SNI/cert values
export DATASET_PRIVACY_SALT='replace-with-a-private-long-random-string'

bash scripts/run_pipeline.sh
```

Stage breakdown:

| Stage | Script(s) | What it does |
|---|---|---|
| Download | `00_download_sources.sh` | Fetch public datasets (CESNET-MINER22, Hikari2021, IoT-23, MineShark artifact, CJ-Sniffer, HuggingFace auto-capture). |
| Unpack | `01_unpack_sources.sh` | Extract archives, prepare directory layout. |
| Manifest | `02_build_manifest.py` | Record sha256, size, license per file. |
| Zeek | `03_run_zeek.sh` | Parse PCAPs into conn/ssl/x509 logs. |
| Sequences | `04_extract_packet_sequences.py` | Per-flow packet length / direction / inter-arrival sequences (via dpkt). |
| Parsers | `05`–`09` | Source-specific feature extraction. |
| Normalize | `10_normalize_schema.py` | Coerce all sources to `configs/schema.yaml`. |
| Merge | `11_merge_and_dedupe.py` | Cross-source dedup by flow key. |
| Validate | `12_validate_and_stats.py` | Quality gates and `stats_report.md`. |
| Export | `13_export_final.py` | Write `samples.parquet`, `samples.csv.gz`, schema, manifest. |
| Benchmark | `15`–`17` | Cross-source benchmark + drift analysis. |
| Verify | `18_verify_counter_factuals.py` | Reproducible counter-factuals for the threats-to-validity section. |

Privacy invariants: the final dataset never contains raw IPs, raw SNI values,
or raw payload. All identifying fields are HMAC-SHA256 truncated to 63 bits.

## Dataset summary

| Property | Value |
|---|---|
| Total flows | 415,670 |
| Mining (`label=1`) | 13,467 |
| Non-mining (`label=0`) | 402,203 |
| Sources | `auto_capture_hf`, `cesnet_miner22`, `cj_sniffer`, `mineshark_artifact`, `hikari2021`, `iot23_mcfp` |
| Schema | 97 columns, ~70 model-input numeric features |
| Class imbalance | ~30 : 1 (non-mining : mining) |
| TLS coverage in mining class | 0.6 % (caveat — see report §6.2) |

Full per-column documentation is in
[`data/final/data_dictionary.md`](data/final/data_dictionary.md).
Source-by-source narrative is in
[`data/final/description.md`](data/final/description.md).

## Reading the results

The single most informative file is
[`BENCHMARK_REPORT.md`](data/final/evaluation/BENCHMARK_REPORT.md).
It contains the headline metrics, the feature-group ablation, the drift
analysis, the drift × generalization synthesis, and §6 threats-to-validity
that we recommend reading first.

[`VERIFICATION_LOG.md`](data/final/evaluation/VERIFICATION_LOG.md)
documents five independent checks (clean-state reproducibility, filter
assertion, two counter-factual experiments, and an independent
re-derivation). Two of the five checks refined our initial framing of the
threats-to-validity — the report was updated to reflect what we actually
measured.

## Threats to validity (short version)

The report enumerates these in §6; they are summarised here for visibility.

1. The `mineshark_artifact` parser produces placeholder rows because the
   raw feature layout is artifact-dependent. We exclude these rows from the
   benchmark and document the gap. Conclusions about obfuscation defeat
   would require re-parsing that source.
2. TLS findings are partially confounded with padding semantics (`has_tls=0`
   rows have zero-padded TLS columns). We quantify this in
   `iot23_tls_padding_ablation.csv`.
3. The in-distribution baseline (recall ≈ 0.999) is an upper bound inflated
   by overall flow-feature separability in this dataset, not real-world
   accuracy. We quantify this in `in_source_port_ablation.csv`.
4. Only n = 3 mining-source folds are usable for correlation analysis;
   reported ρ-values are evidence-of-direction.
5. The baseline uses aggregated timing statistics, not the sequence-based
   CNN that MineShark actually deploys.

## Repository conventions

- Scripts in `scripts/` are numbered in execution order. New steps
  use the next free number; existing scripts are not renumbered.
- All randomness is seeded with `random_state=42`.
- Headline metrics in `BENCHMARK_REPORT.md` correspond exactly to CSV files
  under `data/final/evaluation/`. Numbers in the report do not exist
  outside CSVs that can be regenerated.
- Working principles (fidelity to paper, privacy invariants, no random split
  for final evaluation, etc.) are in [`CLAUDE.md`](CLAUDE.md).

## License and sources

The processed dataset combines public sources with their respective licenses;
see `data/final/manifest.json` for per-file provenance. The reproduction code
in this repository is provided for academic use; choose a license before
publishing.

## Citation

If you build on this benchmark, please cite the original MineShark paper.
A BibTeX entry will be added once the accompanying write-up is finalised.
