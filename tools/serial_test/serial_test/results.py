"""Result records and machine-readable (JSON/CSV) + human-readable output."""
from __future__ import annotations

import csv
import dataclasses
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class LatencySummary:
    sample_count: int
    min_ms: Optional[float]
    median_ms: Optional[float]
    mean_ms: Optional[float]
    max_ms: Optional[float]
    missed_samples: int
    method: str

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclass
class TestResult:
    """One test case's outcome, in the shape required by the task's
    "machine-readable and human-readable results" section."""

    __test__ = False  # not a pytest test class, just named TestResult

    timestamp: str
    test_type: str  # bridge | sweep | sustained | latency | recovery
    port_a: str
    port_b: str
    baud: int
    pattern: str
    direction: str  # "A->B" | "B->A" | "bidirectional"
    bytes_sent: int
    bytes_received: int
    passed: bool
    duration_s: float
    throughput_bps: float
    mismatch_summary: Dict[str, Any] = field(default_factory=dict)
    latency: Optional[LatencySummary] = None
    notes: str = ""

    @classmethod
    def now(cls, **kwargs) -> "TestResult":
        kwargs.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        return cls(**kwargs)

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        if self.latency is not None:
            d["latency"] = self.latency.to_dict()
        return d


def summarize(results: List[TestResult]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "all_passed": passed == total,
    }


def print_console_summary(results: List[TestResult]) -> None:
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(
            f"[{status}] {r.test_type:<10} {r.direction:<12} pattern={r.pattern:<13} "
            f"baud={r.baud:<7} sent={r.bytes_sent:<8} recv={r.bytes_received:<8} "
            f"{r.throughput_bps/1000:8.2f} kbps  {r.duration_s:6.3f}s"
        )
        if not r.passed and r.mismatch_summary:
            print(f"         mismatch: {r.mismatch_summary}")
        if r.latency is not None:
            lat = r.latency
            print(
                f"         latency(ms) n={lat.sample_count} missed={lat.missed_samples} "
                f"min={lat.min_ms} median={lat.median_ms} mean={lat.mean_ms} max={lat.max_ms}"
            )
    summary = summarize(results)
    print("-" * 72)
    print(
        f"TOTAL: {summary['total']}  PASSED: {summary['passed']}  "
        f"FAILED: {summary['failed']}  ALL_PASSED: {summary['all_passed']}"
    )


def write_json(results: List[TestResult], path: str) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summarize(results),
        "results": [r.to_dict() for r in results],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    print(f"Wrote JSON results: {path}", file=sys.stderr)


_CSV_FIELDS = [
    "timestamp",
    "test_type",
    "port_a",
    "port_b",
    "baud",
    "pattern",
    "direction",
    "bytes_sent",
    "bytes_received",
    "passed",
    "duration_s",
    "throughput_bps",
    "dropped_bytes",
    "duplicated_or_extra_bytes",
    "corrupted_bytes",
    "latency_min_ms",
    "latency_median_ms",
    "latency_mean_ms",
    "latency_max_ms",
    "latency_sample_count",
    "notes",
]


def write_csv(results: List[TestResult], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for r in results:
            row = {
                "timestamp": r.timestamp,
                "test_type": r.test_type,
                "port_a": r.port_a,
                "port_b": r.port_b,
                "baud": r.baud,
                "pattern": r.pattern,
                "direction": r.direction,
                "bytes_sent": r.bytes_sent,
                "bytes_received": r.bytes_received,
                "passed": r.passed,
                "duration_s": round(r.duration_s, 6),
                "throughput_bps": round(r.throughput_bps, 2),
                "dropped_bytes": r.mismatch_summary.get("dropped_bytes", ""),
                "duplicated_or_extra_bytes": r.mismatch_summary.get("duplicated_or_extra_bytes", ""),
                "corrupted_bytes": r.mismatch_summary.get("corrupted_bytes", ""),
                "latency_min_ms": r.latency.min_ms if r.latency else "",
                "latency_median_ms": r.latency.median_ms if r.latency else "",
                "latency_mean_ms": r.latency.mean_ms if r.latency else "",
                "latency_max_ms": r.latency.max_ms if r.latency else "",
                "latency_sample_count": r.latency.sample_count if r.latency else "",
                "notes": r.notes,
            }
            writer.writerow(row)
    print(f"Wrote CSV results: {path}", file=sys.stderr)
