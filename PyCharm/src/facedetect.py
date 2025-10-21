# facedetect.py
import os
import cv2
import firebase_admin
from firebase_admin import credentials, storage
from datetime import datetime
from facenet_pytorch import MTCNN
import pyttsx3
import numpy as np

# ========================== KHỞI TẠO TOÀN CỤC ==========================
tts_engine = None


# ========================== KẾT NỐI FIREBASE ==========================
def initialize_firebase():
    """
    Kết nối với Firebase Storage để lưu trữ ảnh khuôn mặt.
    """
    cred_path = os.path.join(os.path.dirname(__file__), '../.env/firebase_credentials.json')
    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"[LỖI] Không tìm thấy tệp chứng thực Firebase: {cred_path}")

    cred = credentials.Certificate(cred_path)

    # ⚙️ Lưu ý: THAY bucket_name này bằng đúng tên trong Firebase Console → Project settings → Storage
    bucket_name = "smartlockfacerecognition.firebasestorage.app"

    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {'storageBucket': bucket_name})

    bucket = storage.bucket()
    if bucket is None:
        raise ConnectionError(f"[LỖI] Không thể khởi tạo bucket '{bucket_name}'.")

    print(f"[THÔNG TIN] ✅ Đã kết nối Firebase thành công với bucket: {bucket.name}")
    return bucket


# ========================== GIỌNG NÓI (TTS) ==========================
def init_tts_engine():
    try:
        engine = pyttsx3.init()
        engine.setProperty('rate', 150)
        engine.setProperty('volume', 1.0)
        voices = engine.getProperty('voices')
        for voice in voices:
            if 'vi' in voice.languages or 'Microsoft An' in voice.name:
                engine.setProperty('voice', voice.id)
                print(f"[INFO] ✅ Đã chọn giọng nói: {voice.name}")
                break
        else:
            print("[WARNING] ⚠ Không tìm thấy giọng nói tiếng Việt. Dùng mặc định.")
        return engine
    except Exception as e:
        print(f"[WARNING] Không thể khởi tạo engine TTS: {e}")
        return None


def speak(text):
    global tts_engine
    if tts_engine is None:
        tts_engine = init_tts_engine()
    if tts_engine:
        try:
            tts_engine.say(text)
            tts_engine.runAndWait()
        except Exception as e:
            print(f"[WARNING] Không thể phát âm thanh: {e}")
    print(f"[VOICE] {text}")


# ========================== UPLOAD LÊN FIREBASE ==========================
def upload_to_firebase(bucket, filepath, face_id, face_name, count):
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"[LỖI] Không tìm thấy tệp: {filepath}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    firebase_filename = f"faces/{face_id}/{face_id}_{face_name.replace(' ', '_')}_{count}_{timestamp}.jpg"

    try:
        blob = bucket.blob(firebase_filename)
        blob.upload_from_filename(filepath)
        blob.make_public()
        print(f"[UPLOAD] ✅ {firebase_filename}")
        return blob.public_url
    except Exception as e:
        print(f"[LỖI] Upload Firebase thất bại: {e}")
        return None


# ========================== HÀM CHÍNH ==========================
def main():
    # --- Kết nối Firebase ---
    try:
        bucket = initialize_firebase()
    except Exception as e:
        print(f"[LỖI] Firebase: {e}")
        speak("Không thể kết nối Firebase. Vui lòng kiểm tra cấu hình.")
        return

    # --- Khởi tạo camera ---
    cam = cv2.VideoCapture(1, cv2.CAP_DSHOW)
    if not cam.isOpened():
        print("[LỖI] Không mở được camera.")
        speak("Không thể mở camera. Vui lòng kiểm tra thiết bị.")
        return
    cam.set(3, 640)
    cam.set(4, 480)

    # --- Khởi tạo MTCNN ---
    try:
        mtcnn = MTCNN(keep_all=False, min_face_size=80,
                      thresholds=[0.6, 0.7, 0.7], factor=0.709)
        print("[THÔNG TIN] ✅ MTCNN đã sẵn sàng.")
    except Exception as e:
        print(f"[LỖI] Không thể tải MTCNN: {e}")
        speak("Không thể tải mô hình phát hiện khuôn mặt.")
        cam.release()
        return

    # --- Nhập thông tin người dùng ---
    print("\n[THÔNG TIN] Vui lòng nhập thông tin người dùng:")
    speak("Vui lòng nhập ID và tên của bạn.")
    face_id = input('Nhập ID người dùng (chỉ nhập số) >> ').strip()
    if not face_id.isdigit():
        speak("ID phải là số. Vui lòng nhập lại.")
        return
    face_name = input('Nhập tên người dùng >> ').strip()
    if not face_name:
        speak("Tên không được để trống.")
        return

    # --- Tạo thư mục dataset ---
    dataset_path = os.path.join(os.path.dirname(__file__), '../dataset')
    os.makedirs(dataset_path, exist_ok=True)

    # --- Cấu hình hướng thu thập ---
    directions = [
        ("Nhìn thẳng vào camera", "straight"),
        ("Quay mặt sang trái", "left"),
        ("Quay mặt sang phải", "right"),
        ("Nhìn lên", "up"),
        ("Nhìn xuống", "down")
    ]
    current_direction_index = 0
    images_per_direction = 10
    sample_limit = len(directions) * images_per_direction
    count = 0

    speak("Bắt đầu thu thập khuôn mặt. Hãy nhìn thẳng vào camera.")
    print("\n[THÔNG TIN] Bắt đầu thu thập ảnh khuôn mặt...")

    try:
        while count < sample_limit:
            ret, frame = cam.read()
            if not ret:
                speak("Lỗi đọc camera.")
                break

            frame = cv2.flip(frame, 1)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            boxes, probs = mtcnn.detect(frame_rgb)

            if boxes is not None and len(boxes) > 0:
                for box, prob in zip(boxes, probs):
                    if prob < 0.9:
                        continue

                    x, y, x2, y2 = box.astype(int)
                    w, h = x2 - x, y2 - y
                    if w < 100 or h < 100:
                        continue

                    # Cắt khuôn mặt
                    face_crop = frame[y:y2, x:x2]
                    if face_crop.size == 0:
                        continue

                    # Lưu ảnh
                    count += 1
                    filename = f"{face_id}_{face_name.replace(' ', '_')}_{directions[current_direction_index][1]}_{count}.jpg"
                    filepath = os.path.join(dataset_path, filename)
                    cv2.imwrite(filepath, face_crop)
                    print(f"[THÔNG TIN] Đã lưu ảnh {count}/{sample_limit}: {filepath}")

                    # Upload Firebase
                    upload_to_firebase(bucket, filepath, face_id, face_name, count)

                    # Hướng dẫn chuyển hướng tiếp theo
                    if count % images_per_direction == 0 and count < sample_limit:
                        current_direction_index = (current_direction_index + 1) % len(directions)
                        next_instruction = directions[current_direction_index][0]
                        print(f"[HƯỚNG DẪN] → {next_instruction}")
                        speak(next_instruction)

                    # Hiển thị tiến trình
                    cv2.rectangle(frame, (x, y), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"Đã thu thập: {count}/{sample_limit}",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            else:
                cv2.putText(frame, "Không phát hiện khuôn mặt",
                            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

            cv2.imshow('Thu thập khuôn mặt', frame)
            key = cv2.waitKey(100) & 0xff
            if key == 27:
                break

    except Exception as e:
        print(f"[LỖI] Quá trình thu thập: {e}")
        speak("Có lỗi xảy ra. Vui lòng thử lại.")
    finally:
        cam.release()
        cv2.destroyAllWindows()
        speak(f"Đã thu thập {count} mẫu. Cảm ơn bạn.")
        print(f"\n[THÔNG TIN] ✅ Hoàn tất thu thập {count}/{sample_limit} ảnh.")


# ========================== CHẠY CHƯƠNG TRÌNH ==========================
if __name__ == "__main__":
    main()
