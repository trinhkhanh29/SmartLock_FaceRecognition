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
import re  # THÊM IMPORT RE

# Cấu hình stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def initialize_firebase():
    """Khởi tạo kết nối đến Firebase."""
    env_path = os.path.join(os.path.dirname(__file__), '../.env/config.env')
    load_dotenv(env_path)
    
    cred_path = os.path.join(os.path.dirname(__file__), '../.env/firebase_credentials.json')
    if not os.path.exists(cred_path):
        raise FileNotFoundError(f"Không tìm thấy file chứng thực: {cred_path}")

    database_url = os.getenv('FIREBASE_DATABASE_URL')
    if not database_url:
        raise ValueError("FIREBASE_DATABASE_URL không được định nghĩa trong config.env")

    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred, {
            'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET'),
            'databaseURL': database_url
        })
    
    return storage.bucket()

def generate_embeddings(lock_id):
    """Tạo và lưu file embeddings cho một lock_id cụ thể."""
    print(f"Bắt đầu tạo embeddings cho khóa: {lock_id}")
    bucket = initialize_firebase()
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Sử dụng device: {device}")

    mtcnn = MTCNN(keep_all=False, min_face_size=50, device=device)
    resnet = InceptionResnetV1(pretrained='vggface2').eval().to(device)

    known_embeddings = []
    known_ids = []
    known_names = []
    
    # Tạo thư mục riêng cho từng lock_id
    dataset_dir = os.path.join(os.path.dirname(__file__), '..', 'dataset', lock_id)
    os.makedirs(dataset_dir, exist_ok=True)

    prefix = f"locks/{lock_id}/faces/"
    blobs = list(bucket.list_blobs(prefix=prefix))
    
    if not blobs:
        print(f"Không tìm thấy ảnh nào cho khóa {lock_id}. Tạo file embeddings rỗng.")
    
    for blob in blobs:
        try:
            parts = blob.name.split('/')
            if len(parts) < 5: continue

            user_id = parts[3]
            filename = parts[4]
            
            # SỬA LẠI REGEX ĐỂ KHỚP VỚI CẢ SỐ VÀ CHỮ (HEX) CHO USERID
            user_name_match = re.match(r'^(\d+|[a-f0-9]+)_(.+?)_\d+_', filename)
            if not user_name_match: continue
            
            user_name = user_name_match.group(2).replace('_', ' ')
            
            local_path = os.path.join(dataset_dir, filename)
            if not os.path.exists(local_path):
                blob.download_to_filename(local_path)

            img = cv2.imread(local_path)
            if img is None: continue

            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            face = mtcnn(img_rgb)

            if face is not None:
                embedding = resnet(face.unsqueeze(0).to(device)).detach().cpu().numpy()
                known_embeddings.append(embedding)
                known_ids.append(user_id)
                known_names.append(user_name)
                print(f"Đã xử lý: {user_name} ({user_id})")
        except Exception as e:
            print(f"Lỗi khi xử lý file {blob.name}: {e}")

    # Lưu file embeddings
    embeddings_path = os.path.join(dataset_dir, "embeddings.pkl")
    with open(embeddings_path, 'wb') as f:
        # CHỈ LƯU 3 PHẦN TỬ: embeddings, ids, names (KHÔNG CẦN processed_files)
        pickle.dump((known_embeddings, known_ids, known_names), f)

    print(f"Hoàn tất! Đã lưu file embeddings vào: {embeddings_path}")
    print(f"Tổng cộng {len(known_ids)} khuôn mặt đã được xử lý.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python trainer.py <lock_id>")
        sys.exit(1)
    
    lock_id_arg = sys.argv[1]
    generate_embeddings(lock_id_arg)
