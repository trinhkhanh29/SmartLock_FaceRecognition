from threading import Thread
import time
import sys
import os
import importlib.util

# Load module động
def load_module(file_path, module_name):
    abs_path = os.path.abspath(file_path)
    spec = importlib.util.spec_from_file_location(module_name, abs_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RECOGNIZE_PATH = os.path.join(BASE_DIR, 'Recognize.py')
TELEGRAM_PATH = os.path.join(BASE_DIR, 'telegram_control.py')

recognize = load_module(RECOGNIZE_PATH, 'Recognize')
telegram_control = load_module(TELEGRAM_PATH, 'telegram_control')

def start_recognition():
    print("[INFO] Bắt đầu nhận diện khuôn mặt...")
    recognize.main()

def start_telegram_control():
    print("[INFO] Bắt đầu điều khiển Telegram...")
    telegram_control.main()  # Gọi đồng bộ, không asyncio.run()

def main():
    thread1 = Thread(target=start_recognition)
    thread2 = Thread(target=start_telegram_control)

    thread1.start()
    thread2.start()

    thread1.join()
    thread2.join()

if __name__ == '__main__':
    main()
