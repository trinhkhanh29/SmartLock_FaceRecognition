import keyboard
import cv2
import sys
import os
import time
from threading import Thread
import importlib.util

# Định nghĩa FILE_PATHS dựa trên thư mục chứa main.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_PATHS = {
    '1': os.path.join(BASE_DIR, 'facedetect.py'),
    '2': os.path.join(BASE_DIR, 'Recognize.py'),
    '3': os.path.join(BASE_DIR, 'telegram_control.py')
}

# Kiểm tra sự tồn tại của các file
for key, path in FILE_PATHS.items():
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        print(f"[ERROR] File not found for mode {key}: {abs_path}")
        sys.exit(1)

# Biến trạng thái toàn cục
current_mode = None
running = True
cam = None

# Hàm nhập module động
def load_module(file_path, module_name):
    abs_path = os.path.abspath(file_path)
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Tải các module
try:
    facedetect = load_module(FILE_PATHS['1'], 'facedetect')
    Recognize = load_module(FILE_PATHS['2'], 'Recognize')
    telegram_control = load_module(FILE_PATHS['3'], 'telegram_control')
except FileNotFoundError as e:
    print(e)
    sys.exit(1)

# Hàm hiển thị menu
def display_menu():
    print("\n=== MENU CHÍNH ===")
    print("1. Thu thập khuôn mặt (facedetect.py)")
    print("2. Nhận diện khuôn mặt (Recognize.py)")
    print("3. Điều khiển cửa qua Telegram (telegram_control.py)")
    print("Nhấn phím 1, 2, hoặc 3 để chọn. Nhấn ESC để thoát.")
    print("==================\n")

# Hàm giải phóng tài nguyên
def cleanup():
    global cam
    if cam and cam.isOpened():
        cam.release()
    cv2.destroyAllWindows()
    # Đóng kết nối serial nếu có
    if hasattr(Recognize, 'ser') and Recognize.ser and Recognize.ser.is_open:
        Recognize.ser.close()
    if hasattr(telegram_control, 'ser') and telegram_control.ser and telegram_control.ser.is_open:
        telegram_control.ser.close()

# Hàm chạy mode được chọn
def run_mode(mode):
    global cam, current_mode
    cleanup()  # Giải phóng tài nguyên trước khi chạy mode mới
    current_mode = mode
    print(f"[INFO] Chuyển sang mode: {mode}")

    try:
        if mode == '1':
            facedetect.main()
        elif mode == '2':
            Recognize.main()
        elif mode == '3':
            telegram_control.main()
    except Exception as e:
        print(f"[ERROR] Lỗi khi chạy {mode}: {str(e)}")
    finally:
        cleanup()

# Hàm xử lý phím bấm
def handle_key_press():
    global running, current_mode
    while running:
        if keyboard.is_pressed('1'):
            if current_mode != '1':
                run_mode('1')
        elif keyboard.is_pressed('2'):
            if current_mode != '2':
                run_mode('2')
        elif keyboard.is_pressed('3'):
            if current_mode != '3':
                run_mode('3')
        elif keyboard.is_pressed('esc'):
            print("[INFO] Thoát chương trình...")
            running = False
            cleanup()
            break
        time.sleep(0.1)  # Giảm tải CPU

def main():
    global running
    display_menu()
    print("Nhấn 1, 2, 3 để chọn chức năng hoặc ESC để thoát.")

    # Bắt đầu luồng xử lý phím bấm
    key_thread = Thread(target=handle_key_press)
    key_thread.daemon = True
    key_thread.start()

    # Giữ chương trình chạy cho đến khi thoát
    try:
        while running:
            time.sleep(0.1)
    except KeyboardInterrupt:
        running = False
        cleanup()
        print("[INFO] Chương trình đã dừng.")

if __name__ == "__main__":
    main()