import re
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Thread

import matplotlib.pyplot as plt
import serial

# シリアルポートの設定
port = "/dev/tty.usbserial-FT9I7HE7"  # 使用するCOMポート
ser = serial.Serial(port, timeout=0)

# バッファのクリア
ser.reset_input_buffer()
ser.reset_output_buffer()


# 蓄積ストップコマンドの送信と応答確認
def send_command(command, display_response=True):
    ser.write(command.encode())
    start_time = time.time()
    while time.time() - start_time < 2:
        response = ser.readline().decode().strip()
        if response:
            if display_response:
                print("Response:", response)
            return response
    print("No response within 2 seconds. Sending recovery command: *f0000001#")
    ser.write("*f0000001#".encode())
    return None


print("\nSending accumulation stop command")
send_command("*40030000#")

# 転送件数設定コマンドの送信
for i in range(16):
    command = f"*10{i:X}007ff#"
    print(f"Sending command: {command}")
    send_command(command)

# 変換速度設定コマンドの送信
print("\nSending conversion speed setting commands")
send_command("*00000006#")
send_command("*00100006#")


# 蓄積開始コマンドの送信
print("\nSending accumulation start command")
send_command("*40020000#")

# 生データの保存ファイル
output_file = "received_data.txt"


# データ受信スレッド
def receive_data():
    with open(output_file, "wb") as file:
        while True:
            try:
                if ser.is_open:  # シリアルポートが開かれているか確認
                    if ser.in_waiting > 0:
                        chunk = ser.read(ser.in_waiting)
                        # chunk = ser.read(10241)
                        # chunk = ser.readline()
                        file.write(chunk)
                        file.flush()  # ファイルにすぐ書き込む
                else:
                    break
            except serial.SerialException as e:
                print(f"Serial exception: {e}")
                break


# スレッド開始
print("Starting data reception...")
receiver_thread = Thread(target=receive_data, daemon=True)
receiver_thread.start()

# データ受信コマンドを送信し、応答を表示しない
# data_command = "*400100aa#*401100aa#*402100aa#*403100aa#*404100aa#*405100aa#*406100aa#*407100aa#*408100aa#*409100aa#*40a100aa#*40b100aa#*40c100aa#*40d100aa#*40e100aa#*40f100aa#"
# data_command = "*40010002#*40110002#*40210002#*40310002#*40410002#*40510002#*40610002#*40710002#*40810002#*40910002#*40a10002#*40b10002#*40c10002#*40d10002#*40e10002#*40f10002#"
# data_command = "*40010003#*40110003#*40210003#*40310003#*40410003#*40510003#*40610003#*40710003#*40810003#*40910003#*40a10003#*40b10003#*40c10003#*40d10003#*40e10003#*40f10003#"
# data_command = "*400100aa#*401100aa#"
# data_command = "*40010320#*40110320#*40210320#*40310320#*40410320#*40510320#*40610320#*40710320#"
data_command = "*40010027#*40110027#*40210027#*40310027#*40410027#*40510027#*40610027#*40710027#*40810027#*40910027#*40A10027#*40B10027#*40C10027#*40D10027#*40E10027#*40F10027#"
ser.write(data_command.encode())

# def send_data_request():
#     for i in range(16):
#         ser.write(f"*40{i:X}10027#".encode())


# executor = ThreadPoolExecutor(max_workers=2)
# executor.submit(send_data_request)
# receiver_thread.join(timeout=11)  # タイムアウトを2秒に設定

# ファイルからデータを読み込み
with open(output_file, "rb") as file:
    raw_data = file.read()
    print(len(raw_data), "bytes received")
    raw_data = raw_data.decode()

# データ解析部分
pattern = r"\*40([0-9a-fA-F])([0-9a-fA-F]{10,})#"
matches = re.findall(pattern, raw_data)

if not matches:
    print(
        "Warning: No matching data found. Check if data format is correct or if data was received."
    )

# チャネルごとのデータ辞書（大文字対応）
channel_data = {hex(i)[-1].upper(): [] for i in range(16)}


def convert_to_voltage(adc_value):
    MAX_ADC_VALUE = 524288  # 2^19
    if adc_value >= MAX_ADC_VALUE:
        signed_adc = adc_value - (MAX_ADC_VALUE * 2)
    else:
        signed_adc = adc_value
    voltage = (signed_adc / MAX_ADC_VALUE) * 5  # ±5V範囲
    return voltage


for match in matches:
    channel = match[0].upper()
    values = match[1]
    for i in range(0, len(values), 5):
        hex_value = values[i : i + 5]
        try:
            adc_value = int(hex_value, 16)
            voltage = convert_to_voltage(adc_value)  # 電圧に変換
            channel_data[channel].append(voltage)
        except ValueError:
            pass

# データ件数の表示
print("\n--- Data Count per Channel ---")
total_data_count = 0
for channel, values in channel_data.items():
    count = len(values)
    total_data_count += count
    print(f"Channel {channel}: {count} samples")

print(f"Total Data Count: {total_data_count} samples")

# 折れ線グラフを描画
plt.figure(figsize=(12, 8))
has_data = False
for channel, values in channel_data.items():
    if values:
        plt.plot(values, label=f"Channel {channel}")
        has_data = True

if has_data:
    plt.xlabel("Sample Number")
    plt.ylabel("ADC Value")
    plt.title("ADC Data by Channel")
    plt.legend()
    plt.show()
else:
    print("No data to plot.")

# バッファのクリア
ser.reset_input_buffer()
ser.reset_output_buffer()
ser.close()  # スレッドの終了確認後に通信終了
