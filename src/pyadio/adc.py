import asyncio
import logging
# from concurrent.futures import ThreadPoolExecutor # Replaced by asyncio tasks
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel
# from serial import Serial # Replaced by asyncio streams

logger = logging.getLogger(__name__)


class ADC_CH(BaseModel):
    """
    Represents the configuration and state for a single ADC channel.
    """
    channel: int
    """The ADC channel number (0-indexed)."""

    conversion_speed: int
    """
    The speed of ADC conversion in kilosamples per second (ksps).
    Determines the sampling rate. Higher values mean higher temporal resolution
    but also generate more data. Must be chosen carefully to avoid aliasing
    (Nyquist theorem: speed > 2 * max_signal_frequency).
    Allowed values are typically 1, 2, 4, 8, 16, 32, 64, 128, 256 ksps.
    """

    chunk_size: int
    """
    The number of samples grouped together by the device for this channel
    before considering a data block (chunk) complete. This affects data
    transfer granularity. Larger chunk_size can improve communication
    efficiency but may increase latency for the first sample in a chunk.
    """

    request_count: int
    """
    The number of chunks (each of `chunk_size` samples) that the host requests
    from the device's buffer in a single `_request_buffer_data` call.
    This influences the total data size per explicit request (`chunk_size * request_count`).
    Also used with `re_request_threshold` to determine background data refresh points.
    """

    input_voltage: float
    """
    The input voltage range setting for the channel (e.g., 5.0 for ±5V).
    This value is used in scaling the raw ADC readings to voltage values.
    """

    re_request_threshold: float = 0.8
    """
    A float between 0.0 and 1.0 representing the threshold for re-requesting data.
    When `recv_chunk_count` reaches `request_count * re_request_threshold`,
    a background task is typically triggered to request more data for the channel.
    Default is 0.8 (80%).
    """

    recv_chunk_count: int = 0
    """
    Counter for the number of chunks received from the device for this channel
    since the last main data request or reset of this counter. Used with
    `re_request_threshold` to trigger data re-requests.
    """

    # model_config = {"arbitrary_types_allowed": True} # If asyncio.Task were stored here (Pydantic V2)
    # For Pydantic V1, if asyncio.Task was needed, one might use:
    # class Config:
    #     arbitrary_types_allowed = True


class ADC:
    """
    Controls Analog-to-Digital Converter (ADC) functionalities of the Adio device
    using an asynchronous interface.

    This class is typically instantiated and used via the `PyAdio` class.
    All I/O operations are asynchronous and must be `await`ed.
    """
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, adio) -> None:
        """
        Initializes the ADC controller with asynchronous stream reader and writer.
        This method is synchronous and sets up the initial state. Async I/O methods
        must be `await`ed by the caller.

        Args:
            reader (asyncio.StreamReader): The stream reader for serial communication.
            writer (asyncio.StreamWriter): The stream writer for serial communication.
            adio: An object providing ADC configuration, typically an instance of `pyadio._adio.Adio`
                  (used to get `adio.ADC_CH_NUM`).
        """
        logger.info("ADC Initialize (async).")

        self.reader = reader
        self.writer = writer
        self.active_request_tasks: Dict[int, asyncio.Task] = {} # Stores active re-request tasks per channel


        self.settings = [
            ADC_CH(
                channel=ch,
                conversion_speed=16,      # Default to 16 ksps
                chunk_size=128,           # Default to 128 samples per chunk
                request_count=10,         # Default to 10 chunks (total 1280 samples)
                input_voltage=5.0,        # Default input voltage
                re_request_threshold=0.8  # Default re-request threshold
            )
            for ch in range(adio.ADC_CH_NUM)
        ]

    async def _set_conversion_speed(
        self,
        channel: int,
        speed: Literal[1, 2, 4, 8, 16, 32, 64, 128, 256],
    ):
        """
        (Async) Sets the conversion speed for a group of ADC channels.
        The Adio device groups channels (e.g., 0-7, 8-15) for speed settings.
        This method must be `await`ed.

        Args:
            channel (int): The first channel number of the group to configure (e.g., 0 or 8).
                           The setting applies to this channel and the next 7 (or fewer if at the end).
            speed (Literal[...]): The desired conversion speed in ksps for the channel group.
        
        Raises:
            ValueError: If an invalid speed is provided.
            Exception: If the command fails or a timeout occurs reading the response.
        """
        __channels = channel // 8 # Determines the channel group (0 for ch 0-7, 1 for ch 8-15 etc.)
        speed_map = {
            1: "0000", 2: "0001", 4: "0002", 8: "0003",
            16: "0004", 32: "0005", 64: "0006", 128: "0007", 256: "0008"
        }
        __data = speed_map.get(speed)
        if __data is None:
            raise ValueError(f"Invalid conversion speed: {speed}")

        __command = f"*00{__channels}0{__data}#"
        self.writer.write(__command.encode())
        await self.writer.drain()

        try:
            response_bytes = await asyncio.wait_for(self.reader.readline(), timeout=2.0)
            __response = response_bytes.decode().strip()
        except asyncio.TimeoutError:
            raise Exception(f"Timeout setting conversion speed for channels {'0~7' if __channels == 0 else '8~15'}")

        if __response == "*OK#":
            logger.info(
                f"Conversion speed successfully set to {speed}ksps for channels {'0~7' if __channels == 0 else '8~15'}."
            )
            idx_range = range(8) if __channels == 0 else range(8, 16)
            for ch_idx in idx_range:
                if ch_idx < len(self.settings): # ensure index is within bounds
                    self.settings[ch_idx].conversion_speed = speed
        else:
            raise Exception(
                f"Cannot set conversion speed for channels {'0~7' if __channels == 0 else '8~15'}. Response: {__response}"
            )

    async def _set_chunk_size(self, channel: int, chunk_size: int):
        """
        (Async) Sets the chunk size (number of samples per chunk) for a specific ADC channel.
        This method must be `await`ed.

        Args:
            channel (int): The channel number to configure.
            chunk_size (int): The desired chunk size (number of samples). Max value is 65535.
        
        Raises:
            Exception: If the command fails or a timeout occurs reading the response.
        """
        if chunk_size >= 0x8000: # Max is 0xFFFF (65535), warn if at/above half of that.
            logger.warning(
                f"Setting a very large chunk_size ({chunk_size}) for channel {channel}. "
                "Ensure the device supports this and consider memory/latency implications."
            )
        __command = f"*10{channel:X}0{format(chunk_size, '04X')}#"
        self.writer.write(__command.encode())
        await self.writer.drain()
        
        try:
            response_bytes = await asyncio.wait_for(self.reader.readline(), timeout=2.0)
            __response = response_bytes.decode().strip()
        except asyncio.TimeoutError:
            raise Exception(f"Timeout setting chunk size for channel {channel}")

        if __response == "*OK#":
            logger.info(
                f"Chunk size successfully set to {chunk_size} for channel {channel}."
            )
            self.settings[channel].chunk_size = chunk_size
        else:
            raise Exception(f"Cannot set chunk size for channel {channel}. Response: {__response}")

    # This method doesn't perform I/O, so it remains synchronous
    def _set_request_count(self, channel: int, request_count: int):
        """
        Sets the number of chunks to request for a channel. This is a synchronous method
        as it only updates internal settings and does not perform I/O.

        Args:
            channel (int): The channel number.
            request_count (int): The number of chunks. Max value for device command is 65535.
        """
        self.settings[channel].request_count = request_count

    async def _set_input_voltage(
        self,
        channel: int,
        input_voltage: Literal[
            "10", "5", "1.25", "0.625", "0.3125", "0.15625"
        ],
    ):
        """
        (Async) Sets the input voltage range for a specified ADC channel.
        This method must be `await`ed.

        Args:
            channel (int): The channel number to configure.
            input_voltage (Literal[...]): The desired input voltage range string (e.g., "5" for ±5V).
        
        Raises:
            ValueError: If an invalid input_voltage string is provided.
            Exception: If the command fails or a timeout occurs reading the response.
        """
        voltage_map = {
            "10": "0000", "5": "0001", "1.25": "0002",
            "0.3125": "0003", "0.15625": "0004" 
        }
        # Correcting a potential typo from original: "0.625" was missing, "0.3125" listed twice.
        # Assuming "0.625" maps to a unique value or was intended to be "0.3125".
        # For now, strictly following the provided map. If "0.625" is valid, its hex code is needed.
        # The prompt's original code had "0.3125" mapped to "0003".
        if input_voltage == "0.625": # If 0.625V is a valid distinct option
             # Placeholder: __data = "XXXX" # Needs correct hex if different from 0.3125V
             # For now, let's assume it might be a typo and it should have been one of the others or shares a code.
             # If strictly following the list: "10", "5", "1.25", "0.3125", "0.15625"
             # "0.625" is not in the original map keys.
             pass # Or raise error if it's an unmapped value. The original code would hit the else.


        __data = voltage_map.get(str(input_voltage))
        if __data is None:
             # Handle cases like "0.625" if not in map or raise error
            raise ValueError(f"Invalid input voltage string: {input_voltage}")


        __command = f"*50{format(channel, 'X')}0{__data}#"
        self.writer.write(__command.encode())
        await self.writer.drain()

        try:
            response_bytes = await asyncio.wait_for(self.reader.readline(), timeout=2.0)
            __response = response_bytes.decode().strip()
        except asyncio.TimeoutError:
            raise Exception(f"Timeout setting input voltage for channel {channel}")

        if __response == "*OK#":
            logger.info(
                f"Input voltage successfully set to {input_voltage}V for channel {channel}."
            )
            self.settings[channel].input_voltage = float(input_voltage)
        else:
            raise Exception(f"Cannot set input voltage for channel {channel}. Response: {__response}")

    async def set_channel(
        self,
        channel: int,
        conversion_speed: Literal[1, 2, 4, 8, 16, 32, 64, 128, 256],
        chunk_size: int = 128,
        request_count: int = 100,
        input_voltage: Literal[
            "10", "5", "1.25", "0.625", "0.3125", "0.15625"
        ] = "5",
    ):
        """
        Configures an ADC channel with the specified parameters.

        Args:
            channel (int): The ADC channel to configure (0-indexed).
            conversion_speed (Literal[1, ..., 256]): ADC conversion speed in ksps.
                Higher speeds provide better temporal resolution but increase data volume.
                Choose based on signal characteristics (Nyquist theorem) and device limits.
            chunk_size (int, optional): Number of samples per data chunk from the device.
                Defaults to 128. Larger chunks can be more efficient for bulk transfer
                but may increase latency for the first sample in a chunk. Max 65535.
            request_count (int, optional): Number of chunks to request in one go.
                Defaults to 100 (Note: ADC_CH default is 10, this method's default is 100.
                Consider aligning these or relying on ADC_CH defaults setup in __init__).
                Total samples per request = chunk_size * request_count. Max 65535.
            input_voltage (Literal[...], optional): Input voltage range setting. Defaults to "5" (±5V).
                Ensure this matches the expected signal amplitude for correct scaling.

        Note on `request_count` default:
            The default value of `request_count=100` in this method signature differs from the
            default set in `ADC_CH` (which is 10). When calling this method, if `request_count`
            is not specified, it will use 100, overriding the `ADC_CH` default for this specific call's
            `_set_request_count` update. This might be intentional for manual `set_channel` calls
            to use a larger default request count than the initial one.

        Performance Considerations:
            - `conversion_speed`: Directly impacts data rate. Ensure the communication link
              and processing can handle the generated data volume.
            - `chunk_size` vs. `request_count`:
                - Many small chunks/requests (e.g., small `chunk_size`, small `request_count`, frequent calls)
                  can lead to high protocol overhead.
                - Fewer large chunks/requests (e.g., large `chunk_size`, moderate `request_count`)
                  are generally more efficient for continuous data streaming.
            - Device Buffers: The device has finite internal buffers. Requesting data significantly
              exceeding available buffered data might lead to incomplete transfers or errors.
              (Device-specific behavior is unknown without documentation).
        """
        # Default for request_count in signature (100) will override ADC_CH default (10) if not provided by caller.
        # This is fine, as it means a direct call to set_channel can use a different default.
        await self._set_conversion_speed(channel, conversion_speed)
        await self._set_chunk_size(channel, chunk_size)
        self._set_request_count(channel, request_count) # This is synchronous, updates the setting
        await self._set_input_voltage(channel, input_voltage)

    async def start_memory_acquisition(self):
        """
        (Async) Initiates the memory acquisition process on the Adio device.
        This typically prepares the device to start sampling according to the
        configured channel settings. This method must be `await`ed.

        Raises:
            Exception: If the command fails or a timeout occurs reading the response.
        """
        __command = "*40020000#"
        self.writer.write(__command.encode())
        await self.writer.drain()

        try:
            response_bytes = await asyncio.wait_for(self.reader.readline(), timeout=2.0)
            __response = response_bytes.decode().strip()
        except asyncio.TimeoutError:
            raise Exception("Timeout starting memory acquisition.")
            
        if __response == "*OK#":
            logger.info("Memory acquisition started successfully.")
        else:
            raise Exception(f"Cannot start memory acquisition. Response: {__response}")

    async def _request_buffer_data(self, ch: int, request_count: int):
        """
        (Async) Sends a command to the Adio device to request a specified number of
        data chunks from its buffer for a given channel.
        This method must be `await`ed. It does not typically expect a direct "*OK#" response
        from the device for this specific command.

        Args:
            ch (int): The channel number from which to request data.
            request_count (int): The number of data chunks to request. Max value for device command is 65535.
        """
        if request_count >= 0x8000: # Max is 0xFFFF (65535 for request_count-1), warn if at/above half.
            logger.warning(
                f"Requesting a very large number of chunks ({request_count}) for channel {ch}. "
                "Ensure the device can handle this (total samples = chunk_size * request_count)."
            )
        __command = f"*40{ch:X}1{format(request_count-1, '04X')}#"
        self.writer.write(__command.encode())
        await self.writer.drain()
        # This command typically does not send a response like "*OK#"

    async def request_buffer_data(self, ch: int):
        """
        (Async) Requests buffer data for a specific channel using its current `request_count` setting.
        This method must be `await`ed.
        
        If non-blocking "fire-and-forget" behavior is desired (e.g., for background refresh
        as used in `get_buffer_data`), the caller should wrap this call with `asyncio.create_task()`.

        Args:
            ch (int): The channel number for which to request buffer data.
        """
        await self._request_buffer_data(ch, self.settings[ch].request_count)

    # Note: The previous `request_buffer_data_thr` method (which used ThreadPoolExecutor)
    # has been removed. Asynchronous tasks should now be created using `asyncio.create_task()`,
    # for example: `asyncio.create_task(adc_instance.request_buffer_data(channel_number))`.
    # This is handled internally by `get_buffer_data` for its re-request logic.

    def _convert_data(self, data: str, input_voltage: float) -> List[float]:
        """
        Converts a hexadecimal string of ADC readings into a list of voltage values.
        This is a synchronous helper method used internally by `_parse_data`.

        Args:
            data (str): A string of concatenated 5-character hexadecimal ADC readings.
            input_voltage (float): The reference input voltage for scaling.

        Returns:
            List[float]: A list of converted voltage values.
        """
        MAX_ADC_VALUE = 524288
        def adjust_adc_value(val: int) -> int:
            if val >= MAX_ADC_VALUE:
                return val - MAX_ADC_VALUE * 2
            return val
        return [
            (adjust_adc_value(int(data[i : i + 5], 16)) / MAX_ADC_VALUE) * input_voltage
            for i in range(0, len(data), 5)
        ]

    def _parse_data(self, data: bytes) -> Optional[Tuple[int, List[float]]]:
        """
        Parses a raw byte string received from the Adio device.
        Expected format: `*40{channel_hex}{hex_payload}#`
        This is a synchronous helper method used internally by `_get_buffer_data`.

        Args:
            data (bytes): The raw byte string from the device.

        Returns:
            Optional[Tuple[int, List[float]]]: A tuple containing the channel number
            and a list of converted voltage values if parsing is successful, otherwise None.
        """
        line = data.decode().strip()
        if line.startswith("*40"):
            try:
                ch = int(line[3], 16)
                # Ensure channel index is valid before accessing settings
                if 0 <= ch < len(self.settings):
                    # The actual data payload is between the channel and the final '#'
                    hex_payload = line[4:-1]
                    if not hex_payload: # Check for empty payload after slicing
                        logger.error(f"Empty data payload for channel {ch} in line: {line!r}")
                        return None
                    converted_data = self._convert_data(
                        hex_payload, input_voltage=self.settings[ch].input_voltage
                    )
                    return ch, converted_data
                else:
                    logger.error(f"Invalid channel number parsed: {ch} (out of range 0-{len(self.settings)-1}) in line: {line!r}")
                    return None
            except ValueError: # Handles int(line[3], 16) if channel char is not hex
                logger.error(f"Failed to parse channel number from line: {line!r}")
                return None
            except IndexError: # Handles cases where line[3] or line[4:-1] might be out of bounds
                logger.error(f"Line format error (too short for parsing): {line!r}")
                return None

        logger.error(f"Cannot parse data (unexpected format or prefix): {line!r}")
        return None

    async def _get_buffer_data(self) -> Tuple[Optional[int], Optional[List[float]]]:
        """
        (Async) Retrieves a line of data from the serial reader, then parses it.
        This method must be `await`ed. It is used internally by `get_buffer_data`.

        Returns:
            Tuple[Optional[int], Optional[List[float]]]: Parsed channel and data, or (None, None) on error/timeout.
        """
        try:
            # Add a reasonable timeout for readline.
            response_bytes = await asyncio.wait_for(self.reader.readline(), timeout=5.0) 
        except asyncio.TimeoutError:
            logger.warning("Timeout waiting for buffer data from device.")
            return None, None
        except Exception as e: # Catch other potential errors during read
            logger.error(f"Error reading buffer data: {e}")
            return None, None

        __parsed = self._parse_data(response_bytes)
        if __parsed is not None:
            return __parsed[0], __parsed[1]
        # Error already logged by _parse_data if parsing failed
        # logger.error(f"Cannot get buffer data (parsing failed for response): {response_bytes!r}") # Redundant if _parse_data logs
        return None, None

    async def get_buffer_data(self) -> Tuple[Optional[int], Optional[List[float]]]:
        """
        (Async) Retrieves and parses a data packet from the Adio device for any channel.
        This is the primary method for fetching ADC data. This method must be `await`ed.

        It handles logic for automatically re-requesting more data in the background
        when the received chunk count for a channel nears its `request_count` goal
        (based on `re_request_threshold`). The background re-request is initiated
        using `asyncio.create_task()`. Management of these background tasks (e.g.,
        preventing duplicates, error handling) is handled internally.

        Returns:
            Tuple[Optional[int], Optional[List[float]]]: A tuple containing the channel number
            and a list of converted voltage values if data is successfully received and parsed.
            Returns (None, None) if a timeout occurs, an error happens during read/parse,
            or if the parsed channel is invalid.
        """
        ch, data = await self._get_buffer_data()

        if ch is not None:
            # Ensure channel index is valid before accessing settings
            if 0 <= ch < len(self.settings):
                self.settings[ch].recv_chunk_count += 1

                if (
                    self.settings[ch].recv_chunk_count
                    >= self.settings[ch].request_count * self.settings[ch].re_request_threshold # Use configurable threshold
                ):
                    self.settings[ch].recv_chunk_count = 0
                    
                    # Check if a task for this channel is already running
                    existing_task = self.active_request_tasks.get(ch)
                    if existing_task and not existing_task.done():
                        logger.debug(f"Data re-request task for channel {ch} is already running.")
                    else:
                        logger.debug(f"Creating background data re-request task for channel {ch}.")
                        task = asyncio.create_task(self.request_buffer_data(ch))
                        self.active_request_tasks[ch] = task
                        task.add_done_callback(self._handle_request_task_completion(ch))
                return ch, data
            else:
                logger.error(f"Received data for invalid channel number: {ch}")
                return None, None # Treat as no valid data if channel is out of bounds

        return None, None

    def _handle_request_task_completion(self, channel_num: int):
        """
        Returns a callback function to handle the completion of a background
        `request_buffer_data` task. This callback is added to tasks created by
        `asyncio.create_task` in `get_buffer_data`.

        The returned callback logs any exceptions from the task and removes the
        task from the `self.active_request_tasks` dictionary, ensuring that
        only genuinely active tasks are tracked.

        Args:
            channel_num (int): The channel number for which the task was created.

        Returns:
            Callable[[asyncio.Task], None]: The callback function to be used with `task.add_done_callback()`.
        """
        def callback(task: asyncio.Task):
            try:
                # Check if the task raised an exception
                exception = task.exception()
                if exception:
                    logger.error(f"Background data re-request task for channel {channel_num} failed: {exception}")
                else:
                    logger.debug(f"Background data re-request task for channel {channel_num} completed successfully.")
            finally:
                # Remove the task from the active list for that channel
                if channel_num in self.active_request_tasks and self.active_request_tasks[channel_num] is task:
                    del self.active_request_tasks[channel_num]
                else: # Should not happen if logic is correct
                    logger.warning(f"Task for channel {channel_num} not found or mismatch in active tasks dict during completion.")
        return callback
