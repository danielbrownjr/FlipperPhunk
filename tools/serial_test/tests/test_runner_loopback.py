"""End-to-end harness-logic tests against the in-process mock bridge.

These validate the harness's own test-mode logic (patterns, comparison,
sweeps, sustained accounting, latency measurement, recovery-gap detection)
with NO real serial hardware. See tools/serial_test/README.md for what
still requires a physical bench run.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from serial_test.baud import FIRMWARE_BAUD_RATES
from serial_test.patterns import DEFAULT_PATTERN_ORDER
from serial_test.portio import PortSpec, SerialSession
from serial_test import runner


def _mock_session(baud=9600, timeout=0.5):
    session = SerialSession(PortSpec("MOCK-A", "A"), PortSpec("MOCK-B", "B"), baud, timeout=timeout, mock=True)
    session.open()
    return session


def test_bridge_all_patterns_roundtrip():
    session = _mock_session()
    try:
        results = runner.run_bridge_test(
            session, "MOCK-A", "MOCK-B", 9600, list(DEFAULT_PATTERN_ORDER), 300, seed=42
        )
        assert len(results) == len(DEFAULT_PATTERN_ORDER) * 2  # both directions
        assert all(r.passed for r in results)
        assert all(r.bytes_sent == r.bytes_received == 300 for r in results)
    finally:
        session.close()


def test_sweep_covers_every_firmware_baud():
    session = _mock_session()
    seen_bauds = []

    def on_baud_change(baud):
        seen_bauds.append(baud)
        session.reopen(baud)

    try:
        results = runner.run_sweep(
            session, "MOCK-A", "MOCK-B", list(FIRMWARE_BAUD_RATES), ["ascii"], 64, 1, on_baud_change
        )
    finally:
        session.close()

    assert seen_bauds == list(FIRMWARE_BAUD_RATES)
    assert len(results) == len(FIRMWARE_BAUD_RATES) * 2  # A->B and B->A per baud
    assert all(r.passed for r in results)


def test_sustained_one_way_by_size():
    session = _mock_session()
    try:
        results = runner.run_sustained(
            session, "MOCK-A", "MOCK-B", 9600, ["A->B"], "incrementing", 5000, None, 200, seed=None
        )
    finally:
        session.close()
    assert len(results) == 1
    r = results[0]
    assert r.bytes_sent == 5000
    assert r.passed
    assert r.bytes_received == 5000


def test_sustained_bidirectional_simultaneous():
    session = _mock_session()
    try:
        results = runner.run_sustained(
            session, "MOCK-A", "MOCK-B", 9600, ["A->B", "B->A"], "random", 4000, None, 128, seed=7
        )
    finally:
        session.close()
    assert {r.direction for r in results} == {"A->B", "B->A"}
    assert all(r.passed for r in results)


def test_sustained_by_duration():
    session = _mock_session()
    try:
        start = time.perf_counter()
        results = runner.run_sustained(
            session, "MOCK-A", "MOCK-B", 9600, ["A->B"], "zeros", None, 0.3, 64, seed=None
        )
        elapsed = time.perf_counter() - start
    finally:
        session.close()
    assert elapsed < 3.0
    assert results[0].bytes_sent > 0
    assert results[0].passed


def test_latency_reports_samples_and_stats():
    session = _mock_session()
    try:
        result = runner.run_latency_test(session, "MOCK-A", "MOCK-B", 9600, "A->B", 10, 1.0, 0.0)
    finally:
        session.close()
    assert result.latency is not None
    assert result.latency.sample_count == 10
    assert result.latency.missed_samples == 0
    assert result.latency.min_ms is not None and result.latency.min_ms >= 0


def test_recovery_watch_detects_no_gap_when_stable():
    session = _mock_session()
    try:
        result = runner.run_recovery_watch(
            session, "MOCK-A", "MOCK-B", 9600, "A->B", duration_s=0.6, heartbeat_interval_s=0.02, gap_threshold_s=0.2
        )
    finally:
        session.close()
    assert result.mismatch_summary["gap_count"] == 0


def test_recovery_watch_detects_simulated_bridge_pause():
    session = _mock_session()

    def pause_then_resume():
        time.sleep(0.2)
        session._mock_bridge.pause()
        time.sleep(0.3)
        session._mock_bridge.resume()

    t = threading.Thread(target=pause_then_resume)
    t.start()
    try:
        result = runner.run_recovery_watch(
            session, "MOCK-A", "MOCK-B", 9600, "A->B", duration_s=1.0, heartbeat_interval_s=0.02, gap_threshold_s=0.15
        )
    finally:
        t.join()
        session.close()
    assert result.mismatch_summary["gap_count"] >= 1
    assert result.mismatch_summary["longest_gap_s"] > 0.1


def test_port_cycle_recovers_after_reopen():
    session = _mock_session()
    try:
        results = runner.run_port_cycle_test(session, "MOCK-A", "MOCK-B", 9600, "A->B")
    finally:
        session.close()
    assert len(results) == 2
    assert all(r.passed for r in results)
