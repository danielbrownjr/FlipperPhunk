"""Real serial-port session handling: open, identify, and safely tear down
the two USB-UART endpoints around the Flipper.

These are 3.3V TTL UART connections to the Flipper's GPIO header, NOT
RS-232 voltage-level connections -- see the top-level README "Safety"
section before wiring anything up.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Optional

try:
    import serial as pyserial
except ImportError:  # pragma: no cover - exercised only when pyserial missing
    pyserial = None


class PortOpenError(RuntimeError):
    pass


@dataclass
class PortSpec:
    device: str
    label: str  # "A" / "B" for logging/results


class SerialSession:
    """Opens Port A and Port B together, or not at all.

    Guardrail: the harness must not transmit on one port unless *both* ports
    opened successfully (task requirement: "avoid transmitting until both
    ports are opened successfully"). Use as a context manager so Ctrl+C /
    exceptions always close whatever was opened.
    """

    def __init__(
        self,
        port_a: PortSpec,
        port_b: PortSpec,
        baudrate: int,
        timeout: float = 0.3,
        mock: bool = False,
    ):
        self.port_a_spec = port_a
        self.port_b_spec = port_b
        self.baudrate = baudrate
        self.timeout = timeout
        self.mock = mock
        self.port_a = None
        self.port_b = None
        self._mock_bridge = None

    def open(self):
        if self.mock:
            from . import mockserial

            self.port_a, self.port_b, self._mock_bridge = mockserial.make_loopback_pair(
                baudrate=self.baudrate, timeout=self.timeout
            )
            print(
                f"[mock] Simulated bridge ready: A={self.port_a.name} "
                f"B={self.port_b.name} baud={self.baudrate}",
                file=sys.stderr,
            )
            return self

        if pyserial is None:
            raise PortOpenError(
                "pyserial is not installed. Run: pip install -r requirements.txt"
            )

        print(
            f"Opening Port A ({self.port_a_spec.device}) and Port B "
            f"({self.port_b_spec.device}) at {self.baudrate} baud, 8N1, "
            f"timeout={self.timeout}s ...",
            file=sys.stderr,
        )
        try:
            self.port_a = pyserial.Serial(
                self.port_a_spec.device,
                self.baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=self.timeout,
            )
        except Exception as exc:
            raise PortOpenError(f"Failed to open Port A {self.port_a_spec.device}: {exc}") from exc

        try:
            self.port_b = pyserial.Serial(
                self.port_b_spec.device,
                self.baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=self.timeout,
            )
        except Exception as exc:
            self.port_a.close()
            self.port_a = None
            raise PortOpenError(f"Failed to open Port B {self.port_b_spec.device}: {exc}") from exc

        if not (self.port_a.is_open and self.port_b.is_open):
            self.close()
            raise PortOpenError("One or both ports reported not open after opening")

        print(
            f"Both ports open: A={self.port_a_spec.device} B={self.port_b_spec.device}",
            file=sys.stderr,
        )
        return self

    def close(self) -> None:
        for attr in ("port_a", "port_b"):
            port = getattr(self, attr)
            if port is not None:
                try:
                    port.close()
                except Exception:
                    pass
        if self._mock_bridge is not None:
            self._mock_bridge.stop()

    def __enter__(self) -> "SerialSession":
        return self.open()

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def reopen(self, baudrate: Optional[int] = None) -> None:
        """Close and reopen both real ports, e.g. to re-apply a new baud rate."""
        if baudrate is not None:
            self.baudrate = baudrate
        self.close()
        self.open()
