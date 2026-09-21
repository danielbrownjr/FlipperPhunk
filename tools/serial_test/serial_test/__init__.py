"""Host-side serial stress-test harness for the FlipperPhunk RS-232 bridge.

Exercises the Flipper's two TTL UART paths (USART / "Side A" and LPUART /
"Side B") directly at 3.3V logic level, independent of the RS-232 level
shifter and Rev C.1 PCB hardware. See the package README for wiring,
usage, and limitations.
"""

__version__ = "0.1.0"
