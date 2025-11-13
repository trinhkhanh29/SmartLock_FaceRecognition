import sys
import os
import json
import threading
from Recognize import main as recognize_main
import signal

# Biến toàn cục để quản lý trạng thái
is_running = False
process_thread = None


def start_face_recognition():
    """Khởi động nhận diện khuôn mặt trong thread riêng"""
    global is_running, process_thread

    if is_running:
        return {"status": "error", "message": "Nhận diện đang chạy"}

    try:
        is_running = True
        process_thread = threading.Thread(target=recognize_main, daemon=True)
        process_thread.start()

        return {"status": "success", "message": "Đã khởi động nhận diện khuôn mặt"}

    except Exception as e:
        is_running = False
        return {"status": "error", "message": f"Lỗi: {str(e)}"}


def stop_face_recognition():
    """Dừng nhận diện khuôn mặt"""
    global is_running, process_thread

    if not is_running:
        return {"status": "error", "message": "Nhận diện không chạy"}

    try:
        # Gửi signal để dừng process (cần modify Recognize.py để hỗ trợ)
        is_running = False

        # Đợi thread kết thúc
        if process_thread and process_thread.is_alive():
            process_thread.join(timeout=5)

        return {"status": "success", "message": "Đã dừng nhận diện khuôn mặt"}

    except Exception as e:
        return {"status": "error", "message": f"Lỗi khi dừng: {str(e)}"}


def get_status():
    """Lấy trạng thái hiện tại"""
    return {
        "status": "success",
        "is_running": is_running,
        "message": "Đang chạy" if is_running else "Đã dừng"
    }


# API cho Node.js gọi qua stdin/stdout
if __name__ == "__main__":
    try:
        # Đọc command từ stdin
        command = sys.stdin.read().strip()
        data = json.loads(command) if command else {}

        action = data.get("action", "")

        if action == "start":
            result = start_face_recognition()
        elif action == "stop":
            result = stop_face_recognition()
        elif action == "status":
            result = get_status()
        else:
            result = {"status": "error", "message": "Action không hợp lệ"}

        # Gửi kết quả qua stdout
        print(json.dumps(result))

    except Exception as e:
        print(json.dumps({"status": "error", "message": f"Lỗi hệ thống: {str(e)}"}))