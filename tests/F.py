import os
import pickle
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

from serial import Serial
from serial.tools.list_ports import comports


def search_port():
    ports = comports()
    os_name = os.name

    for port in ports:
        if os_name == "posix":
            if "usbserial-FT" in port.device:
                return port.device


def convert_data(data, input_voltage):
    MAX_ADC_VALUE = 524288
    __convert_data = []
    for i in range(0, len(data), 5):
        __data = int(data[i : i + 5], 16)
        if __data >= MAX_ADC_VALUE:
            __data -= MAX_ADC_VALUE * 2
        __convert_data.append((__data / MAX_ADC_VALUE) * input_voltage)
    return __convert_data


def _recv_buffer_data(handle: Serial, data_queue: Queue):
    _buffer = b""
    before_length = 0
    while True:
        try:
            if handle.in_waiting > 0:
                _read_data = handle.read(
                    handle.in_waiting
                )  # 直接_bufferに足すのではなく，分けると良いっぽい
                _buffer += _read_data

                # if b"#" in _buffer:
                #     for _ in range(_buffer.count(b"#")):
                #         data = _buffer[: _buffer.index(b"#") + 1]
                #         if not len(data) == before_length:
                #             print(f"Data length: {len(data)}")
                #             print(_buffer)

                #         # data_queue.put(data)

                #         before_length = len(data)
                #         _buffer = _buffer[_buffer.index(b"\n") + 1 :]
        except Exception as e:
            print(e)


def recv_buffer_data(handle: Serial, data_queue: Queue):
    buffer = b""
    _buffer = b""
    before_length = 0
    while True:
        try:
            if handle.is_open:
                if handle.in_waiting > 0:
                    _data = handle.read(handle.in_waiting)
                    buffer += _data
                    _buffer += _data

                    if b"#" in _buffer:
                        for _ in range(_buffer.count(b"#")):
                            data = _buffer[: _buffer.index(b"#") + 1]

                            if not len(data) == before_length:
                                print(f"Data length: {len(data)}")

                            data_queue.put(data)

                            before_length = len(data)

                            _buffer = _buffer[_buffer.index(b"\n") + 1 :]

        except Exception as e:
            print(e)
            print(len(buffer))
            data = {}
            for line in buffer.splitlines():
                parsed = parse_data(line)
                if parsed is not None:
                    if not parsed[0] in data.keys():
                        data[parsed[0]] = []
                    data[parsed[0]].append(parsed[1])
            for ch, d in data.items():
                print(
                    ch,
                    len([item for sublist in d for item in sublist]),
                )
            break


def parse_data(data):
    if isinstance(data, bytes):
        line = data.decode().strip()
    else:
        line = data.strip()
    if line.startswith("*40"):
        ch = int(line[3], 16)
        data = convert_data(line[4:-1], input_voltage=5.0)
        return ch, data


def main():
    ADC_CHANNEL_NUM = 16

    CHUNK_SIZE = 2047
    CHUNK_NUM = 40

    REQUEST_DATA_NUM = 16

    handle = Serial(port=search_port(), timeout=1)
    handle.reset_input_buffer()
    handle.reset_output_buffer()

    # Reset the buffer
    buffer_reset = False
    while not buffer_reset:
        print("...", end="", flush=True)
        response = handle.readline()
        if response == b"":
            buffer_reset = True
            print("Buffer reset.")

    # Stop memory accumulation
    command = "*40030000#"
    handle.write(command.encode())
    response = handle.readline().decode().strip()
    if response:
        print(f"Response: {response}")
    else:
        print(f"No response or timeout for command: {command}")

    # Set the number of data acquisitions
    for i in range(ADC_CHANNEL_NUM):
        command = f"*10{i:X}0{format(CHUNK_SIZE, '04x')}#"
        handle.write(command.encode())
        response = handle.readline().decode().strip()
        if response:
            print(f"Response: {response}")
        else:
            print(f"No response or timeout for command: {command}")

    # Reset the device
    command = "*f0000001#"
    handle.write(command.encode())
    response = handle.readline().decode().strip()
    if response:
        print(f"Response: {response}")
    else:
        print(f"No response or timeout for command: {command}")

    # Set conversion speed
    command = "*00000006#"
    handle.write(command.encode())
    response = handle.readline().decode().strip()
    if response:
        print(f"Response: {response}")
    else:
        print(f"No response or timeout for command: {command}")
    command = "*00100006#"
    handle.write(command.encode())
    response = handle.readline().decode().strip()
    if response:
        print(f"Response: {response}")
    else:
        print(f"No response or timeout for command: {command}")

    # Set the input voltage range
    for i in range(ADC_CHANNEL_NUM):
        command = f"*50{i:X}00001#"
        handle.write(command.encode())
        response = handle.readline().decode().strip()
        if response:
            print(f"Response: {response}")
        else:
            print(f"No response or timeout for command: {command}")

    # Start memory accumulation
    handle.write("*40020000#".encode())
    response = handle.readline().decode().strip()
    if response:
        print(f"Response: {response}")
    else:
        print(f"No response or timeout for command: {command}")

    # Request data transmission
    def send_data_request():
        message = ""
        for i in range(REQUEST_DATA_NUM):
            message += f"*40{i:X}1{format(CHUNK_NUM-1, '04x')}#"
        handle.write(message.encode())

    data_queue = Queue()
    receiver_thread = threading.Thread(
        target=recv_buffer_data, args=(handle, data_queue), daemon=True
    )
    receiver_thread.start()

    send_data_request()

    receiver_thread.join(timeout=5)

    # x = 0
    # recv_chunk_count = 0

    # export_data = {}
    # for i in range(REQUEST_DATA_NUM):
    #     export_data[i] = []

    # start_time = time.time()
    # while True:
    #     try:
    #         # x += 1
    #         if time.time() - start_time > 5:
    #             break

    #         # if data_queue.qsize() > 0:
    #         #     recv_data = data_queue.get_nowait()
    #         # parsed_data = parse_data(recv_data)

    #         # if parsed_data is not None:
    #         #     print(parsed_data[0])
    #         #     export_data[parsed_data[0]].append(parsed_data[1])

    #     except KeyboardInterrupt:
    #         break

    #     except Exception as e:
    #         print(e)

    handle.reset_input_buffer()
    handle.reset_output_buffer()
    handle.close()

    receiver_thread.join(timeout=1)


if __name__ == "__main__":
    main()
