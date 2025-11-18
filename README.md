# SmartLock_FaceRecognition

![System Architecture](images/demo-architecture.png)  
*Ảnh minh họa kiến trúc hệ thống (thay bằng ảnh thực tế của bạn)*


## Giới thiệu

Dự án **SmartLock_FaceRecognition** là hệ thống khóa cửa thông minh ứng dụng nhận diện khuôn mặt, kết hợp AI, IoT và Web, giúp tăng cường bảo mật và tiện ích cho người dùng. Hệ thống được phát triển trên kiến trúc microservices, tích hợp đa nền tảng: Python (AI), Node.js (Backend), ESP32 (Firmware), Firebase (Cloud), Telegram (Thông báo).


## Chức năng nổi bật

- Nhận diện khuôn mặt để mở khóa cửa tự động.  
- Quản lý người dùng, đăng ký/xóa khuôn mặt qua giao diện web.  
- Tạo và quản lý mã truy cập tạm thời (Temporary Code).  
- Gửi cảnh báo real-time qua Telegram khi có truy cập trái phép.  
- Lưu trữ lịch sử truy cập, trạng thái khóa trên Firebase.  
- Điều khiển khóa từ xa qua Web hoặc Telegram Bot.


## Kiến trúc hệ thống

![Demo Hardware](images/demo-hardware.jpg)  
*Ảnh thực tế thiết bị ESP32, camera, mô hình khóa cửa (thay bằng ảnh của bạn)*

- **Web Application**: Giao diện quản trị, đăng ký khuôn mặt, xem lịch sử truy cập.  
- **AI Service (Python)**: Nhận diện khuôn mặt real-time, huấn luyện và xử lý dữ liệu.  
- **IoT Device (ESP32)**: Nhận lệnh mở/đóng khóa, kết nối Wi-Fi, giao tiếp với backend.  
- **Cloud (Firebase)**: Lưu trữ dữ liệu, đồng bộ trạng thái.  
- **Telegram Bot**: Gửi thông báo, nhận lệnh điều khiển từ người dùng.  


## Công nghệ sử dụng

- **Node.js, Express.js**: Backend, RESTful API  
- **Python, OpenCV, Caffe, Flask/FastAPI**: AI nhận diện khuôn mặt  
- **ESP32, Arduino/C++**: Firmware điều khiển khóa  
- **HTML, CSS, JavaScript**: Frontend web  
- **Firebase**: Lưu trữ dữ liệu, đồng bộ trạng thái  
- **Telegram Bot**: Thông báo và điều khiển từ xa  


## Hướng dẫn chạy demo

1. **Clone dự án:**  
```bash
git clone https://github.com/trinhkhanh29/SmartLock_FaceRecognition.git


2. **Cài đặt Node.js backend:**

   ```bash
   cd SmartLock_FaceRecognition/NodeJS_Interface/server
   npm install
   npm start
   ```
3. **Cài đặt Python AI service:**

   ```bash
   cd ../../PyCharm/src
   pip install -r ../requirements.txt
   python api_server.py
   ```
4. **Nạp firmware cho ESP32:**
   Mở `Arduino/connect-wifi/connect-wifi.ino` bằng Arduino IDE, nạp vào ESP32.
5. **Cấu hình Firebase & Telegram:**
   Điền thông tin vào file `.env` và `config.env` theo mẫu.
6. **Truy cập giao diện web:**
   Mở trình duyệt, truy cập `http://localhost:3000` để đăng ký khuôn mặt, quản lý truy cập.

## Demo giao diện

* **Đăng nhập**
  ![Đăng nhập](https://github.com/user-attachments/assets/13b2487e-525a-4d4d-981a-e599fbc3a934)
* **Trang chủ**
  ![Trang chủ](https://github.com/user-attachments/assets/cfac3dc4-c3b2-4274-97b9-1125c306ceab)
  ![Trang chủ](https://github.com/user-attachments/assets/6a0f69b6-1fcd-4084-8729-34826a740e8e)
* **Trang điều khiển khóa cửa**
  ![Điều khiển khóa](https://github.com/user-attachments/assets/f67012e2-bdb0-4d5d-96d2-9b6a8cef7445)
* **Tạo mã tạm thời**
  ![Mã tạm thời](https://github.com/user-attachments/assets/53dc744d-96e4-401c-a089-c5b9896fc405)
* **Danh sách người dùng**
  ![Danh sách người dùng](https://github.com/user-attachments/assets/1232fa52-bd0a-4edb-8f35-d23d7e616242)
* **Thu thập khuôn mặt**
  ![Thu thập khuôn mặt](https://github.com/user-attachments/assets/82f4ed4a-05cd-468c-b70b-73b7dc458bd8)
* **Điều khiển mở khóa & tạo mã qua Telegram**
  ![Telegram Control](https://github.com/user-attachments/assets/9a065c5a-94e8-4845-b3b8-8fbeea269e5c)

## Liên hệ

* **Tác giả:** Trịnh Khánh
* **GVHD:** Tiến Sĩ An Hồng Sơn
* **D.O.B:** 24/08/2003
* **Phone:** (+84) 368 977 130
* **Địa chỉ:** Thịnh Liệt, Hoàng Mai, Hà Nội
* **GitHub:** [trinhkhanh29](https://github.com/trinhkhanh29)
* **LinkedIn:** [linkedin.com/in/trinhkhanhh](https://linkedin.com/in/trinhkhanhh)
* **Email:** [trinh_quockhanh@outlook.com](mailto:trinh_quockhanh@outlook.com)

```
