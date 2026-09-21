"""Baud rates supported by the FlipperPhunk firmware.

This list is derived directly from ``kBaudRates`` in
``firmware/flipperphunk.c`` (the on-device setup-screen sweep) and must be
kept in sync with it. As of the Rev C.1 firmware baseline, the firmware list
and the bench-test requirement list are identical -- no gap to document.
"""

# Keep in the same order as firmware/flipperphunk.c: kBaudRates[].
FIRMWARE_BAUD_RATES = (
    1200,
    2400,
    4800,
    9600,
    19200,
    38400,
    57600,
    115200,
)

# Default index the firmware boots into (kBaudRates[3] == 9600).
FIRMWARE_DEFAULT_BAUD = FIRMWARE_BAUD_RATES[3]
