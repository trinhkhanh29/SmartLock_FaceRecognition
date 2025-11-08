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
import requests
import threading
import time
from dotenv import load_dotenv

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
TELEGRAM_BOT_TOKEN = None
TELEGRAM_CHAT_ID = None
TEMP_DIR = os.path.join(os.path.dirname(__file__), '../temp')
os.makedirs(TEMP_DIR, exist_ok=True)


# ========================== LOAD ENV ==========================
def load_telegram_config():
    global TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    env_path = os.path.join(os.path.dirname(__file__), '../.env/config.env')
    if not os.path.exists(env_path):
        logging.warning("Không tìm thấy config.env - Telegram sẽ không hoạt động")
        return False

    load_dotenv(env_path)
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID trong config.env")
        return False

    logging.info("Đã tải cấu hình Telegram thành công")
    return True


# ========================== TELEGRAM ==========================
def send_telegram_photo_async(photo_path, caption=""):
    def _send():
        if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
            return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        try:
            with open(photo_path, 'rb') as photo:
                payload = {
                    'chat_id': TELEGRAM_CHAT_ID,
                    'caption': caption[:1024],  # Giới hạn caption
                    'parse_mode': 'HTML'
                }
                requests.post(url, data=payload, files={'photo': photo}, timeout=10)
            logging.info(f"Đã gửi Telegram: {caption.split('|')[0]}")
        except Exception as e:
            logging.error(f"Gửi Telegram thất bại: {e}")
        finally:
            time.sleep(0.5)  # Tránh spam

    threading.Thread(target=_send, daemon=True).start()


def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={
            'chat_id': TELEGRAM_CHAT_ID,
            'text': text[:4096],
            'parse_mode': 'HTML'
        }, timeout=10)
    except:
        pass


# ========================== FIREBASE ==========================
def initialize_firebase():
    global bucket
    cred_path = os.path.join(os.path.dirname(__file__), '../.env/firebase_credentials.json')

    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"Không tìm thấy file chứng thực: {cred_path}")

    bucket_name = "smartlockfacerecognition.firebasestorage.app"
    env_path = os.path.join(os.path.dirname(__file__), '../.env/config.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)
        env_bucket = os.getenv('FIREBASE_STORAGE_BUCKET')
        if env_bucket:
            bucket_name = env_bucket

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
            pass
    print(f"[VOICE] {text}")


# ========================== UPLOAD ==========================
def upload_to_firebase(filepath, face_id, face_name, count):
    global bucket
    if not bucket or not os.path.exists(filepath):
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    firebase_path = f"faces/{face_id}/{face_id}_{face_name.replace(' ', '_')}_{count}_{timestamp}.jpg"

    try:
        blob = bucket.blob(firebase_path)
        blob.upload_from_filename(filepath, content_type='image/jpeg')
        blob.make_public()
        logging.info(f"Upload: {firebase_path}")
        return blob.public_url
    except Exception as e:
        logging.error(f"Upload thất bại: {e}")
        return None

def process_single_image(image_path, face_id, face_name):
    """Xử lý một ảnh duy nhất: tìm khuôn mặt, cắt, và upload."""
    if not os.path.exists(image_path):
        logging.error(f"Ảnh không tồn tại: {image_path}")
        return False

    try:
        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        mtcnn = MTCNN(keep_all=False, min_face_size=50, device=device)
        
        frame = cv2.imread(image_path)
        if frame is None:
            logging.error("Không thể đọc file ảnh.")
            return False

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        boxes, probs = mtcnn.detect(frame_rgb)

        if boxes is None:
            logging.warning("Không tìm thấy khuôn mặt nào trong ảnh.")
            speak("Không tìm thấy khuôn mặt trong ảnh đã tải lên.")
            return False

        # Chỉ lấy khuôn mặt có xác suất cao nhất
        best_prob_idx = np.argmax(probs)
        box = boxes[best_prob_idx]
        prob = probs[best_prob_idx]

        if prob < 0.9:
            logging.warning(f"Khuôn mặt có độ tin cậy thấp: {prob:.2f}")
            speak("Khuôn mặt không đủ rõ nét.")
            return False

        x1, y1, x2, y2 = map(int, box)
        face_crop = frame[y1:y2, x1:x2]

        # Lưu ảnh đã cắt vào dataset
        dataset_path = os.path.join(os.path.dirname(__file__), '../dataset')
        os.makedirs(dataset_path, exist_ok=True)
        filename = f"{face_id}_{face_name.replace(' ', '_')}_uploaded_1.jpg"
        filepath = os.path.join(dataset_path, filename)
        cv2.imwrite(filepath, face_crop)

        # Upload và gửi thông báo
        url = upload_to_firebase(filepath, face_id, face_name, 1)
        if url:
            final_message = f"Đã xử lý và lưu trữ thành công khuôn mặt cho {face_name} từ ảnh tải lên."
            logging.info(final_message)
            speak(final_message)
            send_telegram_message(final_message)
            return True
        return False

    except Exception as e:
        logging.error(f"Lỗi khi xử lý ảnh đơn: {e}")
        return False


# ========================== MAIN ==========================
def main():
    global bucket

    # === Chế độ xử lý ảnh đơn ===
    if len(sys.argv) == 4 and sys.argv[1] == '--image':
        image_path = sys.argv[2]
        face_id = sys.argv[3].split(':')[0]
        face_name = sys.argv[3].split(':')[1]
        
        load_telegram_config()
        try:
            initialize_firebase()
        except Exception as e:
            logging.error(f"Lỗi Firebase: {e}")
            sys.exit(1)
            
        process_single_image(image_path, face_id, face_name)
        sys.exit(0)


    # === Load Telegram ===
    load_telegram_config()

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
    send_telegram_message(
        f"<b>THU THẬP KHUÔN MẶT</b>\n"
        f"Người dùng: <b>{face_name}</b>\n"
        f"ID: <code>{face_id}</code>\n"
        f"Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}"
    )

    # === Khởi tạo ===
    try:
        bucket = initialize_firebase()
    except Exception as e:
        logging.error(f"Firebase lỗi: {e}")
        speak("Không thể kết nối Firebase.")
        return

    # === Camera ===
    cam = cv2.VideoCapture(0, cv2.CAP_DSHOW)
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
    send_telegram_message("Bắt đầu thu thập khuôn mặt...")

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

                    # Lưu tạm để gửi Telegram
                    temp_path = os.path.join(TEMP_DIR, f"temp_{count}.jpg")
                    cv2.imwrite(temp_path, face_crop)

                    # Lưu chính thức
                    count += 1
                    direction_key = directions[current_dir_idx][1]
                    filename = f"{face_id}_{face_name.replace(' ', '_')}_{direction_key}_{count}.jpg"
                    filepath = os.path.join(dataset_path, filename)
                    cv2.imwrite(filepath, face_crop)

                    # Upload
                    public_url = upload_to_firebase(filepath, face_id, face_name, count)

                    # Gửi Telegram
                    caption = (
                        f"<b>ĐÃ CHỤP</b> | {face_name}\n"
                        f"Ảnh thứ: <b>{count}/{sample_limit}</b>\n"
                        f"Hướng: <b>{directions[current_dir_idx][0]}</b>\n"
                        f"Thời gian: {datetime.now().strftime('%H:%M:%S')}"
                    )
                    send_telegram_photo_async(temp_path, caption)

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
                        send_telegram_message(f"Chuyển hướng: {next_instruction}")

                    break

            # Hiển thị hướng dẫn
            cv2.putText(frame, directions[current_dir_idx][0], (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            if not face_detected:
                cv2.putText(frame, "Khong phat hien khuon mat", (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            cv2.imshow('Thu thap khuon mat - Nhan ESC de thoat', frame)
            if cv2.waitKey(100) & 0xFF == 27:
                break

    except Exception as e:
        logging.error(f"Lỗi trong vòng lặp: {e}")
    finally:
        cam.release()
        cv2.destroyAllWindows()
        speak(f"Đã thu thập {count} ảnh. Cảm ơn {face_name}!")
        send_telegram_message(
            f"<b>HOÀN TẤT THU THẬP</b>\n"
            f"Người dùng: <b>{face_name}</b>\n"
            f"Tổng ảnh: <b>{count}/{sample_limit}</b>\n"
            f"Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}"
        )
        logging.info(f"Hoàn tất: {count}/{sample_limit} ảnh")


if __name__ == "__main__":
    main()