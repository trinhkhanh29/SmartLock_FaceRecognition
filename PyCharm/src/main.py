import os
import subprocess
import sys


def display_menu():
    print("\nSmartLock Face Recognition")
    print("1. Thu thập dữ liệu khuôn mặt (facedetect.py)")
    print("2. Nhận diện khuôn mặt (Recognize.py)")
    print("Nhập lựa chọn (1 hoặc 2, nhấn 0 để thoát): ")


def run_script(script_name):
    script_path = os.path.join(os.path.dirname(__file__), script_name)
    if not os.path.exists(script_path):
        print(f"[ERROR] File {script_name} không tồn tại tại: {script_path}")
        return False
    try:
        subprocess.run([sys.executable, script_path], check=True)
        print(f"[INFO] Đã chạy {script_name} thành công.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Lỗi khi chạy {script_name}: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Lỗi không xác định khi chạy {script_name}: {e}")
        return False


def main():
    while True:
        display_menu()
        choice = input(">> ").strip()

        if choice == '0':
            print("[INFO] Thoát chương trình.")
            break
        elif choice == '1':
            run_script("facedetect.py")
        elif choice == '2':
            run_script("Recognize.py")
        else:
            print("[ERROR] Lựa chọn không hợp lệ. Vui lòng nhập 0, 1 hoặc 2.")


if __name__ == "__main__":
    main()