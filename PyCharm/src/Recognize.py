# Recognize.py - Updated for Node.js Integration
import cv2
import numpy as np
import os
import sys
import pickle
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, storage
import requests
from dotenv import load_dotenv
import pyttsx3
from facenet_pytorch import MTCNN, InceptionResnetV1
import torch
import time
import traceback
import serial
import pygame
from playsound import playsound
import threading
import re
import cProfile
import pstats
import logging
import json
import signal

# ==================== CONFIGURATION ====================
# Biến toàn cục để điều khiển từ bên ngoài
should_stop = False
is_running = False

# Thiết lập logging cho thống kê hiệu năng
logging.basicConfig(
    filename='performance_log_dell_g3_3579.txt',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger()

# Nạp biến môi trường từ config.env
env_path = os.path.join(os.path.dirname(__file__), '../.env/config.env')
print(f"[DEBUG] Đường dẫn tuyệt đối của .env: {os.path.abspath(env_path)}")
if not os.path.exists(env_path):
    print(f"[ERROR] File .env không tồn tại tại: {env_path}")
    sys.exit(1)
else:
    print(f"[INFO] Đã tìm thấy file .env tại: {env_path}")
    load_dotenv(env_path)

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
print(f"[DEBUG] TELEGRAM_BOT_TOKEN: {TELEGRAM_BOT_TOKEN}")
print(f"[DEBUG] TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("[ERROR] TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID không được định nghĩa trong config.env.")
    sys.exit(1)

# Biến toàn cục để lưu khoảng cách
distance = None
distance_lock = threading.Lock()

# Xác định device cho Torch (hỗ trợ CUDA trên Dell G3 3579 với GPU NVIDIA GTX 1050 Ti hoặc tương tự)
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"[INFO] Sử dụng device: {device} trên Dell G3 3579")


# ==================== SERIAL COMMUNICATION ====================
def init_serial(port='COM4', baudrate=115200):
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"[INFO] Đã kết nối Serial tại {port}")
        return ser
    except serial.SerialException as e:
        print(f"[ERROR] Không thể kết nối Serial: {e}")
        return None


def read_distance_from_serial(ser):
    global distance
    try:
        while True:
            if ser and ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith("DISTANCE:"):
                    distance_str = line.replace("DISTANCE:", "")
                    with distance_lock:
                        if distance_str == "OUT_RANGE":
                            distance = "Ngoài phạm vi"
                        else:
                            try:
                                distance = float(distance_str.replace(" cm", ""))
                                print(f"[INFO] Khoảng cách nhận được: {distance} cm")
                            except ValueError:
                                distance = "Lỗi định dạng"
            time.sleep(0.1)  # Giảm tải CPU
    except serial.SerialException as e:
        print(f"[ERROR] Lỗi Serial trong thread: {e}")
    except AttributeError:
        pass  # Serial port đã bị đóng


def send_serial_command(ser, command, expected_response=None, timeout=10):
    if ser and ser.is_open:
        try:
            ser.reset_input_buffer()
            ser.write(f"{command}\n".encode())
            print(f"[INFO] Đã gửi: {command}, đợi phản hồi...")
            start_time = time.time()
            while time.time() - start_time < timeout:
                if ser.in_waiting > 0:
                    response = ser.readline().decode('utf-8').strip()
                    print(f"[INFO] ESP phản hồi: {response}")
                    if expected_response is None or expected_response in response:
                        return True
            print("[WARNING] Hết thời gian chờ phản hồi từ ESP.")
        except serial.SerialException as e:
            print(f"[ERROR] Lỗi Serial: {e}")
    return False


# ==================== AUDIO FUNCTIONS ====================
def play_startup_sound(sound_path):
    try:
        pygame.mixer.init()
        pygame.mixer.music.load(sound_path)
        pygame.mixer.music.play()
        print("[INFO] Đang phát âm thanh khởi động...")
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
    except Exception as e:
        print(f"[WARNING] Không thể phát âm thanh: {e}")


def init_tts_engine():
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 1.0)
        voices = engine.getProperty('voices')
        for voice in voices:
            if 'vi' in str(voice.languages) or 'Microsoft An' in voice.name:
                engine.setProperty('voice', voice.id)
                print(f"[INFO] Đã chọn giọng nói: {voice.name}")
                break
        else:
            print("[WARNING] Không tìm thấy giọng nói tiếng Việt. Sử dụng giọng mặc định.")
        return engine
    except Exception as e:
        print(f"[WARNING] Không thể khởi tạo engine text-to-speech: {e}")
        return None


# ==================== TELEGRAM FUNCTIONS ====================
def verify_telegram_token():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            print("[INFO] Token Telegram hợp lệ.")
            return True
        else:
            print(f"[ERROR] Token Telegram không hợp lệ: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Không thể xác minh token Telegram: {e}")
        return False


def send_telegram_message_with_photo(message, photo_path):
    if not message or not isinstance(message, str) or len(message.strip()) == 0:
        print("[ERROR] Tin nhắn không hợp lệ hoặc rỗng, bỏ qua gửi Telegram.")
        return False
    if not os.path.exists(photo_path):
        print(f"[ERROR] File ảnh không tồn tại tại: {photo_path}")
        return False
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[ERROR] Thiếu TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID. Kiểm tra file config.env.")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {'chat_id': TELEGRAM_CHAT_ID, 'caption': message.strip()}
    try:
        with open(photo_path, 'rb') as photo_file:
            files = {'photo': photo_file}
            response = requests.post(url, data=payload, files=files, timeout=10)
            if response.status_code != 200:
                print(f"[ERROR] Gửi Telegram thất bại: {response.text}")
                return False
            print("[INFO] Gửi tin nhắn và ảnh Telegram thành công.")
            return True
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Lỗi kết nối khi gửi Telegram: {e}")
        return False


# ==================== FIREBASE FUNCTIONS ====================
def initialize_firebase():
    cred_path = os.path.join(os.path.dirname(__file__), '../.env/firebase_credentials.json')
    if not os.path.exists(cred_path):
        raise FileNotFoundError("[ERROR] Firebase credentials file not found.")

    # Kiểm tra nếu Firebase đã được khởi tạo
    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'smartlockfacerecognition.firebasestorage.app'
        })

    return storage.bucket()


def load_known_faces(bucket, local_dir):
    os.makedirs(local_dir, exist_ok=True)
    embeddings_path = os.path.join(local_dir, "embeddings.pkl")
    cached_data = None

    # Thử tải từ cache
    if os.path.exists(embeddings_path):
        try:
            with open(embeddings_path, 'rb') as f:
                cached_data = pickle.load(f)
                known_embeddings, known_ids, known_names, cached_files = cached_data
                print(f"[INFO] Đã tải {len(known_ids)} embeddings từ cache: {embeddings_path}")

                # Kiểm tra xem cache có còn hợp lệ không
                try:
                    firebase_files = set(blob.name for blob in bucket.list_blobs(prefix='faces/'))
                    if set(cached_files) == firebase_files:
                        print("[INFO] Cache hợp lệ, không cần tải lại từ Firebase.")
                        return known_embeddings, known_ids, known_names
                    else:
                        print("[INFO] Phát hiện thay đổi trong Firebase, cập nhật embeddings.")
                except Exception as e:
                    print(f"[WARNING] Không thể kiểm tra Firebase files: {e}")

        except Exception as e:
            print(f"[WARNING] Lỗi khi tải cache embeddings: {e}. Tải lại từ Firebase.")

    # Tải từ Firebase nếu cache không hợp lệ
    mtcnn = MTCNN(keep_all=False, min_face_size=150, thresholds=[0.7, 0.8, 0.8], device=device)
    resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)
    known_embeddings = []
    known_ids = []
    known_names = []
    processed_files = []

    try:
        for blob in bucket.list_blobs(prefix='faces/'):
            blob_name = blob.name
            print(f"[DEBUG] Xử lý file Firebase: {blob_name}")
            try:
                parts = blob_name.split('/')
                if len(parts) < 3:
                    print(f"[WARNING] Đường dẫn không hợp lệ: {blob_name}")
                    continue

                user_id = int(parts[1])
                filename = parts[2]
                user_name_parts = os.path.splitext(filename)[0].split('_')
                if len(user_name_parts) < 4:
                    print(f"[WARNING] Tên file không đúng định dạng: {filename}")
                    continue

                user_name = '_'.join(user_name_parts[1:-2]).replace('_', ' ')
                local_path = os.path.join(local_dir, filename)

                # Tải file nếu chưa có
                if not os.path.exists(local_path):
                    print(f"[DEBUG] Tải file về: {local_path}")
                    blob.download_to_filename(local_path)
                else:
                    print(f"[DEBUG] Sử dụng ảnh cục bộ: {local_path}")

                # Xử lý ảnh
                img = cv2.imread(local_path)
                if img is None:
                    print(f"[WARNING] Không thể đọc ảnh: {local_path}")
                    continue

                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                face = mtcnn(img_rgb)

                if face is not None:
                    embedding = resnet(face.unsqueeze(0).to(device)).detach().cpu().numpy()
                    known_embeddings.append(embedding)
                    known_ids.append(user_id)
                    known_names.append(user_name)
                    processed_files.append(blob_name)
                    print(f"[INFO] Đã thêm khuôn mặt: ID={user_id}, Name={user_name}")
                else:
                    print(f"[WARNING] Không phát hiện khuôn mặt trong: {filename}")

            except (ValueError, IndexError) as e:
                print(f"[WARNING] Bỏ qua file không hợp lệ: {blob_name}, {str(e)}")

        # Lưu cache
        if known_embeddings:
            try:
                with open(embeddings_path, 'wb') as f:
                    pickle.dump((known_embeddings, known_ids, known_names, processed_files), f)
                print(f"[INFO] Đã lưu embeddings vào: {embeddings_path}")
            except Exception as e:
                print(f"[WARNING] Lỗi khi lưu cache embeddings: {e}")

    except Exception as e:
        print(f"[ERROR] Lỗi khi tải từ Firebase: {e}")

    return known_embeddings, known_ids, known_names


# ==================== FACE DETECTION ====================
def get_model_paths():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cascades_dir = os.path.abspath(os.path.join(base_dir, "..", "cascades"))
    proto_path = os.path.join(cascades_dir, "deploy.prototxt")
    model_path = os.path.join(cascades_dir, "res10_300x300_ssd_iter_140000.caffemodel")
    return proto_path, model_path


def check_model_files():
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
    h, w = frame.shape[:2]
    blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
    net.setInput(blob)
    detections = net.forward()
    faces = []
    min_face_size = 150

    for i in range(detections.shape[2]):
        confidence = detections[0, 0, i, 2]
        if confidence > conf_threshold:
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            (x, y, x2, y2) = box.astype("int")
            width, height = x2 - x, y2 - y
            if width >= min_face_size and height >= min_face_size:
                faces.append((x, y, width, height))
    return faces


# ==================== SIGNAL HANDLING ====================
def signal_handler(sig, frame):
    """Xử lý signal để dừng chương trình"""
    global should_stop
    print("\n[INFO] Nhận tín hiệu dừng từ hệ thống...")
    should_stop = True


# ==================== NODE.JS INTEGRATION ====================
def send_to_nodejs(message, status):
    """Gửi kết quả nhận diện đến Node.js server"""
    try:
        url = "http://localhost:3000/api/face/result"
        data = {
            "message": message,
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        response = requests.post(url, json=data, timeout=2)
        if response.status_code == 200:
            print(f"[INFO] Đã gửi kết quả đến Node.js: {status}")
        else:
            print(f"[WARNING] Không thể gửi đến Node.js: {response.status_code}")
    except Exception as e:
        print(f"[DEBUG] Không thể kết nối đến Node.js: {e}")


# ==================== MAIN FUNCTION ====================
def main():
    global should_stop, is_running

    # Đăng ký signal handler
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    is_running = True
    should_stop = False

    # Khởi tạo profiler cho thống kê hiệu năng
    profiler = cProfile.Profile()
    profiler.enable()

    # Kiểm tra token Telegram
    if not verify_telegram_token():
        print("[ERROR] Không thể tiếp tục do token Telegram không hợp lệ.")
        return

    # Khởi tạo TTS
    tts_engine = init_tts_engine()

    # Khởi tạo Serial
    ser = init_serial(port='COM4')
    serial_thread = None
    if ser:
        # Khởi động thread đọc khoảng cách
        serial_thread = threading.Thread(target=read_distance_from_serial, args=(ser,), daemon=True)
        serial_thread.start()

    # Biến đếm thất bại và khóa
    fail_count = 0
    lockout_time = 0
    lock_duration = 60

    # Biến thống kê thực nghiệm
    correct_recognitions = 0
    total_recognitions = 0
    processing_times = []
    false_positives = 0
    false_negatives = 0
    false_positive_rate = 5.0
    false_negative_rate = 10.0
    serial_latencies = []
    error_count = 0
    frame_drop_count = 0

    try:
        # Khởi tạo Firebase
        bucket = initialize_firebase()

        # Tải danh sách khuôn mặt đã biết
        dataset_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dataset"))
        load_start = time.perf_counter()
        known_embeddings, known_ids, known_names = load_known_faces(bucket, dataset_path)
        load_time = time.perf_counter() - load_start
        logger.info(f"Thời gian tải embeddings: {load_time:.3f}s trên Dell G3 3579")
        print(f"[INFO] Thời gian tải embeddings: {load_time:.3f}s")

        if not known_embeddings:
            print("[ERROR] Không có dữ liệu khuôn mặt nào từ Firebase hoặc cache. Vui lòng thu thập dữ liệu trước.")
            return

        # Khởi tạo FaceNet với device (CUDA nếu có)
        mtcnn = MTCNN(keep_all=False, min_face_size=150, thresholds=[0.7, 0.8, 0.8], device=device)
        resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)

        # Nạp bộ phát hiện khuôn mặt DNN
        face_detector = load_deep_face_detector()
        if face_detector is None:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            if face_cascade.empty():
                print("[ERROR] Không thể tải bộ phát hiện khuôn mặt.")
                return
            print("[INFO] Sử dụng Haar Cascade do thiếu mô hình DNN.")

        # Khởi tạo camera
        cam = cv2.VideoCapture(1, cv2.CAP_DSHOW)
        if not cam.isOpened():
            print("[ERROR] Không thể mở camera.")
            return

        cam.set(3, 640)
        cam.set(4, 480)
        min_face_size = 150
        optimal_face_size = 200

        print("\n[INFO] Face recognition started on Dell G3 3579. Press ESC to exit.")

        frame_count = 0
        start_time = time.perf_counter()
        temp_photo_path = os.path.join(os.path.dirname(__file__), "..", "temp", "temp_face.jpg")
        voice_cooldown = 5
        last_voice_time = datetime.now()

        # Đảm bảo thư mục temp tồn tại
        os.makedirs(os.path.dirname(temp_photo_path), exist_ok=True)

        # Phát âm thanh khởi động
        sound_path = os.path.join(os.path.dirname(__file__), '../sound/Ring-Doorbell-Sound.wav')
        if os.path.exists(sound_path):
            play_startup_sound(sound_path)
        else:
            print(f"[WARNING] File âm thanh không tồn tại tại: {sound_path}")

        # Gửi thông báo bắt đầu đến Node.js
        send_to_nodejs("Hệ thống nhận diện khuôn mặt đã khởi động", "started")

        # Vòng lặp chính
        while not should_stop:
            try:
                ret, frame = cam.read()
                if not ret:
                    print("[ERROR] Không thể đọc khung hình từ camera.")
                    frame_drop_count += 1
                    logger.error("Frame drop detected")
                    continue

                frame = cv2.flip(frame, 1)
                frame_count += 1
                elapsed_time = time.perf_counter() - start_time
                fps = frame_count / elapsed_time if elapsed_time > 0 else 0
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Kiểm tra khóa hệ thống
                if time.perf_counter() < lockout_time:
                    remaining_time = int(lockout_time - time.perf_counter())
                    print(f"[THÔNG BÁO] Hệ thống đang bị khóa, còn {remaining_time}s...")
                    cv2.putText(frame, f"Bi khoa - Con {remaining_time}s...", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    cv2.imshow("Face Recognition", frame)

                    key = cv2.waitKey(1) & 0xFF
                    if key == 27 or key == ord('q') or should_stop:
                        break
                    continue

                # Phát hiện khuôn mặt
                process_start = time.perf_counter()
                if face_detector is not None:
                    faces = detect_faces_dnn(face_detector, frame)
                else:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(
                        gray, scaleFactor=1.1, minNeighbors=6, minSize=(min_face_size, min_face_size)
                    )

                detection_time = time.perf_counter() - process_start
                logger.info(f"Thời gian phát hiện khuôn mặt: {detection_time:.3f}s, Số khuôn mặt: {len(faces)}")
                print(f"[DEBUG] Số khuôn mặt phát hiện: {len(faces)}, thời gian: {detection_time:.3f}s")

                current_time = datetime.now()
                time_since_last_voice = (current_time - last_voice_time).total_seconds()

                for (x, y, w, h) in faces:
                    if should_stop:
                        break

                    if w < min_face_size or h < min_face_size:
                        print(f"[DEBUG] Bỏ qua khuôn mặt nhỏ: {w}x{h}")
                        continue

                    if w < optimal_face_size and time_since_last_voice > voice_cooldown and tts_engine:
                        voice_message = "Vui lòng đưa khuôn mặt gần hơn để nhận diện chính xác"
                        tts_engine.say(voice_message)
                        tts_engine.runAndWait()
                        last_voice_time = current_time
                        print("[VOICE] Phát âm thanh hướng dẫn")

                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    face_img = frame_rgb[y:y + h, x:x + w]
                    recognition_start = time.perf_counter()
                    face_tensor = mtcnn(face_img)
                    name = "Unknown"
                    confidence_percent = 0.0
                    color = (255, 255, 255)

                    if face_tensor is not None:
                        embedding = resnet(face_tensor.unsqueeze(0).to(device)).detach().cpu().numpy()
                        distances = [np.linalg.norm(embedding - emb) for emb in known_embeddings]
                        if distances:
                            min_distance = min(distances)
                            min_idx = distances.index(min_distance)
                            confidence_percent = max(0, min(100, (1 - min_distance / 2) * 100))
                            if min_distance < 0.6:
                                name = known_names[min_idx]
                                color = (0, 255, 0)
                            else:
                                color = (0, 0, 255)

                        recognition_time = time.perf_counter() - recognition_start
                        logger.info(
                            f"Nhận diện: {name}, Độ tin cậy: {confidence_percent:.1f}%, Thời gian: {recognition_time:.3f}s")
                        print(
                            f"[DEBUG] Nhận diện: {name}, Độ tin cậy: {confidence_percent:.1f}%, thời gian: {recognition_time:.3f}s")

                        total_recognitions += 1
                        if name != "Unknown":
                            correct_recognitions += 1
                        else:
                            false_negatives += 1

                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    serial_start = time.perf_counter()

                    if name != "Unknown":
                        fail_count = 0
                        cv2.imwrite(temp_photo_path, frame)
                        message = f"[✅ {now_str}] Mở cửa thành công - {name} (Độ tin cậy: {confidence_percent:.1f}%)"

                        if send_telegram_message_with_photo(message, temp_photo_path):
                            # Gửi thông báo thành công đến Node.js
                            send_to_nodejs(f"Mở cửa cho {name}", "success")

                            if tts_engine:
                                send_serial_command(ser, "SUCCESS")
                                serial_latency = time.perf_counter() - serial_start
                                serial_latencies.append(serial_latency)
                                logger.info(f"Serial SUCCESS latency: {serial_latency:.3f}s")
                                voice_message = f"Xin chào {name}. Đã nhận diện thành công. Mở cửa"
                                tts_engine.say(voice_message)
                                tts_engine.runAndWait()

                            print("[VOICE] Phát âm thanh chào mừng")
                            print("[INFO] Đã gửi thông báo mở cửa.")

                            # Không thoát ngay mà tiếp tục chạy
                            time.sleep(2)  # Chờ 2 giây trước khi tiếp tục

                    elif time_since_last_voice > voice_cooldown and tts_engine:
                        fail_count += 1
                        print(f"[CẢNH BÁO] Nhận diện thất bại {fail_count}/3")
                        cv2.imwrite(temp_photo_path, frame)

                        with distance_lock:
                            distance_str = str(distance) if distance is not None else "Chưa có dữ liệu"

                        message = f"[🚨 {now_str}] CẢNH BÁO: Phát hiện người lạ - Độ tin cậy thấp ({confidence_percent:.1f}%) | Khoảng cách: {distance_str}"

                        if send_telegram_message_with_photo(message, temp_photo_path):
                            # Gửi cảnh báo đến Node.js
                            send_to_nodejs("Phát hiện người lạ", "warning")

                            send_serial_command(ser, "FAIL")
                            serial_latency = time.perf_counter() - serial_start
                            serial_latencies.append(serial_latency)
                            logger.info(f"Serial FAIL latency: {serial_latency:.3f}s")
                            voice_message = "Cảnh báo! Phát hiện người lạ"
                            tts_engine.say(voice_message)
                            tts_engine.runAndWait()
                            print("[VOICE] Phát âm thanh cảnh báo")
                            last_voice_time = current_time

                        if fail_count >= 3:
                            lockout_time = time.perf_counter() + lock_duration
                            fail_count = 0
                            print("[BẢO MẬT] Hệ thống bị khóa trong 1 phút.")
                            # Gửi thông báo khóa đến Node.js
                            send_to_nodejs("Hệ thống bị khóa do nhận diện sai nhiều lần", "locked")

                            if tts_engine:
                                tts_engine.say("Hệ thống bị khóa trong một phút do nhận diện sai quá ba lần")
                                tts_engine.runAndWait()

                    cv2.putText(frame, name, (x + 5, y - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                    cv2.putText(frame, f"{confidence_percent:.1f}%", (x + 5, y + h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                (255, 255, 0), 2)

                # Hiển thị khoảng cách trên frame
                with distance_lock:
                    distance_text = f"Distance: {distance if distance is not None else 'Chưa có dữ liệu'}"
                cv2.putText(frame, distance_text, (10, 180), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

                # Tính thống kê
                frame_process_time = (time.perf_counter() - process_start) * 1000
                processing_times.append(frame_process_time)
                accuracy = (correct_recognitions / total_recognitions * 100) if total_recognitions > 0 else 0.0
                avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0.0
                avg_serial_latency = sum(serial_latencies) / len(serial_latencies) if serial_latencies else 0.0

                # Hiển thị thống kê trên frame
                cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                cv2.putText(frame, f"Accuracy: {accuracy:.1f}%", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255),
                            2)
                cv2.putText(frame, f"Proc Time: {avg_processing_time:.1f} ms", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 255, 255), 2)
                cv2.putText(frame, f"Total: {total_recognitions}", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 255, 255), 2)

                cv2.imshow('Face Recognition - FaceNet DNN on Dell G3 3579', frame)

                key = cv2.waitKey(10) & 0xFF
                if key == 27 or key == ord('q') or should_stop:
                    break

            except KeyboardInterrupt:
                print("\n[INFO] Program interrupted by user.")
                break
            except Exception as e:
                error_count += 1
                logger.error(f"Lỗi trong vòng lặp chính: {str(e)}")
                print(f"[ERROR] Lỗi trong vòng lặp chính: {str(e)}")
                print(f"[DEBUG] Traceback: {traceback.format_exc()}")
                continue

    except Exception as e:
        print(f"[ERROR] Lỗi nghiêm trọng: {str(e)}")
        logger.error(f"Lỗi nghiêm trọng: {str(e)}")

    finally:
        # Cleanup
        is_running = False

        # Gửi thông báo dừng đến Node.js
        send_to_nodejs("Hệ thống nhận diện đã dừng", "stopped")

        # Lưu profiler
        profiler.disable()
        try:
            with open('profile_stats_dell_g3_3579.txt', 'w') as f:
                ps = pstats.Stats(profiler, stream=f)
                ps.sort_stats('cumulative')
                ps.print_stats()
        except:
            pass

        # In thống kê cuối cùng
        accuracy = (correct_recognitions / total_recognitions * 100) if total_recognitions > 0 else 0.0
        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0.0
        avg_serial_latency = sum(serial_latencies) / len(serial_latencies) if serial_latencies else 0.0
        stability = 100.0 * (1 - error_count / (frame_count + 1)) if frame_count > 0 else 100.0

        print("\n[THỐNG KÊ THỰC NGHIỆM TRÊN DELL G3 3579]")
        print(f"Độ chính xác: {accuracy:.1f}%")
        print(f"Tốc độ xử lý trung bình: {avg_processing_time:.1f} ms/frame")
        print(f"Độ trễ serial trung bình: {avg_serial_latency:.1f} ms")
        print(f"Độ ổn định: {stability:.1f}%")
        print(f"Tổng số nhận diện: {total_recognitions}")
        print(f"Nhận diện đúng: {correct_recognitions}")
        print(f"Số lỗi: {error_count}")
        print(f"Số frame drop: {frame_drop_count}")

        logger.info(f"Độ chính xác: {accuracy:.1f}%")
        logger.info(f"Tốc độ xử lý trung bình: {avg_processing_time:.1f} ms/frame")
        logger.info(f"Tổng số nhận diện: {total_recognitions}, Nhận diện đúng: {correct_recognitions}")

        # Dọn dẹp tài nguyên
        try:
            if os.path.exists(temp_photo_path):
                os.remove(temp_photo_path)
                print(f"[INFO] Đã xóa file ảnh tạm: {temp_photo_path}")
        except:
            pass

        try:
            if 'cam' in locals() and cam.isOpened():
                cam.release()
        except:
            pass

        try:
            if 'ser' in locals() and ser and ser.is_open:
                ser.close()
        except:
            pass

        try:
            cv2.destroyAllWindows()
        except:
            pass

        print("\n[INFO] Program exited cleanly on Dell G3 3579.")


# ==================== NODE.JS SERVICE INTEGRATION ====================
def start_face_recognition_service():
    """Hàm để Node.js gọi để khởi động nhận diện"""
    global is_running

    if is_running:
        return {"status": "error", "message": "Nhận diện đang chạy"}

    try:
        # Khởi động trong thread riêng
        recognition_thread = threading.Thread(target=main, daemon=True)
        recognition_thread.start()

        return {"status": "success", "message": "Đã khởi động nhận diện khuôn mặt"}

    except Exception as e:
        return {"status": "error", "message": f"Lỗi: {str(e)}"}


def stop_face_recognition_service():
    """Hàm để Node.js gọi để dừng nhận diện"""
    global should_stop, is_running

    if not is_running:
        return {"status": "error", "message": "Nhận diện không chạy"}

    try:
        should_stop = True
        return {"status": "success", "message": "Đã gửi tín hiệu dừng nhận diện"}

    except Exception as e:
        return {"status": "error", "message": f"Lỗi khi dừng: {str(e)}"}


def get_status_service():
    """Hàm để Node.js gọi để lấy trạng thái"""
    return {
        "status": "success",
        "is_running": is_running,
        "message": "Đang chạy" if is_running else "Đã dừng"
    }


# ==================== COMMAND LINE INTERFACE ====================
if __name__ == "__main__":
    # Kiểm tra nếu được gọi từ Node.js
    if len(sys.argv) > 1 and sys.argv[1] == "--service":
        try:
            # Đọc command từ stdin
            command = sys.stdin.read().strip()
            data = json.loads(command) if command else {}

            action = data.get("action", "")

            if action == "start":
                result = start_face_recognition_service()
            elif action == "stop":
                result = stop_face_recognition_service()
            elif action == "status":
                result = get_status_service()
            else:
                result = {"status": "error", "message": "Action không hợp lệ"}

            # Gửi kết quả qua stdout
            print(json.dumps(result))

        except Exception as e:
            print(json.dumps({"status": "error", "message": f"Lỗi hệ thống: {str(e)}"}))
    else:
        # Chạy trực tiếp
        main()