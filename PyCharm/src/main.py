from threading import Thread
import time
import sys
import os
import importlib.util
import traceback

# Load module động từ file
def load_module(file_path, module_name):
    try:
        abs_path = os.path.abspath(file_path)
        spec = importlib.util.spec_from_file_location(module_name, abs_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception as e:
        print(f"[ERROR] Không thể load module {module_name} từ {file_path}: {e}")
        traceback.print_exc()
        return None

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Đường dẫn tuyệt đối đến các script
RECOGNIZE_PATH = os.path.join(BASE_DIR, 'Recognize.py')
TELEGRAM_PATH = os.path.join(BASE_DIR, 'telegram_control.py')

# Load module
recognize = load_module(RECOGNIZE_PATH, 'Recognize')
telegram_control = load_module(TELEGRAM_PATH, 'telegram_control')

def start_recognition():
    print("[INFO] Bắt đầu nhận diện khuôn mặt...")
    if recognize and hasattr(recognize, 'main'):
        recognize.main()
    else:
        print("[ERROR] Không thể khởi động Recognize.")

def start_telegram_control():
    print("[INFO] Bắt đầu điều khiển Telegram...")
    if telegram_control and hasattr(telegram_control, 'main'):
        telegram_control.main()
    else:
        print("[ERROR] Không thể khởi động Telegram.")

def main():
    print("[INFO] Khởi động hệ thống SmartLock...")
    thread1 = Thread(target=start_recognition, daemon=True)
    thread2 = Thread(target=start_telegram_control, daemon=True)

    thread1.start()
    thread2.start()

    try:
        while True:
            time.sleep(1)  # giữ cho main thread sống
    except KeyboardInterrupt:
        print("\n[INFO] Dừng chương trình bởi người dùng.")

if __name__ == '__main__':
    main()
