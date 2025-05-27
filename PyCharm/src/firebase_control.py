import firebase_admin
from firebase_admin import credentials, db
import time
import sys

# Khởi tạo Firebase
try:
    cred = credentials.Certificate('.env/firebase_credentials.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://smartlockfacerecognition-default-rtdb.asia-southeast1.firebasedatabase.app/'
    })
except Exception as e:
    print(f"[Firebase] Lỗi khi khởi tạo Firebase: {e}")
    sys.exit(1)

# Tham chiếu đến node lệnh điều khiển
control_ref = db.reference('esp32/control')
response_ref = db.reference('esp32/response')

def send_command(cmd):
    """
    Gửi lệnh mới đến ESP32 qua Firebase.
    """
    data = {
        'command': cmd,
        'timestamp': int(time.time())
    }
    try:
        control_ref.set(data)
        print(f"[Firebase] Đã gửi lệnh: {data}")
    except Exception as e:
        print(f"[Firebase] Lỗi khi gửi lệnh: {e}")

def listen_response(poll_interval=1, timeout=60):
    """
    Lắng nghe phản hồi từ ESP32 trong khoảng timeout (giây).
    """
    last_response = None
    start_time = time.time()
    print("[Firebase] Bắt đầu lắng nghe phản hồi từ ESP32...")
    try:
        while time.time() - start_time < timeout:
            try:
                response = response_ref.get()
            except Exception as e:
                print(f"[Firebase] Lỗi khi lấy phản hồi: {e}")
                response = None

            if response != last_response:
                print(f"[Firebase] Phản hồi mới từ ESP32: {response}")
                last_response = response
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\n[Firebase] Dừng lắng nghe.")
    print("[Firebase] Kết thúc lắng nghe sau timeout.")

if __name__ == "__main__":
    # Gửi lệnh mở cửa làm ví dụ
    send_command("OPEN_DOOR")

    # Bắt đầu lắng nghe phản hồi tối đa 60 giây
    listen_response()
