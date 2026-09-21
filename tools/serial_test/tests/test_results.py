import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from serial_test.results import LatencySummary, TestResult, summarize, write_csv, write_json


def _sample_result(passed=True):
    return TestResult.now(
        test_type="bridge",
        port_a="COM1",
        port_b="COM2",
        baud=9600,
        pattern="ascii",
        direction="A->B",
        bytes_sent=100,
        bytes_received=100 if passed else 90,
        passed=passed,
        duration_s=0.05,
        throughput_bps=16000.0,
        mismatch_summary={} if passed else {"dropped_bytes": 10},
    )


def test_summarize_counts_pass_fail():
    results = [_sample_result(True), _sample_result(True), _sample_result(False)]
    s = summarize(results)
    assert s == {"total": 3, "passed": 2, "failed": 1, "all_passed": False}


def test_write_json_round_trips(tmp_path):
    results = [_sample_result(True), _sample_result(False)]
    out = tmp_path / "results.json"
    write_json(results, str(out))
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["summary"]["total"] == 2
    assert len(payload["results"]) == 2
    assert payload["results"][0]["port_a"] == "COM1"


def test_write_csv_has_header_and_rows(tmp_path):
    results = [_sample_result(True)]
    out = tmp_path / "results.csv"
    write_csv(results, str(out))
    text = out.read_text(encoding="utf-8")
    lines = text.strip().splitlines()
    assert lines[0].startswith("timestamp,")
    assert "bridge" in lines[1]


def test_latency_summary_serializes():
    lat = LatencySummary(
        sample_count=10, min_ms=1.0, median_ms=2.0, mean_ms=2.5, max_ms=5.0, missed_samples=0, method="test"
    )
    d = lat.to_dict()
    assert d["sample_count"] == 10
    assert d["method"] == "test"
