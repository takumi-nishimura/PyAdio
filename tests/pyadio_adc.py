import logging

from pyadio import *


def main():
    logger = logging.getLogger()
    logger.setLevel("INFO")

    REQUEST_DATA_NUM = 6

    pyadio = PyAdio()

    buffer_reset = False
    while not buffer_reset:
        print("...", end="", flush=True)
        response = pyadio.handle.readline()
        if response == b"":
            print("")
            logging.info("Clear buffer.")
            buffer_reset = True

    pyadio.adc.set_input_voltage(channel=0, input_voltage="5")
    pyadio.adc.set_conversion_speed(channels=0, speed=16)

    for ch in range(REQUEST_DATA_NUM):
        pyadio.adc.set_chunk_size(ch, 128)

    pyadio.adc.start_memory_acquisition()

    for ch in range(REQUEST_DATA_NUM):
        pyadio.adc.request_buffer_data(ch)

    try:
        x = 0
        while True:
            x += 1

            ch, data = pyadio.adc._get_buffer_data()
            if data:
                logging.info(data)

    except Exception as e:
        logger.error(e)


if __name__ == "__main__":
    main()
