import logging
import pickle
import socket

from pyadio import PyAdio


def main():
    logging.basicConfig(level=logging.DEBUG)
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    plot_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    REQUEST_DATA_NUM = 6
    pyadio = PyAdio()

    for ch in range(REQUEST_DATA_NUM):
        pyadio.adc.set_channel(
            channel=ch,
            conversion_speed=1,
            chunk_size=128,
            input_voltage="5",
        )

    pyadio.adc.start_memory_acquisition()
    for ch in range(REQUEST_DATA_NUM):
        pyadio.adc.request_buffer_data(ch)

    try:
        x = 0
        while True:
            recv_data_dict = {}

            for _ in range(REQUEST_DATA_NUM):
                ch, data = pyadio.adc.get_buffer_data()
                if ch is not None:
                    logger.debug(f"Received data for channel {ch}.")
                    if ch in recv_data_dict:
                        logger.error(
                            f"Duplicate data received for channel {ch}."
                        )
                        continue

                    recv_data_dict[ch] = data

            x += 1
            send_data = {"x": x}
            for ch, data in recv_data_dict.items():
                send_data[f"y{ch+1}"] = data
            plot_sock.sendto(pickle.dumps(send_data), ("localhost", 4000))

    except Exception as e:
        logger.error(e)


if __name__ == "__main__":
    main()
