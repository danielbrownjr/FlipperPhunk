"""Command-line entry point for the FlipperPhunk host-side serial test harness.

Run `python -m serial_test.cli --help` (from tools/serial_test/) or
`serial-test --help` if installed. See ../README.md for full usage,
wiring, and safety notes -- these are 3.3V TTL UART connections to the
Flipper's GPIO header, NOT RS-232 voltage-level connections.
"""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .baud import FIRMWARE_BAUD_RATES, FIRMWARE_DEFAULT_BAUD
from .patterns import DEFAULT_PATTERN_ORDER
from .portio import PortOpenError, PortSpec, SerialSession
from .results import TestResult, print_console_summary, write_csv, write_json
from . import runner

LONG_SOAK_DURATION_S = 300.0  # 5 minutes
LONG_SOAK_SIZE_BYTES = 50_000_000  # 50 MB


def _add_common_port_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--port-a", help="Serial device for Side A / HOST (e.g. COM5, /dev/ttyUSB0)")
    p.add_argument("--port-b", help="Serial device for Side B / INSTRUMENT (e.g. COM6, /dev/ttyUSB1)")
    p.add_argument("--baud", type=int, default=FIRMWARE_DEFAULT_BAUD, help="Baud rate (must match the Flipper's on-device selection)")
    p.add_argument("--timeout", type=float, default=0.3, help="Per-read timeout in seconds for host serial ports")
    p.add_argument("--mock", action="store_true", help="Use an in-process simulated bridge instead of real hardware")
    p.add_argument("--out-json", help="Write JSON results to this path")
    p.add_argument("--out-csv", help="Write CSV results to this path")


def _require_ports(args) -> None:
    if not args.mock and (not args.port_a or not args.port_b):
        raise SystemExit("--port-a and --port-b are required unless --mock is given")


def _open_session(args) -> SerialSession:
    a = PortSpec(args.port_a or "MOCK-A", "A")
    b = PortSpec(args.port_b or "MOCK-B", "B")
    session = SerialSession(a, b, args.baud, timeout=args.timeout, mock=args.mock)
    try:
        session.open()
    except PortOpenError as exc:
        raise SystemExit(f"error: {exc}")
    return session


def _emit(results: List[TestResult], args) -> bool:
    print_console_summary(results)
    if args.out_json:
        write_json(results, args.out_json)
    if getattr(args, "out_csv", None):
        write_csv(results, args.out_csv)
    return all(r.passed for r in results)


def cmd_list_ports(_args) -> int:
    try:
        import serial.tools.list_ports as list_ports
    except ImportError:
        print("pyserial is not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        return 1
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return 0
    for p in ports:
        print(f"{p.device}\t{p.description}\t{p.hwid}")
    return 0


def cmd_bridge(args) -> int:
    _require_ports(args)
    patterns = args.patterns
    with _open_session(args) as session:
        results = runner.run_bridge_test(
            session, args.port_a or "MOCK-A", args.port_b or "MOCK-B", args.baud, patterns, args.length, args.seed
        )
    return 0 if _emit(results, args) else 1


def cmd_sweep(args) -> int:
    _require_ports(args)
    bauds = args.bauds or list(FIRMWARE_BAUD_RATES)
    session = _open_session(args)

    def on_baud_change(baud: int) -> None:
        if not args.mock:
            print(
                f"\n>>> Set the Flipper's setup-screen baud to {baud} and (re)start the relay, "
                f"then press Enter to continue...",
                file=sys.stderr,
            )
            input()
        session.reopen(baud)

    try:
        results = runner.run_sweep(
            session, args.port_a or "MOCK-A", args.port_b or "MOCK-B", bauds, args.patterns, args.length, args.seed, on_baud_change
        )
    finally:
        session.close()
    return 0 if _emit(results, args) else 1


def _direction_list(direction: str) -> List[str]:
    return {"a2b": ["A->B"], "b2a": ["B->A"], "bidirectional": ["A->B", "B->A"]}[direction]


def cmd_sustained(args) -> int:
    _require_ports(args)
    if (args.size is None) == (args.duration is None):
        raise SystemExit("Specify exactly one of --size or --duration for a sustained test")
    if args.duration is not None and args.duration > LONG_SOAK_DURATION_S and not args.allow_long_soak:
        raise SystemExit(
            f"--duration {args.duration}s exceeds the {LONG_SOAK_DURATION_S}s soak-test guardrail; "
            f"pass --allow-long-soak to run it anyway"
        )
    if args.size is not None and args.size > LONG_SOAK_SIZE_BYTES and not args.allow_long_soak:
        raise SystemExit(
            f"--size {args.size} bytes exceeds the {LONG_SOAK_SIZE_BYTES}-byte soak-test guardrail; "
            f"pass --allow-long-soak to run it anyway"
        )

    directions = _direction_list(args.direction)
    with _open_session(args) as session:
        results = runner.run_sustained(
            session,
            args.port_a or "MOCK-A",
            args.port_b or "MOCK-B",
            args.baud,
            directions,
            args.pattern,
            args.size,
            args.duration,
            args.chunk_size,
            args.seed,
        )
    return 0 if _emit(results, args) else 1


def cmd_latency(args) -> int:
    _require_ports(args)
    with _open_session(args) as session:
        result = runner.run_latency_test(
            session,
            args.port_a or "MOCK-A",
            args.port_b or "MOCK-B",
            args.baud,
            args.direction,
            args.samples,
            args.timeout_s,
            args.gap,
        )
    return 0 if _emit([result], args) else 1


def cmd_recover_watch(args) -> int:
    _require_ports(args)
    if args.duration > LONG_SOAK_DURATION_S and not args.allow_long_soak:
        raise SystemExit(
            f"--duration {args.duration}s exceeds the {LONG_SOAK_DURATION_S}s soak-test guardrail; "
            f"pass --allow-long-soak to run it anyway"
        )
    print(
        "Streaming a heartbeat now. Perform the failure/recovery action you want to observe "
        "(app restart, bridge stop/restart, cable disconnect/reconnect, on-device pause) during this window.",
        file=sys.stderr,
    )
    with _open_session(args) as session:
        result = runner.run_recovery_watch(
            session,
            args.port_a or "MOCK-A",
            args.port_b or "MOCK-B",
            args.baud,
            args.direction,
            args.duration,
            args.heartbeat_interval,
            args.gap_threshold,
        )
    _emit([result], args)
    return 0


def cmd_recover_port_cycle(args) -> int:
    _require_ports(args)
    with _open_session(args) as session:
        results = runner.run_port_cycle_test(
            session, args.port_a or "MOCK-A", args.port_b or "MOCK-B", args.baud, args.direction
        )
    return 0 if _emit(results, args) else 1


def cmd_self_test(args) -> int:
    """Runs the full test battery against the in-process mock bridge.

    Proves the harness's own logic is internally consistent. It exercises
    NO real serial hardware -- see the README for what still needs a bench
    run with an actual Flipper and two USB-UART adapters.
    """
    args.mock = True
    args.port_a = None
    args.port_b = None
    args.timeout = 0.5
    all_results: List[TestResult] = []

    with _open_session(args) as session:
        all_results.extend(
            runner.run_bridge_test(session, "MOCK-A", "MOCK-B", args.baud, list(DEFAULT_PATTERN_ORDER), 512, 1234)
        )
        all_results.extend(
            runner.run_sustained(
                session, "MOCK-A", "MOCK-B", args.baud, ["A->B", "B->A"], "random", 8192, None, 256, 42
            )
        )
        all_results.append(
            runner.run_latency_test(session, "MOCK-A", "MOCK-B", args.baud, "A->B", 20, 1.0, 0.0)
        )

    ok = _emit(all_results, args)
    print("\nself-test: MOCK BRIDGE ONLY -- no real serial hardware was exercised.", file=sys.stderr)
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="serial_test",
        description="Host-side serial stress-test harness for the FlipperPhunk RS-232 bridge/logger firmware.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list-ports", help="List available serial ports")
    p_list.set_defaults(func=cmd_list_ports)

    p_bridge = sub.add_parser("bridge", help="Basic bidirectional payload verification (requirement #1/#2)")
    _add_common_port_args(p_bridge)
    p_bridge.add_argument("--patterns", nargs="+", default=list(DEFAULT_PATTERN_ORDER), choices=list(DEFAULT_PATTERN_ORDER))
    p_bridge.add_argument("--length", type=int, default=512, help="Payload length in bytes per pattern")
    p_bridge.add_argument("--seed", type=int, default=1234, help="Seed for the 'random' pattern")
    p_bridge.set_defaults(func=cmd_bridge)

    p_sweep = sub.add_parser("sweep", help="Baud-rate sweep (requirement #3)")
    _add_common_port_args(p_sweep)
    p_sweep.add_argument("--bauds", type=int, nargs="+", default=None, help=f"Bauds to test (default: {list(FIRMWARE_BAUD_RATES)})")
    p_sweep.add_argument("--patterns", nargs="+", default=["ascii", "incrementing", "random"], choices=list(DEFAULT_PATTERN_ORDER))
    p_sweep.add_argument("--length", type=int, default=256)
    p_sweep.add_argument("--seed", type=int, default=1234)
    p_sweep.set_defaults(func=cmd_sweep)

    p_sus = sub.add_parser("sustained", help="Sustained transfer test (requirement #4)")
    _add_common_port_args(p_sus)
    p_sus.add_argument("--direction", choices=["a2b", "b2a", "bidirectional"], default="a2b")
    p_sus.add_argument("--pattern", default="random", choices=list(DEFAULT_PATTERN_ORDER))
    p_sus.add_argument("--size", type=int, default=None, help="Total bytes to send per direction")
    p_sus.add_argument("--duration", type=float, default=None, help="Duration in seconds to stream")
    p_sus.add_argument("--chunk-size", type=int, default=256)
    p_sus.add_argument("--seed", type=int, default=1234)
    p_sus.add_argument("--allow-long-soak", action="store_true", help=f"Allow duration > {LONG_SOAK_DURATION_S}s or size > {LONG_SOAK_SIZE_BYTES} bytes")
    p_sus.set_defaults(func=cmd_sustained)

    p_lat = sub.add_parser("latency", help="Approximate forwarding-latency characterization (requirement #5)")
    _add_common_port_args(p_lat)
    p_lat.add_argument("--direction", choices=["A->B", "B->A"], default="A->B")
    p_lat.add_argument("--samples", type=int, default=50)
    p_lat.add_argument("--timeout-s", type=float, default=1.0)
    p_lat.add_argument("--gap", type=float, default=0.02, help="Delay between samples in seconds")
    p_lat.set_defaults(func=cmd_latency)

    p_recover = sub.add_parser("recover", help="Failure/recovery test helpers (requirement #6)")
    recover_sub = p_recover.add_subparsers(dest="recover_command", required=True)

    p_watch = recover_sub.add_parser("watch", help="Guided: stream a heartbeat and log arrival gaps while you perform a failure action")
    _add_common_port_args(p_watch)
    p_watch.add_argument("--direction", choices=["A->B", "B->A"], default="A->B")
    p_watch.add_argument("--duration", type=float, default=30.0)
    p_watch.add_argument("--heartbeat-interval", type=float, default=0.1)
    p_watch.add_argument("--gap-threshold", type=float, default=0.5, help="Seconds of silence before a gap is logged")
    p_watch.add_argument("--allow-long-soak", action="store_true")
    p_watch.set_defaults(func=cmd_recover_watch)

    p_cycle = recover_sub.add_parser("port-cycle", help="Automated: verify recovery across a host-side serial port close/reopen")
    _add_common_port_args(p_cycle)
    p_cycle.add_argument("--direction", choices=["A->B", "B->A"], default="A->B")
    p_cycle.set_defaults(func=cmd_recover_port_cycle)

    p_self = sub.add_parser("self-test", help="Run the full battery against an in-process mock bridge (no hardware required)")
    p_self.add_argument("--baud", type=int, default=FIRMWARE_DEFAULT_BAUD)
    p_self.add_argument("--out-json")
    p_self.add_argument("--out-csv")
    p_self.set_defaults(func=cmd_self_test)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted; closing ports.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
