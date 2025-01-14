import logging
from typing import Optional

from serial import Serial

from pyadio._adio import Adio
from pyadio.adc import ADC
from pyadio.utils import search_adio_port

logger = logging.getLogger(__name__)


class PyAdio:
    """
    PyAdio class for interfacing with an Adio device via a serial port.

    Attributes:
        adio (Adio): Instance of the Adio class.
        handle (Serial): Serial connection handle to the Adio device.
        adc (ADC): ADC instance for handling analog-to-digital conversion.

    Methods:
        __init__(port: Optional[str] = None, **kwargs) -> None:
            Initializes the PyAdio instance, sets up the serial connection, and initializes ADC.
        close() -> None:
            Closes the serial connection and logs the closure.
    """

    def __init__(self, port: Optional[str] = None, **kwargs) -> None:
        logger.info("Setup PyAdio.")

        if not port:
            port = search_adio_port()

        self.adio = Adio()
        self.handle = Serial(port, timeout=kwargs.get("timeout", 1))
        self.reset_device()
        self.adc = ADC(self.handle, self.adio)

    def __reset_device(self):
        self.handle.write("*F0000000#".encode())
        __response = self.handle.readline().decode().strip()
        if __response == "*OK#":
            logger.info("Completed device reset.")
        else:
            raise Exception(f"Failed to reset device. Response: {__response}")

    def reset_device(self):
        buffer_reset = False
        while not buffer_reset:
            print("...", end="", flush=True)
            response = self.handle.readline()
            if response == b"":
                buffer_reset = True
        self.__reset_device()

    def close(self):
        self.handle.close()
        logger.info("Closed PyAdio.")
