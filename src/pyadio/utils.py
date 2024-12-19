import os
from typing import Optional

from serial.tools.list_ports import comports


def search_adio_port() -> Optional[str]:
    ports = comports()
    os_name = os.name

    for port in ports:
        if os_name == "posix":
            if "usbserial-FT" in port.device:
                return port.device

        elif os_name == "nt":
            if "COM" in port.device:
                return port.device
