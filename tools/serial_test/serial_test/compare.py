"""Byte-exact comparison / framing analysis between sent and received data.

The firmware relay is a raw byte pipe (no framing, no ACKs), so the ground
truth check is always "are these two byte strings identical". When they are
not, we use a byte-level diff to classify *why* -- dropped bytes, duplicated
bytes, or corrupted bytes -- which is far more actionable than a bare
pass/fail when debugging a real bridge.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import List, Tuple

# Above this size, skip the O(n) difflib alignment pass (still cheap, but not
# worth it for multi-megabyte soak captures) and fall back to summary counts.
DETAILED_DIFF_MAX_BYTES = 262_144


@dataclass
class DiffOp:
    tag: str  # "equal" | "replace" | "delete" | "insert"
    sent_range: Tuple[int, int]
    received_range: Tuple[int, int]


@dataclass
class ComparisonResult:
    sent_len: int
    received_len: int
    exact_match: bool
    first_mismatch_index: int | None
    dropped_bytes: int
    duplicated_or_extra_bytes: int
    corrupted_bytes: int
    detailed_diff_skipped: bool
    ops: List[DiffOp] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.exact_match

    def to_dict(self) -> dict:
        return {
            "sent_len": self.sent_len,
            "received_len": self.received_len,
            "exact_match": self.exact_match,
            "first_mismatch_index": self.first_mismatch_index,
            "dropped_bytes": self.dropped_bytes,
            "duplicated_or_extra_bytes": self.duplicated_or_extra_bytes,
            "corrupted_bytes": self.corrupted_bytes,
            "detailed_diff_skipped": self.detailed_diff_skipped,
        }


def _first_mismatch(sent: bytes, received: bytes) -> int | None:
    for i, (a, b) in enumerate(zip(sent, received)):
        if a != b:
            return i
    if len(sent) != len(received):
        return min(len(sent), len(received))
    return None


def compare(sent: bytes, received: bytes, detailed: bool = True) -> ComparisonResult:
    """Compare sent vs. received bytes and classify any mismatch.

    "duplicated_or_extra_bytes" covers difflib "insert" regions: bytes that
    appear on the receive side with no corresponding send-side bytes at that
    point. On a pure relay this is almost always retransmission/duplication
    rather than fabricated data, but we can't prove that from byte content
    alone, hence the combined label -- see the README limitations section.
    """
    if sent == received:
        return ComparisonResult(
            sent_len=len(sent),
            received_len=len(received),
            exact_match=True,
            first_mismatch_index=None,
            dropped_bytes=0,
            duplicated_or_extra_bytes=0,
            corrupted_bytes=0,
            detailed_diff_skipped=False,
        )

    first_mismatch = _first_mismatch(sent, received)

    too_large = len(sent) > DETAILED_DIFF_MAX_BYTES or len(received) > DETAILED_DIFF_MAX_BYTES
    if not detailed or too_large:
        dropped = max(0, len(sent) - len(received))
        extra = max(0, len(received) - len(sent))
        return ComparisonResult(
            sent_len=len(sent),
            received_len=len(received),
            exact_match=False,
            first_mismatch_index=first_mismatch,
            dropped_bytes=dropped,
            duplicated_or_extra_bytes=extra,
            corrupted_bytes=0,
            detailed_diff_skipped=True,
        )

    matcher = difflib.SequenceMatcher(None, sent, received, autojunk=False)
    ops: List[DiffOp] = []
    dropped = duplicated = corrupted = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        ops.append(DiffOp(tag, (i1, i2), (j1, j2)))
        if tag == "delete":
            dropped += i2 - i1
        elif tag == "insert":
            duplicated += j2 - j1
        elif tag == "replace":
            corrupted += max(i2 - i1, j2 - j1)

    return ComparisonResult(
        sent_len=len(sent),
        received_len=len(received),
        exact_match=False,
        first_mismatch_index=first_mismatch,
        dropped_bytes=dropped,
        duplicated_or_extra_bytes=duplicated,
        corrupted_bytes=corrupted,
        detailed_diff_skipped=False,
        ops=ops,
    )
