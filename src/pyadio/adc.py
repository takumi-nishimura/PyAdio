import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel
from serial import Serial

logger = logging.getLogger(__name__)


class ADC_CH(BaseModel):
    channel: int
    conversion_speed: int
    chunk_size: int
    request_count: int
    input_voltage: float

    recv_chunk_count: int = 0


class ADC:
    def __init__(self, handle: Serial, adio) -> None:
        logger.info("ADC Initialize.")

        self.handle = handle
        self.request_buffer_executor = ThreadPoolExecutor(max_workers=6)

        self.settings = [
            ADC_CH(
                channel=ch,
                conversion_speed=1,
                chunk_size=1,
                request_count=100,
                input_voltage=5.0,
            )
            for ch in range(adio.ADC_CH_NUM)
        ]

    def _set_conversion_speed(
        self,
        channel: int,
        speed: Literal[1, 2, 4, 8, 16, 32, 64, 128, 256],
    ):
        """
        Sets the conversion speed for the specified ADC channels.
        Args:
            channels (Literal[0, 1]): The channel group to set the speed for.
                                      0 for channels 0~7, 1 for channels 8~15.
            speed (Literal[1, 2, 4, 8, 16, 32, 64, 128, 256]): The conversion speed in ksps (kilosamples per second).
        Raises:
            ValueError: If an invalid speed or channel is provided.
        Example:
            >>> adc = ADC()
            >>> adc.set_conversion_speed(0, 16)
            True
        """

        __channels = channel // len(self.settings)

        if speed == 1:
            __data = "0000"
        elif speed == 2:
            __data = "0001"
        elif speed == 4:
            __data = "0002"
        elif speed == 8:
            __data = "0003"
        elif speed == 16:
            __data = "0004"
        elif speed == 32:
            __data = "0005"
        elif speed == 64:
            __data = "0006"
        elif speed == 128:
            __data = "0007"
        elif speed == 256:
            __data = "0008"

        __command = f"*00{__channels}0{__data}#"
        self.handle.write(__command.encode())

        __response = self.handle.readline().decode().strip()
        if __response == "*OK#":
            logger.info(
                f"Conversion speed successfully set to {speed}ksps for channels {'0~7' if __channels == 0 else '8~15'}."
            )
            if channel == 0:
                for ch in range(8):
                    self.settings[ch].conversion_speed = speed
            else:
                for ch in range(8):
                    self.settings[ch + 8].conversion_speed = speed
        else:
            raise Exception(
                f"Cannot set conversion speed for channels {'0~7' if __channels == 0 else '8~15'}"
            )

    def _set_chunk_size(self, channel: int, chunk_size: int):
        """
        Sets the chunk size for a specified channel.
        This method sends a command to set the chunk size for the given channel
        and updates the settings if the command is successful.
        Args:
            ch (int): The channel number for which the chunk size is to be set.
            chunk_size (int): The desired chunk size to be set for the channel.
        Raises:
            Exception: If the chunk size cannot be set for the specified channel.
        """

        __command = f"*10{channel:X}0{format(chunk_size, '04X')}#"
        self.handle.write(__command.encode())

        __response = self.handle.readline().decode().strip()
        if __response == "*OK#":
            logger.info(
                f"Chunk size successfully set to {chunk_size} for channel {channel}."
            )
            self.settings[channel].chunk_size = chunk_size
        else:
            raise Exception(f"Cannot set chunk size for channel {channel}.")

    def _set_request_count(self, channel: int, request_count: int):
        self.settings[channel].request_count = request_count

    def _set_input_voltage(
        self,
        channel: int,
        input_voltage: Literal[
            "10", "5", "1.25", "0.625", "0.3125", "0.15625"
        ],
    ):
        """Sets the input voltage for a specified channel.

        Args:
            channel (int): channel number.
            voltage (float): input voltage range.
                             ±0.15625V, ±0.3125V, ±0.625V, ±1.25V, ±5V, ±10V.
        """

        if input_voltage == "10":
            __data = "0000"
        elif input_voltage == "5":
            __data = "0001"
        elif input_voltage == "1.25":
            __data = "0002"
        elif input_voltage == "0.3125":
            __data = "0003"
        elif input_voltage == "0.15625":
            __data = "0004"

        __command = f"*50{format(channel, 'X')}0{__data}#"
        self.handle.write(__command.encode())

        __response = self.handle.readline().decode().strip()
        if __response == "*OK#":
            logger.info(
                f"Input voltage successfully set to {input_voltage}V for channel {channel}."
            )
            self.settings[channel].input_voltage = float(input_voltage)
        else:
            raise Exception(f"Cannot set input voltage for channel {channel}.")

    def set_channel(
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
        Configures the ADC channel with the specified parameters.
        Args:
            channel (int): The ADC channel to configure.
            conversion_speed (Literal[1, 2, 4, 8, 16, 32, 64, 128, 256]): The speed of the ADC conversion.
            chunk_size (int, optional): The size of data chunks to process. Defaults to 128.
            request_count (int, optional): The number of requests to process. Defaults to 100.
            input_voltage (Literal["10", "5", "1.25", "0.625", "0.3125", "0.15625"], optional): The input voltage range. Defaults to "5".
        Returns:
            None
        """

        self._set_conversion_speed(channel, conversion_speed)
        self._set_chunk_size(channel, chunk_size)
        self._set_request_count(channel, request_count)
        self._set_input_voltage(channel, input_voltage)

    def start_memory_acquisition(self):
        """
        Initiates the memory acquisition process by sending a specific command to the device.
        This method sends the command "*40020000#" to the device through the handle's write method.
        It then reads the response from the device. If the response is "*OK#", it logs a success message.
        Otherwise, it raises an exception indicating that the memory acquisition could not be started.
        Raises:
            Exception: If the response from the device is not "*OK#".
        Logs:
            Info: If the memory acquisition starts successfully.
        """

        __command = "*40020000#"
        self.handle.write(__command.encode())

        __response = self.handle.readline().decode().strip()
        if __response == "*OK#":
            logger.info("Memory acquisition started successfully.")
        else:
            raise Exception("Cannot start memory acquisition.")

    def _request_buffer_data(self, ch: int, request_count: int):
        """
        Requests buffer data from the ADC for a specific channel.
        This method sends a command to the ADC to request a specified number of data points
        from the buffer of a given channel.
        Args:
            ch (int): The channel number from which to request data.
            request_count (int): The number of data points to request from the buffer.
        """

        __command = f"*40{ch:X}1{format(request_count-1, '04X')}#"
        self.handle.write(__command.encode())

    def request_buffer_data(self, ch: int):
        """
        Request buffer data for a specific channel.
        This method requests buffer data for the specified channel by calling
        the internal method `_request_buffer_data` with the channel number and
        the request count from the settings.
        Args:
            ch (int): The channel number for which to request buffer data.
        """

        self._request_buffer_data(ch, self.settings[ch].request_count)

    def request_buffer_data_thr(self, ch: int):
        """
        Requests buffer data for a specific channel in a separate thread.
        Args:
            ch (int): The channel number for which to request buffer data.
        This method submits a task to the request_buffer_executor to call the
        _request_buffer_data method with the specified channel and its corresponding
        request count from the settings.
        """

        self.request_buffer_executor.submit(
            self._request_buffer_data, ch, self.settings[ch].request_count
        )

    def _convert_data(self, data: str, input_voltage: float) -> List[float]:
        """
        Convert hexadecimal string data to a list of floating-point values representing voltages.
        Args:
            data (str): A string of hexadecimal values.
            input_voltage (float): The input voltage reference value.
        Returns:
            List[float]: A list of converted floating-point voltage values.
        Notes:
            - The input data is expected to be a string where each 5-character segment represents a hexadecimal value.
            - The maximum ADC value is 524288. If the converted integer value is greater than or equal to this,
              it is adjusted by subtracting twice the maximum ADC value to handle negative values.
            - The final voltage values are scaled by the input voltage reference.
        """

        MAX_ADC_VALUE = 524288
        __convert_data = []
        for i in range(0, len(data), 5):
            __data = int(data[i : i + 5], 16)
            if __data >= MAX_ADC_VALUE:
                __data -= MAX_ADC_VALUE * 2
            __convert_data.append((__data / MAX_ADC_VALUE) * input_voltage)
        return __convert_data

    def _parse_data(self, data: bytes) -> Optional[Tuple[int, List[float]]]:
        """
        Parses the given byte data and extracts channel information and converted data.
        Args:
            data (bytes): The byte data to be parsed.
        Returns:
            Optional[Tuple[int, List[float]]]: A tuple containing the channel number and a list of converted data values if parsing is successful, otherwise None.
        """

        line = data.decode().strip()
        if line.startswith("*40"):
            ch = int(line[3], 16)
            converted_data = self._convert_data(
                line[4:-1], input_voltage=self.settings[ch].input_voltage
            )
            return ch, converted_data
        logger.error("Cannot parsing data.")
        return None

    def _get_buffer_data(self) -> Tuple[Optional[int], Optional[List[float]]]:
        """
        Retrieves buffer data from the handle and parses it.
        This method reads a line of data from the handle, parses it, and returns
        the parsed data if successful. If parsing fails, it logs an error and
        returns None for both elements of the tuple.
        Returns:
            Tuple[Optional[int], Optional[List[float]]]: A tuple containing an
            integer and a list of floats if parsing is successful, otherwise
            (None, None).
        """

        __response = self.handle.readline()
        __parsed = self._parse_data(__response)
        if __parsed is not None:
            return __parsed[0], __parsed[1]
        logger.error(f"Cannot get buffer data: {__response}")
        return None, None

    def get_buffer_data(self) -> Tuple[Optional[int], Optional[List[float]]]:
        """
        Retrieves buffer data for a specific channel.
        This method calls an internal function to get buffer data and updates the
        receive chunk count for the corresponding channel. If the receive chunk
        count reaches 80% of the requested count, it resets the count and starts
        a new thread to request more buffer data for the channel.
        Returns:
            Tuple[Optional[int], Optional[List[float]]]: A tuple containing the
            channel number and the buffer data. If no data is available, returns
            (None, None).
        """

        ch, data = self._get_buffer_data()

        if ch is not None:
            self.settings[ch].recv_chunk_count += 1

            if (
                self.settings[ch].recv_chunk_count
                >= self.settings[ch].request_count * 0.8
            ):
                self.settings[ch].recv_chunk_count = 0
                self.request_buffer_data_thr(ch)
                logger.debug(f"Request data for channel {ch}.")

            return ch, data

        return None, None
