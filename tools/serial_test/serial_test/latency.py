"""Approximate one-way forwarding-latency measurement.

Method (documented here because the task calls for a documented, explicit
method rather than a black box):

1. Drain the receiver's input buffer so no stale bytes are waiting.
2. Record a host timestamp, then write a single marker byte to the sender.
3. Block-read on the receiver (bounded by --timeout) for exactly one byte,
   and record a second host timestamp the instant it arrives.
4. latency_sample = t_rx - t_tx.
5. Wait --gap seconds before the next sample so consecutive markers can't
   be ambiguous on the wire.

This is a coarse, host-side, single-byte measurement. It bundles together
Python/OS scheduling jitter, the USB-UART adapter's own buffering, USB
polling interval, and the Flipper's actual firmware forwarding time -- it is
NOT a lab-grade, firmware-only latency instrument, and precision should not
be over-read past roughly 1ms. See the README limitations section.
"""
from __future__ import annotations

import statistics
import time
from typing import List, Optional

from .results import LatencySummary

METHOD_DESCRIPTION = (
    "single marker byte per sample, host timestamps around write()/read(1), "
    "receiver buffer drained before each sample"
)


def measure_latency(
    writer,
    reader,
    sample_count: int = 50,
    timeout_s: float = 1.0,
    gap_s: float = 0.02,
) -> LatencySummary:
    reader.reset_input_buffer()
    samples_ms: List[float] = []
    missed = 0

    for i in range(sample_count):
        marker = i & 0xFF
        reader.timeout = timeout_s
        reader.reset_input_buffer()

        t0 = time.perf_counter()
        writer.write(bytes([marker]))
        data = reader.read(1)
        t1 = time.perf_counter()

        if len(data) != 1:
            missed += 1
        else:
            samples_ms.append((t1 - t0) * 1000.0)
            # We don't hard-fail on data[0] != marker: on a correctly
            # functioning single-flight bridge it always matches, but if it
            # doesn't, the *timing* sample is still real (a byte arrived);
            # flag it by leaving detailed byte auditing to the bridge tests.

        if gap_s > 0:
            time.sleep(gap_s)

    def _stat(fn) -> Optional[float]:
        return round(fn(samples_ms), 4) if samples_ms else None

    return LatencySummary(
        sample_count=len(samples_ms),
        min_ms=_stat(min),
        median_ms=_stat(statistics.median),
        mean_ms=_stat(statistics.mean),
        max_ms=_stat(max),
        missed_samples=missed,
        method=METHOD_DESCRIPTION,
    )
