import os
import pickle
import socket
import threading
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


def parse_data(data):
    line = data.decode().strip()
    if line.startswith("*40"):
        ch = int(line[3], 16)
        data = convert_data(line[4:-1], input_voltage=5.0)
        return ch, data


def main():
    plot_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    SOCK_ADDRESS = ("localhost", 4000)

    ADC_CHANNEL_NUM = 16

    CHUNK_SIZE = 127
    CHUNK_NUM = 100

    REQUEST_DATA_NUM = 3

    handle = Serial(port=search_port(), timeout=1)
    handle.reset_input_buffer()
    handle.reset_output_buffer()

    buffer_reset = False
    while not buffer_reset:
        print("...", end="", flush=True)
        response = handle.readline()
        if response == b"":
            buffer_reset = True

    # Set conversion speed
    command = "*00000008#"
    handle.write(command.encode())
    response = handle.readline().decode().strip()
    if response:
        print(f"Response: {response}")
    else:
        print(f"No response or timeout for command: {command}")

    # Set the number of data acquisitions
    for i in range(ADC_CHANNEL_NUM):
        command = f"*10{i:X}0{format(CHUNK_SIZE, '04X')}#"
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

    # Set the input voltage range
    for i in range(ADC_CHANNEL_NUM):
        command = f"*50{i:X}00001#"
        handle.write(command.encode())
        response = handle.readline().decode().strip()
        if response:
            print(f"Response: {response}")
        else:
            print(f"No response or timeout for command: {command}")

    # Request data transmission
    def send_data_request():
        for i in range(REQUEST_DATA_NUM):
            handle.write(f"*40{i:X}1{format(CHUNK_NUM-1, '04X')}#".encode())

    threading.Thread(target=send_data_request, daemon=True).start()

    socket_queue = Queue()

    def recv_thr():
        while True:
            __response = handle.read(
                (12 + 5 * (CHUNK_SIZE - 1)) * REQUEST_DATA_NUM
            )
            socket_queue.put(__response)

    threading.Thread(target=recv_thr, daemon=True).start()

    x = 0
    recv_chunk_count = 0

    while True:
        try:
            x += 1

            while not socket_queue.empty():
                response = socket_queue.get_nowait()

                lines = response.split(b"\r\n")

        except KeyboardInterrupt:
            print("Keyboard Interrupt")
            break


if __name__ == "__main__":
    main()
