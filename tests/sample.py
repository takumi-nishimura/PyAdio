import asyncio
import os
import logging
import sys
from unittest.mock import patch # For monkeypatching

# --- Adjust sys.path to find the pyadio module ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from pyadio.pyadio import PyAdio

logger = logging.getLogger(__name__)
# Configure logging to show debug messages from mocks if needed, and info for general flow
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')


# --- Mocking pyserial-asyncio Reader/Writer ---
class MockStreamReader:
    def __init__(self, data_lines_bytes, profiling_iterations, request_data_num_per_iteration):
        self.data_lines_bytes = data_lines_bytes
        self.current_line_index = 0
        self.profiling_iterations = profiling_iterations
        # request_data_num_per_iteration is not directly used here as get_buffer_data calls readline once
        self.total_reads_for_profile = self.profiling_iterations 
        self.reads_done_count = 0
        self.eof_reached_flag = False
        # logger.debug(f"MockStreamReader initialized for {self.total_reads_for_profile} total reads.")

    async def readline(self) -> bytes:
        if self.reads_done_count >= self.total_reads_for_profile or not self.data_lines_bytes:
            if not self.eof_reached_flag:
                # logger.debug(f"MockStreamReader: EOF or max reads ({self.reads_done_count}/{self.total_reads_for_profile}). Returning b''.")
                self.eof_reached_flag = True
            await asyncio.sleep(0.0000001) # Simulate tiny delay
            return b''
        
        line = self.data_lines_bytes[self.current_line_index % len(self.data_lines_bytes)]
        self.current_line_index += 1
        self.reads_done_count += 1
        # logger.debug(f"MockStreamReader readline call {self.reads_done_count}/{self.total_reads_for_profile}: returning {line!r}")
        await asyncio.sleep(0.0000001)  # Simulate very small I/O delay
        return line

class MockStreamWriter:
    def __init__(self):
        self.written_data = []
        self._closed = False

    def write(self, data: bytes):
        if self._closed:
            # Simulating a closed stream write attempt
            # raise OSError("Cannot write to a closed stream") # More specific asyncio exception might be ConnectionResetError
            raise ConnectionResetError("Connection closed")

        # logger.debug(f"MockStreamWriter write: {data!r}")
        self.written_data.append(data)

    async def drain(self):
        if self._closed:
            raise ConnectionResetError("Connection closed")
        # logger.debug("MockStreamWriter drain called.")
        await asyncio.sleep(0.0000001)  # Simulate small I/O delay

    def close(self):
        # logger.debug("MockStreamWriter close called.")
        self._closed = True

    async def wait_closed(self):
        # logger.debug("MockStreamWriter wait_closed called.")
        await asyncio.sleep(0) 

    def get_extra_info(self, name, default=None): 
        if name == 'socket': return None
        if name == 'peername': return 'mock_serial_peer'
        return default

async def main_async_profiling():
    PROFILING_ITERATIONS = 100 
    # Each iteration calls pyadio_dev.adc.get_buffer_data() once.
    # This internally calls reader.readline() once.

    # ADC_CH defaults are: conversion_speed=16, chunk_size=128, request_count=10
    # One line from readline (a "chunk" from device) contains 128 samples.
    mock_payload_length = 128 * 5 
    sample_hex_payload = ('1A2B3' * (mock_payload_length // 5 + 1))[:mock_payload_length]
    
    mock_data_lines = []
    for i in range(4): 
        mock_data_lines.append(f"*40{i:X}{sample_hex_payload}#".encode('ascii'))

    mock_reader = MockStreamReader(mock_data_lines, 
                                   profiling_iterations=PROFILING_ITERATIONS, 
                                   request_data_num_per_iteration=1) 
    mock_writer = MockStreamWriter()

    # Using a local function for the return_value of the patch,
    # as suggested by documentation for async mocks.
    async def mock_open_connection(*args, **kwargs):
        # logger.debug(f"mock_open_connection called with args: {args}, kwargs: {kwargs}")
        return mock_reader, mock_writer

    # Patch serial_asyncio.open_serial_connection
    # This ensures PyAdio uses our mock reader/writer.
    # Note: The target string for patch should be where the object is looked up.
    # If pyadio.pyadio imports serial_asyncio directly, then 'pyadio.pyadio.serial_asyncio.open_serial_connection'
    # might be needed if 'serial_asyncio' is used like 'serial_asyncio.open_serial_connection' in pyadio.py.
    # Assuming PyAdio imports 'import serial_asyncio' and calls 'serial_asyncio.open_serial_connection'.
    # If PyAdio does 'from serial_asyncio import open_serial_connection', target is 'pyadio.pyadio.open_serial_connection'.
    # Based on pyadio.py, it's 'import serial_asyncio', so 'serial_asyncio.open_serial_connection' is correct if
    # the tests/sample.py context can patch it before PyAdio module loads it, or if PyAdio refers to it via the module.
    # A safer bet is to patch it where it's used: 'pyadio.pyadio.serial_asyncio.open_serial_connection'
    # For simplicity now, assuming 'serial_asyncio.open_serial_connection' works if patch is active before PyAdio.connect()
    
    # The actual patch target should be where 'open_serial_connection' is referenced in the PyAdio module.
    # If PyAdio.py does 'import serial_asyncio', then it calls 'serial_asyncio.open_serial_connection'.
    # So we patch 'serial_asyncio.open_serial_connection' in the global context where PyAdio will find it.
    # However, if PyAdio.py does 'from serial_asyncio import open_serial_connection', then the patch target
    # must be 'pyadio.pyadio.open_serial_connection'.
    # Given the current pyadio.py structure, it's 'import serial_asyncio'.
    
    # To ensure the patch targets the correct object that PyAdio will use,
    # we patch it in the 'pyadio.pyadio' module's namespace.
    patch_target = 'pyadio.pyadio.serial_asyncio.open_serial_connection'
    if 'pyadio.pyadio' not in sys.modules:
        # If pyadio.pyadio hasn't been imported yet by something else,
        # then patching serial_asyncio globally might work, but it's less robust.
        # This indicates a potential structural issue or the need for careful import order.
        # For this test, we assume pyadio.pyadio will be loaded and use serial_asyncio.
        # The most common way to ensure patching works is to patch the name in the module *where it is used*.
        # So if pyadio.py calls serial_asyncio.open_serial_connection, we patch that specific reference.
        pass # Fallback to global serial_asyncio if pyadio.pyadio not loaded, but not ideal.

    with patch(patch_target, new_callable=lambda: mock_open_connection) as mock_connect_func:
        pyadio_dev = PyAdio(port="/dev/mockport") 
        try:
            await pyadio_dev.connect() 
        except Exception as e:
            logger.error(f"Error during pyadio_dev.connect: {e}")
            logger.error("Patch target might be incorrect or an error occurred in mock_open_connection setup.")
            return # Cannot proceed if connection fails

        if pyadio_dev.adc is None:
            logger.error("ADC not initialized after connect. Aborting profile.")
            return

        # logger.info(f"Starting profiling loop for {PROFILING_ITERATIONS} iterations...")
        actual_iterations = 0
        for i in range(PROFILING_ITERATIONS):
            actual_iterations = i + 1
            ch, data_list = await pyadio_dev.adc.get_buffer_data()
            if ch is None and data_list is None and mock_reader.eof_reached_flag:
                # logger.info(f"End of mock data stream confirmed by get_buffer_data at iteration {actual_iterations}.")
                break
        
        # logger.info(f"Profiling loop finished after {actual_iterations} iterations.")
        await pyadio_dev.close()

if __name__ == "__main__":
    if os.environ.get("PROFILING_MODE") == "true":
        # logger.info("Running in Profiling Mode (Async)...")
        # To ensure pyadio.pyadio is loaded before we try to patch its namespace members
        # we can do a preliminary import if necessary, though it's usually handled by Python's import system.
        # For the patch to work correctly, 'from pyadio.pyadio import PyAdio' above should ensure 'pyadio.pyadio' is loaded.
        asyncio.run(main_async_profiling())
        # logger.info("Profiling run completed.")
    else:
        logger.info("Not in profiling mode. Set PROFILING_MODE=true to profile.")

```
