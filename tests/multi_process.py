import ctypes
import multiprocessing
import os
import time

from serial import Serial, SerialException, SerialTimeoutException
from serial.tools import list_ports

ADC_CHANNEL_NUM = 16

REQUEST_DATA_NUM = 16
CHUNK_SIZE = 2047
CHUNK_NUM = 40


def search_port():
    ports = list_ports.comports()
    os_name = os.name

    for port in ports:
        if os_name == "posix":
            if "usbserial-FT" in port.device:
                return port.device


def send_command(command: str, ser: Serial, verbose: bool = True):
    ser.write(command.encode())
    try:
        response = ser.readline()
        if b"OK" in response:
            if verbose:
                print(f"Command {command} sent successfully.")
        elif b"NG" in response:
            if verbose:
                raise Exception(f"Command {command} failed.")
        else:
            raise Exception(f"Unexpected response: {response}")

    except SerialTimeoutException:
        print(
            f"No response within {ser.timeout} seconds. Sending recovery command: *f0000001#"
        )
        ser.write("*f0000001#".encode())
        __response = ser.readline().decode().strip()


def serial_process(
    shared_buffer, current_buffer_size, buffer_lock, data_ready, terminate
):
    try:
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
        send_command("*40030000#", handle)

        # Set the number of data acquisitions
        for i in range(ADC_CHANNEL_NUM):
            command = f"*10{i:X}0{format(CHUNK_SIZE, '04x')}#"
            send_command(command, handle)

        # Reset the device
        send_command("*f0000001#", handle)

        # Set conversion speed
        send_command("*00000006#", handle)
        send_command("*00100006#", handle)

        # Set the input voltage range
        for i in range(ADC_CHANNEL_NUM):
            send_command(f"*50{i:X}00001#", handle)

        # Start memory accumulation
        send_command("*40020000#", handle)

        # Request data transmission
        def send_data_request():
            message = ""
            for i in range(REQUEST_DATA_NUM):
                message += f"*40{i:X}1{format(CHUNK_NUM-1, '04x')}#"
            handle.write(message.encode())

        send_data_request()

        while not terminate.is_set():
            try:
                bytes_to_read = handle.in_waiting
                if bytes_to_read > 0:
                    with buffer_lock:
                        if (
                            bytes_to_read
                            > len(shared_buffer) - current_buffer_size.value
                        ):
                            bytes_to_read = (
                                len(shared_buffer) - current_buffer_size.value
                            )
                            print("Buffer overflow detected.")

                        view = memoryview(shared_buffer).cast("B")
                        handle.readinto(
                            view[
                                current_buffer_size.value : current_buffer_size.value
                                + bytes_to_read
                            ]
                        )
                        current_buffer_size.value += bytes_to_read
                        data_ready.notify()

            except SerialException as e:
                print(f"Serial exception: {e}")
                terminate.set()
                break

            except Exception as e:
                print("Unexpected exception:", e)
                terminate.set()
                break

    finally:
        handle.reset_input_buffer()
        handle.reset_output_buffer()
        handle.close()


def main():
    buffer_capacity = 8192
    shared_buffer = multiprocessing.RawArray(ctypes.c_ubyte, buffer_capacity)
    current_buffer_size = multiprocessing.Value("i", 0)
    buffer_lock = multiprocessing.Lock()
    data_ready = multiprocessing.Condition(buffer_lock)
    terminate = multiprocessing.Event()

    # 受信したデータを蓄積するためのリスト
    combined_data = []

    serial_proc = multiprocessing.Process(
        target=serial_process,
        args=(
            shared_buffer,
            current_buffer_size,
            buffer_lock,
            data_ready,
            terminate,
        ),
    )
    serial_proc.start()

    data_len = 0
    start_time = time.time()
    try:
        while not terminate.is_set():
            if time.time() - start_time > 2:
                break

            with buffer_lock:
                if current_buffer_size.value > 0:
                    data_len = current_buffer_size.value
                    current_buffer_size.value = 0

                if terminate.is_set():
                    break

            if data_len > 0:
                # データを取得してリストに追加
                view = memoryview(shared_buffer).cast("B")[:data_len]
                data = bytes(view)
                combined_data.append(data)

    except KeyboardInterrupt:
        print("Keyboard interrupt detected.")
        terminate.set()

    finally:
        serial_proc.join()
        # 全データを結合して長さを表示
        if combined_data:
            total_data = b"".join(combined_data)
            print(f"Total received data: {len(total_data)} bytes")
        print("Program terminated.")


if __name__ == "__main__":
    main()
