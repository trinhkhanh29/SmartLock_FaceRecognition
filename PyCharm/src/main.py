from threading import Thread
import time
import sys
import os
import importlib.util
import traceback
import keyboard  # Thêm thư viện để bắt phím

# --- HÀM LOAD MODULE ---
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

# --- ĐƯỜNG DẪN CÁC FILE ---
RECOGNIZE_PATH = os.path.join(BASE_DIR, 'Recognize.py')
TELEGRAM_PATH = os.path.join(BASE_DIR, 'telegram_control.py')
ADDFACE_PATH = os.path.join(BASE_DIR, 'facedetect.py')

# --- LOAD MODULE ---
recognize = load_module(RECOGNIZE_PATH, 'Recognize')
telegram_control = load_module(TELEGRAM_PATH, 'telegram_control')

# --- HÀM CHẠY CÁC MODULE ---
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


# --- HÀM NGHE BÀN PHÍM ---
def keyboard_listener():
    print("[KEYBOARD] Hệ thống sẵn sàng. Bấm:")
    print("   [1] → Thêm khuôn mặt mới")
    print("   [2] → Khởi động lại nhận diện")
    print("   [Q] → Thoát chương trình")

    while True:
        try:
            if keyboard.is_pressed('1'):
                print("[KEYBOARD] → Phím 1 được bấm: thêm khuôn mặt mới")
                os.system(f'python "{ADDFACE_PATH}"')
                time.sleep(1)

            elif keyboard.is_pressed('2'):
                print("[KEYBOARD] → Phím 2 được bấm: khởi động lại nhận diện")
                Thread(target=start_recognition, daemon=True).start()
                time.sleep(1)

            elif keyboard.is_pressed('q'):
                print("[KEYBOARD] → Nhấn Q: thoát chương trình.")
                os._exit(0)

            time.sleep(0.1)
        except Exception as e:
            print(f"[ERROR] Trong keyboard listener: {e}")
            time.sleep(1)


# --- HÀM MAIN ---
def main():
    print("[INFO] Khởi động hệ thống SmartLock...")

    # Tạo các luồng
    thread_recognize = Thread(target=start_recognition, daemon=True)
    thread_telegram = Thread(target=start_telegram_control, daemon=True)
    thread_keyboard = Thread(target=keyboard_listener, daemon=True)

    # Chạy các luồng
    thread_recognize.start()
    thread_telegram.start()
    thread_keyboard.start()

    try:
        while True:
            time.sleep(1)  # giữ cho main thread sống
    except KeyboardInterrupt:
        print("\n[INFO] Dừng chương trình bởi người dùng.")


if __name__ == '__main__':
    main()
