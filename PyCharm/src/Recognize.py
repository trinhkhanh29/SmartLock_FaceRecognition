import cv2
import numpy as np
import os
import sys
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, storage


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


# Tải danh sách tên từ Firebase
def load_names_from_firebase(bucket):
    """Tải danh sách tên từ Firebase Storage"""
    names = ['Unknown']  # ID 0 mặc định là Unknown
    id_name_map = {}

    # Lấy tất cả file trong thư mục faces/
    blobs = bucket.list_blobs(prefix='faces/')

    for blob in blobs:
        # Tên file ví dụ: faces/1/trinh_1_20250508_123456.jpg
        filename = blob.name
        parts = filename.split('/')

        if len(parts) < 3:
            print(f"[WARNING] Tên tệp không hợp lệ trên Firebase: {filename}")
            continue

        try:
            # Lấy face_id từ tên thư mục (phần thứ hai: 1 trong faces/1/trinh_1_...)
            user_id = int(parts[1])
            # Lấy user_name từ tên file (trinh trong faces/1/trinh_1_20250508_123456.jpg)
            file_parts = parts[2].split('_')
            user_name = file_parts[0]  # Phần đầu tiên trước dấu "_"
            id_name_map[user_id] = user_name
        except (ValueError, IndexError) as e:
            print(f"[WARNING] Không thể phân tích ID hoặc tên từ tệp trên Firebase: {filename}, {str(e)}")
            continue

    if id_name_map:
        max_id = max(id_name_map.keys())
        names = ['Unknown'] * (max_id + 1)
        for user_id, name in id_name_map.items():
            names[user_id] = name

    return names


def get_model_paths():
    """Lấy đường dẫn tuyệt đối tới các file mô hình"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    models_dir = os.path.abspath(os.path.join(base_dir, "..", "models"))

    proto_path = os.path.join(models_dir, "deploy.prototxt")
    model_path = os.path.join(models_dir, "res10_300x300_ssd_iter_140000_fp16.caffemodel")

    return proto_path, model_path


def check_model_files():
    """Kiểm tra sự tồn tại của các file mô hình"""
    proto_path, model_path = get_model_paths()

    if not os.path.exists(proto_path):
        print(f"[ERROR] Không tìm thấy file prototxt tại: {proto_path}")
        return False

    if not os.path.exists(model_path):
        print(f"[ERROR] Không tìm thấy file model tại: {model_path}")
        return False

    print("[SUCCESS] Tất cả file mô hình đã sẵn sàng")
    return True


def load_deep_face_detector():
    """Load DNN-based face detector với xử lý lỗi chi tiết"""
    proto_path, model_path = get_model_paths()

    if not check_model_files():
        print("[WARNING] Sử dụng Haar Cascade thay thế")
        return None

    try:
        net = cv2.dnn.readNetFromCaffe(proto_path, model_path)
        print("[INFO] Đã tải thành công DNN model")
        return net
    except Exception as e:
        print(f"[ERROR] Lỗi khi tải DNN model: {str(e)}")
        return None


def detect_faces_dnn(net, frame, conf_threshold=0.7):
    """Detect faces using DNN model"""
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
    net.setInput(blob)
    detections = net.forward()
    faces = []

    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2]
        if confidence > conf_threshold:
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            (x, y, x2, y2) = box.astype("int")
            faces.append((x, y, x2 - x, y2 - y))

    return faces


def preprocess_face(face_img):
    """Enhance face image for better recognition"""
    if len(face_img.shape) > 2:
        face_img = cv2.cvtColor(face_img, cv2.COLOR_BGR2GRAY)

    face_img = cv2.equalizeHist(face_img)

    gamma = 1.5
    inv_gamma = 1.0 / gamma
    table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
    face_img = cv2.LUT(face_img, table)

    return face_img


def main():
    try:
        # Khởi tạo Firebase
        try:
            bucket = initialize_firebase()
        except Exception as e:
            print(f"[ERROR] Firebase initialization failed: {str(e)}")
            sys.exit(1)

        # Initialize face recognizer
        try:
            recognizer = cv2.face.LBPHFaceRecognizer_create(
                radius=2,
                neighbors=16,
                grid_x=8,
                grid_y=8,
                threshold=90
            )
        except AttributeError:
            print("[ERROR] OpenCV face module not found.")
            print("Please install opencv-contrib-python with:")
            print("pip install opencv-contrib-python")
            sys.exit(1)

        # Load trained model
        if not os.path.exists('trainer/trainer.yml'):
            print("[ERROR] Trainer file not found. Please train the model first.")
            sys.exit(1)

        recognizer.read('trainer/trainer.yml')

        # Load face detector (try DNN first, fallback to Haar)
        face_detector = load_deep_face_detector()
        if face_detector is None:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            if face_cascade.empty():
                print("[ERROR] Could not load any face detector.")
                sys.exit(1)

        # Load names from Firebase
        names = load_names_from_firebase(bucket)
        print(f"[INFO] Loaded names from Firebase: {names}")

        # Initialize camera
        cam = cv2.VideoCapture(0)
        if not cam.isOpened():
            print("[ERROR] Could not open camera.")
            sys.exit(1)

        cam.set(3, 1280)  # width
        cam.set(4, 720)  # height

        min_face_size = 100

        print("\n[INFO] Face recognition started. Press ESC to exit.")

        frame_count = 0
        start_time = datetime.now()

        while True:
            try:
                ret, frame = cam.read()
                if not ret:
                    print("[ERROR] Could not read frame.")
                    break

                frame = cv2.flip(frame, 1)

                frame_count += 1
                elapsed_time = (datetime.now() - start_time).total_seconds()
                fps = frame_count / elapsed_time

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                if face_detector is not None:
                    faces = detect_faces_dnn(face_detector, frame)
                else:
                    faces = face_cascade.detectMultiScale(
                        gray,
                        scaleFactor=1.1,
                        minNeighbors=6,
                        minSize=(min_face_size, min_face_size),
                        flags=cv2.CASCADE_SCALE_IMAGE
                    )

                for (x, y, w, h) in faces:
                    if w < min_face_size or h < min_face_size:
                        continue

                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                    face_roi = gray[y:y + h, x:x + w]
                    processed_face = preprocess_face(face_roi)

                    id, confidence = recognizer.predict(processed_face)

                    confidence_percent = max(0, min(100, 100 - confidence))

                    if confidence < 80:
                        name = names[id] if id < len(names) else f"ID_{id}"
                        color = (0, 255, 0)
                        if confidence < 50:
                            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 4)
                    else:
                        name = "Unknown"
                        color = (0, 0, 255)

                    cv2.putText(frame, name, (x + 5, y - 15),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                    cv2.putText(frame, f"{confidence_percent:.1f}%",
                                (x + 5, y + h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

                cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

                cv2.imshow('Face Recognition - High Accuracy Mode', frame)

                key = cv2.waitKey(10)
                if key == 27 or key == ord('q'):
                    break

            except KeyboardInterrupt:
                print("\n[INFO] Program interrupted by user.")
                break
            except Exception as e:
                print(f"[ERROR] {str(e)}")
                break

    finally:
        if 'cam' in locals() and cam.isOpened():
            cam.release()
        cv2.destroyAllWindows()
        print("\n[INFO] Program exited cleanly.")


if __name__ == "__main__":
    main()