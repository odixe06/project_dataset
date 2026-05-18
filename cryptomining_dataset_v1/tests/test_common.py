from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "lib"))

from dataset_common import hmac_hash64, load_privacy_config, normalize_row, sample_id, sequence_stats


def test_hmac_hash64_is_stable_and_signed_int64_safe(monkeypatch):
    monkeypatch.setenv("DATASET_PRIVACY_SALT", "unit-test-salt")
    salt = load_privacy_config()["salt"]
    a = hmac_hash64("example.com", salt)
    b = hmac_hash64("example.com", salt)
    assert a == b
    assert 0 < a < 2**63
    assert hmac_hash64("", salt) == 0


def test_normalize_row_pads_tls_and_sequence(monkeypatch):
    monkeypatch.setenv("DATASET_PRIVACY_SALT", "unit-test-salt")
    row = normalize_row({"source": "unit", "label": 1, "src_port": 1, "dst_port": 2})
    assert row["has_tls"] == 0
    assert row["tls_source"] == "none"
    assert row["seq_pkt_len"] == []
    assert row["sample_id"]


def test_sample_id_stable():
    row = {
        "schema_version": "mining_dataset_v1",
        "source": "unit",
        "source_file": "x.pcap",
        "source_record_id": "abc",
        "proto": "tcp",
        "src_ip_hash64": 1,
        "dst_ip_hash64": 2,
        "src_port": 10,
        "dst_port": 20,
        "time_first": 1.0,
        "time_last": 2.0,
        "label": 1,
    }
    assert sample_id(row) == sample_id(dict(row))


def test_sequence_stats_basic():
    stats = sequence_stats([100, 200, 300], [100, -200, 300], [1, -1, 1], [0.0, 0.1, 1.2])
    assert stats["pkt_len_mean"] == 200
    assert stats["burst_count"] == 2
    assert stats["seq_len_stored"] if "seq_len_stored" in stats else True

