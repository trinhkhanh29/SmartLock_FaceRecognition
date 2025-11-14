import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

import cv2
import numpy as np
import os
import pickle
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, storage, db
import requests
from dotenv import load_dotenv
import pyttsx3
from facenet_pytorch import MTCNN, InceptionResnetV1
import torch
import time
import traceback
import serial
import pygame
import threading
import re
import cProfile
import pstats
import logging
import argparse

# THÊM IMPORT CÁC HÀM XỬ LÝ ÁNH SÁNG YẾU
from image_enhancement import (
    enhance_image_for_low_light, 
    auto_gamma,  # THAY ĐỔI: Dùng auto_gamma thay vì adjust_gamma
    auto_brightness_contrast, 
    detect_low_light,
    preprocess_image  # THÊM: Hàm pipeline tự động
)

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
EXPECTED_PIN = os.getenv('EXPECTED_PIN', '2828')
print(f"[DEBUG] TELEGRAM_BOT_TOKEN: {TELEGRAM_BOT_TOKEN}")
print(f"[DEBUG] TELEGRAM_CHAT_ID: {TELEGRAM_CHAT_ID}")
print(f"[DEBUG] EXPECTED_PIN: {EXPECTED_PIN}")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("[ERROR] TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID không được định nghĩa trong config.env.")
    sys.exit(1)

# Biến toàn cục để lưu khoảng cách
distance = None
distance_lock = threading.Lock()

# Xác định device cho Torch
device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
print(f"[INFO] Sử dụng device: {device}")

# Khởi tạo Serial và đọc khoảng cách
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
            if ser.in_waiting > 0:
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
    finally:
        if ser.is_open:
            ser.close()

# Gửi lệnh Serial
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

# Khởi tạo engine text-to-speech
def init_tts_engine():
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 1.0)
        voices = engine.getProperty('voices')
        for voice in voices:
            print(f"Tên giọng nói: {voice.name}")
            print(f"Ngôn ngữ: {voice.languages}")
            print(f"ID giọng nói: {voice.id}")
            print("---")
            if 'vi' in voice.languages or 'Microsoft An' in voice.name:
                engine.setProperty('voice', voice.id)
                print(f"[INFO] Đã chọn giọng nói: {voice.name}")
                break
        else:
            print("[WARNING] Không tìm thấy giọng nói tiếng Việt. Sử dụng giọng mặc định.")
        return engine
    except Exception as e:
        print(f"[WARNING] Không thể khởi tạo engine text-to-speech: {e}")
        return None

# Kiểm tra token Telegram
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

# Khởi tạo Firebase
def initialize_firebase():
    cred_path = os.path.join(os.path.dirname(__file__), '../.env/firebase_credentials.json')
    if not os.path.exists(cred_path):
        raise FileNotFoundError("[ERROR] Firebase credentials file not found.")
    
    database_url = os.getenv('FIREBASE_DATABASE_URL', 'https://smartlockfacerecognition-default-rtdb.asia-southeast1.firebasedatabase.app/')
    
    cred = credentials.Certificate(cred_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {
            'storageBucket': 'smartlockfacerecognition.firebasestorage.app',
            'databaseURL': database_url
        })
    return storage.bucket()

# --- Hàm mới để ghi log vào Realtime Database ---
def write_activity_log(lock_id, event_type, user_name, confidence, image_url):
    ref = db.reference(f'locks/{lock_id}/activity_log')
    ref.push({
        'type': event_type,
        'name': user_name,
        'confidence': f"{confidence:.1f}",
        'imageUrl': image_url,
        'timestamp': int(time.time() * 1000)
    })
# ---------------------------------------------

# Tải danh sách tên và embeddings từ Firebase hoặc cache cục bộ (sử dụng device)
def load_known_faces(bucket, local_dir, lock_id):
    # Tạo thư mục riêng cho từng lock_id
    lock_dataset_dir = os.path.join(local_dir, lock_id)
    os.makedirs(lock_dataset_dir, exist_ok=True)
    embeddings_path = os.path.join(lock_dataset_dir, "embeddings.pkl")
    
    # Kiểm tra xem file embeddings đã tồn tại chưa
    if not os.path.exists(embeddings_path):
        print(f"[INFO] Không tìm thấy embeddings cho khóa {lock_id}. Đang gọi trainer...")
        # Gọi trainer.py để tạo embeddings
        trainer_script = os.path.join(os.path.dirname(__file__), 'trainer.py')
        import subprocess
        try:
            result = subprocess.run(
                [sys.executable, trainer_script, lock_id],
                check=True,
                capture_output=True,
                text=True,
                encoding='utf-8'
            )
            print(result.stdout)
            if result.stderr:
                print(f"[WARNING] Trainer stderr: {result.stderr}")
        except subprocess.CalledProcessError as e:
            print(f"[ERROR] Trainer thất bại: {e.stderr}")
            return [], [], []
    
    # Tải embeddings từ file đã được tạo
    if os.path.exists(embeddings_path):
        try:
            with open(embeddings_path, 'rb') as f:
                data = pickle.load(f)
                # Xử lý cả định dạng cũ (4 phần tử) và mới (3 phần tử)
                if len(data) == 4:
                    print("[WARNING] Phát hiện file embeddings định dạng cũ. Đang xóa và tạo lại...")
                    os.remove(embeddings_path)
                    # Gọi lại trainer để tạo mới
                    trainer_script = os.path.join(os.path.dirname(__file__), 'trainer.py')
                    import subprocess
                    try:
                        result = subprocess.run(
                            [sys.executable, trainer_script, lock_id],
                            check=True,
                            capture_output=True,
                            text=True,
                            encoding='utf-8'
                        )
                        print(result.stdout)
                        # Đọc lại file mới
                        with open(embeddings_path, 'rb') as f2:
                            known_embeddings, known_ids, known_names = pickle.load(f2)
                    except subprocess.CalledProcessError as e:
                        print(f"[ERROR] Trainer thất bại: {e.stderr}")
                        return [], [], []
                elif len(data) == 3:
                    known_embeddings, known_ids, known_names = data
                else:
                    print(f"[ERROR] Định dạng file embeddings không hợp lệ")
                    return [], [], []
                
                print(f"[INFO] Đã tải {len(known_ids)} embeddings từ cache cho khóa {lock_id}")
                return known_embeddings, known_ids, known_names
        except Exception as e:
            print(f"[ERROR] Lỗi khi đọc file embeddings: {e}")
            print("[INFO] Đang xóa file lỗi và tạo lại...")
            try:
                os.remove(embeddings_path)
                # Gọi trainer để tạo mới
                trainer_script = os.path.join(os.path.dirname(__file__), 'trainer.py')
                import subprocess
                result = subprocess.run(
                    [sys.executable, trainer_script, lock_id],
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )
                print(result.stdout)
                # Đọc lại file mới
                with open(embeddings_path, 'rb') as f:
                    known_embeddings, known_ids, known_names = pickle.load(f)
                    print(f"[INFO] Đã tải {len(known_ids)} embeddings từ cache sau khi tạo lại")
                    return known_embeddings, known_ids, known_names
            except Exception as e2:
                print(f"[ERROR] Không thể tạo lại embeddings: {e2}")
                return [], [], []
    
    print(f"[WARNING] Không thể tạo embeddings cho khóa {lock_id}")
    return [], [], []

# Tải mô hình DNN
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
        print("Vui lòng tải từ: https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt")
        return False
    if not os.path.exists(model_path):
        print(f"[ERROR] Không tìm thấy file model tại: {model_path}")
        print("Vui lòng tải từ: https://github.com/opencv/opencv_3rdparty/raw/dnn_samples_face_detector_20180205_fp16/res10_300x300_ssd_iter_140000_fp16.caffemodel")
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
    files = {'photo': open(photo_path, 'rb')}
    try:
        response = requests.post(url, data=payload, files=files, timeout=5)
        if response.status_code != 200:
            print(f"[ERROR] Gửi Telegram thất bại: {response.text}")
            return False
        print("[INFO] Gửi tin nhắn và ảnh Telegram thành công.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] Lỗi kết nối khi gửi Telegram: {e}")
        return False
    finally:
        files['photo'].close()

# --- Hàm mới để upload ảnh và lấy URL ---
def upload_and_get_url(bucket, local_path, lock_id, remote_folder='logs'):
    if not os.path.exists(local_path):
        return None
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"log_{timestamp}.jpg"
    blob = bucket.blob(f"locks/{lock_id}/{remote_folder}/{filename}")
    
    try:
        blob.upload_from_filename(local_path)
        blob.make_public()
        return blob.public_url
    except Exception as e:
        print(f"[ERROR] Lỗi khi upload ảnh log: {e}")
        return None
# -----------------------------------------

# Parse command-line arguments for mode & pin
def parse_cli_args():
    parser = argparse.ArgumentParser(description="Face recognition runtime mode selection")
    parser.add_argument("--mode", choices=["face_only", "face_pin"], default="face_only", help="Recognition mode")
    parser.add_argument("--lock_id", required=True, help="ID of the lock to use")
    return parser.parse_args()

def enable_ir_mode(cam):
    """
    Kích hoạt chế độ hồng ngoại nếu camera hỗ trợ
    """
    try:
        # Tắt auto white balance
        cam.set(cv2.CAP_PROP_AUTO_WB, 0)
        # Tăng exposure
        cam.set(cv2.CAP_PROP_EXPOSURE, 0.5)
        # Tăng gain
        cam.set(cv2.CAP_PROP_GAIN, 100)
        print("[INFO] Đã kích hoạt chế độ IR")
        return True
    except Exception as e:
        print(f"[WARNING] Không thể kích hoạt IR: {e}")
        return False

# --- Thêm hằng số cấu hình ---
FACE_MATCH_THRESHOLD = 0.3
# -----------------------------------

def main():
    args = parse_cli_args()
    selected_mode = args.mode
    lock_id = args.lock_id

    print(f"[MODE] Chế độ hoạt động: {selected_mode}")
    print(f"[LOCK] Sử dụng lock_id: {lock_id}")

    profiler = cProfile.Profile()
    profiler.enable()

    if not verify_telegram_token():
        print("[ERROR] Token Telegram không hợp lệ.")
        sys.exit(1)

    tts_engine = init_tts_engine()
    ser = init_serial(port='COM4')
    if ser:
        send_serial_command(ser, "SYSTEM_READY") # SỬA: Gửi SYSTEM_READY thay vì RECOGNIZING
        threading.Thread(target=read_distance_from_serial, args=(ser,), daemon=True).start()

    fail_count = 0
    lockout_time = 0
    lock_duration = 60

    frame_count = 0
    start_time = time.perf_counter()
    temp_photo_path = os.path.join(os.path.dirname(__file__), "..", "temp", "temp_face.jpg")
    voice_cooldown = 5
    last_voice_time = datetime.now()

    correct_recognitions = 0
    total_recognitions = 0
    processing_times = []
    serial_latencies = []
    error_count = 0
    frame_drop_count = 0

    # Thống kê hiệu suất
    low_light_frames = 0
    enhanced_frames = 0

    try:
        bucket = initialize_firebase()
        dataset_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dataset"))
        load_start = time.perf_counter()
        known_embeddings, known_ids, known_names = load_known_faces(bucket, dataset_path, lock_id)
        load_time = time.perf_counter() - load_start
        logger.info(f"Thời gian tải embeddings: {load_time:.3f}s")
        print(f"[INFO] Tải embeddings: {load_time:.3f}s")

        if not known_embeddings:
            print("[ERROR] Không có dữ liệu khuôn mặt.")
            sys.exit(1)

        # Khởi tạo MTCNN với cấu hình phù hợp ánh sáng yếu
        # Giảm ngưỡng thresholds để dễ phát hiện hơn trong điều kiện thiếu sáng
        mtcnn = MTCNN(
            keep_all=False, 
            min_face_size=120,  # Giảm từ 150 xuống 120
            thresholds=[0.6, 0.7, 0.7],  # Giảm từ [0.7, 0.8, 0.8]
            device=device,
            post_process=True  # Bật post-processing
        )
        
        resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)
        face_detector = load_deep_face_detector()
        if face_detector is None:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            if face_cascade.empty():
                print("[ERROR] Không tải được Haar Cascade.")
                sys.exit(1)
            print("[INFO] Dùng Haar Cascade.")

        cam = cv2.VideoCapture(1, cv2.CAP_DSHOW)
        if not cam.isOpened():
            print("[ERROR] Không mở được camera.")
            sys.exit(1)
        cam.set(3, 640)
        cam.set(4, 480)
        
        # Kích hoạt IR nếu có
        enable_ir_mode(cam)

        sound_path = os.path.join(os.path.dirname(__file__), '../sound/Ring-Doorbell-Sound.wav')
        if os.path.exists(sound_path):
            play_startup_sound(sound_path)

        print("\n[INFO] Hệ thống sẵn sàng. Nhấn 'q' để thoát.")

        while True:
            ret, frame = cam.read()
            if not ret:
                print("[ERROR] Không đọc được frame.")
                frame_drop_count += 1
                continue

            frame = cv2.flip(frame, 1)
            frame_count += 1
            
            # SỬA LỖI: Lấy giá trị brightness trước khi xử lý ảnh
            # Điều này đảm bảo biến 'brightness' luôn được định nghĩa.
            _, brightness = detect_low_light(frame)

            # === PHÁT HIỆN VÀ XỬ LÝ ÁNH SÁNG YẾU (CÁCH 1: Tự động hoàn toàn) ===
            frame = preprocess_image(frame)  # SỬ DỤNG PIPELINE TỰ ĐỘNG
            
            # HOẶC CÁCH 2: Xử lý thủ công như cũ nhưng dùng auto_gamma
            """
            is_low_light, brightness = detect_low_light(frame)
            
            if is_low_light:
                low_light_frames += 1
                print(f"[WARNING] Phát hiện ánh sáng yếu (độ sáng: {brightness:.1f})")
                
                frame = enhance_image_for_low_light(frame)
                enhanced_frames += 1
                
                cv2.putText(frame, f"LOW LIGHT - Enhanced (Brightness: {brightness:.0f})", 
                           (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            else:
                frame = auto_brightness_contrast(frame, clip_hist_percent=1)
            """
            
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if time.perf_counter() < lockout_time:
                cv2.putText(frame, "He thong bi khoa 1 phut...", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                cv2.imshow("Face Recognition", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
                continue

            process_start = time.perf_counter()
            if face_detector:
                faces = detect_faces_dnn(face_detector, frame)
            else:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.1, 6, minSize=(150, 150))
            detection_time = time.perf_counter() - process_start
            processing_times.append(detection_time * 1000)

            current_time = datetime.now()
            time_since_last_voice = (current_time - last_voice_time).total_seconds()

            for (x, y, w, h) in faces:
                if w < 150 or h < 150:
                    continue

                if w < 200 and time_since_last_voice > voice_cooldown and tts_engine:
                    tts_engine.say("Vui lòng đưa khuôn mặt gần hơn")
                    tts_engine.runAndWait()
                    last_voice_time = current_time

                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                face_img = frame_rgb[y:y + h, x:x + w]
                face_tensor = mtcnn(face_img)

                name = "Unknown"
                confidence_percent = 0.0

                if face_tensor is not None:
                    embedding = resnet(face_tensor.unsqueeze(0).to(device)).detach().cpu().numpy()
                    distances = [np.linalg.norm(embedding - emb) for emb in known_embeddings]
                    if distances:
                        min_distance = min(distances)
                        min_idx = distances.index(min_distance)
                        confidence_percent = max(0, min(100, (1 - min_distance / 2) * 100))
                        if min_distance < FACE_MATCH_THRESHOLD:
                            name = known_names[min_idx]
                            total_recognitions += 1
                            correct_recognitions += 1

                now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cv2.putText(frame, f"{name}: {confidence_percent:.1f}%", (x, y - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0) if name != "Unknown" else (0, 0, 255), 2)

                # === XỬ LÝ THEO CHẾ ĐỘ ===
                if name != "Unknown":
                    fail_count = 0
                    cv2.imwrite(temp_photo_path, frame)
                    
                    # Upload ảnh log và ghi vào Realtime Database
                    log_image_url = upload_and_get_url(bucket, temp_photo_path, lock_id)
                    write_activity_log(lock_id, 'SUCCESS', name, confidence_percent, log_image_url)

                    if selected_mode == "face_only":
                        # CHẾ ĐỘ 1: MỞ CỬA NGAY
                        message = f"[✅ Mở cửa] {name} - {confidence_percent:.1f}% | {now_str}"
                        send_telegram_message_with_photo(message, temp_photo_path)
                        
                        send_serial_command(ser, "SUCCESS")
                        
                        if tts_engine:
                            tts_engine.say(f"Xin chào {name}. Mở cửa.")
                            tts_engine.runAndWait()
                        
                        print("[INFO] Chế độ face_only: Đã mở cửa.")
                        
                        # THÊM: Đợi 6 giây (5s mở cửa + 1s buffer) rồi gửi lệnh RECOGNITION_DONE
                        time.sleep(6)
                        send_serial_command(ser, "RECOGNITION_DONE")
                        
                        return

                    elif selected_mode == "face_pin":
                        # CHẾ ĐỘ 2: YÊU CẦU PIN VÀ CHỜ KẾT QUẢ
                        print(f"[ACTION] Nhận diện: {name} ({confidence_percent:.1f}%) → Yêu cầu PIN")
                        
                        if tts_engine:
                            tts_engine.say(f"Xin chào {name}. Vui lòng nhập mã PIN trên thiết bị.")
                            tts_engine.runAndWait()

                        # Gửi yêu cầu và chờ ESP32 sẵn sàng
                        if not send_serial_command(ser, "PIN_REQUIRED", expected_response="PIN_PROMPT", timeout=5):
                            print("[ERROR] ESP32 không phản hồi yêu cầu nhập PIN.")
                            return

                        # CHỜ NHẬN PIN TỪ ESP32
                        print("[INFO] Đang chờ người dùng nhập PIN trên ESP32...")
                        received_pin = ""
                        expected_pin = EXPECTED_PIN
                        print(f"[DEBUG] Mã PIN mong đợi: {expected_pin}")
                        start_wait = time.time()
                        
                        while time.time() - start_wait < 35:
                            if ser.in_waiting > 0:
                                response = ser.readline().decode('utf-8').strip()
                                print(f"[DEBUG] ESP32 Response: {response}")
                                
                                if response.startswith("PIN_ENTERED:"):
                                    received_pin = response.replace("PIN_ENTERED:", "").strip()
                                    print(f"[INFO] Đã nhận PIN từ ESP32: {received_pin}")
                                    break
                                
                                if "PIN_TIMEOUT" in response:
                                    print("[FAIL] Người dùng không nhập PIN kịp thời.")
                                    message = f"[❌ Timeout] {name} - Không nhập PIN | {now_str}"
                                    send_telegram_message_with_photo(message, temp_photo_path)
                                    send_serial_command(ser, "FAIL")
                                    return
                        
                        # Kiểm tra PIN  
                        if received_pin == expected_pin:
                            print("[SUCCESS] PIN chính xác!")
                            message = f"[✅ Mở cửa] {name} - PIN đúng | {now_str}"
                            send_telegram_message_with_photo(message, temp_photo_path)
                            send_serial_command(ser, "SUCCESS")
                            print("[INFO] Đã gửi lệnh mở cửa.")
                            write_activity_log(lock_id, 'SUCCESS_PIN', name, confidence_percent, log_image_url)
                            
                            # THÊM: Đợi 6 giây rồi gửi RECOGNITION_DONE
                            time.sleep(6)
                            send_serial_command(ser, "RECOGNITION_DONE")
                        else:
                            print("[FAIL] PIN sai hoặc không nhận được PIN.")
                            message = f"[❌ PIN sai] {name} - PIN: {received_pin} | {now_str}"
                            send_telegram_message_with_photo(message, temp_photo_path)
                            send_serial_command(ser, "FAIL")
                            print("[INFO] Đã gửi lệnh báo thất bại.")
                            write_activity_log(lock_id, 'FAIL_PIN', name, confidence_percent, log_image_url)
                            
                            # THÊM: Gửi RECOGNITION_DONE sau khi thất bại
                            time.sleep(2)
                            send_serial_command(ser, "RECOGNITION_DONE")
                        
                        return

                else:
                    # NGƯỜI LẠ
                    if time_since_last_voice > voice_cooldown:
                        fail_count += 1
                        cv2.imwrite(temp_photo_path, frame)
                        
                        # Upload ảnh log và ghi vào Realtime Database
                        log_image_url = upload_and_get_url(bucket, temp_photo_path, lock_id)
                        write_activity_log(lock_id, 'FAIL', 'Unknown', 0, log_image_url)

                        message = f"[CẢNH BÁO] Người lạ (lần {fail_count})"
                        send_telegram_message_with_photo(message, temp_photo_path)
                        
                        if tts_engine:
                            tts_engine.say("Cảnh báo, phát hiện người lạ.")
                            tts_engine.runAndWait()
                        last_voice_time = current_time

                        if fail_count >= 3:
                            lockout_time = time.perf_counter() + lock_duration
                            fail_count = 0
                            if tts_engine:
                                tts_engine.say("Hệ thống tạm khóa.")
                                tts_engine.runAndWait()

            # Hiển thị thông tin độ sáng
            cv2.putText(frame, f"Brightness: {brightness:.0f}", (10, frame.shape[0] - 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
            
            fps = frame_count / (time.perf_counter() - start_time)
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            cv2.imshow("Face Recognition", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except Exception as e:
        print(f"[EXCEPTION] {traceback.format_exc()}")
        error_count += 1
    finally:
        profiler.disable()
        with open('profile_stats_dell_g3_3579.txt', 'w') as f:
            pstats.Stats(profiler, stream=f).sort_stats('cumulative').print_stats()

        accuracy = (correct_recognitions / total_recognitions * 100) if total_recognitions > 0 else 0.0
        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0.0
        avg_serial_latency = sum(serial_latencies) / len(serial_latencies) if serial_latencies else 0.0
        
        print("\n[THỐNG KÊ]")
        print(f"Độ chính xác: {accuracy:.1f}%")
        print(f"Tốc độ xử lý: {avg_processing_time:.1f} ms/frame")
        print(f"Độ trễ serial: {avg_serial_latency:.3f} s")
        print(f"Tổng nhận diện: {total_recognitions}, Đúng: {correct_recognitions}")

        print(f"\n[THỐNG KÊ ÁNH SÁNG]")
        print(f"Số frame ánh sáng yếu: {low_light_frames}/{frame_count} ({low_light_frames/frame_count*100:.1f}% nếu frame_count > 0 else 0)")
        print(f"Số frame đã nâng cao: {enhanced_frames}")

        if os.path.exists(temp_photo_path):
            try: 
                os.remove(temp_photo_path)
            except: 
                pass
        if 'cam' in locals(): 
            cam.release()
        if 'ser' in locals() and ser and ser.is_open: 
            ser.close()
        cv2.destroyAllWindows()
        print("[INFO] Đã thoát chương trình.")

if __name__ == "__main__":
    main()