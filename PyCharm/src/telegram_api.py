from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from threading import Thread

# Load environment variables
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env/config.env'))

app = Flask(__name__)
CORS(app)

# Configuration
ESP32_IP = os.getenv("ESP32_IP", "10.55.26.33")
BACKEND_API = os.getenv("BACKEND_API_URL", "http://localhost:3000")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    """Gửi tin nhắn qua Telegram Bot"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"[TELEGRAM] Error sending message: {e}")
        return False

def send_command_to_esp32(command):
    """Gửi lệnh đến ESP32"""
    url = f"http://{ESP32_IP}/{command}"
    params = {"key": "28280303"} if command == "SUCCESS" else {}
    try:
        response = requests.get(url, params=params, timeout=5)
        print(f"[ESP32] Response: {response.text}")
        return True
    except Exception as e:
        print(f"[ESP32] Error: {e}")
        return False

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "ok", "message": "Telegram API is running"}), 200

@app.route('/telegram/open', methods=['POST'])
def open_door():
    """Mở cửa qua Telegram"""
    try:
        data = request.json
        lock_id = data.get('lockId', 'unknown')
        
        print(f"[TELEGRAM] Opening door for lock: {lock_id}")
        
        if send_command_to_esp32("SUCCESS"):
            message = f"✅ Cửa đã được mở thành công!\n🔓 Lock ID: {lock_id}\n⏰ Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}"
            send_telegram_message(message)
            
            return jsonify({
                "success": True,
                "message": "Cửa đã được mở thành công qua Telegram"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Không thể gửi lệnh đến ESP32"
            }), 500
            
    except Exception as e:
        print(f"[TELEGRAM] Error opening door: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/telegram/close', methods=['POST'])
def close_door():
    """Đóng cửa qua Telegram"""
    try:
        data = request.json
        lock_id = data.get('lockId', 'unknown')
        
        print(f"[TELEGRAM] Closing door for lock: {lock_id}")
        
        if send_command_to_esp32("CLOSE"):
            message = f"🔒 Cửa đã được đóng!\n🔐 Lock ID: {lock_id}\n⏰ Thời gian: {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}"
            send_telegram_message(message)
            
            return jsonify({
                "success": True,
                "message": "Cửa đã được đóng thành công qua Telegram"
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": "Không thể gửi lệnh đến ESP32"
            }), 500
            
    except Exception as e:
        print(f"[TELEGRAM] Error closing door: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/telegram/createcode', methods=['POST'])
def create_temp_code():
    """Tạo mã PIN tạm thời"""
    try:
        data = request.json
        lock_id = data.get('lockId')
        hours = data.get('hours', 1)
        
        if not lock_id:
            return jsonify({
                "success": False,
                "error": "Missing lockId"
            }), 400
        
        print(f"[TELEGRAM] Creating temp code for lock: {lock_id}, duration: {hours}h")
        
        # Gọi API backend để tạo mã
        response = requests.post(
            f"{BACKEND_API}/api/temp-code/create",
            json={
                "lockId": lock_id,
                "duration": f"{hours}h",
                "description": f"Telegram Bot - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            },
            timeout=10
        )
        
        if response.status_code in [200, 201]:
            result = response.json()
            
            if result.get('success'):
                code = result['code']
                expire_at = result['expireAtFormatted']
                
                # Gửi thông báo qua Telegram
                message = (
                    f"✅ *Mã PIN tạm thời đã được tạo!*\n\n"
                    f"🔑 Mã: `{code}`\n"
                    f"🔐 Lock ID: {lock_id}\n"
                    f"⏰ Có hiệu lực: {hours} giờ\n"
                    f"📅 Hết hạn: {expire_at}\n"
                    f"🔢 Số lần dùng: 1 lần\n\n"
                    f"_Chia sẻ mã này để mở cửa!_"
                )
                send_telegram_message(message)
                
                return jsonify({
                    "success": True,
                    "message": "Mã PIN đã được tạo thành công",
                    "code": code,
                    "expireAt": expire_at
                }), 200
            else:
                return jsonify({
                    "success": False,
                    "error": result.get('error', 'Unknown error')
                }), 500
        else:
            return jsonify({
                "success": False,
                "error": f"Backend error: {response.status_code}"
            }), 500
            
    except Exception as e:
        print(f"[TELEGRAM] Error creating code: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/telegram/listcodes/<lock_id>', methods=['GET'])
def list_codes(lock_id):
    """Lấy danh sách mã đang hoạt động"""
    try:
        print(f"[TELEGRAM] Listing codes for lock: {lock_id}")
        
        response = requests.get(
            f"{BACKEND_API}/api/temp-code/active/{lock_id}",
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get('success'):
                return jsonify({
                    "success": True,
                    "codes": result['codes']
                }), 200
            else:
                return jsonify({
                    "success": False,
                    "codes": []
                }), 200
        else:
            return jsonify({
                "success": False,
                "error": f"Backend error: {response.status_code}"
            }), 500
            
    except Exception as e:
        print(f"[TELEGRAM] Error listing codes: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

def run_server():
    """Chạy Flask server"""
    print("🚀 Starting Telegram API Server on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)

if __name__ == '__main__':
    run_server()
