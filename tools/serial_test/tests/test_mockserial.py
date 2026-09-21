import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from serial_test.mockserial import make_loopback_pair


def test_loopback_pair_forwards_a_to_b():
    a, b, bridge = make_loopback_pair(baudrate=9600, timeout=1.0)
    try:
        a.write(b"hello")
        data = b.read(5)
        assert data == b"hello"
    finally:
        bridge.stop()


def test_loopback_pair_forwards_b_to_a():
    a, b, bridge = make_loopback_pair(baudrate=9600, timeout=1.0)
    try:
        b.write(b"world")
        data = a.read(5)
        assert data == b"world"
    finally:
        bridge.stop()


def test_pause_blocks_forwarding_until_resumed():
    a, b, bridge = make_loopback_pair(baudrate=9600, timeout=0.3)
    try:
        bridge.pause()
        a.write(b"stuck")
        time.sleep(0.2)
        assert b.in_waiting == 0
        bridge.resume()
        data = b.read(5)
        assert data == b"stuck"
    finally:
        bridge.stop()


def test_stopped_bridge_delivers_nothing():
    a, b, bridge = make_loopback_pair(baudrate=9600, timeout=0.3)
    bridge.stop()
    a.write(b"gone")
    time.sleep(0.2)
    assert b.in_waiting == 0


def test_read_timeout_returns_partial_data():
    a, b, bridge = make_loopback_pair(baudrate=9600, timeout=0.2)
    try:
        a.write(b"ab")
        data = b.read(10)  # only 2 bytes ever arrive
        assert data == b"ab"
    finally:
        bridge.stop()
