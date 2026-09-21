import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from serial_test.cli import main


def test_self_test_command_passes(capsys):
    rc = main(["self-test"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ALL_PASSED: True" in out


def test_self_test_writes_json(tmp_path):
    out_path = tmp_path / "results.json"
    rc = main(["self-test", "--out-json", str(out_path)])
    assert rc == 0
    assert out_path.exists()
    assert out_path.stat().st_size > 0


def test_bridge_requires_ports_without_mock():
    try:
        main(["bridge"])
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code != 0


def test_sustained_requires_exactly_one_of_size_or_duration():
    try:
        main(["sustained", "--mock", "--size", "100", "--duration", "1"])
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code != 0


def test_sustained_long_soak_guardrail_blocks_without_flag():
    try:
        main(["sustained", "--mock", "--duration", "400"])
        assert False, "expected SystemExit"
    except SystemExit as exc:
        assert exc.code != 0


def test_bridge_mock_end_to_end(capsys):
    rc = main(["bridge", "--mock", "--patterns", "ascii", "incrementing", "--length", "128"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "PASS" in out
