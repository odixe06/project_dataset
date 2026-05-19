#!/usr/bin/env python3
"""Build evaluation split artifacts for the final cryptomining dataset.

The script intentionally writes split/index files instead of copying the full
dataset into every fold. Consumers can join the generated files back to
samples.csv.gz or samples.parquet by sample_id.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "samples.csv.gz"
SCHEMA_JSON = ROOT / "schema.json"
OUT = ROOT / "evaluation"

DIR_SOURCE = OUT / "01_source_file_group_holdout"
DIR_SLICES = OUT / "02_performance_slices"
DIR_DEDUP = OUT / "03_deduplicated_feature_groups"
DIR_ABLATION = OUT / "04_feature_group_ablations"

SPLIT_RATIOS = {"train": 0.70, "validation": 0.15, "test": 0.15}
FLOAT_PRECISION = 6


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def split_bucket(key: str) -> str:
    value = int(stable_hash(key)[:12], 16) / float(16**12)
    if value < SPLIT_RATIOS["train"]:
        return "train"
    if value < SPLIT_RATIOS["train"] + SPLIT_RATIOS["validation"]:
        return "validation"
    return "test"


def is_one(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip() in {"1", "1.0", "true", "True", "TRUE"}


def open_gzip_csv(path: Path, mode: str):
    return gzip.open(path, mode, newline="", encoding="utf-8")


def write_csv(path: Path, rows, fieldnames: list[str], gzip_output: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = open_gzip_csv if gzip_output else open
    with opener(path, "wt") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def load_schema() -> tuple[dict[str, dict], list[str]]:
    schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
    columns = {col["name"]: col for col in schema["columns"]}
    with open_gzip_csv(INPUT_CSV, "rt") as f:
        header = next(csv.reader(f))
    return columns, header


def model_columns_by_group(columns: dict[str, dict], header: list[str]) -> dict[str, list[str]]:
    present = set(header)
    groups: dict[str, list[str]] = defaultdict(list)
    for name, spec in columns.items():
        if name not in present:
            continue
        if spec.get("can_use_for_model_input") is True:
            groups[spec.get("group", "")].append(name)
    return {k: v for k, v in sorted(groups.items())}


def load_metadata() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with open_gzip_csv(INPUT_CSV, "rt") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    "sample_id": row["sample_id"],
                    "label": row["label"],
                    "source": row["source"],
                    "source_file": row["source_file"],
                    "has_tls": "1" if is_one(row.get("has_tls")) else "0",
                    "packet_seq_available": "1"
                    if is_one(row.get("packet_seq_available"))
                    else "0",
                    "timing_full_available": "1"
                    if is_one(row.get("timing_full_available"))
                    else "0",
                }
            )
    return rows


def label_counts(rows: list[dict[str, str]]) -> Counter:
    counts: Counter = Counter()
    for row in rows:
        counts[row["label"]] += 1
    return counts


def source_role(pos: int, neg: int) -> str:
    if pos and not neg:
        return "mining_source"
    if neg and not pos:
        return "non_mining_source"
    return "mixed_source"


def build_source_holdout(rows: list[dict[str, str]]) -> None:
    DIR_SOURCE.mkdir(parents=True, exist_ok=True)
    sources = sorted({row["source"] for row in rows})

    source_counts: dict[str, Counter] = {source: Counter() for source in sources}
    for row in rows:
        source_counts[row["source"]][row["label"]] += 1

    summary_rows = []
    total_counts = label_counts(rows)
    for source in sources:
        test_counts = source_counts[source]
        train_pos = total_counts["1"] - test_counts["1"]
        train_neg = total_counts["0"] - test_counts["0"]
        test_pos = test_counts["1"]
        test_neg = test_counts["0"]
        note = ""
        if test_pos == 0:
            note = "heldout test has only non-mining labels"
        elif test_neg == 0:
            note = "heldout test has only mining labels"
        summary_rows.append(
            {
                "fold_id": f"holdout_source__{source}",
                "heldout_source": source,
                "heldout_role": source_role(test_pos, test_neg),
                "train_count": train_pos + train_neg,
                "train_label_0": train_neg,
                "train_label_1": train_pos,
                "test_count": test_pos + test_neg,
                "test_label_0": test_neg,
                "test_label_1": test_pos,
                "note": note,
            }
        )

    write_csv(
        DIR_SOURCE / "source_holdout_summary.csv",
        summary_rows,
        [
            "fold_id",
            "heldout_source",
            "heldout_role",
            "train_count",
            "train_label_0",
            "train_label_1",
            "test_count",
            "test_label_0",
            "test_label_1",
            "note",
        ],
    )

    with open_gzip_csv(DIR_SOURCE / "source_holdout_membership.csv.gz", "wt") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "fold_id",
                "heldout_source",
                "sample_id",
                "split",
                "label",
                "source",
                "source_file_group_id",
            ],
        )
        writer.writeheader()
        for source in sources:
            fold_id = f"holdout_source__{source}"
            for row in rows:
                group_id = stable_hash(f"{row['source']}\0{row['source_file']}")[:16]
                writer.writerow(
                    {
                        "fold_id": fold_id,
                        "heldout_source": source,
                        "sample_id": row["sample_id"],
                        "split": "test" if row["source"] == source else "train",
                        "label": row["label"],
                        "source": row["source"],
                        "source_file_group_id": group_id,
                    }
                )


def choose_group_split(
    split_sizes: dict[str, int], group_size: int, total_size: int, group_key: str
) -> str:
    choices = []
    for split, ratio in SPLIT_RATIOS.items():
        target = max(total_size * ratio, 1)
        projected_ratio = (split_sizes[split] + group_size) / target
        current_ratio = split_sizes[split] / target
        choices.append((projected_ratio, current_ratio, stable_hash(group_key + split), split))
    choices.sort()
    return choices[0][-1]


def build_source_file_group_split(rows: list[dict[str, str]]) -> None:
    groups: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for row in rows:
        groups[(row["source"], row["source_file"])]["count"] += 1
        groups[(row["source"], row["source_file"])][f"label_{row['label']}"] += 1

    split_sizes = {split: 0 for split in SPLIT_RATIOS}
    group_to_split: dict[tuple[str, str], str] = {}
    ordered_groups = sorted(
        groups.items(),
        key=lambda item: (-item[1]["count"], stable_hash(f"{item[0][0]}\0{item[0][1]}")),
    )
    for group_key, counts in ordered_groups:
        encoded_key = f"{group_key[0]}\0{group_key[1]}"
        split = choose_group_split(split_sizes, counts["count"], len(rows), encoded_key)
        group_to_split[group_key] = split
        split_sizes[split] += counts["count"]

    group_summary_rows = []
    for (source, source_file), counts in sorted(groups.items()):
        group_id = stable_hash(f"{source}\0{source_file}")[:16]
        group_summary_rows.append(
            {
                "source_file_group_id": group_id,
                "split": group_to_split[(source, source_file)],
                "source": source,
                "source_file": source_file,
                "count": counts["count"],
                "label_0": counts["label_0"],
                "label_1": counts["label_1"],
            }
        )

    write_csv(
        DIR_SOURCE / "source_file_group_summary.csv",
        group_summary_rows,
        [
            "source_file_group_id",
            "split",
            "source",
            "source_file",
            "count",
            "label_0",
            "label_1",
        ],
    )

    with open_gzip_csv(DIR_SOURCE / "source_file_group_split.csv.gz", "wt") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "sample_id",
                "split",
                "label",
                "source",
                "source_file_group_id",
            ],
        )
        writer.writeheader()
        for row in rows:
            group_id = stable_hash(f"{row['source']}\0{row['source_file']}")[:16]
            writer.writerow(
                {
                    "sample_id": row["sample_id"],
                    "split": group_to_split[(row["source"], row["source_file"])],
                    "label": row["label"],
                    "source": row["source"],
                    "source_file_group_id": group_id,
                }
            )


def build_performance_slices(rows: list[dict[str, str]]) -> None:
    DIR_SLICES.mkdir(parents=True, exist_ok=True)
    slice_counts: Counter = Counter()
    membership_path = DIR_SLICES / "reporting_slices.csv.gz"
    with open_gzip_csv(membership_path, "wt") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "sample_id",
                "label",
                "source",
                "tls_slice",
                "sequence_slice",
                "source_tls_sequence_slice",
            ],
        )
        writer.writeheader()
        for row in rows:
            tls_slice = "tls" if row["has_tls"] == "1" else "non_tls"
            sequence_slice = (
                "sequence_available"
                if row["packet_seq_available"] == "1"
                else "sequence_unavailable"
            )
            combined = f"{row['source']}__{tls_slice}__{sequence_slice}"
            writer.writerow(
                {
                    "sample_id": row["sample_id"],
                    "label": row["label"],
                    "source": row["source"],
                    "tls_slice": tls_slice,
                    "sequence_slice": sequence_slice,
                    "source_tls_sequence_slice": combined,
                }
            )
            for slice_type, slice_value in [
                ("source", row["source"]),
                ("tls", tls_slice),
                ("sequence", sequence_slice),
                ("source_tls_sequence", combined),
            ]:
                slice_counts[(slice_type, slice_value, row["label"])] += 1

    aggregate: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for (slice_type, slice_value, label), count in slice_counts.items():
        aggregate[(slice_type, slice_value)][f"label_{label}"] += count

    rows_out = []
    for (slice_type, slice_value), counts in sorted(aggregate.items()):
        rows_out.append(
            {
                "slice_type": slice_type,
                "slice_value": slice_value,
                "count": counts["label_0"] + counts["label_1"],
                "label_0": counts["label_0"],
                "label_1": counts["label_1"],
            }
        )
    write_csv(
        DIR_SLICES / "slice_counts.csv",
        rows_out,
        ["slice_type", "slice_value", "count", "label_0", "label_1"],
    )
    write_csv(
        DIR_SLICES / "metrics_template.csv",
        [],
        [
            "model_name",
            "slice_type",
            "slice_value",
            "count",
            "tp",
            "fp",
            "tn",
            "fn",
            "accuracy",
            "precision_label_1",
            "recall_label_1",
            "f1_label_1",
            "roc_auc",
            "pr_auc",
        ],
    )


def canonical_value(value: str, spec: dict) -> str:
    dtype = spec.get("dtype", "")
    if value == "":
        value = spec.get("padding", "")
    if str(dtype).startswith("float"):
        try:
            number = float(value)
            if not math.isfinite(number):
                number = float(spec.get("padding", 0.0))
        except (TypeError, ValueError):
            number = float(spec.get("padding", 0.0))
        return f"{number:.{FLOAT_PRECISION}g}"
    if str(dtype).startswith("int"):
        try:
            return str(int(float(value)))
        except (TypeError, ValueError):
            return str(int(spec.get("padding", 0) or 0))
    return str(value)


def build_dedup(columns: dict[str, dict], header: list[str]) -> None:
    DIR_DEDUP.mkdir(parents=True, exist_ok=True)
    present = set(header)
    feature_cols = [
        name
        for name, spec in columns.items()
        if spec.get("can_use_for_model_input") is True and name in present
    ]

    groups: dict[str, Counter] = defaultdict(Counter)
    representatives: dict[str, str] = {}
    with open_gzip_csv(INPUT_CSV, "rt") as f:
        reader = csv.DictReader(f)
        for row in reader:
            parts = [
                f"{name}={canonical_value(row.get(name, ''), columns[name])}"
                for name in feature_cols
            ]
            fingerprint = stable_hash("\x1f".join(parts))
            groups[fingerprint]["count"] += 1
            groups[fingerprint][f"label_{row['label']}"] += 1
            representatives.setdefault(fingerprint, row["sample_id"])

    group_ids = {
        fingerprint: f"dedup_{idx:07d}"
        for idx, fingerprint in enumerate(sorted(groups), start=1)
    }
    group_splits = {fingerprint: split_bucket(fingerprint) for fingerprint in groups}

    summary_rows = []
    mixed_label_groups = 0
    max_group_size = 0
    for fingerprint, counts in sorted(groups.items()):
        mixed = counts["label_0"] > 0 and counts["label_1"] > 0
        mixed_label_groups += int(mixed)
        max_group_size = max(max_group_size, counts["count"])
        summary_rows.append(
            {
                "dedup_group_id": group_ids[fingerprint],
                "dedup_fingerprint": fingerprint,
                "split": group_splits[fingerprint],
                "count": counts["count"],
                "label_0": counts["label_0"],
                "label_1": counts["label_1"],
                "mixed_label_group": int(mixed),
                "representative_sample_id": representatives[fingerprint],
            }
        )
    write_csv(
        DIR_DEDUP / "dedup_group_summary.csv.gz",
        summary_rows,
        [
            "dedup_group_id",
            "dedup_fingerprint",
            "split",
            "count",
            "label_0",
            "label_1",
            "mixed_label_group",
            "representative_sample_id",
        ],
        gzip_output=True,
    )

    with open_gzip_csv(INPUT_CSV, "rt") as src, open_gzip_csv(
        DIR_DEDUP / "dedup_group_split.csv.gz", "wt"
    ) as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(
            dst,
            fieldnames=[
                "sample_id",
                "split",
                "label",
                "dedup_group_id",
                "dedup_group_size",
                "is_group_representative",
            ],
        )
        writer.writeheader()
        for row in reader:
            parts = [
                f"{name}={canonical_value(row.get(name, ''), columns[name])}"
                for name in feature_cols
            ]
            fingerprint = stable_hash("\x1f".join(parts))
            writer.writerow(
                {
                    "sample_id": row["sample_id"],
                    "split": group_splits[fingerprint],
                    "label": row["label"],
                    "dedup_group_id": group_ids[fingerprint],
                    "dedup_group_size": groups[fingerprint]["count"],
                    "is_group_representative": int(
                        representatives[fingerprint] == row["sample_id"]
                    ),
                }
            )

    summary = {
        "input": str(INPUT_CSV.relative_to(ROOT)),
        "feature_columns_used": feature_cols,
        "near_identical_rule": (
            f"same scalar model-input vector after padding missing values and "
            f"rounding floats to {FLOAT_PRECISION} significant digits"
        ),
        "total_samples": sum(counts["count"] for counts in groups.values()),
        "unique_feature_groups": len(groups),
        "samples_in_duplicate_or_near_duplicate_groups": sum(
            counts["count"] for counts in groups.values() if counts["count"] > 1
        ),
        "max_group_size": max_group_size,
        "mixed_label_groups": mixed_label_groups,
        "split_ratios": SPLIT_RATIOS,
    }
    (DIR_DEDUP / "dedup_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def build_ablations(columns: dict[str, dict], header: list[str]) -> None:
    DIR_ABLATION.mkdir(parents=True, exist_ok=True)
    groups = model_columns_by_group(columns, header)
    tls_like = groups.get("tls", []) + groups.get("certificate", [])
    feature_sets = {
        "flow_only": groups.get("flow", []),
        "flow_timing": groups.get("flow", []) + groups.get("timing", []),
        "flow_tls": groups.get("flow", []) + tls_like,
        "flow_timing_tls": groups.get("flow", [])
        + groups.get("timing", [])
        + tls_like,
    }
    feature_sets = {name: cols for name, cols in feature_sets.items() if cols}
    for name, feature_cols in feature_sets.items():
        out_path = DIR_ABLATION / f"{name}.csv.gz"
        fieldnames = ["sample_id", "label"] + feature_cols
        with open_gzip_csv(INPUT_CSV, "rt") as src, open_gzip_csv(out_path, "wt") as dst:
            reader = csv.DictReader(src)
            writer = csv.DictWriter(dst, fieldnames=fieldnames)
            writer.writeheader()
            for row in reader:
                writer.writerow({field: row.get(field, "") for field in fieldnames})

    payload = {
        "input": str(INPUT_CSV.relative_to(ROOT)),
        "note": "TLS ablations include schema groups tls and certificate.",
        "feature_sets": feature_sets,
    }
    (DIR_ABLATION / "feature_columns.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def write_readmes() -> None:
    (OUT / "README.md").write_text(
        """# Evaluation Artifacts

Thư mục này chứa các artifact phục vụ chia dữ liệu, chống leakage, chạy
feature ablation và báo cáo kết quả đánh giá cho dataset
`cryptomining_dataset_v1/data/final`.

Các file được sinh từ `samples.csv.gz`. Hầu hết artifact chỉ chứa `sample_id`,
metadata split hoặc subset feature, không copy toàn bộ `samples.parquet`. Khi
cần train/evaluate trên đầy đủ dữ liệu, join các file này với
`samples.csv.gz` hoặc `samples.parquet` bằng khóa `sample_id`.

## Cách dùng nhanh

1. Dùng `01_source_file_group_holdout/source_holdout_membership.csv.gz` nếu
   muốn đánh giá khả năng generalize sang từng nguồn dữ liệu chưa thấy.
2. Dùng `01_source_file_group_holdout/source_file_group_split.csv.gz` nếu muốn
   có một split train/validation/test tránh trộn cùng `source_file` giữa các
   split.
3. Dùng `03_deduplicated_feature_groups/dedup_group_split.csv.gz` cho final
   evaluation chống leakage từ các vector feature giống hoặc gần giống nhau.
4. Dùng các file trong `04_feature_group_ablations/` để train model với từng
   nhóm feature: flow only, flow + timing, flow + TLS, flow + timing + TLS.
5. Sau khi có prediction, dùng `02_performance_slices/reporting_slices.csv.gz`
   để report metric theo source, TLS/non-TLS và sequence availability.

## File gốc và script

| File | Mục đích |
|---|---|
| `README.md` | Tài liệu tổng quan về các artifact evaluation. |
| `build_evaluation_artifacts.py` | Script sinh lại toàn bộ nội dung trong thư mục `evaluation` từ `samples.csv.gz` và `schema.json`. Dùng khi dataset final thay đổi hoặc muốn regenerate artifact. |

## `01_source_file_group_holdout/`

Nhóm file này phục vụ đánh giá theo nguồn dữ liệu và split theo nhóm file gốc.
Mục tiêu là hạn chế source leakage, vì random split đơn giản có thể làm model
học đặc trưng riêng của capture/source thay vì hành vi cryptomining.

| File | Sử dụng làm gì |
|---|---|
| `README.md` | Ghi chú ngắn cho nhóm artifact source/file-group holdout. |
| `source_holdout_membership.csv.gz` | File membership cho leave-one-source-out evaluation. Mỗi `fold_id` tương ứng một `heldout_source`; các dòng thuộc source đó có `split=test`, các source còn lại có `split=train`. Dùng file này để train trên tất cả source trừ một source, rồi test riêng trên source bị holdout. |
| `source_holdout_summary.csv` | Bảng tóm tắt từng fold source-holdout: source nào bị holdout, số mẫu train/test, số label 0/1 và ghi chú nếu test chỉ có một class. Dùng để kiểm tra nhanh fold có phù hợp với metric đang tính hay không. |
| `source_file_group_split.csv.gz` | Một split train/validation/test duy nhất, giữ toàn bộ mẫu có cùng `(source, source_file)` trong cùng một split. Dùng khi cần split ổn định theo file gốc để giảm leakage giữa train và test. |
| `source_file_group_summary.csv` | Thống kê từng group `(source, source_file)`: group id, split, source, source file, count và phân bố label. Dùng để audit split và kiểm tra source/file nào nằm ở train, validation hoặc test. |

Lưu ý: một số source chỉ có một `source_file`, nên không thể chia nội bộ source
đó sang nhiều split mà vẫn giữ ràng buộc group theo file.

## `02_performance_slices/`

Nhóm file này không dùng để chia train/test trực tiếp. Nó dùng để gắn thêm nhãn
slice khi báo cáo kết quả, sau khi model đã tạo prediction.

| File | Sử dụng làm gì |
|---|---|
| `README.md` | Ghi chú ngắn cho nhóm artifact reporting slice. |
| `reporting_slices.csv.gz` | Mapping từ `sample_id` sang các slice báo cáo: `source`, `tls_slice` (`tls` hoặc `non_tls`), `sequence_slice` (`sequence_available` hoặc `sequence_unavailable`) và slice kết hợp `source_tls_sequence_slice`. Join prediction với file này để tính metric theo từng lát cắt. |
| `slice_counts.csv` | Số mẫu và phân bố label 0/1 cho từng slice. Dùng để biết slice nào đủ lớn, slice nào chỉ có một class, và để diễn giải metric cẩn thận. |
| `metrics_template.csv` | Template trống để điền kết quả model theo từng slice, gồm các cột như TP, FP, TN, FN, accuracy, precision, recall, F1, ROC-AUC, PR-AUC. Dùng như format thống nhất cho báo cáo. |

## `03_deduplicated_feature_groups/`

Nhóm file này phục vụ deduplicate hoặc group near-identical feature vectors
trước final evaluation. Các dòng được group theo scalar model-input features
sau khi áp dụng padding từ schema và làm tròn float tới 6 chữ số có nghĩa.

| File | Sử dụng làm gì |
|---|---|
| `README.md` | Ghi chú ngắn cho nhóm artifact dedup/near-duplicate. |
| `dedup_group_split.csv.gz` | Mapping từng `sample_id` sang `dedup_group_id`, kích thước group, cờ representative và split train/validation/test. Dùng file này cho final split chống leakage: mọi sample trong cùng một near-identical group luôn nằm cùng một split. |
| `dedup_group_summary.csv.gz` | Thống kê ở cấp group: fingerprint, split, count, label_0, label_1, group có mixed label hay không, và `representative_sample_id`. Dùng để audit duplicate group hoặc chỉ giữ representative khi muốn train/evaluate trên bản deduplicated. |
| `dedup_summary.json` | Metadata của quá trình dedup: danh sách feature dùng để tạo fingerprint, quy tắc near-identical, tổng số mẫu, số group unique, số mẫu thuộc group duplicate, max group size và split ratio. Dùng để mô tả phương pháp trong báo cáo/thí nghiệm. |

Nếu muốn tạo bản deduplicated thật sự, có thể lấy các dòng
`is_group_representative=1` từ `dedup_group_split.csv.gz`, rồi join lại với
`samples.csv.gz` hoặc `samples.parquet`.

## `04_feature_group_ablations/`

Nhóm file này chứa các CSV scalar đã được lọc sẵn theo nhóm feature để chạy
ablation. Mỗi file có `sample_id`, `label` và các feature tương ứng. Các file
này không chứa sequence arrays vì sequence chỉ có trong `samples.parquet`.

| File | Sử dụng làm gì |
|---|---|
| `README.md` | Ghi chú ngắn cho nhóm artifact feature ablation. |
| `feature_columns.json` | Danh sách cột chính xác cho từng ablation set. Dùng để kiểm tra model đang nhận feature nào và để reproduce thí nghiệm. |
| `flow_only.csv.gz` | Dataset scalar chỉ gồm flow features như duration, proto, ports, bytes, packets, byte rate, packet rate và ratio forward. Dùng làm baseline tối giản. |
| `flow_timing.csv.gz` | Flow features cộng timing/statistical packet features như packet length stats, IAT stats, burst và periodicity. Dùng để đo đóng góp của timing patterns. |
| `flow_tls.csv.gz` | Flow features cộng TLS và certificate metadata. TLS variants bao gồm cả schema group `tls` và `certificate`. Dùng để đo đóng góp của TLS/certificate metadata khi không dùng timing. |
| `flow_timing_tls.csv.gz` | Flow + timing + TLS/certificate. Đây là bộ scalar đầy đủ nhất trong 4 ablation và dùng để so sánh với các subset nhỏ hơn. |

## Gợi ý join với split

Các ablation CSV không tự chứa cột `split`. Khi train/evaluate, hãy join một
file ablation với một file split bằng `sample_id`, ví dụ:

```python
import pandas as pd

features = pd.read_csv("04_feature_group_ablations/flow_timing_tls.csv.gz")
split = pd.read_csv("03_deduplicated_feature_groups/dedup_group_split.csv.gz")
df = features.merge(split[["sample_id", "split"]], on="sample_id", how="inner")

train = df[df["split"] == "train"]
validation = df[df["split"] == "validation"]
test = df[df["split"] == "test"]
```

Sau khi model sinh prediction theo `sample_id`, join prediction với
`02_performance_slices/reporting_slices.csv.gz` để tính metric theo từng slice.
""",
        encoding="utf-8",
    )
    (DIR_SOURCE / "README.md").write_text(
        """# Source And File-Group Holdout

`source_holdout_membership.csv.gz` contains one fold per source. For a given
`fold_id`, rows from `heldout_source` are `test`; all other rows are `train`.
This gives explicit holdout tests for every mining source and every non-mining
source.

`source_file_group_split.csv.gz` is a single train/validation/test split where
all rows from the same `(source, source_file)` group stay in the same split.
Some sources have only one source file, so those sources cannot be internally
split without violating the file-group constraint.
""",
        encoding="utf-8",
    )
    (DIR_SLICES / "README.md").write_text(
        """# Performance Reporting Slices

Use `reporting_slices.csv.gz` to report metrics per source, TLS/non-TLS, and
sequence-available/unavailable. `slice_counts.csv` provides the label counts
for each slice; `metrics_template.csv` is a blank table for model results.
""",
        encoding="utf-8",
    )
    (DIR_DEDUP / "README.md").write_text(
        """# Deduplicated Near-Identical Feature Groups

Rows are grouped by scalar model-input feature vectors after applying schema
padding and rounding float values to 6 significant digits. The generated split
keeps each near-identical group entirely in one split so final evaluation does
not leak duplicate-like feature vectors across train and test.
""",
        encoding="utf-8",
    )
    (DIR_ABLATION / "README.md").write_text(
        """# Feature-Group Ablations

Each CSV contains `sample_id`, `label`, and only the selected scalar feature
groups. TLS variants include both the `tls` and `certificate` schema groups.
Sequence array columns are only available in `samples.parquet` and are not
included in these scalar ablation CSVs.
""",
        encoding="utf-8",
    )


def main() -> None:
    columns, header = load_schema()
    rows = load_metadata()
    OUT.mkdir(parents=True, exist_ok=True)
    build_source_holdout(rows)
    build_source_file_group_split(rows)
    build_performance_slices(rows)
    build_dedup(columns, header)
    build_ablations(columns, header)
    write_readmes()


if __name__ == "__main__":
    main()
