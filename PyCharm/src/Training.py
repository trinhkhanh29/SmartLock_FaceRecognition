import cv2
import numpy as np
import os
from PIL import Image
import firebase_admin
from firebase_admin import credentials, storage
import urllib.request
import io


# Khởi tạo Firebase
def initialize_firebase():
    cred_path = os.path.join(os.path.dirname(__file__), '../.env/firebase_credentials.json')
    if not os.path.exists(cred_path):
        raise FileNotFoundError("[ERROR] Firebase credentials file not found.")

    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'smartlockfacerecognition.firebasestorage.app'  # Sử dụng bucket chính xác
    })
    return storage.bucket()


# Tải danh sách hình ảnh từ Firebase
def download_images_from_firebase(bucket):
    # Đường dẫn trên Firebase Storage (thư mục faces/)
    blobs = bucket.list_blobs(prefix='faces/')  # Lấy tất cả file trong thư mục faces/

    face_samples = []
    ids = []
    detector = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    for blob in blobs:
        # Lấy tên file từ blob (ví dụ: faces/1/trinh_1_20250508_123456.jpg)
        filename = blob.name
        parts = filename.split('/')

        if len(parts) < 3:
            print(f"[ERROR] Tên tệp không hợp lệ trên Firebase: {filename}")
            continue

        # Lấy face_id từ tên thư mục (phần thứ hai: 1 trong faces/1/trinh_1_...)
        try:
            face_id = int(parts[1])
        except ValueError:
            print(f"[ERROR] Không thể lấy ID từ tên tệp trên Firebase: {filename}")
            continue

        # Tải hình ảnh từ Firebase
        try:
            # Tạo URL công khai hoặc tải trực tiếp file
            blob.make_public()  # Nếu file không công khai, cần làm công khai tạm thời
            image_url = blob.public_url
            print(f"[INFO] Đang tải hình ảnh: {image_url}")

            # Tải hình ảnh từ URL
            with urllib.request.urlopen(image_url) as url_response:
                image_data = url_response.read()
                image_array = np.asarray(bytearray(image_data), dtype=np.uint8)
                img = cv2.imdecode(image_array, cv2.IMREAD_GRAYSCALE)

            if img is None:
                print(f"[ERROR] Không thể tải hoặc giải mã hình ảnh: {filename}")
                continue

            # Phát hiện khuôn mặt
            faces = detector.detectMultiScale(img)

            for (x, y, w, h) in faces:
                face_samples.append(img[y:y + h, x:x + w])
                ids.append(face_id)

        except Exception as e:
            print(f"[ERROR] Lỗi khi tải hình ảnh từ Firebase: {filename}, {str(e)}")
            continue

    return face_samples, np.array(ids)


def main():
    # Khởi tạo Firebase
    try:
        bucket = initialize_firebase()
    except Exception as e:
        print(f"[ERROR] Firebase initialization failed: {str(e)}")
        return

    # Khởi tạo nhận diện khuôn mặt bằng LBPH
    recognizer = cv2.face.LBPHFaceRecognizer_create()

    print("\n[INFO] Đang tải dữ liệu từ Firebase và training...")
    faces, ids = download_images_from_firebase(bucket)

    # Kiểm tra xem có khuôn mặt nào được thu thập hay không
    if len(faces) == 0 or len(ids) == 0:
        print("[ERROR] Không có dữ liệu để train từ Firebase.")
        return

    # Huấn luyện mô hình
    recognizer.train(faces, ids)

    # Lưu mô hình huấn luyện
    trainer_path = 'trainer/trainer.yml'
    if not os.path.exists('trainer'):
        os.makedirs('trainer')
    recognizer.save(trainer_path)

    print(f"\n[INFO] {len(np.unique(ids))} khuôn mặt được train. Thoát")


if __name__ == "__main__":
    main()