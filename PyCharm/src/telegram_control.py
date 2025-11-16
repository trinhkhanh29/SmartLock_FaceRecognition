from telegram.ext import Updater, CommandHandler, ConversationHandler, MessageHandler, Filters, CallbackQueryHandler
import requests
import os
from dotenv import load_dotenv
import random
import string
from datetime import datetime, timedelta
from threading import Thread
import time
import json
import sys
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Fix encoding cho Windows console
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Load biến môi trường
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env/config.env'))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BACKEND_API = os.getenv("BACKEND_API_URL", "http://localhost:3000")
DEFAULT_ESP32_IP = os.getenv("DEFAULT_ESP32_IP", "10.55.26.33")
EXTERNAL_API_KEY = os.getenv("EXTERNAL_API_KEY") # THÊM DÒNG NÀY

# File lưu thông tin user-lock mapping
USER_DATA_FILE = os.path.join(os.path.dirname(__file__), '../data/telegram_users.json')

# States cho conversation
REGISTER_LOCK = 1

# Cache mã tạm thời local
local_temp_codes = {}

def load_user_data():
    """Đọc dữ liệu user từ file"""
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_data(data):
    """Lưu dữ liệu user vào file"""
    os.makedirs(os.path.dirname(USER_DATA_FILE), exist_ok=True)
    with open(USER_DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_user_lock_id(user_id):
    """Lấy lockId của user"""
    users = load_user_data()
    return users.get(str(user_id), {}).get('lockId')

def set_user_lock_id(user_id, lock_id, username=None):
    """Gán lockId cho user"""
    users = load_user_data()
    users[str(user_id)] = {
        'lockId': lock_id,
        'username': username,
        'registeredAt': datetime.now().isoformat()
    }
    save_user_data(users)

def get_esp32_ip(lock_id):
    """Lấy IP của ESP32 từ Firebase"""
    print(f"[{lock_id}] Bắt đầu lấy IP cho ESP32...")
    try:
        url = f"{BACKEND_API}/api/lock-info/{lock_id}"
        print(f"[{lock_id}] Gọi đến backend: {url}")
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            ip_from_db = data.get('ipAddress')
            if ip_from_db:
                # THÊM .strip() để loại bỏ khoảng trắng
                ip_from_db = ip_from_db.strip()
                print(f"[{lock_id}] Tìm thấy IP trong database: '{ip_from_db}'")
                return ip_from_db
            else:
                print(f"[{lock_id}] Không tìm thấy IP trong database, sử dụng IP mặc định.")
        else:
            print(f"[{lock_id}] Backend trả về lỗi {response.status_code}, sử dụng IP mặc định.")
    except Exception as e:
        print(f"[{lock_id}] Lỗi khi gọi backend để lấy IP: {e}. Sử dụng IP mặc định.")
        pass
    
    print(f"[{lock_id}] IP mặc định được sử dụng: {DEFAULT_ESP32_IP}")
    return DEFAULT_ESP32_IP.strip()

def start_flask_api():
    """DEPRECATED - Không cần nữa vì NodeJS đã xử lý"""
    pass  # Không làm gì cả

def start_telegram_api():
    """DEPRECATED - Không cần nữa"""
    pass  # Không làm gì cả

def check_backend_connection():
    """Kiểm tra kết nối đến backend"""
    max_retries = 5
    for i in range(max_retries):
        try:
            response = requests.get(f"{BACKEND_API}/health", timeout=2)
            if response.status_code == 200:
                return True
        except:
            if i < max_retries - 1:
                time.sleep(1)
    return False

def send_command_to_esp32(command, lock_id):
    """Gửi lệnh đến ESP32 theo lockId"""
    esp32_ip = get_esp32_ip(lock_id)
    url = f"http://{esp32_ip}/{command}"
    params = {"key": "28280303"} if command == "SUCCESS" else {}
    
    print(f"[{lock_id}] Chuẩn bị gửi lệnh '{command}' đến {url} với params: {params}")
    
    try:
        response = requests.get(url, params=params, timeout=5)
        print(f"[{lock_id}] ESP32 phản hồi: STATUS={response.status_code}, BODY='{response.text}'")
        return True
    except requests.exceptions.RequestException as e:
        print(f"[{lock_id}] Lỗi khi gửi lệnh đến ESP32: {e}")
        return False

def start(update, context):
    """Xử lý lệnh /start"""
    user_id = update.effective_user.id
    user_lock_id = get_user_lock_id(user_id)
    
    if user_lock_id:
        message = (
            f"👋 Chào mừng trở lại!\n\n"
            f"🔐 Lock ID của bạn: `{user_lock_id}`\n\n"
            f"Sử dụng /help để xem danh sách lệnh.\n"
            f"Sử dụng /changelockid để đổi Lock ID."
        )
    else:
        message = (
            f"👋 Chào mừng đến với SmartLock Bot!\n\n"
            f"Vui lòng đăng ký Lock ID của bạn bằng lệnh:\n"
            f"/registerlockid <lock_id>\n\n"
            f"Ví dụ: `/registerlockid a03ab4496ccca125`"
        )
    
    update.message.reply_text(message, parse_mode='Markdown')

def register_lock_id_command(update, context):
    """Đăng ký Lock ID"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    if not context.args:
        update.message.reply_text(
            "⚠️ Vui lòng cung cấp Lock ID\n\n"
            "Sử dụng: /registerlockid <lock_id>\n"
            "Ví dụ: /registerlockid a03ab4496ccca125"
        )
        return
    
    lock_id = context.args[0].strip()
    
    # Kiểm tra Lock ID có tồn tại trong hệ thống không
    try:
        response = requests.get(f"{BACKEND_API}/api/lock-info/{lock_id}", timeout=5)
        if response.status_code == 404:
            update.message.reply_text(
                f"❌ Lock ID `{lock_id}` không tồn tại trong hệ thống!\n\n"
                f"Vui lòng kiểm tra lại Lock ID của bạn.",
                parse_mode='Markdown'
            )
            return
        elif response.status_code != 200:
            update.message.reply_text(
                "❌ Không thể xác thực Lock ID. Vui lòng thử lại sau."
            )
            return
        
        lock_data = response.json()
        lock_name = lock_data.get('name', 'Unknown')
        
    except Exception as e:
        print(f"[REGISTER] Error checking lock: {e}")
        update.message.reply_text(
            "❌ Không thể kết nối đến server. Vui lòng thử lại sau."
        )
        return
    
    # Lưu thông tin user
    set_user_lock_id(user_id, lock_id, username)
    
    update.message.reply_text(
        f"✅ Đăng ký thành công!\n\n"
        f"🔐 Lock ID: `{lock_id}`\n"
        f"🏠 Tên khóa: {lock_name}\n\n"
        f"Bạn có thể bắt đầu sử dụng các lệnh điều khiển.\n"
        f"Gõ /help để xem danh sách lệnh.",
        parse_mode='Markdown'
    )
    
    print(f"✅ User {user_id} ({username}) registered with lock {lock_id}")

def change_lock_id(update, context):
    """Đổi Lock ID"""
    user_id = update.effective_user.id
    
    if not context.args:
        current_lock = get_user_lock_id(user_id)
        if current_lock:
            update.message.reply_text(
                f"🔐 Lock ID hiện tại: `{current_lock}`\n\n"
                f"Để đổi Lock ID, sử dụng:\n"
                f"/changelockid <lock_id_mới>\n\n"
                f"Ví dụ: /changelockid b04bc5597dddb236",
                parse_mode='Markdown'
            )
        else:
            update.message.reply_text(
                "⚠️ Bạn chưa đăng ký Lock ID.\n"
                "Sử dụng /registerlockid để đăng ký."
            )
        return
    
    # Sử dụng lại logic register
    register_lock_id_command(update, context)

def require_lock_id(func):
    """Decorator kiểm tra user đã đăng ký Lock ID chưa"""
    def wrapper(update, context):
        user_id = update.effective_user.id
        lock_id = get_user_lock_id(user_id)
        
        if not lock_id:
            update.message.reply_text(
                "❌ Bạn chưa đăng ký Lock ID!\n\n"
                "Vui lòng đăng ký bằng lệnh:\n"
                "/registerlockid <lock_id>\n\n"
                "Ví dụ: /registerlockid a03ab4496ccca125"
            )
            return
        
        # Truyền lock_id vào context để sử dụng
        context.user_data['lock_id'] = lock_id
        return func(update, context)
    
    return wrapper

@require_lock_id
def open_door(update, context):
    """Mở cửa"""
    lock_id = context.user_data['lock_id']
    print(f"[{lock_id}] === BẮT ĐẦU LỆNH MỞ CỬA ===")
    
    # Lấy IP của ESP32
    esp32_ip = get_esp32_ip(lock_id)
    print(f"[{lock_id}] ESP32 IP: {esp32_ip}")
    
    # Gửi lệnh trực tiếp đến ESP32
    url = f"http://{esp32_ip}/SUCCESS"
    params = {"key": "28280303"}
    
    print(f"[{lock_id}] Đang gửi GET request đến: {url}")
    print(f"[{lock_id}] Params: {params}")
    
    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"[{lock_id}] Response Status: {response.status_code}")
        print(f"[{lock_id}] Response Body: {response.text}")
        
        if response.status_code == 200:
            update.message.reply_text(
                f"✅ Cửa khóa `{lock_id}` đang mở!\n\n"
                f"🌐 ESP32 IP: {esp32_ip}\n"
                f"📡 Status: {response.status_code}",
                parse_mode='Markdown'
            )
        else:
            update.message.reply_text(
                f"⚠️ ESP32 phản hồi nhưng không thành công\n\n"
                f"Status: {response.status_code}\n"
                f"Response: {response.text[:100]}"
            )
    except requests.exceptions.Timeout:
        print(f"[{lock_id}] ❌ TIMEOUT - ESP32 không phản hồi sau 10 giây")
        update.message.reply_text(
            f"❌ Timeout khi kết nối đến ESP32!\n\n"
            f"🌐 IP: {esp32_ip}\n"
            f"⏱️ ESP32 không phản hồi sau 10 giây\n\n"
            f"Kiểm tra:\n"
            f"1. ESP32 có đang bật không?\n"
            f"2. ESP32 có kết nối WiFi không?\n"
            f"3. IP {esp32_ip} có đúng không?"
        )
    except requests.exceptions.ConnectionError as e:
        print(f"[{lock_id}] ❌ CONNECTION ERROR: {e}")
        update.message.reply_text(
            f"❌ Không thể kết nối đến ESP32!\n\n"
            f"🌐 IP: {esp32_ip}\n"
            f"🔌 Lỗi: {str(e)[:100]}\n\n"
            f"Kiểm tra:\n"
            f"1. Máy chạy bot và ESP32 cùng mạng LAN?\n"
            f"2. Firewall có chặn không?\n"
            f"3. IP có đúng không?"
        )
    except Exception as e:
        print(f"[{lock_id}] ❌ UNEXPECTED ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        update.message.reply_text(f"❌ Lỗi: {type(e).__name__}: {str(e)}")

@require_lock_id
def close_door(update, context):
    """Đóng cửa"""
    lock_id = context.user_data['lock_id']
    print(f"[{lock_id}] === BẮT ĐẦU LỆNH ĐÓNG CỬA ===")
    
    # Lấy IP của ESP32
    esp32_ip = get_esp32_ip(lock_id)
    print(f"[{lock_id}] ESP32 IP: {esp32_ip}")
    
    # Gửi lệnh trực tiếp đến ESP32
    url = f"http://{esp32_ip}/CLOSE"
    
    print(f"[{lock_id}] Đang gửi GET request đến: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        print(f"[{lock_id}] Response Status: {response.status_code}")
        print(f"[{lock_id}] Response Body: {response.text}")
        
        if response.status_code == 200:
            update.message.reply_text(
                f"🔒 Đã đóng cửa khóa `{lock_id}`!\n\n"
                f"🌐 ESP32 IP: {esp32_ip}\n"
                f"📡 Status: {response.status_code}",
                parse_mode='Markdown'
            )
        else:
            update.message.reply_text(
                f"⚠️ ESP32 phản hồi nhưng không thành công\n\n"
                f"Status: {response.status_code}\n"
                f"Response: {response.text[:100]}"
            )
    except requests.exceptions.Timeout:
        print(f"[{lock_id}] ❌ TIMEOUT - ESP32 không phản hồi sau 10 giây")
        update.message.reply_text(
            f"❌ Timeout khi kết nối đến ESP32!\n\n"
            f"🌐 IP: {esp32_ip}\n"
            f"⏱️ ESP32 không phản hồi sau 10 giây"
        )
    except requests.exceptions.ConnectionError as e:
        print(f"[{lock_id}] ❌ CONNECTION ERROR: {e}")
        update.message.reply_text(
            f"❌ Không thể kết nối đến ESP32!\n\n"
            f"🌐 IP: {esp32_ip}\n"
            f"🔌 Lỗi: {str(e)[:100]}"
        )
    except Exception as e:
        print(f"[{lock_id}] ❌ UNEXPECTED ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        update.message.reply_text(f"❌ Lỗi: {type(e).__name__}: {str(e)}")

def generate_temp_code():
    """Tạo mã 6 chữ số ngẫu nhiên"""
    return ''.join(random.choices(string.digits, k=6))

@require_lock_id
def create_temp_code(update, context):
    """Hiển thị menu chọn thời hạn mã tạm thời"""
    lock_id = context.user_data['lock_id']
    
    print(f"[CREATE_CODE] User {update.effective_user.id} requested temp code menu for lock {lock_id}")
    
    # Tạo inline keyboard với các tùy chọn thời hạn
    keyboard = [
        [
            InlineKeyboardButton("⏱️ 1 giờ", callback_data=f"code_{lock_id}_1h"),
            InlineKeyboardButton("⏱️ 3 giờ", callback_data=f"code_{lock_id}_3h"),
        ],
        [
            InlineKeyboardButton("⏱️ 6 giờ", callback_data=f"code_{lock_id}_6h"),
            InlineKeyboardButton("⏱️ 12 giờ", callback_data=f"code_{lock_id}_12h"),
        ],
        [
            InlineKeyboardButton("📅 1 ngày", callback_data=f"code_{lock_id}_1d"),
            InlineKeyboardButton("📅 3 ngày", callback_data=f"code_{lock_id}_3d"),
        ],
        [
            InlineKeyboardButton("📅 7 ngày", callback_data=f"code_{lock_id}_7d"),
        ],
        [
            InlineKeyboardButton("❌ Hủy", callback_data="code_cancel"),
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    update.message.reply_text(
        f"🔑 *Tạo mã tạm thời cho khóa `{lock_id}`*\n\n"
        f"Chọn thời hạn hiệu lực của mã:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

def handle_create_code_callback(update, context):
    """Xử lý callback khi người dùng chọn thời hạn"""
    query = update.callback_query
    query.answer()
    
    callback_data = query.data
    
    print(f"[CALLBACK] Received: {callback_data}")
    
    # Xử lý nút Hủy
    if callback_data == "code_cancel":
        query.edit_message_text("❌ Đã hủy tạo mã tạm thời.")
        return
    
    # Parse callback data: code_{lockId}_{duration}
    try:
        parts = callback_data.split('_')
        if len(parts) != 3 or parts[0] != "code":
            query.edit_message_text("❌ Lỗi: Dữ liệu không hợp lệ")
            return
        
        lock_id = parts[1]
        duration = parts[2]
        
        print(f"[CREATE_CODE] Creating code for {lock_id} with duration {duration}")
        
        # Hiển thị loading
        query.edit_message_text("⏳ Đang tạo mã tạm thời...")
        
        # Gửi request đến backend
        url = f"{BACKEND_API}/api/temp-code/create"
        payload = {
            "lockId": lock_id,
            "duration": duration,
            "description": f"Telegram - {query.from_user.username or 'User'}"
        }
        headers = {
            'Content-Type': 'application/json',
            'X-API-Key': EXTERNAL_API_KEY
        }
        
        print(f"[CREATE_CODE] Sending request to: {url}")
        print(f"[CREATE_CODE] Payload: {payload}")
        
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        print(f"[CREATE_CODE] Response status: {response.status_code}")
        
        # Kiểm tra content type
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' not in content_type:
            print(f"[CREATE_CODE] ERROR: Expected JSON but got {content_type}")
            query.edit_message_text(
                f"❌ Server trả về định dạng không hợp lệ\n"
                f"Status: {response.status_code}\n"
                f"Content-Type: {content_type}"
            )
            return
        
        if response.status_code in [200, 201]:
            result = response.json()
            print(f"[CREATE_CODE] Success! Code: {result.get('code')}")
            
            # Tính thời gian hiệu lực
            duration_text = duration.replace('h', ' giờ').replace('d', ' ngày')
            
            message = (
                f"✅ *Mã tạm thời đã được tạo!*\n\n"
                f"🔐 Lock ID: `{lock_id}`\n"
                f"🔑 Mã: `{result['code']}`\n"
                f"⏰ Có hiệu lực: {duration_text}\n"
                f"📅 Hết hạn: {result['expireAtFormatted']}\n"
                f"🔢 Số lần dùng: 1 lần\n\n"
                f"⚠️ *Lưu ý:* Chia sẻ mã này để người khác có thể mở cửa!"
            )
            
            query.edit_message_text(message, parse_mode='Markdown')
        else:
            print(f"[CREATE_CODE] Error response: {response.text}")
            query.edit_message_text(
                f"❌ Server trả về lỗi\n"
                f"Status: {response.status_code}\n"
                f"Message: {response.text[:200]}"
            )
            
    except requests.exceptions.Timeout:
        print("[CREATE_CODE] Request timeout!")
        query.edit_message_text("❌ Timeout khi kết nối đến server. Vui lòng thử lại.")
    except requests.exceptions.ConnectionError as e:
        print(f"[CREATE_CODE] Connection error: {e}")
        query.edit_message_text(
            f"❌ Không thể kết nối đến server.\n\n"
            f"Backend URL: {BACKEND_API}"
        )
    except Exception as e:
        print(f"[CREATE_CODE] Unexpected error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        query.edit_message_text(f"❌ Lỗi: {type(e).__name__}: {str(e)}")

@require_lock_id
def list_active_codes(update, context):
    """Hiển thị danh sách mã đang hoạt động"""
    lock_id = context.user_data['lock_id']
    
    try:
        url = f"{BACKEND_API}/api/temp-code/active/{lock_id}"
        headers = { 'X-API-Key': EXTERNAL_API_KEY }
        print(f"[LIST_CODES] Requesting: {url}")
        
        response = requests.get(url, headers=headers, timeout=5)
        
        print(f"[LIST_CODES] Response status: {response.status_code}")
        print(f"[LIST_CODES] Content-Type: {response.headers.get('Content-Type')}")
        
        # Kiểm tra content type
        content_type = response.headers.get('Content-Type', '')
        if 'application/json' not in content_type:
            print(f"[LIST_CODES] ERROR: Expected JSON but got {content_type}")
            update.message.reply_text(f"❌ Server trả về định dạng không hợp lệ: {content_type}")
            return
        
        if response.status_code == 200:
            result = response.json()
            
            if not result.get('success') or not result.get('codes'):
                update.message.reply_text("📭 Không có mã nào đang hoạt động.")
                return
            
            message = f"📋 Danh sách mã đang hoạt động cho `{lock_id}`:\n\n"
            
            for idx, code_data in enumerate(result['codes'], 1):
                message += (
                    f"{idx}. `{code_data['code']}`\n"
                    f"   📝 {code_data.get('description', 'No description')}\n"
                    f"   ⏰ Hết hạn: {code_data['expireAt']}\n"
                    f"   🔢 Đã dùng: {code_data.get('usedCount', 0)}/{code_data.get('maxUses', 1)}\n\n"
                )
            
            update.message.reply_text(message, parse_mode='Markdown')
        else:
            update.message.reply_text(f"❌ Server error: {response.status_code}")
    except Exception as e:
        print(f"[LIST_CODES] Error: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        update.message.reply_text(f"❌ Lỗi: {type(e).__name__}: {str(e)}")

@require_lock_id
def check_code(update, context):
    """Kiểm tra và sử dụng mã tạm thời"""
    lock_id = context.user_data['lock_id']
    
    if not context.args:
        update.message.reply_text("⚠️ Sử dụng: /checkcode <mã>\nVí dụ: /checkcode 123456")
        return
    
    code = context.args[0]
    
    try:
        response = requests.post(
            f"{BACKEND_API}/api/verify-temp-code",
            json={"code": code, "lockId": lock_id},
            timeout=5
        )
        
        result = response.json()
        
        if result.get('success') and result.get('valid'):
            update.message.reply_text("✅ Mã hợp lệ! Đang mở cửa...")
            send_command_to_esp32("SUCCESS", lock_id)
            print(f"[{lock_id}] Code {code} verified")
        else:
            update.message.reply_text(f"❌ {result.get('message', 'Mã không hợp lệ')}")
    except Exception as e:
        print(f"[{lock_id}] Error verifying code: {e}")
        update.message.reply_text("❌ Không thể xác thực mã")

def help_command(update, context):
    """Hiển thị hướng dẫn sử dụng"""
    user_id = update.effective_user.id
    lock_id = get_user_lock_id(user_id)
    
    if lock_id:
        help_text = (
            f"🤖 *Hướng dẫn sử dụng Smart Lock Bot*\n\n"
            f"🔐 Lock ID của bạn: `{lock_id}`\n\n"
            f"📌 *Các lệnh điều khiển cửa:*\n"
            f"/open - Mở cửa\n"
            f"/close - Đóng cửa\n"
            f"/testconnection - Kiểm tra kết nối ESP32\n\n"
            f"🔑 *Các lệnh quản lý mã tạm thời:*\n"
            f"/createcode <giờ> - Tạo mã tạm thời\n"
            f"   Ví dụ: /createcode 2\n"
            f"/listcodes - Xem danh sách mã đang hoạt động\n"
            f"/checkcode <mã> - Kiểm tra và sử dụng mã\n\n"
            f"⚙️ *Cài đặt:*\n"
            f"/changelockid - Đổi Lock ID\n"
            f"/help - Hiển thị hướng dẫn này"
        )
    else:
        help_text = (
            f"🤖 *Hướng dẫn sử dụng Smart Lock Bot*\n\n"
            f"⚠️ Bạn chưa đăng ký Lock ID!\n\n"
            f"📝 *Đăng ký Lock ID:*\n"
            f"/registerlockid <lock_id>\n"
            f"   Ví dụ: /registerlockid a03ab4496ccca125\n\n"
            f"/help - Hiển thị hướng dẫn này"
        )
    
    update.message.reply_text(help_text, parse_mode='Markdown')

def main():
    try:
        print("=" * 50)
        print("TELEGRAM BOT INITIALIZATION")
        print("=" * 50)
        print(f"Bot Token: {BOT_TOKEN[:20]}..." if BOT_TOKEN else "Bot Token: NOT SET!")
        print(f"Backend API: {BACKEND_API}")
        print(f"Default ESP32 IP: {DEFAULT_ESP32_IP}")
        print(f"User Data File: {USER_DATA_FILE}")
        print(f"External API Key: {'SET' if EXTERNAL_API_KEY else 'NOT SET'}")
        print("=" * 50)
        
        if not BOT_TOKEN:
            print("ERROR: TELEGRAM_BOT_TOKEN not set in .env file!")
            return
        
        if not EXTERNAL_API_KEY:
            print("WARNING: EXTERNAL_API_KEY not set in .env file!")
            print("Bot may not be able to create temp codes!")
        
        print("Initializing Telegram Bot...")
        
        # Kiểm tra kết nối backend
        print("Checking backend connection...")
        try:
            response = requests.get(f"{BACKEND_API}/api/test-firebase", timeout=5)
            if response.status_code == 200:
                print("✅ Connected to backend API")
            else:
                print(f"⚠️ Backend responded with status: {response.status_code}")
        except Exception as e:
            print(f"❌ Cannot connect to backend API: {e}")
            print("Bot will run but may have limited functionality")
        
        print("Creating Updater...")
        updater = Updater(BOT_TOKEN, use_context=True, request_kwargs={'connect_timeout': 30, 'read_timeout': 30})
        dp = updater.dispatcher
        
        print("Registering command handlers...")
        # Đăng ký handlers theo thứ tự ưu tiên
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("help", help_command))
        dp.add_handler(CommandHandler("registerlockid", register_lock_id_command))
        dp.add_handler(CommandHandler("changelockid", change_lock_id))
        dp.add_handler(CommandHandler("open", open_door))
        dp.add_handler(CommandHandler("close", close_door))
        dp.add_handler(CommandHandler("createcode", create_temp_code))
        dp.add_handler(CommandHandler("listcodes", list_active_codes))
        dp.add_handler(CommandHandler("checkcode", check_code))
        
        # Đăng ký callback handler SAU tất cả command handlers
        dp.add_handler(CallbackQueryHandler(handle_create_code_callback, pattern='^code_'))
        
        print("✅ All handlers registered successfully!")
        print("Registered commands:")
        print("  - /start, /help")
        print("  - /registerlockid, /changelockid")
        print("  - /open, /close")
        print("  - /createcode, /listcodes, /checkcode")
        print("  - Callback handler for inline keyboards")
        
        print("Starting bot polling...")
        print("=" * 50)
        print("🤖 BOT IS NOW RUNNING!")
        print("Send /start to the bot to test connection")
        print("=" * 50)
        
        updater.start_polling(poll_interval=1.0, timeout=30)
        print("✅ Polling started successfully!")
        
        # Test kết nối với Telegram
        try:
            bot_info = updater.bot.get_me()
            print(f"✅ Bot connected as: @{bot_info.username}")
            print(f"   Bot ID: {bot_info.id}")
        except Exception as e:
            print(f"❌ Could not get bot info: {e}")
        
        updater.idle()
        
    except Exception as e:
        print("=" * 50)
        print("💥 FATAL ERROR INITIALIZING BOT")
        print("=" * 50)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        print("=" * 50)

if __name__ == "__main__":
    main()