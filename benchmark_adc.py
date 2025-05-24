import timeit
from typing import List

# Original _convert_data function (as found in src/pyadio/adc.py)
def _convert_data_original(data: str, input_voltage: float) -> List[float]:
    MAX_ADC_VALUE = 524288
    __convert_data = []
    for i in range(0, len(data), 5):
        __data = int(data[i : i + 5], 16)
        if __data >= MAX_ADC_VALUE:
            __data -= MAX_ADC_VALUE * 2
        __convert_data.append((__data / MAX_ADC_VALUE) * input_voltage)
    return __convert_data

# Optimized _convert_data function v1 (List Comprehension with direct slicing)
def _convert_data_optimized_v1(data: str, input_voltage: float) -> List[float]:
    MAX_ADC_VALUE = 524288
    
    def adjust_adc_value(val: int) -> int:
        if val >= MAX_ADC_VALUE:
            return val - MAX_ADC_VALUE * 2
        return val

    return [
        (adjust_adc_value(int(data[i : i + 5], 16)) / MAX_ADC_VALUE) * input_voltage
        for i in range(0, len(data), 5)
    ]

# Optimized _convert_data function v2 (Pre-splitting string then List Comprehension)
def _convert_data_optimized_v2(data: str, input_voltage: float) -> List[float]:
    MAX_ADC_VALUE = 524288
    
    chunks = [data[i : i + 5] for i in range(0, len(data), 5)]

    def adjust_adc_value(val: int) -> int:
        if val >= MAX_ADC_VALUE:
            return val - MAX_ADC_VALUE * 2
        return val

    return [
        (adjust_adc_value(int(chunk, 16)) / MAX_ADC_VALUE) * input_voltage
        for chunk in chunks
    ]

if __name__ == "__main__":
    num_readings = 127
    data_segments = []
    for i in range(num_readings):
        segment = format((i * 1234567) % (16**5), '05x') 
        data_segments.append(segment)
    sample_data_string = "".join(data_segments)
    
    input_voltage_val = 5.0
    num_executions = 10000 

    print(f"Benchmarking with {num_readings} readings per call, {num_executions} executions.\n")

    # Original
    t_original = timeit.timeit(
        lambda: _convert_data_original(sample_data_string, input_voltage_val),
        number=num_executions
    )
    print(f"Original function:")
    print(f"  Total time: {t_original:.6f} seconds")
    if num_executions > 0: print(f"  Average time: {t_original/num_executions:.8f} seconds")

    # Optimized v1
    t_optimized_v1 = timeit.timeit(
        lambda: _convert_data_optimized_v1(sample_data_string, input_voltage_val),
        number=num_executions
    )
    print(f"\nOptimized function v1 (List Comprehension with direct slicing):")
    print(f"  Total time: {t_optimized_v1:.6f} seconds")
    if num_executions > 0: print(f"  Average time: {t_optimized_v1/num_executions:.8f} seconds")
    if t_original != 0 and num_executions > 0:
        percentage_diff_v1 = ((t_original - t_optimized_v1) / t_original) * 100 
        if percentage_diff_v1 > 0:
            print(f"  v1 is {percentage_diff_v1:.2f}% faster than original.")
        else:
            print(f"  v1 is {abs(percentage_diff_v1):.2f}% slower than original.")

    # Optimized v2
    t_optimized_v2 = timeit.timeit(
        lambda: _convert_data_optimized_v2(sample_data_string, input_voltage_val),
        number=num_executions
    )
    print(f"\nOptimized function v2 (Pre-splitting string then List Comprehension):")
    print(f"  Total time: {t_optimized_v2:.6f} seconds")
    if num_executions > 0: print(f"  Average time: {t_optimized_v2/num_executions:.8f} seconds")
    if t_original != 0 and num_executions > 0:
        percentage_diff_v2 = ((t_original - t_optimized_v2) / t_original) * 100
        if percentage_diff_v2 > 0:
            print(f"  v2 is {percentage_diff_v2:.2f}% faster than original.")
        else:
            print(f"  v2 is {abs(percentage_diff_v2):.2f}% slower than original.")

    print("\nVerifying correctness of outputs...")
    original_result = _convert_data_original(sample_data_string, input_voltage_val)
    optimized_v1_result = _convert_data_optimized_v1(sample_data_string, input_voltage_val)
    optimized_v2_result = _convert_data_optimized_v2(sample_data_string, input_voltage_val)

    correct_v1 = original_result == optimized_v1_result
    correct_v2 = original_result == optimized_v2_result

    print(f"Output v1 is identical to original: {correct_v1}")
    print(f"Output v2 is identical to original: {correct_v2}")

    if not correct_v1: print("Error: v1 output differs from original.")
    if not correct_v2: print("Error: v2 output differs from original.")
```
