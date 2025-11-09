# filepath: c:\Users\PC\source\repos\NCKH-2025\SmartLock_FaceRecognition\PyCharm\src\Collect.py
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
import os
import time
import serial
from dotenv import load_dotenv

# Nạp biến môi trường
env_path = os.path.join(os.path.dirname(__file__), '../.env/config.env')
load_dotenv(env_path)

EXPECTED_PIN = os.getenv('EXPECTED_PIN', '2828')

def init_serial(port='COM4', baudrate=115200):
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"[INFO] Đã kết nối Serial tại {port}")
        return ser
    except serial.SerialException as e:
        print(f"[ERROR] Không thể kết nối Serial: {e}")
        return None

def send_serial_command(ser, command):
    if ser and ser.is_open:
        ser.write(f"{command}\n".encode())
        print(f"[INFO] Đã gửi: {command}")

def main():
    print("[INFO] Bắt đầu quá trình thu thập khuôn mặt...")
    
    ser = init_serial()
    if not ser:
        print("[ERROR] Không thể kết nối với ESP32.")
        return
    
    # Gửi yêu cầu nhập PIN
    send_serial_command(ser, "PIN_REQUIRED")
    print("[INFO] Đang chờ người dùng nhập PIN trên ESP32...")
    
    received_pin = ""
    start_wait = time.time()
    
    while time.time() - start_wait < 30:
        if ser.in_waiting > 0:
            response = ser.readline().decode('utf-8').strip()
            print(f"[DEBUG] ESP32 Response: {response}")
            
            if response.startswith("PIN_ENTERED:"):
                received_pin = response.replace("PIN_ENTERED:", "").strip()
                print(f"[INFO] Đã nhận PIN từ ESP32: {received_pin}")
                break
            
            if "PIN_TIMEOUT" in response:
                print("[FAIL] Người dùng không nhập PIN kịp thời.")
                send_serial_command(ser, "FAIL")
                ser.close()
                return
    
    # Kiểm tra PIN
    if received_pin != EXPECTED_PIN:
        print(f"[FAIL] PIN sai! Nhận: {received_pin}, Mong đợi: {EXPECTED_PIN}")
        send_serial_command(ser, "FAIL")
        ser.close()
        return
    
    print("[SUCCESS] PIN chính xác! Bắt đầu thu thập khuôn mặt...")
    send_serial_command(ser, "SUCCESS")
    
    # TODO: Thêm code thu thập khuôn mặt ở đây
    # Ví dụ: Mở camera, chụp ảnh, lưu vào Firebase, v.v.
    
    print("[INFO] Quá trình thu thập hoàn tất.")
    ser.close()

if __name__ == "__main__":
    main()