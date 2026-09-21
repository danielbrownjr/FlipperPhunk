"""In-process mock serial ports + a simulated bridge, used when no real
USB-UART hardware / Flipper is attached.

This does NOT talk to any real serial hardware. It exists so the harness's
own logic (pattern generation, comparison, sweeps, sustained-transfer
accounting, recovery-gap detection) can be exercised end to end in CI or on
a dev machine with nothing plugged in. It intentionally mimics the
FlipperPhunk firmware's behavior -- an active relay thread that copies bytes
from one side's TX to the other side's RX -- rather than a trivial
``loop://`` single-port loopback, so "Side A" and "Side B" are modeled as
genuinely separate endpoints.

Passing a self-test against this mock proves the harness is internally
correct. It proves nothing about the real firmware, real UART electricals,
or real Flipper behavior -- that still requires the physical bench setup
described in the README.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Optional


class MockSerialPort:
    """Minimal pyserial.Serial-compatible interface backed by in-memory queues."""

    def __init__(self, name: str, baudrate: int, timeout: float = 0.2):
        self.port = name
        self.name = name
        self.baudrate = baudrate
        self.timeout = timeout
        self.is_open = True
        self._outbox: "queue.Queue[bytes]" = queue.Queue()
        self._inbox_buf = bytearray()
        self._inbox_lock = threading.Lock()
        self._inbox_ready = threading.Event()

    # -- pyserial-compatible surface used by the rest of this package --
    def write(self, data: bytes) -> int:
        if not self.is_open:
            raise IOError(f"{self.name} is closed")
        self._outbox.put(bytes(data))
        return len(data)

    def read(self, size: int = 1) -> bytes:
        deadline = time.monotonic() + self.timeout
        out = bytearray()
        while len(out) < size:
            with self._inbox_lock:
                take = min(size - len(out), len(self._inbox_buf))
                if take:
                    out.extend(self._inbox_buf[:take])
                    del self._inbox_buf[:take]
                if not self._inbox_buf:
                    self._inbox_ready.clear()
            if len(out) >= size:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._inbox_ready.wait(timeout=min(remaining, 0.02))
        return bytes(out)

    @property
    def in_waiting(self) -> int:
        with self._inbox_lock:
            return len(self._inbox_buf)

    def reset_input_buffer(self) -> None:
        with self._inbox_lock:
            self._inbox_buf.clear()
            self._inbox_ready.clear()
        while not self._outbox.empty():
            try:
                self._outbox.get_nowait()
            except queue.Empty:
                break

    def close(self) -> None:
        self.is_open = False

    def open(self) -> None:
        self.is_open = True

    # -- bridge-internal plumbing --
    def _drain_outbox_nowait(self) -> bytes:
        chunks = []
        while True:
            try:
                chunks.append(self._outbox.get_nowait())
            except queue.Empty:
                break
        return b"".join(chunks)

    def _deliver(self, data: bytes) -> None:
        if not data:
            return
        with self._inbox_lock:
            self._inbox_buf.extend(data)
            self._inbox_ready.set()


class MockBridge:
    """Simulates the Flipper's relay thread between two MockSerialPort ends.

    ``pause()``/``resume()`` model the firmware's on-device pause toggle.
    ``stop()``/``start()`` model the app/relay not running at all (Rev C.1
    has no fail-safe bypass, so a stopped bridge means zero bytes get
    through in either direction -- see hardware/README.md).
    """

    def __init__(
        self,
        port_a: MockSerialPort,
        port_b: MockSerialPort,
        latency_s: float = 0.0,
        drop_every_n: Optional[int] = None,
    ):
        self._a = port_a
        self._b = port_b
        self.latency_s = latency_s
        self.drop_every_n = drop_every_n
        self._byte_counter = 0
        self._running = threading.Event()
        self._paused = threading.Event()
        self._stop_flag = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag.clear()
        self._running.set()
        self._thread = threading.Thread(target=self._run, name="MockBridge", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_flag.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._running.clear()

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    @property
    def running(self) -> bool:
        return self._running.is_set() and not self._stop_flag.is_set()

    def _forward(self, src: MockSerialPort, dst: MockSerialPort) -> None:
        if self._paused.is_set():
            # Leave bytes sitting in src's outbox (undelivered) rather than
            # draining-and-discarding, so resume() can still forward them.
            return
        data = src._drain_outbox_nowait()
        if not data:
            return
        if self.drop_every_n:
            kept = bytearray()
            for b in data:
                self._byte_counter += 1
                if self._byte_counter % self.drop_every_n == 0:
                    continue
                kept.append(b)
            data = bytes(kept)
        if self.latency_s > 0:
            time.sleep(self.latency_s)
        dst._deliver(data)

    def _run(self) -> None:
        while not self._stop_flag.is_set():
            self._forward(self._a, self._b)
            self._forward(self._b, self._a)
            time.sleep(0.001)


def make_loopback_pair(
    baudrate: int = 9600, timeout: float = 0.5, latency_s: float = 0.0
) -> tuple[MockSerialPort, MockSerialPort, MockBridge]:
    """Convenience constructor: two connected mock ports + a running bridge."""
    port_a = MockSerialPort("MOCK-A", baudrate, timeout)
    port_b = MockSerialPort("MOCK-B", baudrate, timeout)
    bridge = MockBridge(port_a, port_b, latency_s=latency_s)
    bridge.start()
    return port_a, port_b, bridge
