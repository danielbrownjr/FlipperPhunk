"""Deterministic, reproducible test-payload generators.

Every generator is a pure function of (length, seed) -- calling it twice with
the same arguments always yields byte-identical output. That determinism is
what lets the harness compare "what we sent" against "what came back" byte
for byte, including across separate processes/runs.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Dict

_ASCII_SAMPLE = (
    b"The quick brown fox jumps over the lazy dog 0123456789 "
    b"!@#$%^&*()_+-=[]{}|;:,.<>/?\r\n"
)


def _tile(chunk: bytes, length: int) -> bytes:
    if length <= 0:
        return b""
    reps = (length // len(chunk)) + 1
    return (chunk * reps)[:length]


def pattern_ascii(length: int, seed: int | None = None) -> bytes:
    """Printable ASCII text, tiled to length. Good for eyeballing captures."""
    del seed
    return _tile(_ASCII_SAMPLE, length)


def pattern_zeros(length: int, seed: int | None = None) -> bytes:
    """Repeated 0x00 -- exercises stuck-low / framing-on-idle edge cases."""
    del seed
    return b"\x00" * max(length, 0)


def pattern_ones(length: int, seed: int | None = None) -> bytes:
    """Repeated 0xFF -- exercises stuck-high / break-adjacent edge cases."""
    del seed
    return b"\xff" * max(length, 0)


def pattern_alt_55_aa(length: int, seed: int | None = None) -> bytes:
    """Alternating 0x55/0xAA -- classic UART bit-transition stress pattern."""
    del seed
    return _tile(b"\x55\xaa", length)


def pattern_incrementing(length: int, seed: int | None = None) -> bytes:
    """0x00..0xFF incrementing, wrapping -- makes byte loss/reorder obvious."""
    del seed
    return _tile(bytes(range(256)), length)


def pattern_random(length: int, seed: int | None = 0) -> bytes:
    """Seeded pseudorandom binary data. Reproducible for a given seed."""
    if length <= 0:
        return b""
    rng = random.Random(seed if seed is not None else 0)
    return bytes(rng.getrandbits(8) for _ in range(length))


@dataclass(frozen=True)
class PatternSpec:
    name: str
    description: str
    generate: Callable[[int, int | None], bytes]


PATTERNS: Dict[str, PatternSpec] = {
    spec.name: spec
    for spec in (
        PatternSpec("ascii", "Printable ASCII test string", pattern_ascii),
        PatternSpec("zeros", "0x00 repeated block", pattern_zeros),
        PatternSpec("ones", "0xFF repeated block", pattern_ones),
        PatternSpec("alt55aa", "0x55 / 0xAA alternating pattern", pattern_alt_55_aa),
        PatternSpec("incrementing", "Incrementing 0x00..0xFF blocks", pattern_incrementing),
        PatternSpec("random", "Seeded pseudorandom binary data", pattern_random),
    )
}

DEFAULT_PATTERN_ORDER = tuple(PATTERNS.keys())


def generate_pattern(name: str, length: int, seed: int | None = None) -> bytes:
    try:
        spec = PATTERNS[name]
    except KeyError as exc:
        raise ValueError(
            f"Unknown pattern {name!r}; choose from {sorted(PATTERNS)}"
        ) from exc
    return spec.generate(length, seed)


_TILE_CYCLES: Dict[str, bytes] = {
    "ascii": _ASCII_SAMPLE,
    "zeros": b"\x00",
    "ones": b"\xff",
    "alt55aa": b"\x55\xaa",
    "incrementing": bytes(range(256)),
}


class PatternStream:
    """Stateful, chunked pattern generator for sustained-transfer tests.

    Equivalent to repeatedly calling ``generate_pattern(name, offset + n,
    seed)[offset:offset + n]`` -- i.e. every pattern is prefix-stable, so a
    stream's output for a given (name, seed) never depends on how it was
    chunked -- but does the work in O(n) per call instead of O(total).
    """

    def __init__(self, name: str, seed: int | None = None):
        if name not in PATTERNS:
            raise ValueError(f"Unknown pattern {name!r}; choose from {sorted(PATTERNS)}")
        self.name = name
        self._offset = 0
        if name == "random":
            self._rng: random.Random | None = random.Random(seed if seed is not None else 0)
            self._cycle = None
        else:
            self._rng = None
            self._cycle = _TILE_CYCLES[name]

    def next(self, n: int) -> bytes:
        if n <= 0:
            return b""
        if self._rng is not None:
            data = bytes(self._rng.getrandbits(8) for _ in range(n))
        else:
            cycle = self._cycle
            start = self._offset % len(cycle)
            reps = (n + start) // len(cycle) + 1
            data = (cycle * reps)[start : start + n]
        self._offset += n
        return data
