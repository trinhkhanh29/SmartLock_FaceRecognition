import firebase_admin
from firebase_admin import credentials, db
import time

# Khởi tạo Firebase
cred = credentials.Certificate('PyCharm/.env/firebase_credentials.json')
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://smartlockfacerecognition-default-rtdb.asia-southeast1.firebasedatabase.app/'  # Thay đúng URL Realtime DB
})

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
    control_ref.set(data)
    print(f"[Firebase] Đã gửi lệnh: {data}")

def listen_response(poll_interval=5):
    """
    Lắng nghe phản hồi từ ESP32.
    """
    last_response = None
    print("[Firebase] Bắt đầu lắng nghe phản hồi từ ESP32...")
    try:
        while True:
            response = response_ref.get()
            if response != last_response:
                print(f"[Firebase] Phản hồi mới từ ESP32: {response}")
                last_response = response
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        print("\n[Firebase] Dừng lắng nghe.")

if __name__ == "__main__":
    # Gửi lệnh mở cửa làm ví dụ
    send_command("OPEN_DOOR")

    # Bắt đầu lắng nghe phản hồi
    listen_response()