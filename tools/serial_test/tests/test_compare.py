import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from serial_test.compare import compare


def test_exact_match():
    r = compare(b"hello world", b"hello world")
    assert r.exact_match
    assert r.passed
    assert r.dropped_bytes == 0
    assert r.duplicated_or_extra_bytes == 0
    assert r.corrupted_bytes == 0
    assert r.first_mismatch_index is None


def test_dropped_bytes_detected():
    sent = bytes(range(20))
    received = sent[:10] + sent[15:]  # bytes 10..14 dropped
    r = compare(sent, received)
    assert not r.exact_match
    assert r.dropped_bytes == 5
    assert r.duplicated_or_extra_bytes == 0
    assert r.first_mismatch_index == 10


def test_duplicated_bytes_detected():
    sent = bytes(range(10))
    received = sent[:5] + sent[3:5] + sent[5:]  # bytes 3,4 duplicated
    r = compare(sent, received)
    assert not r.exact_match
    assert r.duplicated_or_extra_bytes == 2
    assert r.dropped_bytes == 0


def test_corrupted_bytes_detected():
    sent = bytearray(range(10))
    received = bytearray(sent)
    received[4] = 0xFF
    r = compare(bytes(sent), bytes(received))
    assert not r.exact_match
    assert r.corrupted_bytes >= 1
    assert r.first_mismatch_index == 4


def test_length_mismatch_without_detailed_diff():
    sent = b"\x00" * 10
    received = b"\x00" * 7
    r = compare(sent, received, detailed=False)
    assert not r.exact_match
    assert r.detailed_diff_skipped
    assert r.dropped_bytes == 3
    assert r.duplicated_or_extra_bytes == 0


def test_large_payload_skips_detailed_diff_automatically():
    big = b"\x00" * (300_000)
    other = b"\x00" * (300_000 - 1)
    r = compare(big, other)
    assert r.detailed_diff_skipped
    assert r.dropped_bytes == 1


def test_empty_vs_empty():
    r = compare(b"", b"")
    assert r.exact_match
    assert r.sent_len == 0
    assert r.received_len == 0
