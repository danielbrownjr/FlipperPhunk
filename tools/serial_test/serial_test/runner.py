"""Test orchestration: turns (session, patterns, config) into TestResult rows."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence

from .compare import compare
from .latency import measure_latency
from .patterns import PatternStream, generate_pattern
from .results import TestResult

BITS_PER_BYTE_8N1 = 10  # 1 start + 8 data + 1 stop, no parity


def estimate_transfer_seconds(nbytes: int, baud: int, margin: float = 3.0, fixed_margin_s: float = 1.0) -> float:
    """Worst-case-ish time budget for `nbytes` to cross the wire at `baud`."""
    if baud <= 0:
        return fixed_margin_s
    return (nbytes * BITS_PER_BYTE_8N1 / baud) * margin + fixed_margin_s


def read_exact_or_timeout(port, expected_len: int, overall_timeout_s: float, poll_timeout_s: float = 0.2) -> bytes:
    """Read up to expected_len bytes, polling until overall_timeout_s elapses."""
    original_timeout = getattr(port, "timeout", poll_timeout_s)
    port.timeout = poll_timeout_s
    out = bytearray()
    deadline = time.monotonic() + overall_timeout_s
    try:
        while len(out) < expected_len and time.monotonic() < deadline:
            chunk = port.read(expected_len - len(out))
            if chunk:
                out.extend(chunk)
    finally:
        port.timeout = original_timeout
    return bytes(out)


def run_bridge_test(
    session,
    port_a_name: str,
    port_b_name: str,
    baud: int,
    pattern_names: Sequence[str],
    length: int,
    seed: Optional[int],
    test_type: str = "bridge",
    directions: Sequence[str] = ("A->B", "B->A"),
) -> List[TestResult]:
    """Requirement #1/#2: send known payloads each direction, verify byte-exact."""
    results: List[TestResult] = []
    for name in pattern_names:
        payload = generate_pattern(name, length, seed)
        for direction in directions:
            tx = session.port_a if direction == "A->B" else session.port_b
            rx = session.port_b if direction == "A->B" else session.port_a
            rx.reset_input_buffer()

            overall_timeout = estimate_transfer_seconds(len(payload), baud)
            t0 = time.perf_counter()
            tx.write(payload)
            received = read_exact_or_timeout(rx, len(payload), overall_timeout)
            t1 = time.perf_counter()
            duration = max(t1 - t0, 1e-9)

            cmp_result = compare(payload, received)
            throughput = (len(received) * 8) / duration

            results.append(
                TestResult.now(
                    test_type=test_type,
                    port_a=port_a_name,
                    port_b=port_b_name,
                    baud=baud,
                    pattern=name,
                    direction=direction,
                    bytes_sent=len(payload),
                    bytes_received=len(received),
                    passed=cmp_result.passed,
                    duration_s=duration,
                    throughput_bps=throughput,
                    mismatch_summary=({} if cmp_result.passed else cmp_result.to_dict()),
                )
            )
    return results


def run_sweep(
    session,
    port_a_name: str,
    port_b_name: str,
    baud_list: Sequence[int],
    pattern_names: Sequence[str],
    length: int,
    seed: Optional[int],
    on_baud_change: Callable[[int], None],
) -> List[TestResult]:
    """Requirement #3: exercise each firmware-supported baud rate.

    IMPORTANT: the Flipper's own baud rate is selected on-device (Up/Down
    on the setup screen) before the relay is started -- this harness cannot
    remotely command it. `on_baud_change` is the caller's hook to reopen the
    host-side ports (and, for real hardware, prompt the operator to match
    the Flipper's selection) before each step.
    """
    results: List[TestResult] = []
    for baud in baud_list:
        on_baud_change(baud)
        results.extend(
            run_bridge_test(session, port_a_name, port_b_name, baud, pattern_names, length, seed, test_type="sweep")
        )
    return results


def run_latency_test(
    session,
    port_a_name: str,
    port_b_name: str,
    baud: int,
    direction: str,
    sample_count: int,
    timeout_s: float,
    gap_s: float,
) -> TestResult:
    """Requirement #5: approximate one-way forwarding latency."""
    writer, reader = (session.port_a, session.port_b) if direction == "A->B" else (session.port_b, session.port_a)
    t0 = time.perf_counter()
    summary = measure_latency(writer, reader, sample_count=sample_count, timeout_s=timeout_s, gap_s=gap_s)
    duration = max(time.perf_counter() - t0, 1e-9)

    return TestResult.now(
        test_type="latency",
        port_a=port_a_name,
        port_b=port_b_name,
        baud=baud,
        pattern="latency-marker",
        direction=direction,
        bytes_sent=sample_count,
        bytes_received=summary.sample_count,
        passed=summary.sample_count > 0,
        duration_s=duration,
        throughput_bps=0.0,
        latency=summary,
        notes="" if summary.missed_samples == 0 else f"{summary.missed_samples} sample(s) timed out",
    )


@dataclass
class _PumpState:
    sent: bytearray = field(default_factory=bytearray)
    received: bytearray = field(default_factory=bytearray)
    lock: threading.Lock = field(default_factory=threading.Lock)
    writer_done: threading.Event = field(default_factory=threading.Event)


def _writer_pump(tx, pattern_name, seed, size_bytes, duration_s, chunk_size, state: _PumpState):
    stream = PatternStream(pattern_name, seed)
    deadline = time.monotonic() + duration_s if duration_s is not None else None
    written = 0
    while True:
        if size_bytes is not None and written >= size_bytes:
            break
        if deadline is not None and time.monotonic() >= deadline:
            break
        n = chunk_size if size_bytes is None else min(chunk_size, size_bytes - written)
        chunk = stream.next(n)
        tx.write(chunk)
        with state.lock:
            state.sent.extend(chunk)
        written += len(chunk)
    state.writer_done.set()


def _reader_pump(rx, state: _PumpState, chunk_size: int, grace_s: float, stop_all: threading.Event):
    rx.timeout = 0.05
    idle_since_writer_done: Optional[float] = None
    while not stop_all.is_set():
        chunk = rx.read(chunk_size)
        if chunk:
            with state.lock:
                state.received.extend(chunk)
            idle_since_writer_done = None
            continue
        if state.writer_done.is_set():
            if idle_since_writer_done is None:
                idle_since_writer_done = time.monotonic()
            elif time.monotonic() - idle_since_writer_done >= grace_s:
                break


def run_sustained(
    session,
    port_a_name: str,
    port_b_name: str,
    baud: int,
    directions: Sequence[str],
    pattern_name: str,
    size_bytes: Optional[int],
    duration_s: Optional[float],
    chunk_size: int,
    seed: Optional[int],
    read_grace_s: float = 1.0,
) -> List[TestResult]:
    """Requirement #4: one-way or simultaneous bidirectional sustained transfer."""
    states = {d: _PumpState() for d in directions}
    threads: List[threading.Thread] = []
    stop_all = threading.Event()
    start = time.perf_counter()

    for d in directions:
        tx, rx = (session.port_a, session.port_b) if d == "A->B" else (session.port_b, session.port_a)
        state = states[d]
        wt = threading.Thread(
            target=_writer_pump, args=(tx, pattern_name, seed, size_bytes, duration_s, chunk_size, state)
        )
        rt = threading.Thread(target=_reader_pump, args=(rx, state, chunk_size, read_grace_s, stop_all))
        threads.extend([wt, rt])
        wt.start()
        rt.start()

    for t in threads:
        t.join()
    duration = max(time.perf_counter() - start, 1e-9)

    results: List[TestResult] = []
    label = "bidirectional" if len(directions) > 1 else directions[0]
    for d in directions:
        state = states[d]
        sent = bytes(state.sent)
        received = bytes(state.received)
        cmp_result = compare(sent, received)
        throughput = (len(received) * 8) / duration
        results.append(
            TestResult.now(
                test_type="sustained",
                port_a=port_a_name,
                port_b=port_b_name,
                baud=baud,
                pattern=pattern_name,
                direction=d,
                bytes_sent=len(sent),
                bytes_received=len(received),
                passed=cmp_result.passed,
                duration_s=duration,
                throughput_bps=throughput,
                mismatch_summary=({} if cmp_result.passed else cmp_result.to_dict()),
                notes=f"mode={label}",
            )
        )
    return results


@dataclass
class GapEvent:
    start_s: float
    end_s: Optional[float]
    duration_s: Optional[float]


def run_recovery_watch(
    session,
    port_a_name: str,
    port_b_name: str,
    baud: int,
    direction: str,
    duration_s: float,
    heartbeat_interval_s: float = 0.1,
    gap_threshold_s: float = 0.5,
) -> TestResult:
    """Requirement #6 (guided): stream a heartbeat and log arrival gaps.

    This does NOT trigger app restarts, bridge stop/restart, cable
    disconnects, or the on-device pause toggle itself -- those require a
    human at the bench. Run this while performing one of those actions;
    the reported gaps are the *observed* recovery behavior to compare
    against the *expected* behavior documented in the README.
    """
    tx, rx = (session.port_a, session.port_b) if direction == "A->B" else (session.port_b, session.port_a)
    rx.reset_input_buffer()
    rx.timeout = 0.05

    stop_writer = threading.Event()
    counter = [0]

    def _heartbeat_writer():
        while not stop_writer.is_set():
            tx.write(bytes([counter[0] & 0xFF]))
            counter[0] += 1
            time.sleep(heartbeat_interval_s)

    gaps: List[GapEvent] = []
    received_count = 0
    start = time.monotonic()
    last_rx = start
    wt = threading.Thread(target=_heartbeat_writer, daemon=True)
    wt.start()

    in_gap = False
    gap_start = 0.0
    while time.monotonic() - start < duration_s:
        data = rx.read(64)
        now = time.monotonic()
        if data:
            received_count += len(data)
            if in_gap:
                gaps.append(GapEvent(gap_start - start, now - start, now - gap_start))
                in_gap = False
            last_rx = now
        else:
            if not in_gap and (now - last_rx) >= gap_threshold_s:
                in_gap = True
                gap_start = last_rx

    stop_writer.set()
    wt.join(timeout=1.0)
    if in_gap:
        gaps.append(GapEvent(gap_start - start, None, None))

    sent_count = counter[0]
    longest_gap = max((g.duration_s for g in gaps if g.duration_s is not None), default=0.0)

    return TestResult.now(
        test_type="recovery",
        port_a=port_a_name,
        port_b=port_b_name,
        baud=baud,
        pattern="incrementing-heartbeat",
        direction=direction,
        bytes_sent=sent_count,
        bytes_received=received_count,
        passed=True,  # informational: pass/fail judged by the operator vs. expected behavior
        duration_s=duration_s,
        throughput_bps=(received_count * 8) / duration_s if duration_s > 0 else 0.0,
        mismatch_summary={
            "gap_count": len(gaps),
            "longest_gap_s": round(longest_gap, 3),
            "gaps": [
                {
                    "start_s": round(g.start_s, 3),
                    "end_s": None if g.end_s is None else round(g.end_s, 3),
                    "duration_s": None if g.duration_s is None else round(g.duration_s, 3),
                }
                for g in gaps
            ],
        },
        notes="Heartbeat gap log -- correlate gap windows with the manual action performed during this run.",
    )


def run_port_cycle_test(
    session,
    port_a_name: str,
    port_b_name: str,
    baud: int,
    direction: str,
    payload_length: int = 64,
    seed: Optional[int] = None,
) -> List[TestResult]:
    """Requirement #6 (automated): host-side serial-port open/close/reopen.

    Verifies (a) a normal transfer works, (b) closing then reopening the
    host port doesn't itself corrupt the next transfer once both ports are
    open again. It does not restart the Flipper app or bridge -- see
    run_recovery_watch / README for those.
    """
    results = run_bridge_test(
        session,
        port_a_name,
        port_b_name,
        baud,
        ["incrementing"],
        payload_length,
        seed,
        test_type="port-cycle-before",
        directions=(direction,),
    )

    session.reopen(baud)

    results.extend(
        run_bridge_test(
            session,
            port_a_name,
            port_b_name,
            baud,
            ["incrementing"],
            payload_length,
            seed,
            test_type="port-cycle-after",
            directions=(direction,),
        )
    )
    return results
