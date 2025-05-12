#main.py
import os
import sys
import cv2
import requests
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtGui import QImage, QPixmap
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), '../.env/config.env')
if not os.path.exists(env_path):
    print(f"[ERROR] .env file not found at: {env_path}")
else:
    print(f"[INFO] Loading .env file from: {env_path}")
load_dotenv(env_path)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)

        # Thêm các khởi tạo sau:
        self.recognizer = None  # Bộ nhận diện khuôn mặt
        self.names = ['Unknown']  # Danh sách tên người dùng
        self.min_face_size = 100  # Kích thước khuôn mặt tối thiểu
        self.optimal_face_size = 200  # Kích thước tối ưu để nhận diện

        # Khởi tạo bộ nhận diện khuôn mặt
        self.init_face_recognizer()

        # Kiểm tra và load danh sách tên từ file (nếu có)
        self.load_names()
    def setupUi(self, MainWindow):
        # Placeholder for UI setup
        self.setWindowTitle("SmartLock Face Recognition")
        self.setGeometry(100, 100, 800, 600)

        # Initialize label for video display
        self.label = QtWidgets.QLabel(self)
        self.label.setGeometry(50, 50, 640, 480)
        self.label.setStyleSheet("background-color: black;")
        self.label.setAlignment(QtCore.Qt.AlignCenter)

        # Initialize buttons
        self.button_start = QtWidgets.QPushButton("Start", self)
        self.button_start.setGeometry(50, 550, 100, 30)

        self.button_stop = QtWidgets.QPushButton("Stop", self)
        self.button_stop.setGeometry(200, 550, 100, 30)

    def init_face_recognizer(self):
        """Khởi tạo bộ nhận diện khuôn mặt"""
        try:
            self.recognizer = cv2.face.LBPHFaceRecognizer_create()
            # Kiểm tra nếu có file trainer đã tồn tại
            trainer_path = 'trainer/trainer.yml'
            if os.path.exists(trainer_path):
                self.recognizer.read(trainer_path)
                print("[INFO] Đã tải mô hình nhận diện từ file trainer")
        except Exception as e:
            print(f"[ERROR] Không thể khởi tạo bộ nhận diện: {e}")

    def load_names(self):
        """Tải danh sách tên từ file (nếu có)"""
        try:
            names_path = 'names.txt'
            if os.path.exists(names_path):
                with open(names_path, 'r') as f:
                    self.names = [line.strip() for line in f.readlines()]
                print(f"[INFO] Đã tải danh sách tên: {self.names}")
        except Exception as e:
            print(f"[ERROR] Không thể tải danh sách tên: {e}")

    def start_video(self):
        # Nhập ID khuôn mặt từ người dùng
        if self.face_id is None:
            self.face_id, ok = QtWidgets.QInputDialog.getText(self, 'Input', 'Nhập ID Khuôn Mặt:')
            if not ok:
                return

        if self.capture is None:
            self.capture = cv2.VideoCapture(0)  # 0 cho camera mặc định

        # Đặt kích thước hình ảnh
        self.capture.set(3, 640)  # Chiều rộng
        self.capture.set(4, 480)  # Chiều cao

        self.timer.start(30)  # Cập nhật mỗi 30 ms

    def stop_video(self):
        self.timer.stop()
        if self.capture:
            self.capture.release()
            self.capture = None
        self.label.clear()  # Xóa hình ảnh hiển thị
        self.count = 0  # Reset count khi dừng

    def send_telegram_message(self, message):
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            print("[WARNING] Thiếu cấu hình Telegram.")
            return

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message
        }
        try:
            response = requests.post(url, data=payload)
            if response.status_code != 200:
                print(f"[ERROR] Gửi Telegram thất bại: {response.text}")
        except Exception as e:
            print(f"[ERROR] Gửi Telegram gặp lỗi: {e}")

    def update_frame(self):
        if self.capture is not None:
            ret, img = self.capture.read()
            if ret:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                faces = self.face_detector.detectMultiScale(gray, 1.3, 5,
                                                            minSize=(self.min_face_size, self.min_face_size))

                for (x, y, w, h) in faces:
                    cv2.rectangle(img, (x, y), (x + w, y + h), (255, 0, 0), 2)

                    # Nếu đang trong chế độ thu thập dữ liệu
                    if hasattr(self, 'face_id') and self.face_id:
                        self.count += 1
                        image_path = os.path.join(self.dataset_path, f"dataset.User.{self.face_id}.{self.count}.jpg")
                        cv2.imwrite(image_path, gray[y:y + h, x:x + w])

                        if self.count == 1:
                            message = f"[🔓] Đang thu thập dữ liệu khuôn mặt, ID: {self.face_id}."
                            self.send_telegram_message(message)

                    # Nếu đang trong chế độ nhận diện
                    elif self.recognizer:
                        face_roi = gray[y:y + h, x:x + w]
                        try:
                            id, confidence = self.recognizer.predict(face_roi)
                            confidence_percent = max(0, min(100, 100 - confidence))

                            if confidence < 70:  # Ngưỡng tin cậy
                                name = self.names[id] if id < len(self.names) else f"ID_{id}"
                                cv2.putText(img, name, (x + 5, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                                cv2.putText(img, f"{confidence_percent:.1f}%", (x + 5, y + h - 5),
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

                                if confidence_percent > 80:  # Chỉ gửi thông báo khi độ tin cậy cao
                                    message = f"[👤] Nhận diện: {name} (ID: {id}, Độ tin cậy: {confidence_percent:.1f}%)"
                                    self.send_telegram_message(message)
                        except Exception as e:
                            print(f"[ERROR] Lỗi nhận diện: {e}")

                # Hiển thị hình ảnh
                frame_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                q_image = QImage(frame_rgb.data, w, h, ch * w, QImage.Format_RGB888)
                self.label.setPixmap(QPixmap.fromImage(q_image))

                if hasattr(self, 'count') and self.count >= 30:
                    self.stop_video()
                    message = f"[✅] Hoàn thành thu thập 30 ảnh cho ID: {self.face_id}"
                    self.send_telegram_message(message)

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
