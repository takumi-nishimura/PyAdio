# PyAdio

PyAdio is a Python library for ADio, now featuring asynchronous I/O capabilities for enhanced performance and concurrency.

## Installation

This library requires Python 3.9+ and the following packages:
- `pyserial>=3.5`
- `pydantic>=2.10.4`
- `pyserial-asyncio>=0.6` (for asynchronous operations)

```bash
pip install pyadio
```
Alternatively, for the latest development version:
```bash
pip install git+https://github.com/takumi-nishimura/PyAdio.git
```

## Basic Usage (Asynchronous)

Here's a basic example of how to use `PyAdio` with `async/await`:

```python
import asyncio
import logging
from pyadio.pyadio import PyAdio # Assuming PyAdio is installed or in PYTHONPATH

# Configure logging to see PyAdio logs
logging.basicConfig(level=logging.INFO)

async def main():
    pyadio_device = None
    try:
        # Instantiate PyAdio. Port can be auto-detected if None.
        # Baudrate and other serial parameters can be passed as kwargs.
        pyadio_device = PyAdio(port=None, baudrate=115200) 
        
        # Establish the connection (this is an async operation)
        await pyadio_device.connect()
        
        # ADC is now available via pyadio_device.adc
        if pyadio_device.adc:
            # Example: Configure ADC channel 0
            # Parameters: channel, conversion_speed (ksps), chunk_size (samples), 
            #             request_count (chunks), input_voltage ("5" for ±5V etc.)
            await pyadio_device.adc.set_channel(
                channel=0,
                conversion_speed=128, # 128 ksps
                chunk_size=256,       # 256 samples per chunk
                request_count=20,     # Request 20 chunks
                input_voltage="5"     # ±5V range
            )
            
            # Example: Start memory acquisition on the device
            await pyadio_device.adc.start_memory_acquisition()
            
            print("Starting data acquisition loop...")
            for i in range(100): # Acquire 100 data points/chunks
                # Get buffer data (this is an async operation)
                # Returns (channel_number, list_of_voltage_values) or (None, None)
                ch, data = await pyadio_device.adc.get_buffer_data()
                
                if ch is not None and data:
                    print(f"Received data from channel {ch}: {len(data)} samples. First sample: {data[0]:.4f} V")
                    # Process your data here
                elif ch is None and data is None:
                    logging.info("No data received, possibly timeout or end of stream from mock.")
                    # If using a real device, this might indicate a problem or end of configured acquisition.
                    await asyncio.sleep(0.1) # Wait a bit before retrying or breaking
                
                if i % 20 == 0 and i > 0: # Periodically log
                    logging.info(f"Acquired {i} data segments...")

        else:
            logging.error("ADC not available after connect.")

    except Exception as e:
        logging.error(f"An error occurred: {e}")
    finally:
        if pyadio_device:
            logging.info("Closing connection...")
            await pyadio_device.close()
            logging.info("Connection closed.")

if __name__ == "__main__":
    asyncio.run(main())
```

> [!Tip]
> You can use [pgliveApp](https://github.com/takumi-nishimura/pgliveApp.git) to visualize the ADC waveform (may require adaptation for asynchronous data feeding or a separate data acquisition script).
> ```bash
> pgliveapp --num 6 --col 2
> ```

## ADC Configuration Parameters

The behavior and performance of the ADC can be tuned using several parameters, typically set via `adc.set_channel(...)` or by modifying `adc.settings[channel_index]` after `PyAdio.connect()`. The defaults for new channels (as of version 0.2.0+) are:
- `conversion_speed`: 16 ksps
- `chunk_size`: 128 samples
- `request_count`: 10 chunks

Key parameters in the `ADC_CH` model include:

*   **`conversion_speed` (ksps)**:
    *   **Meaning**: Samples per second per channel (e.g., 16 ksps = 16,000 samples/sec).
    *   **Impact**: Higher speed gives better time resolution for fast-changing signals but increases data volume. Lower speed is suitable for slower signals and reduces data.
    *   **Consideration**: Must be at least twice the maximum frequency of the input signal to avoid aliasing (Nyquist theorem).
*   **`chunk_size` (samples)**:
    *   **Meaning**: Number of samples grouped by the device into a single "chunk" for a channel.
    *   **Impact**: Larger `chunk_size` can improve communication efficiency (less overhead per sample) for bulk transfers but may increase latency for the first sample in a chunk.
    *   **Default**: 128 samples.
*   **`request_count` (chunks)**:
    *   **Meaning**: Number of chunks the host requests from the device in one `_request_buffer_data` operation (total samples = `chunk_size * request_count`).
    *   **Impact**: Affects the total amount of data fetched per explicit request. The `get_buffer_data` method uses this (along with `re_request_threshold`) to determine when to trigger background data refresh.
    *   **Default**: 10 chunks.
*   **`re_request_threshold` (ratio)**:
    *   **Meaning**: A ratio (0.0 to 1.0) of `request_count`. When received chunks reach this proportion, a background task attempts to request more data.
    *   **Impact**: Controls how proactively new data is fetched. A lower value means more aggressive pre-fetching.
    *   **Default**: 0.8 (i.e., 80%).
*   **`input_voltage` (Volts string)**:
    *   **Meaning**: Represents the expected input voltage range (e.g., "5" for +/-5V). Used for scaling raw ADC values.
    *   **Impact**: Incorrect setting leads to wrong voltage readings.

Adjust these parameters based on your application's specific needs regarding signal characteristics, data volume, latency, and communication efficiency. The new defaults aim for a more balanced starting point.

## Contributing

Pull requests are welcome. For major changes, please open an issue first
to discuss what you would like to change.

## License

This project is licensed under the MIT License - see the [LICENSE](https://github.com/takumi-nishimura/PyAdio/blob/dev/LICENCE.txt) file for details.

* **pydantic** is licensed under the MIT License. [LICENCE](https://github.com/pydantic/pydantic/blob/main/LICENSE)
* **pyserial** is licensed under the BSD 3-Clause License. [LICENCE](https://github.com/pyserial/pyserial/blob/master/LICENSE.txt)
* **pyserial-asyncio** is licensed under the BSD 3-Clause License. [LICENCE](https://github.com/pyserial/pyserial-asyncio/blob/master/LICENSE.txt)

```
