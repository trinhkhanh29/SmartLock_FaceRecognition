import os
import shutil
import random
import logging
from datetime import datetime
import cv2
import numpy as np
import torch
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, storage
from facenet_pytorch import MTCNN

# ================= Configuration =================
input_dir = r"C:\Users\PC\source\repos\NCKH-2025\SmartLock_FaceRecognition\PyCharm\dataset\img_align_celeba"
output_dir = r"C:\Users\PC\source\repos\NCKH-2025\SmartLock_FaceRecognition\PyCharm\dataset\faces"
os.makedirs(output_dir, exist_ok=True)

english_names = [
    "Alice", "Bob", "Charlie", "Daisy", "Ethan", "Fiona",
    "George", "Hannah", "Ivan", "Julia", "Kevin", "Lily",
    "Mike", "Nora", "Oscar", "Paula", "Quinn", "Ruby",
    "Sam", "Tina", "Victor", "Wendy", "Xander", "Yara", "Zane"
]

bucket = None

# ================= Firebase =====================
def initialize_firebase():
    global bucket
    cred_path = os.path.join(os.path.dirname(__file__), '../.env/firebase_credentials.json')
    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"Không tìm thấy file chứng thực: {cred_path}")

    load_dotenv(os.path.join(os.path.dirname(__file__), '../.env/config.env'))
    bucket_name = os.getenv('FIREBASE_STORAGE_BUCKET', 'smartlockfacerecognition.firebasestorage.app')

    cred = credentials.Certificate(cred_path)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred, {'storageBucket': bucket_name})

    bucket = storage.bucket()
    logging.info(f"Đã kết nối Firebase: {bucket.name}")
    return bucket

# ================= Upload =======================
def upload_to_firebase(filepath, face_id, face_name):
    global bucket
    if not bucket or not os.path.exists(filepath):
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    firebase_path = f"faces/{face_id}/{face_id}_{face_name}_{timestamp}.jpg"

    try:
        blob = bucket.blob(firebase_path)
        blob.upload_from_filename(filepath, content_type='image/jpeg')
        blob.make_public()
        logging.info(f"Upload: {firebase_path}")
        return blob.public_url
    except Exception as e:
        logging.error(f"Upload thất bại: {e}")
        return None

# ================= Process =======================
def process_image(image_path, face_id, face_name):
    try:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        mtcnn = MTCNN(keep_all=False, min_face_size=50, device=device)

        img = cv2.imread(image_path)
        if img is None:
            logging.error("Không đọc được ảnh.")
            return None

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        boxes, probs = mtcnn.detect(img_rgb)

        if boxes is None or len(boxes) == 0:
            logging.warning(f"Không tìm thấy khuôn mặt: {image_path}")
            return None

        idx_best = np.argmax(probs)
        box = boxes[idx_best]
        x1, y1, x2, y2 = map(int, box)
        face_crop = img[y1:y2, x1:x2]

        # Lưu file cắt mặt tạm
        person_folder = os.path.join(output_dir, face_id)
        os.makedirs(person_folder, exist_ok=True)
        save_path = os.path.join(person_folder, f"{face_id}_{face_name}.jpg")
        cv2.imwrite(save_path, face_crop)

        # Upload Firebase
        url = upload_to_firebase(save_path, face_id, face_name)
        return url

    except Exception as e:
        logging.error(f"Lỗi xử lý ảnh {image_path}: {e}")
        return None

# ================= Main =========================
def main():
    initialize_firebase()
    all_files = sorted([f for f in os.listdir(input_dir) if f.lower().endswith(('.jpg', '.png'))])

    for idx, file in enumerate(all_files, start=1):
        face_id = f"person_{idx}"
        face_name = random.choice(english_names)
        src_path = os.path.join(input_dir, file)

        url = process_image(src_path, face_id, face_name)
        if url:
            print(f"✅ {face_id} uploaded: {url}")
        else:
            print(f"❌ {face_id} failed: {file}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
