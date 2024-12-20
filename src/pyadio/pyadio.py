import logging
from typing import Optional

from serial import Serial

from pyadio._adio import Adio
from pyadio.adc import ADC
from pyadio.utils import search_adio_port

logger = logging.getLogger(__name__)


class PyAdio:
    def __init__(self, port: Optional[str] = None, **kwargs) -> None:
        logger.info("Setup PyAdio.")

        if not port:
            port = search_adio_port()

        self.adio = Adio()
        self.handle = Serial(port, timeout=kwargs.get("timeout", 1))
        self.adc = ADC(self.handle, self.adio)

    def close(self):
        self.handle.close()
        logger.info("Closed PyAdio.")
