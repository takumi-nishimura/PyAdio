import os
from typing import Optional

from serial.tools.list_ports import comports


def search_adio_port() -> Optional[str]:
    """
    Searches for an ADIO port connected to the system.

    This function scans through the available serial ports on the system and
    returns the device name of the first port that matches the criteria for
    an ADIO device. The criteria differ based on the operating system:

    - On POSIX systems (e.g., Linux, macOS), it looks for ports with "usbserial-FT" in the device name.
    - On Windows systems (nt), it looks for ports with "COM" in the device name.

    Returns:
        Optional[str]: The device name of the first matching ADIO port, or None if no matching port is found.
    """

    ports = comports()
    os_name = os.name

    for port in ports:
        if os_name == "posix":
            if "usbserial-FT" in port.device:
                return port.device

        elif os_name == "nt":
            if "COM" in port.device:
                return port.device
