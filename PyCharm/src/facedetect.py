# PyCharm/src/facedetect.py
import sys
import os
import cv2
import firebase_admin
from firebase_admin import credentials, storage
from datetime import datetime
from facenet_pytorch import MTCNN
import pyttsx3
import numpy as np
import logging
import io

# === Cấu hình stdout UTF-8 cho Windows ===
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# === Logging ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("recognize.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# ========================== TOÀN CỤC ==========================
tts_engine = None
bucket = None


# ========================== FIREBASE ==========================
def initialize_firebase():
    global bucket
    cred_path = os.path.join(os.path.dirname(__file__), '../.env/firebase_credentials.json')

    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"Không tìm thấy file chứng thực: {cred_path}")

    # Đọc bucket từ file .env hoặc fallback
    env_path = os.path.join(os.path.dirname(__file__), '../.env/config.env')
    bucket_name = "smartlockfacerecognition.firebasestorage.app"
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("FIREBASE_STORAGE_BUCKET"):
                    bucket_name = line.split("=")[1].strip().strip('"')

    cred = credentials.Certificate(cred_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {'storageBucket': bucket_name})

    bucket = storage.bucket()
    logging.info(f"Đã kết nối Firebase: {bucket.name}")
    return bucket


# ========================== TTS ==========================
def init_tts_engine():
    global tts_engine
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 1.0)
        voices = engine.getProperty('voices')
        for voice in voices:
            if any(lang in voice.languages for lang in [b'vi', b'vi-vn']) or 'Vietnamese' in voice.name:
                engine.setProperty('voice', voice.id)
                logging.info(f"Đã chọn giọng nói: {voice.name}")
                break
        tts_engine = engine
    except Exception as e:
        logging.warning(f"Không thể khởi tạo TTS: {e}")


def speak(text):
    global tts_engine
    if tts_engine is None:
        init_tts_engine()
    if tts_engine:
        try:
            tts_engine.say(text)
            tts_engine.runAndWait()
        except:
            pass  # Silent fail
    print(f"[VOICE] {text}")


# ========================== UPLOAD ==========================
def upload_to_firebase(filepath, face_id, face_name, count):
    global bucket
    if not os.path.exists(filepath):
        logging.error(f"File không tồn tại: {filepath}")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    firebase_path = f"faces/{face_id}/{face_id}_{face_name.replace(' ', '_')}_{count}_{timestamp}.jpg"

    try:
        blob = bucket.blob(firebase_path)
        blob.upload_from_filename(filepath, content_type='image/jpeg')
        blob.make_public()
        logging.info(f"Đã upload: {firebase_path}")
        return blob.public_url
    except Exception as e:
        logging.error(f"Upload thất bại: {e}")
        return None


# ========================== MAIN ==========================
def main():
    global bucket

    # === Nhận tham số từ Node.js ===
    if len(sys.argv) < 3:
        print("Usage: python facedetect.py <user_id> <user_name>")
        sys.exit(1)

    face_id = sys.argv[1].strip()
    face_name = sys.argv[2].strip()

    if not face_id or not face_name:
        print("ID và Tên không được để trống!")
        sys.exit(1)

    logging.info(f"Bắt đầu thu thập cho: ID={face_id}, Tên={face_name}")

    # === Khởi tạo ===
    try:
        bucket = initialize_firebase()
    except Exception as e:
        logging.error(f"Firebase lỗi: {e}")
        speak("Không thể kết nối Firebase.")
        return

    # === Camera ===
    cam = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    if not cam.isOpened():
        cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
    if not cam.isOpened():
        speak("Không thể mở camera.")
        logging.error("Camera không mở được")
        return

    cam.set(3, 640)
    cam.set(4, 480)

    # === MTCNN ===
    try:
        mtcnn = MTCNN(keep_all=False, min_face_size=80, device='cpu')
        logging.info("MTCNN đã sẵn sàng")
    except Exception as e:
        logging.error(f"MTCNN lỗi: {e}")
        speak("Không thể tải mô hình khuôn mặt.")
        cam.release()
        return

    # === Cấu hình thu thập ===
    directions = [
        ("Nhìn thẳng vào camera", "straight"),
        ("Quay mặt sang trái", "left"),
        ("Quay mặt sang phải", "right"),
        ("Nhìn lên trên", "up"),
        ("Nhìn xuống dưới", "down")
    ]
    images_per_direction = 10
    sample_limit = len(directions) * images_per_direction
    count = 0
    current_dir_idx = 0

    dataset_path = os.path.join(os.path.dirname(__file__), '../dataset')
    os.makedirs(dataset_path, exist_ok=True)

    speak("Bắt đầu thu thập. Hãy nhìn thẳng vào camera.")
    logging.info("Bắt đầu vòng lặp thu thập...")

    try:
        while count < sample_limit:
            ret, frame = cam.read()
            if not ret:
                continue

            frame = cv2.flip(frame, 1)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            boxes, probs = mtcnn.detect(frame_rgb)

            face_detected = False
            if boxes is not None:
                for box, prob in zip(boxes, probs):
                    if prob < 0.9:
                        continue
                    x1, y1, x2, y2 = map(int, box)
                    w, h = x2 - x1, y2 - y1
                    if w < 100 or h < 100:
                        continue

                    face_crop = frame[y1:y2, x1:x2]
                    if face_crop.size == 0:
                        continue

                    # Lưu ảnh
                    count += 1
                    direction_key = directions[current_dir_idx][1]
                    filename = f"{face_id}_{face_name.replace(' ', '_')}_{direction_key}_{count}.jpg"
                    filepath = os.path.join(dataset_path, filename)
                    cv2.imwrite(filepath, face_crop)

                    # Upload
                    upload_to_firebase(filepath, face_id, face_name, count)

                    # Hiển thị
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"{count}/{sample_limit}", (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    face_detected = True

                    # Chuyển hướng
                    if count % images_per_direction == 0 and count < sample_limit:
                        current_dir_idx += 1
                        next_instruction = directions[current_dir_idx][0]
                        speak(next_instruction)
                        logging.info(f"Chuyển hướng: {next_instruction}")

                    break  # Chỉ xử lý 1 khuôn mặt

            # Hiển thị hướng dẫn
            cv2.putText(frame, directions[current_dir_idx][0], (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            if not face_detected:
                cv2.putText(frame, "Khong phat hien khuon mat", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.imshow('Thu thap khuon mat - Nhan ESC de thoat', frame)
            if cv2.waitKey(100) & 0xFF == 27:  # ESC
                break

    except Exception as e:
        logging.error(f"Lỗi trong vòng lặp: {e}")
    finally:
        cam.release()
        cv2.destroyAllWindows()
        speak(f"Đã thu thập {count} ảnh. Cảm ơn bạn!")
        logging.info(f"Hoàn tất: {count}/{sample_limit} ảnh")


if __name__ == "__main__":
    main()