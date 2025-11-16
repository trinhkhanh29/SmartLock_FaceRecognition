import os
import sys
import pickle
import cv2
import firebase_admin
from firebase_admin import credentials, storage
from facenet_pytorch import MTCNN, InceptionResnetV1
import torch
from dotenv import load_dotenv
import io
import re
import numpy as np

# Cấu hình stdout (UTF-8) cho Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# --- Cấu hình mặc định ---
# Nếu bạn muốn trainer KHÔNG bao giờ download ảnh từ Firebase, set DOWNLOAD_FROM_FIREBASE = "false" trong .env
DOWNLOAD_ENV_VAR = "DOWNLOAD_FROM_FIREBASE"

def initialize_firebase():
    """Khởi tạo kết nối đến Firebase và trả về object bucket."""
    env_path = os.path.join(os.path.dirname(__file__), '../.env/config.env')
    if os.path.exists(env_path):
        load_dotenv(env_path)

    cred_path = os.path.join(os.path.dirname(__file__), '../.env/firebase_credentials.json')
    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"Không tìm thấy file chứng thực: {cred_path}")

    # Lấy các biến từ env (nếu có)
    bucket_name = os.getenv('FIREBASE_STORAGE_BUCKET')
    database_url = os.getenv('FIREBASE_DATABASE_URL')

    cred = credentials.Certificate(cred_path)
    if not firebase_admin._apps:
        # Nếu có databaseURL trong env, truyền vào (không bắt buộc)
        init_opts = {}
        if bucket_name:
            init_opts['storageBucket'] = bucket_name
        if database_url:
            init_opts['databaseURL'] = database_url
        firebase_admin.initialize_app(cred, init_opts)

    bucket = storage.bucket()
    print(f"[FIREBASE] Connected to bucket: {bucket.name}")
    return bucket

def should_download_from_firebase():
    env = os.getenv(DOWNLOAD_ENV_VAR, "true").lower()
    return env not in ("0", "false", "no")

def _extract_name_from_filename(filename):
    """
    Cố gắng lấy user_name từ tên file theo định dạng:
    <faceId>_<name-with-underscores>_...jpg
    Ví dụ: 7165ac2f_Tran_Van_A_straight_1.jpg -> 'Tran Van A'
    """
    m = re.match(r'^(\d+|[a-f0-9]+)_(.+?)_', filename)
    if not m:
        return None
    name = m.group(2).replace('_', ' ')
    return name

def _process_image_file(img_path, mtcnn, resnet, device):
    """
    Trả về embedding 1D numpy array hoặc None nếu gặp lỗi / không phát hiện khuôn mặt.
    """
    try:
        img = cv2.imread(img_path)
        if img is None:
            return None

        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # MTCNN trả về tensor (face) khi dùng như mtcnn(img_rgb)
        face = mtcnn(img_rgb)
        if face is None:
            return None

        with torch.no_grad():
            face = face.unsqueeze(0).to(device)
            emb = resnet(face).detach().cpu().numpy()
            emb = np.squeeze(emb)  # 1D vector
            return emb
    except Exception as e:
        print(f"[ERROR] processing {img_path}: {e}")
        return None

def generate_embeddings(lock_id):
    """
    Tạo embeddings cho tất cả người trong lock_id.
    Quy trình:
    1) Quét thư mục local dataset/<lock_id>/<face_id>/* — ưu tiên dùng local.
    2) Nếu local không có file nào, (và biến env cho phép) sẽ query Firebase và download chỉ các file thiếu.
    3) Lưu embeddings.pkl trong dataset/<lock_id>/embeddings.pkl
    """
    print(f"[START] Generating embeddings for lock: {lock_id}")

    # Khởi tạo Firebase (chỉ khi cần list/download)
    bucket = None
    download_allowed = should_download_from_firebase()
    if download_allowed:
        try:
            bucket = initialize_firebase()
        except Exception as e:
            print(f"[WARN] Không thể khởi tạo Firebase: {e}. Tiếp tục chỉ với local files.")
            bucket = None
            # Nếu không có Firebase và không có local -> file embeddings rỗng sẽ được tạo

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"[INFO] Using device: {device}")

    mtcnn = MTCNN(keep_all=False, min_face_size=50, device=device)
    resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)

    known_embeddings = []
    known_ids = []
    known_names = []

    # Thư mục dataset dành cho lock
    base_dataset_dir = os.path.join(os.path.dirname(__file__), '..', 'dataset')
    dataset_dir = os.path.join(base_dataset_dir, lock_id)
    os.makedirs(dataset_dir, exist_ok=True)

    # ---- 1) QUÉT LOCAL: dataset/<lock_id>/<face_id>/* ----
    local_found_any = False
    if os.path.isdir(dataset_dir):
        for entry in sorted(os.listdir(dataset_dir)):
            face_dir = os.path.join(dataset_dir, entry)
            if not os.path.isdir(face_dir):
                continue
            face_id = entry
            # duyệt tất cả file ảnh trong thư mục người dùng
            for filename in sorted(os.listdir(face_dir)):
                if not filename.lower().endswith(('.jpg', '.jpeg', '.png')):
                    continue
                local_found_any = True
                local_path = os.path.join(face_dir, filename)
                emb = _process_image_file(local_path, mtcnn, resnet, device)
                if emb is not None:
                    known_embeddings.append(emb)
                    known_ids.append(face_id)
                    # Nếu tên người trong filename -> lấy, nếu không -> face_id
                    name = _extract_name_from_filename(filename) or face_id
                    known_names.append(name)
                    print(f"[LOCAL] Processed {face_id}/{filename} -> {name}")
                else:
                    print(f"[LOCAL] No face found in {local_path} (skipped)")

    # ---- 2) NẾU KHÔNG CÓ LOCAL HOẶC MUỐN BỔ SUNG: QUÉT FIREBASE (chỉ khi cho phép) ----
    if download_allowed and bucket is not None:
        # chuẩn bị prefix cho cả faces và pending_faces
        prefixes = [f"locks/{lock_id}/faces/", f"locks/{lock_id}/pending_faces/"]
        for prefix in prefixes:
            try:
                blobs = list(bucket.list_blobs(prefix=prefix))
            except Exception as e:
                print(f"[WARN] Không thể list blobs cho prefix {prefix}: {e}")
                blobs = []

            for blob in blobs:
                try:
                    parts = blob.name.split('/')
                    # mong muốn dạng: locks/<lockId>/(faces|pending_faces)/<userId>/<filename>
                    if len(parts) < 5:
                        continue
                    blob_lock, folder_type, user_id = parts[0], parts[2], parts[3] if len(parts) >= 4 else None
                    # parts layout check
                    user_id = parts[3]
                    filename = parts[4]

                    # local expected path: dataset/<lock_id>/<user_id>/<filename>
                    local_user_dir = os.path.join(dataset_dir, user_id)
                    os.makedirs(local_user_dir, exist_ok=True)
                    local_path = os.path.join(local_user_dir, filename)

                    # Nếu file đã được xử lý trong local pass (tránh xử lý duplicate)
                    # Nếu local exists, _process_image_file sẽ handle nó (we already processed local above).
                    # Chỉ download nếu file local chưa có
                    if not os.path.exists(local_path):
                        try:
                            blob.download_to_filename(local_path)
                            print(f"[DOWNLOAD] {blob.name} -> {local_path}")
                        except Exception as e:
                            print(f"[WARN] Không thể download {blob.name}: {e}")
                            continue
                    else:
                        # nếu đã có local, chỉ thông báo
                        print(f"[SKIP] Local exists, skip download: {local_path}")

                    # Sau khi đảm bảo file tồn tại local, process nó
                    emb = _process_image_file(local_path, mtcnn, resnet, device)
                    if emb is not None:
                        known_embeddings.append(emb)
                        known_ids.append(user_id)
                        name = _extract_name_from_filename(filename) or user_id
                        known_names.append(name)
                        print(f"[FIREBASE] Processed {user_id}/{filename} -> {name}")
                    else:
                        print(f"[FIREBASE] No face found in {local_path} (skipped)")

                except Exception as e:
                    print(f"[ERROR] processing blob {getattr(blob, 'name', str(blob))}: {e}")

    # ---- 3) LƯU embeddings (dưới dạng pickle) ----
    embeddings_path = os.path.join(dataset_dir, "embeddings.pkl")
    try:
        # Chuyển embeddings thành list để pickle ổn định
        # (mỗi embedding là 1D numpy array)
        pickle.dump((known_embeddings, known_ids, known_names), open(embeddings_path, 'wb'))
        print(f"[DONE] Embeddings saved to: {embeddings_path}")
        print(f"[SUMMARY] Total faces processed: {len(known_ids)}")
    except Exception as e:
        print(f"[ERROR] Không thể lưu embeddings: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python trainer.py <lock_id>")
        sys.exit(1)

    lock_id_arg = sys.argv[1]
    generate_embeddings(lock_id_arg)
