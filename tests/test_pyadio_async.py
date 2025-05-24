import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch, call
import logging
import sys
import os

# srcディレクトリをsys.pathに追加して、pyadioモジュールをインポート可能にする
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from pyadio.adc import ADC, ADC_CH
from pyadio._adio import Adio # ADCが初期化時にadio.ADC_CH_NUMを参照するため

# テスト中のログ出力を制御
# logging.basicConfig(level=logging.DEBUG) # テストデバッグ用にログレベルを設定
# logging.getLogger('pyadio.adc').setLevel(logging.DEBUG)


# --- Mock Stream Reader/Writer for asyncio ---
class MockAsyncStreamReader:
    def __init__(self, initial_data_lines=None):
        self._data_buffer = asyncio.Queue()
        if initial_data_lines:
            for line in initial_data_lines:
                self._data_buffer.put_nowait(line)
        self._eof = False

    async def readline(self) -> bytes:
        if self._eof and self._data_buffer.empty():
            return b''
        try:
            line = await self._data_buffer.get()
            self._data_buffer.task_done()
            return line
        except asyncio.CancelledError:
            raise
        except Exception:
            if self._eof: return b''
            raise

    async def read(self, n: int = -1) -> bytes:
        if n == -1:
            return await self.readline()
        line = await self.readline()
        return line[:n]

    def feed_data(self, data: bytes):
        if not self._eof:
            self._data_buffer.put_nowait(data)

    def feed_eof(self):
        self._eof = True
        self._data_buffer.put_nowait(b'')


class MockAsyncStreamWriter:
    def __init__(self):
        self.written_data = bytearray()
        self._closed = False
        self.drain_calls = 0
        self.write_call_count = 0

    def write(self, data: bytes):
        if self._closed:
            raise ConnectionResetError("Connection closed")
        self.written_data.extend(data)
        self.write_call_count +=1

    async def drain(self):
        if self._closed:
            raise ConnectionResetError("Connection closed")
        self.drain_calls += 1
        await asyncio.sleep(0)

    def close(self):
        self._closed = True

    async def wait_closed(self):
        await asyncio.sleep(0)

    def get_extra_info(self, name, default=None):
        return default

    def clear(self):
        self.written_data = bytearray()
        self.drain_calls = 0
        self.write_call_count = 0

class MockAdioConfig:
    def __init__(self, num_channels=16):
        self.ADC_CH_NUM = num_channels

class TestAdcAsync(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_reader = MockAsyncStreamReader()
        self.mock_writer = MockAsyncStreamWriter()
        self.mock_adio_config = MockAdioConfig(num_channels=16)
        self.adc = ADC(self.mock_reader, self.mock_writer, self.mock_adio_config)

    # --- ADC_CH Default Value Tests ---
    def test_adc_ch_default_values(self):
        # ADC.__init__で設定されるデフォルト値を確認
        for ch_setting in self.adc.settings:
            self.assertEqual(ch_setting.conversion_speed, 16)
            self.assertEqual(ch_setting.chunk_size, 128)
            self.assertEqual(ch_setting.request_count, 10)
            self.assertEqual(ch_setting.input_voltage, 5.0)
            self.assertEqual(ch_setting.re_request_threshold, 0.8)

    # --- set_channel Method Tests ---
    async def test_set_channel_updates_settings_and_calls_internal_methods(self):
        ch_to_test = 0
        test_speed = 32 # ksps
        test_chunk_size = 64
        test_request_count = 5
        test_voltage = "1.25"

        # 内部メソッドをAsyncMockでパッチ
        self.adc._set_conversion_speed = AsyncMock()
        self.adc._set_chunk_size = AsyncMock()
        self.adc._set_input_voltage = AsyncMock()
        # _set_request_countは同期メソッドなのでMagicMock
        self.adc._set_request_count = MagicMock()

        await self.adc.set_channel(
            ch_to_test,
            conversion_speed=test_speed,
            chunk_size=test_chunk_size,
            request_count=test_request_count,
            input_voltage=test_voltage
        )

        self.adc._set_conversion_speed.assert_called_once_with(ch_to_test, test_speed)
        self.adc._set_chunk_size.assert_called_once_with(ch_to_test, test_chunk_size)
        self.adc._set_request_count.assert_called_once_with(ch_to_test, test_request_count) # 同期メソッドの呼び出し確認
        self.adc._set_input_voltage.assert_called_once_with(ch_to_test, test_voltage)
        
        # 設定が実際に更新されたかも確認 (これは_set_request_countのテストになる)
        # self.assertEqual(self.adc.settings[ch_to_test].request_count, test_request_count)
        # 他のセッターメソッドも同様に設定更新を内部でテストするため、ここでは呼び出し確認が主

    # --- _set_conversion_speed のテスト ---
    async def test_set_conversion_speed_ok(self):
        channel_group_ch = 0 # ch 0-7
        speed_ksps = 16
        expected_command = b"*00000004#"
        
        self.mock_reader.feed_data(b"*OK#\n")
        await self.adc._set_conversion_speed(channel_group_ch, speed_ksps)
        
        self.assertIn(expected_command, self.mock_writer.written_data)
        self.assertEqual(self.mock_writer.drain_calls, 1) # drainが1回呼ばれる
        for i in range(8):
            self.assertEqual(self.adc.settings[i].conversion_speed, speed_ksps)

    async def test_set_conversion_speed_timeout(self):
        with self.assertRaisesRegex(Exception, "Timeout setting conversion speed"):
            await self.adc._set_conversion_speed(0, 16)

    # --- _set_chunk_size のテスト ---
    async def test_set_chunk_size_ok(self):
        channel = 3
        chunk_size = 256
        expected_command = b"*10300100#"
        
        self.mock_reader.feed_data(b"*OK#\n")
        await self.adc._set_chunk_size(channel, chunk_size)
        
        self.assertIn(expected_command, self.mock_writer.written_data)
        self.assertEqual(self.mock_writer.drain_calls, 1)
        self.assertEqual(self.adc.settings[channel].chunk_size, chunk_size)
        
    async def test_set_chunk_size_large_value_warning(self):
        channel = 1
        chunk_size = 0x8000
        expected_command = b"*10108000#"
        
        self.mock_reader.feed_data(b"*OK#\n")
        with self.assertLogs(logger='pyadio.adc', level='WARNING') as cm:
            await self.adc._set_chunk_size(channel, chunk_size)
        self.assertTrue(any("very large chunk_size" in message for message in cm.output))
        self.assertIn(expected_command, self.mock_writer.written_data)

    # --- _request_buffer_data のテスト ---
    async def test_request_buffer_data_command(self):
        channel = 5
        request_count = self.adc.settings[channel].request_count
        expected_command = f"*40{channel:X}1{format(request_count-1, '04X')}#".encode('ascii')
        
        await self.adc._request_buffer_data(channel, request_count)
        
        self.assertIn(expected_command, self.mock_writer.written_data)
        self.assertEqual(self.mock_writer.drain_calls, 1)

    async def test_request_buffer_data_large_value_warning(self):
        channel = 1
        request_count = 0x9000
        expected_command = f"*4011{format(request_count-1, '04X')}#".encode('ascii')
        
        with self.assertLogs(logger='pyadio.adc', level='WARNING') as cm:
            await self.adc._request_buffer_data(channel, request_count)
        self.assertTrue(any("very large number of chunks" in message for message in cm.output))
        self.assertIn(expected_command, self.mock_writer.written_data)

    # --- _get_buffer_data, _parse_data, _convert_data の統合テスト ---
    async def test_get_buffer_data_ok_parses_and_converts(self):
        channel = 2
        adc_ch_setting = self.adc.settings[channel]
        payload_len = adc_ch_setting.chunk_size * 5
        hex_payload = ('A' * 5) * adc_ch_setting.chunk_size
        
        MAX_ADC_VALUE = 524288
        raw_val = int('AAAAA', 16)
        adjusted_val = raw_val - 2 * MAX_ADC_VALUE if raw_val >= MAX_ADC_VALUE else raw_val
        expected_voltage_val = (adjusted_val / MAX_ADC_VALUE) * adc_ch_setting.input_voltage
        
        mock_line = f"*40{channel:X}{hex_payload}#\n".encode('ascii')
        self.mock_reader.feed_data(mock_line)
        
        ch_result, data_result = await self.adc._get_buffer_data()
        
        self.assertEqual(ch_result, channel)
        self.assertIsNotNone(data_result)
        self.assertEqual(len(data_result), adc_ch_setting.chunk_size)
        for val in data_result:
            self.assertAlmostEqual(val, expected_voltage_val, places=5)

    async def test_get_buffer_data_parse_error_invalid_line(self):
        self.mock_reader.feed_data(b"Invalid data line\n")
        
        with self.assertLogs(logger='pyadio.adc', level='ERROR') as cm:
            ch, data = await self.adc._get_buffer_data()
        self.assertIsNone(ch)
        self.assertIsNone(data)
        self.assertTrue(any("Cannot parse data: Invalid data line" in message for message in cm.output))

    async def test_get_buffer_data_timeout(self):
        with self.assertLogs(logger='pyadio.adc', level='WARNING') as cm:
            ch, data = await self.adc._get_buffer_data()
        self.assertIsNone(ch)
        self.assertIsNone(data)
        self.assertTrue(any("Timeout waiting for buffer data" in message for message in cm.output))

    # --- 再リクエストロジックのテスト (get_buffer_data内) ---
    @patch('asyncio.create_task')
    async def test_get_buffer_data_re_request_logic(self, mock_create_task: MagicMock):
        ch_to_test = 0
        s = self.adc.settings[ch_to_test]
        s.request_count = 10
        s.re_request_threshold = 0.8
        trigger_recv_count = int(s.request_count * s.re_request_threshold)

        hex_payload = ('0' * 5) * s.chunk_size
        mock_line = f"*40{ch_to_test:X}{hex_payload}#\n".encode('ascii')

        # 閾値に達するまで呼び出し
        for i in range(trigger_recv_count):
            self.mock_reader.feed_data(mock_line)
            await self.adc.get_buffer_data()
            if i < trigger_recv_count - 1:
                mock_create_task.assert_not_called()
        
        # 閾値に達した後の呼び出しでタスクが作成される
        mock_create_task.assert_called_once()
        # 最初の引数（コルーチン）を確認
        self.assertEqual(mock_create_task.call_args[0][0].__qualname__, 'ADC.request_buffer_data')
        
        # タスクが保存されているか確認
        self.assertIn(ch_to_test, self.adc.active_request_tasks)
        created_task_mock = mock_create_task.return_value # create_taskの戻り値(モックされたタスク)
        self.assertEqual(self.adc.active_request_tasks[ch_to_test], created_task_mock)
        created_task_mock.add_done_callback.assert_called_once() # コールバックが追加されたか

        # 既存タスクが実行中の場合、新たなタスクは作成されない
        mock_create_task.reset_mock()
        created_task_mock.done.return_value = False # タスクはまだ実行中とマーク
        self.mock_reader.feed_data(mock_line) 
        s.recv_chunk_count = trigger_recv_count # 再度閾値状態にする
        await self.adc.get_buffer_data()
        mock_create_task.assert_not_called()

        # 既存タスクが完了していれば、新たなタスクが作成される
        created_task_mock.done.return_value = True # タスク完了とマーク
        self.adc.active_request_tasks.pop(ch_to_test) # _handle_request_task_completionが呼ばれたと仮定して削除
        self.mock_reader.feed_data(mock_line)
        s.recv_chunk_count = trigger_recv_count
        await self.adc.get_buffer_data()
        mock_create_task.assert_called_once()


    async def test_handle_request_task_completion_success(self):
        ch_to_test = 0
        mock_task = AsyncMock(spec=asyncio.Task)
        mock_task.exception.return_value = None # 例外なし
        
        self.adc.active_request_tasks[ch_to_test] = mock_task
        
        done_callback = self.adc._handle_request_task_completion(ch_to_test)
        
        with self.assertLogs(logger='pyadio.adc', level='DEBUG') as cm:
            done_callback(mock_task)
        
        self.assertTrue(any(f"Background data re-request task for channel {ch_to_test} completed successfully." in message for message in cm.output))
        self.assertNotIn(ch_to_test, self.adc.active_request_tasks) # タスクが削除されたか

    async def test_handle_request_task_completion_with_exception(self):
        ch_to_test = 1
        mock_task = AsyncMock(spec=asyncio.Task)
        test_exception = ValueError("Test Exception in Task")
        mock_task.exception.return_value = test_exception
        
        self.adc.active_request_tasks[ch_to_test] = mock_task
        
        done_callback = self.adc._handle_request_task_completion(ch_to_test)
        
        with self.assertLogs(logger='pyadio.adc', level='ERROR') as cm:
            done_callback(mock_task)
            
        self.assertTrue(any(f"Background data re-request task for channel {ch_to_test} failed: {test_exception}" in message for message in cm.output))
        self.assertNotIn(ch_to_test, self.adc.active_request_tasks)


    # --- _convert_data の直接テスト (様々な入力パターン) ---
    def test_convert_data_various_inputs(self):
        input_voltage = 5.0 
        MAX_ADC_VALUE = 524288

        test_cases = {
            "zero": ("00000", 0.0),
            "positive_near_max": (format(MAX_ADC_VALUE - 1, '05x'), ((MAX_ADC_VALUE - 1) / MAX_ADC_VALUE) * input_voltage),
            "negative_max_boundary": (format(MAX_ADC_VALUE, '05x'), -input_voltage), # Adjusted: -MAX_ADC_VALUE / MAX_ADC_VALUE * voltage
            "negative_just_over_boundary": (format(MAX_ADC_VALUE + 1, '05x'), ((1 - MAX_ADC_VALUE) / MAX_ADC_VALUE) * input_voltage), # Adjusted: (MAX_ADC_VALUE + 1 - 2*MAX_ADC_VALUE) / MAX_ADC_VALUE * voltage
            "max_hex_value": ("FFFFF", ((int("FFFFF", 16) - 2 * MAX_ADC_VALUE) / MAX_ADC_VALUE) * input_voltage) # Example: FFFFF (1048575) -> adjusted
        }

        for name, (hex_str, expected_val) in test_cases.items():
            with self.subTest(msg=name, hex_str=hex_str):
                result = self.adc._convert_data(hex_str, input_voltage)
                self.assertEqual(len(result), 1)
                self.assertAlmostEqual(result[0], expected_val, places=5)

        hex_multi = test_cases["zero"][0] + test_cases["positive_near_max"][0] + test_cases["negative_max_boundary"][0]
        results = self.adc._convert_data(hex_multi, input_voltage)
        self.assertEqual(len(results), 3)
        self.assertAlmostEqual(results[0], test_cases["zero"][1])
        self.assertAlmostEqual(results[1], test_cases["positive_near_max"][1])
        self.assertAlmostEqual(results[2], test_cases["negative_max_boundary"][1])

    # --- _parse_data の直接テスト ---
    def test_parse_data_valid(self):
        original_voltage = self.adc.settings[0].input_voltage
        self.adc.settings[0].input_voltage = 10.0
        
        hex_payload = "12345" # (74565 dec)
        expected_val = (int("12345",16) / 524288) * 10.0
        line = f"*400{hex_payload}#\n".encode('ascii') # Channel 0
        ch, data = self.adc._parse_data(line)
        
        self.assertEqual(ch, 0)
        self.assertIsNotNone(data)
        self.assertEqual(len(data), 1)
        self.assertAlmostEqual(data[0], expected_val, places=5)
        
        self.adc.settings[0].input_voltage = original_voltage

    def test_parse_data_invalid_conditions(self):
        test_cases = [
            (b"!40012345#\n", "Cannot parse data: !40012345#", None, ValueError), # Invalid start
            (b"*4001234#\n", "Cannot parse data: *4001234#", None, IndexError),     # Payload not multiple of 5 (implicit via string slicing)
            (b"*40012345\n", "Cannot parse data: *40012345", None, None),      # Missing # (strip might remove \n, then no #)
            (b"*40X12345#\n", None, ValueError, None), # Invalid channel char 'X'
        ]
        
        for line, log_msg, expected_exc, parse_exc in test_cases:
            with self.subTest(line=line):
                if log_msg: # Expecting an error log
                    with self.assertLogs(logger='pyadio.adc', level='ERROR') as cm:
                        if parse_exc: # If parsing itself (e.g. int()) raises an error before returning None
                            with self.assertRaises(parse_exc):
                                self.adc._parse_data(line)
                        else:
                             self.assertIsNone(self.adc._parse_data(line))
                    if log_msg and not parse_exc: # Only check log if parse_exc didn't happen or wasn't expected
                         self.assertTrue(any(log_msg in message for message in cm.output))
                elif expected_exc: # Expecting specific exception from int() etc.
                    with self.assertRaises(expected_exc):
                        self.adc._parse_data(line)


    def test_parse_data_channel_out_of_bounds(self):
        num_channels = self.mock_adio_config.ADC_CH_NUM # e.g. 16
        line_out_of_range = f"*40{num_channels:X}12345#\n".encode('ascii') # Channel 16 (0-15 valid)
        
        with self.assertLogs(logger='pyadio.adc', level='ERROR') as cm:
            result = self.adc._parse_data(line_out_of_range)
        self.assertIsNone(result)
        self.assertTrue(any(f"Invalid channel number parsed: {num_channels}" in message for message in cm.output))

    # --- Writer Exception Handling (Example) ---
    async def test_write_operations_connection_error_propagation(self):
        # writerをクローズ状態にして、ConnectionResetErrorを発生させる
        self.mock_writer.close() 
        
        with self.assertRaises(ConnectionResetError):
            await self.adc._set_chunk_size(0, 128) # write/drain を使用するメソッド

        # drainが呼ばれる前にwriteでエラーになるので、drain_callsは0のまま
        self.assertEqual(self.mock_writer.drain_calls, 0)


if __name__ == '__main__':
    unittest.main()

```
