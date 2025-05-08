import os
import sys

import cv2
from PyQt5 import QtCore, QtWidgets
from PyQt5.QtGui import QImage, QPixmap



class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)

        # Khởi tạo camera và bộ phân loại khuôn mặt
        self.capture = None
        self.face_detector = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_frame)

        # Kết nối các nút button với các hàm xử lý
        self.button_start.clicked.connect(self.start_video)
        self.button_stop.clicked.connect(self.stop_video)

        # Đường dẫn đến thư mục dataset
        self.dataset_path = r"D:\NCKH Dec 2024\my_pythonProject\dataset"
        if not os.path.exists(self.dataset_path):
            os.makedirs(self.dataset_path)

        self.face_id = None
        self.count = 0

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

    def update_frame(self):
        if self.capture is not None:
            ret, img = self.capture.read()
            if ret:
                # Chuyển đổi hình ảnh sang màu xám
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

                # Phát hiện khuôn mặt
                faces = self.face_detector.detectMultiScale(gray, 1.3, 5)

                for (x, y, w, h) in faces:
                    # Vẽ hình chữ nhật quanh khuôn mặt
                    cv2.rectangle(img, (x, y), (x+w, y+h), (255, 0, 0), 2)
                    self.count += 1

                    # Lưu ảnh khuôn mặt
                    image_path = os.path.join(self.dataset_path, f"dataset.User.{self.face_id}.{self.count}.jpg")
                    cv2.imwrite(image_path, gray[y:y+h, x:x+w])

                # Chuyển đổi hình ảnh từ BGR sang RGB để hiển thị
                frame_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                h, w, ch = frame_rgb.shape
                bytes_per_line = ch * w
                q_image = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format_RGB888)
                self.label.setPixmap(QPixmap.fromImage(q_image))

                # Kiểm tra số lượng ảnh và dừng nếu đủ 30 ảnh
                if self.count >= 30:
                   self.stop_video()

if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
