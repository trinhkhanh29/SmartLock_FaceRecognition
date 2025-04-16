# Server Nhận Diện Khuôn Mặt

## Cài đặt
1. Cài Python 3.9+
2. Tạo môi trường ảo: `python -m venv venv`
3. Kích hoạt môi trường ảo:
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`
4. Cài thư viện: `pip install -r requirements.txt`
5. Cấu hình Firebase: Thêm file `firebase-adminsdk.json` vào thư mục gốc và cập nhật `config.py`

## Chạy server
1. Chạy: `python src/main.py`
2. Server chạy tại: `http://192.168.1.100:5000`