import logging
from typing import Dict, List, Literal, Optional, Tuple

from serial import Serial

from pyadio._adio import Adio


class ADC:
    def __init__(self, handle: Serial, chunk_num: int = 100) -> None:
        logging.info("ADC Initialize.")

        self.adio = Adio()
        self.handle = handle

        self.chunk_num = chunk_num

        self.settings = {}
        for ch in range(self.adio.ADC_CH_NUM):
            self.settings[ch] = {
                "conversion_speed": 1,
                "chunk_size": 50,
                "input_voltage": 5.0,
            }

    def set_conversion_speed(
        self,
        channels: Literal[0, 1],
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

        __command = f"*00{channels}0{__data}#"
        self.handle.write(__command.encode())

        __response = self.handle.readline().decode().strip()
        if __response == "*OK#":
            logging.info(
                f"Conversion speed successfully set to {speed}ksps for channels {'0~7' if channels == 0 else '8~15'}"
            )
            if channels == 0:
                for ch in range(8):
                    self.settings[ch]["conversion_speed"] = speed
            else:
                for ch in range(8):
                    self.settings[ch + 8]["conversion_speed"] = speed
        else:
            raise Exception(
                f"Cannot set conversion speed for channels {'0~7' if channels == 0 else '8~15'}"
            )

    def set_chunk_size(self, ch: int, chunk_size: int):
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

        __command = f"*10{ch:X}0{format(chunk_size, '04X')}#"
        self.handle.write(__command.encode())

        __response = self.handle.readline().decode().strip()
        if __response == "*OK#":
            logging.info(
                f"Chunk size successfully set to {chunk_size} for channel {ch}."
            )
            self.settings[ch]["chunk_size"] = chunk_size
        else:
            raise Exception(f"Cannot set chunk size for channel {ch}.")

    def set_input_voltage(
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
            logging.info(
                f"Input voltage successfully set to {input_voltage}V for channel {channel}."
            )
            self.settings[channel]["input_voltage"] = float(input_voltage)
        else:
            raise Exception(f"Cannot set input voltage for channel {channel}.")

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
            logging.info("Memory acquisition started successfully.")
        else:
            raise Exception("Cannot start memory acquisition.")

    def _request_buffer_data(self, ch: int, request_count: int):
        __command = f"*40{ch:X}1{format(request_count-1, '04X')}#"
        self.handle.write(__command.encode())

    def request_buffer_data(self, ch: int):
        self._request_buffer_data(ch, self.chunk_num)

    def _convert_data(self, data: str, input_voltage: float) -> List[float]:
        MAX_ADC_VALUE = 524288
        __convert_data = []
        for i in range(0, len(data), 5):
            __data = int(data[i : i + 5], 16)
            if __data >= MAX_ADC_VALUE:
                __data -= MAX_ADC_VALUE * 2
            __convert_data.append((__data / MAX_ADC_VALUE) * input_voltage)
        return __convert_data

    def _parse_data(self, data: bytes) -> Optional[Tuple[int, List[float]]]:
        line = data.decode().strip()
        if line.startswith("*40"):
            ch = int(line[3], 16)
            converted_data = self._convert_data(
                line[4:-1], input_voltage=self.settings[ch]["input_voltage"]
            )
            return ch, converted_data
        logging.error("Cannot parsing data.")

    def _get_buffer_data(self) -> Tuple[Optional[int], Optional[List[float]]]:
        __response = self.handle.readline()
        __parsed = self._parse_data(__response)
        if __parsed is not None:
            return __parsed[0], __parsed[1]
        return None, None
