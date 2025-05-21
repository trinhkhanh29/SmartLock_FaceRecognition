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

# Khởi tạo Serial
def init_serial(port='COM4', baudrate=115200):
    try:
        ser = serial.Serial(port, baudrate, timeout=1)
        print(f"[INFO] Đã kết nối Serial tại {port}")
        return ser
    except serial.SerialException as e:
        print(f"[ERROR] Không thể kết nối Serial: {e}")
        return None

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
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'smartlockfacerecognition.firebasestorage.app'
    })
    return storage.bucket()

# Tải danh sách tên và embeddings từ Firebase hoặc cache cục bộ
def load_known_faces(bucket, local_dir):
    os.makedirs(local_dir, exist_ok=True)
    embeddings_path = os.path.join(local_dir, "embeddings.pkl")

    # Lấy danh sách file trên Firebase
    firebase_files = set(blob.name for blob in bucket.list_blobs(prefix='faces/'))
    print(f"[DEBUG] Số file trên Firebase: {len(firebase_files)}")

    # Kiểm tra cache embeddings cục bộ
    cached_data = None
    if os.path.exists(embeddings_path):
        try:
            with open(embeddings_path, 'rb') as f:
                cached_data = pickle.load(f)
                known_embeddings, known_ids, known_names, cached_files = cached_data
                print(f"[INFO] Đã tải {len(known_ids)} embeddings từ cache: {embeddings_path}")
                if set(cached_files) == firebase_files:
                    print("[INFO] Cache hợp lệ, không cần tải lại từ Firebase.")
                    return known_embeddings, known_ids, known_names
                else:
                    print("[INFO] Phát hiện thay đổi trong Firebase, cập nhật embeddings.")
        except Exception as e:
            print(f"[WARNING] Lỗi khi tải cache embeddings: {e}. Tải lại từ Firebase.")

    # Nếu cache không hợp lệ hoặc không tồn tại, tải từ Firebase
    mtcnn = MTCNN(keep_all=False, min_face_size=150, thresholds=[0.7, 0.8, 0.8])
    resnet = InceptionResnetV1(pretrained='vggface2').eval()
    known_embeddings = []
    known_ids = []
    known_names = []
    processed_files = []

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
            if not os.path.exists(local_path):
                print(f"[DEBUG] Tải file về: {local_path}")
                blob.download_to_filename(local_path)
            else:
                print(f"[DEBUG] Sử dụng ảnh cục bộ: {local_path}")
            img = cv2.imread(local_path)
            if img is None:
                print(f"[WARNING] Không thể đọc ảnh: {local_path}")
                continue
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            face = mtcnn(img_rgb)
            if face is not None:
                embedding = resnet(face.unsqueeze(0)).detach().numpy()
                known_embeddings.append(embedding)
                known_ids.append(user_id)
                known_names.append(user_name)
                processed_files.append(blob_name)
                print(f"[INFO] Đã thêm khuôn mặt: ID={user_id}, Name={user_name}")
            else:
                print(f"[WARNING] Không phát hiện khuôn mặt trong: {filename}")
        except (ValueError, IndexError) as e:
            print(f"[WARNING] Bỏ qua file không hợp lệ: {blob_name}, {str(e)}")

    # Lưu embeddings và danh sách file vào cache
    if known_embeddings:
        try:
            with open(embeddings_path, 'wb') as f:
                pickle.dump((known_embeddings, known_ids, known_names, processed_files), f)
            print(f"[INFO] Đã lưu embeddings vào: {embeddings_path}")
        except Exception as e:
            print(f"[WARNING] Lỗi khi lưu cache embeddings: {e}")

    return known_embeddings, known_ids, known_names

# Tải mô hình DNN cho phát hiện khuôn mặt
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

def main():
    # Kiểm tra token Telegram
    if not verify_telegram_token():
        print("[ERROR] Không thể tiếp tục do token Telegram không hợp lệ.")
        sys.exit(1)

    # Khởi tạo TTS
    tts_engine = init_tts_engine()
    ser = init_serial(port='COM4')

    # Biến đếm thất bại và khóa
    fail_count = 0
    lockout_time = 0
    lock_duration = 60  # thời gian khóa: 60 giây

    # Biến thống kê thực nghiệm
    correct_recognitions = 0
    total_recognitions = 0
    processing_times = []
    false_positives = 0
    false_negatives = 0
    # Placeholder cho tỉ lệ sai từ 100 thử nghiệm (cập nhật sau khi thử nghiệm thực tế)
    false_positive_rate = 5.0  # % (giả định, thay bằng dữ liệu thực)
    false_negative_rate = 10.0  # % (giả định, thay bằng dữ liệu thực)

    try:
        # Khởi tạo Firebase
        bucket = initialize_firebase()

        # Tải danh sách khuôn mặt đã biết
        dataset_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "dataset"))
        load_start = time.time()
        known_embeddings, known_ids, known_names = load_known_faces(bucket, dataset_path)
        print(f"[INFO] Thời gian tải embeddings: {(time.time() - load_start):.3f}s")
        if not known_embeddings:
            print("[ERROR] Không có dữ liệu khuôn mặt nào từ Firebase hoặc cache. Vui lòng thu thập dữ liệu trước.")
            sys.exit(1)

        # Khởi tạo FaceNet
        mtcnn = MTCNN(keep_all=False, min_face_size=150, thresholds=[0.7, 0.8, 0.8])
        resnet = InceptionResnetV1(pretrained='vggface2').eval()

        # Nạp bộ phát hiện khuôn mặt DNN
        face_detector = load_deep_face_detector()
        if face_detector is None:
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            if face_cascade.empty():
                print("[ERROR] Không thể tải bộ phát hiện khuôn mặt.")
                sys.exit(1)
            print("[INFO] Sử dụng Haar Cascade do thiếu mô hình DNN.")

        # Khởi tạo camera
        cam = cv2.VideoCapture(0)
        if not cam.isOpened():
            print("[ERROR] Không thể mở camera.")
            sys.exit(1)
        cam.set(3, 640)
        cam.set(4, 480)
        min_face_size = 150
        optimal_face_size = 200
        print("\n[INFO] Face recognition started. Press ESC to exit.")

        min_face_size = 150
        optimal_face_size = 200
        print("\n[INFO] Face recognition started. Press ESC to exit.")
        frame_count = 0
        start_time = time.time()
        temp_photo_path = os.path.join(os.path.dirname(__file__), "..", "temp", "temp_face.jpg")
        voice_cooldown = 5
        last_voice_time = datetime.now()

        # Phát âm thanh khởi động khi bật camera
        sound_path = os.path.join(os.path.dirname(__file__), '../sound/Ring-Doorbell-Sound.wav')
        if not os.path.exists(sound_path):
            print(f"[ERROR] File âm thanh không tồn tại tại: {sound_path}")
        else:
            play_startup_sound(sound_path)

        while True:
            try:
                ret, frame = cam.read()
                if not ret:
                    print("[ERROR] Không thể đọc khung hình từ camera.")
                    break

                frame = cv2.flip(frame, 1)
                frame_count += 1
                elapsed_time = time.time() - start_time
                fps = frame_count / elapsed_time if elapsed_time > 0 else 0
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Kiểm tra xem có đang trong thời gian bị khóa không
                if time.time() < lockout_time:
                    print("[THÔNG BÁO] Hệ thống đang bị khóa vì nhận diện sai quá 3 lần.")
                    cv2.putText(frame, "Bi khoa 1 phut - Vui long doi...", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                    cv2.imshow("Face Recognition", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break
                    continue  # Bỏ qua xử lý nhận diện trong lúc bị khóa

                # Bắt đầu đo thời gian xử lý
                frame_process_start = time.time()

                # Phát hiện khuôn mặt
                process_start = time.time()
                if face_detector is not None:
                    faces = detect_faces_dnn(face_detector, frame)
                else:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(
                        gray, scaleFactor=1.1, minNeighbors=6, minSize=(min_face_size, min_face_size)
                    )
                print(f"[DEBUG] Số khuôn mặt phát hiện: {len(faces)}, thời gian: {(time.time() - process_start):.3f}s")

                current_time = datetime.now()
                time_since_last_voice = (current_time - last_voice_time).total_seconds()

                for (x, y, w, h) in faces:
                    if w < min_face_size or h < min_face_size:
                        print(f"[DEBUG] Bỏ qua khuôn mặt nhỏ: {w}x{h}")
                        continue

                    # Hướng dẫn người dùng nếu khuôn mặt nhỏ
                    if w < optimal_face_size and time_since_last_voice > voice_cooldown and tts_engine:
                        voice_message = "Vui lòng đưa khuôn mặt gần hơn để nhận diện chính xác"
                        tts_engine.say(voice_message)
                        tts_engine.runAndWait()
                        last_voice_time = current_time
                        print("[VOICE] Phát âm thanh hướng dẫn")

                    cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                    face_img = frame_rgb[y:y + h, x:x + w]
                    recognition_start = time.time()
                    face_tensor = mtcnn(face_img)
                    name = "Unknown"
                    confidence_percent = 0.0
                    color = (255, 255, 255)

                    if face_tensor is not None:
                        embedding = resnet(face_tensor.unsqueeze(0)).detach().numpy()
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
                        print(
                            f"[DEBUG] Nhận diện: {name}, Độ tin cậy: {confidence_percent:.1f}%, thời gian: {(time.time() - recognition_start):.3f}s")

                        # Cập nhật thống kê
                        total_recognitions += 1
                        if name != "Unknown":
                            correct_recognitions += 1
                        # Giả định false positive/negative (cần thử nghiệm thực tế để xác định)
                        # Ví dụ: nếu name != "Unknown" nhưng thực tế là người lạ -> false positive
                        # Nếu name == "Unknown" nhưng thực tế là người quen -> false negative
                        # Cập nhật sau khi có dữ liệu thực nghiệm

                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if name != "Unknown":
                        fail_count = 0  # Reset fail count on successful recognition
                        cv2.imwrite(temp_photo_path, frame)
                        message = f"[✅ {now_str}] Mở cửa thành công - {name} (Độ tin cậy: {confidence_percent:.1f}%)"
                        if send_telegram_message_with_photo(message, temp_photo_path):
                            if tts_engine:
                                send_serial_command(ser, "SUCCESS")
                                voice_message = f"Xin chào {name}. Đã nhận diện thành công. Mở cửa"
                                tts_engine.say(voice_message)
                                tts_engine.runAndWait()
                            print("[VOICE] Phát âm thanh chào mừng")
                            print("[INFO] Đã gửi thông báo mở cửa. Thoát chương trình.")
                            return
                    elif time_since_last_voice > voice_cooldown and tts_engine:
                        fail_count += 1  # Increment fail count for unknown face
                        print(f"[CẢNH BÁO] Nhận diện thất bại {fail_count}/3")
                        cv2.imwrite(temp_photo_path, frame)
                        message = f"[🚨 {now_str}] CẢNH BÁO: Phát hiện người lạ - Độ tin cậy thấp ({confidence_percent:.1f}%)"
                        if send_telegram_message_with_photo(message, temp_photo_path):
                            send_serial_command(ser, "FAIL")
                            voice_message = "Cảnh báo! Phát hiện người lạ"
                            tts_engine.say(voice_message)
                            tts_engine.runAndWait()
                            print("[VOICE] Phát âm thanh cảnh báo")
                            last_voice_time = current_time

                        # Check if failed 3 times
                        if fail_count >= 3:
                            lockout_time = time.time() + lock_duration
                            fail_count = 0
                            print("[BẢO MẬT] Hệ thống bị khóa trong 1 phút.")
                            if tts_engine:
                                tts_engine.say("Hệ thống bị khóa trong một phút do nhận diện sai quá ba lần")
                                tts_engine.runAndWait()

                    cv2.putText(frame, name, (x + 5, y - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
                    cv2.putText(frame, f"{confidence_percent:.1f}%", (x + 5, y + h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                                (255, 255, 0), 2)

                # Tính thời gian xử lý frame
                frame_process_time = (time.time() - frame_process_start) * 1000  # ms
                processing_times.append(frame_process_time)

                # Tính toán thống kê
                accuracy = (correct_recognitions / total_recognitions * 100) if total_recognitions > 0 else 0.0
                avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0.0

                # Hiển thị thống kê trên frame
                cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                cv2.putText(frame, f"Accuracy: {accuracy:.1f}%", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                cv2.putText(frame, f"Proc Time: {avg_processing_time:.1f} ms", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                cv2.putText(frame, f"FP Rate: {false_positive_rate:.1f}%", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                cv2.putText(frame, f"FN Rate: {false_negative_rate:.1f}%", (10, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

                cv2.imshow('Face Recognition - FaceNet DNN', frame)

                key = cv2.waitKey(10)
                if key == 27 or key == ord('q'):
                    break

            except KeyboardInterrupt:
                print("\n[INFO] Program interrupted by user.")
                break
            except Exception as e:
                print(f"[ERROR] Lỗi trong vòng lặp chính: {str(e)}")
                print(f"[DEBUG] Traceback: {traceback.format_exc()}")
                continue

    finally:
        # In thống kê cuối cùng
        accuracy = (correct_recognitions / total_recognitions * 100) if total_recognitions > 0 else 0.0
        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0.0
        print("\n[THỐNG KÊ THỰC NGHIỆM]")
        print(f"Độ chính xác: {accuracy:.1f}%")
        print(f"Tốc độ xử lý trung bình: {avg_processing_time:.1f} ms/frame")
        print(f"Tỉ lệ False Positive (trong 100 thử nghiệm): {false_positive_rate:.1f}%")
        print(f"Tỉ lệ False Negative (trong 100 thử nghiệm): {false_negative_rate:.1f}%")
        print(f"Tổng số nhận diện: {total_recognitions}")
        print(f"Nhận diện đúng: {correct_recognitions}")

        if os.path.exists(temp_photo_path):
            try:
                os.remove(temp_photo_path)
                print(f"[INFO] Đã xóa file ảnh tạm: {temp_photo_path}")
            except Exception as e:
                print(f"[ERROR] Không thể xóa file ảnh tạm: {str(e)}")
        if 'cam' in locals() and cam.isOpened():
            cam.release()
        cv2.destroyAllWindows()
        print("\n[INFO] Program exited cleanly.")

if __name__ == "__main__":
    main()
