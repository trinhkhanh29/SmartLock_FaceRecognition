#facedetect.py
import os
import cv2
import firebase_admin
from firebase_admin import credentials, storage
from datetime import datetime
from facenet_pytorch import MTCNN
import numpy as np
import pyttsx3
# from gtts import gTTS
# import playsound
import tempfile

# Global TTS engine
tts_engine = None


# Khởi tạo kết nối Firebase để lưu trữ ảnh khuôn mặt

# Khởi tạo kết nối Firebase để lưu trữ ảnh khuôn mặt
def initialize_firebase():
    """
    Kết nối với Firebase Storage để lưu trữ ảnh khuôn mặt.
    """
    cred_path = os.path.join(os.path.dirname(__file__), '../.env/firebase_credentials.json')
    if not os.path.exists(cred_path):
        raise FileNotFoundError("[LỖI] Không tìm thấy tệp chứng thực Firebase tại: " + cred_path)
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'smartlockfacerecognition.firebasestorage.app'
    })
    print("[THÔNG TIN] Đã kết nối thành công với Firebase.")
    return storage.bucket()

# Phát âm thanh bằng tiếng Việt, ưu tiên giọng Microsoft An
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


# Hàm phát âm thanh
def speak(text):
    global tts_engine
    if tts_engine is None:
        tts_engine = init_tts_engine()

    if tts_engine is not None:
        try:
            tts_engine.say(text)
            tts_engine.runAndWait()
        except Exception as e:
            print(f"[WARNING] Không thể phát âm thanh: {e}")
    else:
        print(f"[THÔNG BÁO] {text}")


# Tải ảnh lên Firebase và trả về URL công khai
def upload_to_firebase(bucket, filepath, face_id, face_name, count):
    """
    Tải ảnh khuôn mặt lên Firebase Storage và trả về URL công khai.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"[LỖI] Không tìm thấy tệp tại: {filepath}")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    firebase_filename = f"faces/{face_id}/{face_id}_{face_name.replace(' ', '_')}_{count}_{timestamp}.jpg"
    print(f"[THÔNG TIN] Tải lên Firebase với tên: {firebase_filename}")
    blob = bucket.blob(firebase_filename)
    blob.upload_from_filename(filepath)
    blob.make_public()
    return blob.public_url

def main():
    # Khởi tạo Firebase
    try:
        bucket = initialize_firebase()
    except Exception as e:
        print(f"[LỖI] Không thể kết nối với Firebase: {str(e)}")
        speak("Lỗi kết nối Firebase. Vui lòng kiểm tra tệp cấu hình.")
        return

    # Khởi tạo camera
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        print("[LỖI] Không thể mở camera. Vui lòng kiểm tra thiết bị.")
        speak("Không thể mở camera. Vui lòng kiểm tra thiết bị.")
        return
    cam.set(3, 640)
    cam.set(4, 480)

    # Khởi tạo MTCNN để phát hiện khuôn mặt
    try:
        mtcnn = MTCNN(keep_all=False, min_face_size=100, thresholds=[0.6, 0.7, 0.7], factor=0.709)
        print("[THÔNG TIN] Đã tải mô hình phát hiện khuôn mặt MTCNN.")
    except Exception as e:
        print(f"[LỖI] Không thể tải MTCNN: {str(e)}")
        speak("Lỗi khi tải mô hình phát hiện khuôn mặt.")
        cam.release()
        return

    # Nhập ID và tên người dùng
    print("\n[THÔNG TIN] Vui lòng nhập thông tin để bắt đầu thu thập dữ liệu khuôn mặt.")
    speak("Vui lòng nhập ID và tên của bạn.")
    face_id = input('Nhập ID người dùng (chỉ nhập số) >> ').strip()
    if not face_id.isdigit():
        print("[LỖI] ID phải là một số nguyên. Vui lòng thử lại.")
        speak("ID phải là một số. Vui lòng nhập lại.")
        cam.release()
        return
    face_name = input('Nhập tên người dùng >> ').strip()
    if not face_name:
        print("[LỖI] Tên không được để trống. Vui lòng thử lại.")
        speak("Tên không được để trống. Vui lòng nhập lại.")
        cam.release()
        return

    speak(f"Xin chào {face_name}. Vui lòng nhìn vào camera và di chuyển nhẹ để thu thập dữ liệu khuôn mặt.")
    print("\n[THÔNG TIN] Bắt đầu thu thập khuôn mặt...")
    print(
        "[HƯỚNG DẪN] Nhìn vào camera, di chuyển nhẹ đầu để chụp các góc khác nhau. Đảm bảo ánh sáng tốt và khuôn mặt rõ ràng.")

    # Tạo thư mục dataset
    dataset_path = os.path.join(os.path.dirname(__file__), '../dataset')
    os.makedirs(dataset_path, exist_ok=True)

    count = 0
    sample_limit = 50
    min_face_size = 100
    optimal_face_size = 200
    last_instruction_time = datetime.now()
    instruction_cooldown = 10  # Hướng dẫn bằng giọng nói mỗi 10 giây nếu cần

    try:
        while count < sample_limit:
            ret, frame = cam.read()
            if not ret:
                print("[LỖI] Không thể đọc khung hình từ camera.")
                speak("Lỗi camera. Vui lòng kiểm tra thiết bị.")
                break

            frame = cv2.flip(frame, 1)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Phát hiện khuôn mặt bằng MTCNN
            boxes, probs = mtcnn.detect(frame_rgb)
            current_time = datetime.now()
            instruction_needed = (current_time - last_instruction_time).total_seconds() > instruction_cooldown

            if boxes is not None and len(boxes) > 0:
                for box, prob in zip(boxes, probs):
                    if prob < 0.9:
                        cv2.putText(frame, "Khuôn mặt không rõ, vui lòng nhìn thẳng",
                                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        if instruction_needed:
                            speak("Khuôn mặt không rõ. Vui lòng nhìn thẳng vào camera.")
                            last_instruction_time = current_time
                        continue
                    x, y, x2, y2 = box.astype(int)
                    w, h = x2 - x, y2 - y
                    if w < min_face_size or h < min_face_size:
                        cv2.putText(frame, "Khuôn mặt quá nhỏ, đến gần hơn",
                                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                        if instruction_needed:
                            speak("Khuôn mặt quá nhỏ. Vui lòng đến gần camera hơn.")
                            last_instruction_time = current_time
                        continue

                    # Vẽ khung quanh khuôn mặt
                    cv2.rectangle(frame, (x, y), (x2, y2), (0, 255, 0), 2)

                    # Lưu ảnh khuôn mặt nếu đủ lớn
                    if w >= optimal_face_size and h >= optimal_face_size:
                        count += 1
                        filename = f"{face_id}_{face_name.replace(' ', '_')}_{count}.jpg"
                        filepath = os.path.join(dataset_path, filename)
                        # cv2.imwrite(filepath, frame[y:y2, x:x2])
                        # Đảm bảo toạ độ nằm trong kích thước ảnh
                        x = max(0, x)
                        y = max(0, y)
                        x2 = min(frame.shape[1], x2)
                        y2 = min(frame.shape[0], y2)

                        # Cắt khuôn mặt và lưu
                        face_crop = frame[y:y2, x:x2]
                        if face_crop.size == 0:
                            print("[CẢNH BÁO] Khuôn mặt trích xuất bị rỗng, bỏ qua mẫu này.")
                            continue

                        cv2.imwrite(filepath, face_crop)
                        print(f"[THÔNG TIN] Đã lưu ảnh {count}/{sample_limit}: {filepath}")

                        # Tải lên Firebase
                        try:
                            public_url = upload_to_firebase(bucket, filepath, face_id, face_name, count)
                            print(f"[THÔNG TIN] Đã tải lên Firebase: {public_url}")
                        except Exception as e:
                            print(f"[LỖI] Không thể tải lên Firebase: {str(e)}")

                        # Hiển thị số lượng ảnh đã thu thập
                        cv2.putText(frame, f"Đã thu thập: {count}/{sample_limit}",
                                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
                        cv2.imshow('Khuôn mặt đã chụp', frame[y:y2, x:x2])
                        if count % 10 == 0:
                            speak(f"Đã thu thập {count} ảnh. Tiếp tục nhìn vào camera.")

            else:
                cv2.putText(frame, "Không phát hiện khuôn mặt",
                            (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
                if instruction_needed:
                    speak("Không phát hiện khuôn mặt. Vui lòng nhìn vào camera.")
                    last_instruction_time = current_time

            # Hiển thị khung hình chính
            cv2.imshow('Thu thập khuôn mặt', frame)

            # Thoát khi nhấn ESC hoặc đủ mẫu
            key = cv2.waitKey(100) & 0xff
            if key == 27 or count >= sample_limit:
                break

    except Exception as e:
        print(f"[LỖI] Lỗi trong quá trình thu thập: {str(e)}")
        speak("Có lỗi xảy ra. Vui lòng thử lại.")
    finally:
        cam.release()
        cv2.destroyAllWindows()
        print(f"\n[THÔNG TIN] Đã thu thập {count} mẫu. Chương trình kết thúc.")
        speak(f"Đã thu thập {count} mẫu. Cảm ơn bạn.")


if __name__ == "__main__":
    main()