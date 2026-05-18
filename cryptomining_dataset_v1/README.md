# Cryptomining / Non-Mining Dataset V1

This project implements a local batch pipeline for building a binary flow-level dataset from the sources described in `../plan.md`.

## Quick Start

Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

Set a private salt before running parsers that hash IP/SNI/certificate fields:

```bash
export DATASET_PRIVACY_SALT='replace-with-a-private-long-random-string'
```

Run the full pipeline:

```bash
bash scripts/run_pipeline.sh
```

For a dry-run download check:

```bash
DRY_RUN=1 bash scripts/00_download_sources.sh
```

Large public sources can be blocked by mirrors or require browser verification. If a download fails, place the file at the configured `local_file` path and rerun from `scripts/01_unpack_sources.sh`.

## Final Outputs

The final artifacts are written under `data/final/`:

- `samples.parquet`: primary dataset, including sequence arrays.
- `samples.csv.gz`: scalar-only export.
- `schema.json`, `feature_vocab.json`, `manifest.json`, `provenance.parquet`.
- `stats.json`, `stats_report.md`, `data_dictionary.md`.

## Privacy Rules

The final dataset must not contain raw IPs, raw SNI values, or raw payload. Hashes use HMAC-SHA256 truncated to 63 bits so values fit signed `int64` without leaking direct unsalted hashes.

