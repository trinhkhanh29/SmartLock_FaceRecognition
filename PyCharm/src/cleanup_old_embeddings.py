import os
import sys

# Xóa tất cả file embeddings.pkl cũ
dataset_dir = os.path.join(os.path.dirname(__file__), '..', 'dataset')

if os.path.exists(dataset_dir):
    for root, dirs, files in os.walk(dataset_dir):
        for file in files:
            if file.endswith('.pkl'):
                filepath = os.path.join(root, file)
                try:
                    os.remove(filepath)
                    print(f"Đã xóa: {filepath}")
                except Exception as e:
                    print(f"Lỗi khi xóa {filepath}: {e}")
    print("Hoàn tất xóa cache cũ.")
else:
    print("Thư mục dataset không tồn tại.")
