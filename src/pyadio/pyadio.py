import asyncio
import logging
from typing import Optional, Tuple

# Assuming pyserial-asyncio is installed and provides these
import serial_asyncio 
# from serial import Serial # No longer directly used for instantiation here

from pyadio._adio import Adio
from pyadio.adc import ADC
from pyadio.utils import search_adio_port

logger = logging.getLogger(__name__)


class PyAdio:
    """
    PyAdio class for interfacing with an Adio device via an asynchronous serial port.
    This class handles the serial connection and provides access to ADC functionalities.

    To use this class:
    1. Instantiate `PyAdio`: `pyadio_dev = PyAdio(port="/dev/ttyUSB0")`
    2. Establish connection: `await pyadio_dev.connect()`
    3. Access ADC: `adc = pyadio_dev.adc`
    4. Configure and use ADC: `await adc.set_channel(...)`, `await adc.get_buffer_data()`
    5. Close connection: `await pyadio_dev.close()`

    Attributes:
        port_name (str): The name of the serial port (e.g., "/dev/ttyUSB0", "COM3").
                         Can be auto-detected if not provided in `__init__`.
        serial_kwargs (dict): Keyword arguments passed to `serial_asyncio.open_serial_connection`
                              (e.g., `baudrate`, `timeout`).
        adio (Adio): Internal instance managing device-specific configurations (like `ADC_CH_NUM`).
        reader (Optional[asyncio.StreamReader]): The stream reader for async serial communication.
                                                 Initialized after `await self.connect()` is called.
        writer (Optional[asyncio.StreamWriter]): The stream writer for async serial communication.
                                                 Initialized after `await self.connect()` is called.
        adc (Optional[ADC]): The ADC controller instance, providing access to ADC functions.
                             Initialized after `await self.connect()` is called.
    """

    def __init__(self, port: Optional[str] = None, **kwargs) -> None:
        """
        Initializes the PyAdio class. Does not establish connection yet.
        Call `await self.connect()` to open the serial port and initialize ADC.

        Args:
            port (Optional[str]): The serial port name. If None, attempts to auto-detect.
            **kwargs: Additional keyword arguments for `serial_asyncio.open_serial_connection`
                      (e.g., `baudrate=115200`). Note: `timeout` in `kwargs` is used
                      by `serial_asyncio.open_serial_connection` for the underlying serial port,
                      but actual read/write operation timeouts are handled by `asyncio.wait_for`
                      within the methods.
        """
        logger.info("PyAdio instance created. Call connect() to establish connection.")
        self.port_name = port if port else search_adio_port()
        self.serial_kwargs = kwargs
        self.adio = Adio() # Manages ADC_CH_NUM etc.
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.adc: Optional[ADC] = None

    async def connect(self) -> None:
        """
        Establishes the asynchronous serial connection using `serial_asyncio.open_serial_connection`,
        resets the Adio device, and initializes the ADC controller.
        This method must be `await`ed.
        """
        logger.info(f"Connecting to PyAdio on port {self.port_name}...")
        if not self.port_name:
            raise ValueError("Serial port not specified or found.")

        self.reader, self.writer = await serial_asyncio.open_serial_connection(
            url=self.port_name, 
            baudrate=self.serial_kwargs.get("baudrate", 115200), # Default or from kwargs
            timeout=self.serial_kwargs.get("timeout", 1) # open_serial_connection might not use timeout directly this way
                                                          # It's more for the Serial object it creates internally.
                                                          # Actual read timeouts are handled by await reader.read...()
        )
        logger.info(f"Connected to PyAdio on {self.port_name}.")
        await self._reset_device()
        self.adc = ADC(self.reader, self.writer, self.adio)


    async def _reset_device_sequence(self):
        """
        (Async) Sends the reset command sequence to the Adio device.
        This method is part of the connection process and must be `await`ed.
        """
        if not self.writer or not self.reader:
            logger.error("Writer/Reader not available for _reset_device_sequence. Connection not established.")
            return

        self.writer.write("*f0000000#".encode())
        await self.writer.drain()
        try:
            # Add a timeout for readline to prevent indefinite blocking
            response_bytes = await asyncio.wait_for(self.reader.readline(), timeout=2.0)
            __response = response_bytes.decode().strip()
            if __response == "*OK#":
                logger.info("Completed device reset.")
            else:
                raise Exception(f"Failed to reset device. Response: {__response}")
        except asyncio.TimeoutError:
            raise Exception("Timeout waiting for reset response from device.")


    async def _reset_device(self):
        """
        (Async) Clears any pre-existing data from the serial port's read buffer and then
        sends the reset command sequence to the Adio device.
        This method is part of the connection process and must be `await`ed.
        """
        if not self.reader:
            logger.error("Reader not available for _reset_device. Connection not established.")
            return
            
        logger.info("Attempting to clear pre-reset buffer...")
        buffer_reset = False
        try:
            while not buffer_reset:
                # Non-blocking read with timeout to clear buffer
                response = await asyncio.wait_for(self.reader.readuntil(b'\n'), timeout=0.1) 
                if response == b"": # Or some other condition indicating buffer is clear or line break found
                    buffer_reset = True
                # Log bytes received during buffer clearing if necessary
                # logger.debug(f"Buffer clear read: {response!r}")
        except asyncio.TimeoutError:
            # This is expected if the buffer is empty or doesn't send newlines quickly
            logger.info("Buffer clearing timed out, proceeding with reset (this is often normal).")
            buffer_reset = True 
        except Exception as e:
            logger.warning(f"Error during buffer clearing: {e}, proceeding with reset.")
            buffer_reset = True # Proceed anyway

        await self._reset_device_sequence()

    async def close(self):
        """
        (Async) Closes the asynchronous serial connection.
        This method should be `await`ed to ensure proper closure, especially if `writer.wait_closed()` is used.
        """
        if self.writer:
            logger.info(f"Closing PyAdio connection to {self.port_name}...")
            self.writer.close()
            try:
                await self.writer.wait_closed() # New in Python 3.7+
            except AttributeError: # For older Python versions or if not available on all transports
                pass # writer.close() is usually sufficient to initiate closure
            logger.info(f"Closed PyAdio connection to {self.port_name}.")
        else:
            logger.info("PyAdio connection was not open or already closed.")
