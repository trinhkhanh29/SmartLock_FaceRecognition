import cv2
import os
import firebase_admin
from firebase_admin import credentials, storage
from datetime import datetime
from facenet_pytorch import MTCNN
import numpy as np

def initialize_firebase():
    cred_path = os.path.join(os.path.dirname(__file__), '../.env/firebase_credentials.json')
    if not os.path.exists(cred_path):
        raise FileNotFoundError("[ERROR] Firebase credentials file not found.")
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'smartlockfacerecognition.firebasestorage.app'
    })
    return storage.bucket()

def upload_to_firebase(bucket, filepath, face_id, face_name, count):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"[ERROR] File không tồn tại tại: {filepath}")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    firebase_filename = f"faces/{face_id}/{face_id}_{face_name.replace(' ', '_')}_{count}_{timestamp}.jpg"
    print(f"[DEBUG] Tải lên Firebase với tên: {firebase_filename}")
    blob = bucket.blob(firebase_filename)
    blob.upload_from_filename(filepath)
    blob.make_public()
    return blob.public_url

def main():
    # Khởi tạo Firebase
    try:
        bucket = initialize_firebase()
    except Exception as e:
        print(f"[ERROR] Firebase initialization failed: {str(e)}")
        return

    # Khởi tạo camera
    cam = cv2.VideoCapture(1)
    if not cam.isOpened():
        print("[ERROR] Không thể mở camera.")
        return
    cam.set(3, 640)
    cam.set(4, 480)

    # Khởi tạo MTCNN
    try:
        mtcnn = MTCNN(keep_all=False, min_face_size=100, thresholds=[0.6, 0.7, 0.7], factor=0.709)
        print("[INFO] Đã tải MTCNN để phát hiện khuôn mặt.")
    except Exception as e:
        print(f"[ERROR] Không thể tải MTCNN: {str(e)}")
        cam.release()
        return

    # Nhập ID và tên người dùng
    face_id = input('\nEnter user ID (number) >> ').strip()
    if not face_id.isdigit():
        print("[ERROR] ID phải là số.")
        cam.release()
        return
    face_name = input('Enter user name >> ').strip()
    if not face_name:
        print("[ERROR] Tên không được để trống.")
        cam.release()
        return

    print("\n[INFO] Bắt đầu thu thập khuôn mặt... Nhìn vào camera và di chuyển nhẹ để chụp các góc khác nhau.")

    # Tạo thư mục dataset
    dataset_path = os.path.join(os.path.dirname(__file__), '../dataset')
    os.makedirs(dataset_path, exist_ok=True)

    count = 0
    sample_limit = 50
    min_face_size = 100
    optimal_face_size = 200

    try:
        while count < sample_limit:
            ret, frame = cam.read()
            if not ret:
                print("[ERROR] Không thể đọc khung hình.")
                break

            frame = cv2.flip(frame, 1)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Phát hiện khuôn mặt bằng MTCNN
            boxes, probs = mtcnn.detect(frame_rgb)
            if boxes is not None and len(boxes) > 0:
                for box, prob in zip(boxes, probs):
                    if prob < 0.9:
                        print(f"[DEBUG] Bỏ qua khuôn mặt với độ tin cậy thấp: {prob:.2f}")
                        continue
                    x, y, x2, y2 = box.astype(int)
                    w, h = x2 - x, y2 - y
                    if w < min_face_size or h < min_face_size:
                        print(f"[DEBUG] Bỏ qua khuôn mặt nhỏ: {w}x{h}")
                        continue

                    # Vẽ khung quanh khuôn mặt
                    cv2.rectangle(frame, (x, y), (x2, y2), (0, 255, 0), 2)

                    # Lưu ảnh khuôn mặt (màu RGB)
                    if w >= optimal_face_size and h >= optimal_face_size:
                        count += 1
                        filename = f"{face_id}_{face_name.replace(' ', '_')}_{count}.jpg"
                        filepath = os.path.join(dataset_path, filename)
                        print(f"[DEBUG] Lưu ảnh tại: {filepath}")
                        cv2.imwrite(filepath, frame[y:y2, x:x2])

                        # Tải lên Firebase
                        try:
                            public_url = upload_to_firebase(bucket, filepath, face_id, face_name, count)
                            print(f"[INFO] Đã tải lên khuôn mặt {count}/{sample_limit}: {public_url}")
                        except Exception as e:
                            print(f"[ERROR] Không thể tải lên Firebase: {str(e)}")

                        # Hiển thị số lượng ảnh đã thu thập
                        cv2.putText(frame, f"Collected: {count}/{sample_limit}",
                                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                        # Hiển thị vùng khuôn mặt được lưu
                        cv2.imshow('Captured Face', frame[y:y2, x:x2])

            # Hiển thị khung hình chính
            cv2.imshow('Face Collection', frame)

            # Thoát khi nhấn ESC hoặc đủ mẫu
            key = cv2.waitKey(100) & 0xff
            if key == 27 or count >= sample_limit:
                break

    except Exception as e:
        print(f"[ERROR] Lỗi trong quá trình thu thập: {str(e)}")
    finally:
        cam.release()
        cv2.destroyAllWindows()
        print(f"\n[INFO] Đã thu thập {count} mẫu. Chương trình kết thúc.")

if __name__ == "__main__":
    main()