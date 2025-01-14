import os
import pickle
import socket
from concurrent.futures import ThreadPoolExecutor

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

    REQUEST_DATA_NUM = 6

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

    # Reset the device
    command = "*F0000000#"
    handle.write(command.encode())
    response = handle.readline().decode().strip()
    if response:
        print(f"Response: {response}")
    else:
        print(f"No response or timeout for command: {command}")

    # Set conversion speed
    command = "*00000000#"
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

    executor = ThreadPoolExecutor(max_workers=2)
    executor.submit(send_data_request)

    x = 0
    recv_chunk_count = 0

    while True:
        try:
            data_dict = {}

            for _ in range(REQUEST_DATA_NUM):
                response = handle.readline()
                parsed = parse_data(response)
                if parsed is not None:
                    ch, data = parsed
                    data_dict[ch] = data

            recv_chunk_count += 1
            if recv_chunk_count >= CHUNK_NUM * 0.8:
                recv_chunk_count = 0
                executor.submit(send_data_request)

            x += 1
            send_data = {"x": x}
            for ch, data in data_dict.items():
                send_data[f"y{ch+1}"] = data
            plot_socket.sendto(pickle.dumps(send_data), SOCK_ADDRESS)

        except KeyboardInterrupt:
            print("Keyboard Interrupt")
            break


if __name__ == "__main__":
    main()
