import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from serial_test.patterns import PATTERNS, PatternStream, generate_pattern


def test_all_named_patterns_registered():
    expected = {"ascii", "zeros", "ones", "alt55aa", "incrementing", "random"}
    assert set(PATTERNS) == expected


def test_deterministic_across_calls():
    for name in PATTERNS:
        a = generate_pattern(name, 1024, seed=7)
        b = generate_pattern(name, 1024, seed=7)
        assert a == b
        assert len(a) == 1024


def test_random_seed_changes_output():
    a = generate_pattern("random", 256, seed=1)
    b = generate_pattern("random", 256, seed=2)
    assert a != b


def test_zeros_and_ones_content():
    assert generate_pattern("zeros", 16) == b"\x00" * 16
    assert generate_pattern("ones", 16) == b"\xff" * 16


def test_alt_pattern_content():
    data = generate_pattern("alt55aa", 6)
    assert data == b"\x55\xaa\x55\xaa\x55\xaa"


def test_incrementing_wraps():
    data = generate_pattern("incrementing", 300)
    assert data[:256] == bytes(range(256))
    assert data[256:260] == bytes(range(4))


def test_zero_length_is_empty():
    for name in PATTERNS:
        assert generate_pattern(name, 0) == b""


def test_pattern_stream_matches_bulk_generation():
    for name in PATTERNS:
        seed = 99
        bulk = generate_pattern(name, 1000, seed=seed)
        stream = PatternStream(name, seed=seed)
        rebuilt = bytearray()
        for n in (1, 7, 250, 500, 242):
            rebuilt.extend(stream.next(n))
        assert bytes(rebuilt) == bulk


def test_pattern_stream_is_prefix_stable_vs_bulk_regeneration():
    # Streaming in small chunks must equal a single bulk call of the same
    # total length -- this is the property sustained-transfer tests rely on.
    stream = PatternStream("random", seed=55)
    chunks = [stream.next(37) for _ in range(10)]
    streamed = b"".join(chunks)
    bulk = generate_pattern("random", 370, seed=55)
    assert streamed == bulk
