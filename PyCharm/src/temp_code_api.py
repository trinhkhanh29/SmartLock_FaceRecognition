from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import json
import os
from threading import Thread

app = Flask(__name__)
CORS(app)

# File lưu trữ mã tạm thời
DATA_FILE = os.path.join(os.path.dirname(__file__), '../data/temp_codes.json')

def load_codes():
    """Đọc mã từ file"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_codes(codes):
    """Lưu mã vào file"""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(codes, f, indent=2, ensure_ascii=False)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "ok", "message": "Temp Code API is running"}), 200

@app.route('/api/temp-codes/create', methods=['POST'])
def create_code():
    """Tạo mã tạm thời mới"""
    try:
        data = request.json
        code = data.get('code')
        lock_id = data.get('lockId')
        expires_at = data.get('expiresAt')
        
        if not all([code, lock_id, expires_at]):
            return jsonify({"error": "Missing required fields"}), 400
        
        codes = load_codes()
        
        codes[code] = {
            "code": code,
            "lockId": lock_id,
            "expiresAt": expires_at,
            "createdBy": data.get('createdBy', 'unknown'),
            "maxUses": data.get('maxUses', 1),
            "usedCount": 0,
            "createdAt": datetime.now().isoformat()
        }
        
        save_codes(codes)
        
        print(f"✅ Created code: {code}")
        return jsonify(codes[code]), 201
        
    except Exception as e:
        print(f"❌ Error creating code: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/temp-codes/verify', methods=['POST'])
def verify_code():
    """Xác thực mã tạm thời"""
    try:
        data = request.json
        code = data.get('code')
        lock_id = data.get('lockId')
        
        if not code:
            return jsonify({"valid": False, "message": "Code is required"}), 400
        
        codes = load_codes()
        
        if code not in codes:
            return jsonify({"valid": False, "message": "Code not found"}), 404
        
        code_data = codes[code]
        
        # Kiểm tra lock ID
        if lock_id and code_data['lockId'] != lock_id:
            return jsonify({"valid": False, "message": "Wrong lock"}), 403
        
        # Kiểm tra hết hạn
        expires_at = datetime.fromisoformat(code_data['expiresAt'])
        if datetime.now() > expires_at:
            return jsonify({"valid": False, "message": "Code expired"}), 403
        
        # Kiểm tra số lần sử dụng
        if code_data['usedCount'] >= code_data['maxUses']:
            return jsonify({"valid": False, "message": "Code used up"}), 403
        
        # Tăng số lần sử dụng
        codes[code]['usedCount'] += 1
        codes[code]['lastUsedAt'] = datetime.now().isoformat()
        save_codes(codes)
        
        print(f"✅ Verified code: {code}")
        return jsonify({"valid": True, "code": codes[code]}), 200
        
    except Exception as e:
        print(f"❌ Error verifying code: {e}")
        return jsonify({"valid": False, "error": str(e)}), 500

@app.route('/api/temp-codes/active/<lock_id>', methods=['GET'])
def get_active_codes(lock_id):
    """Lấy danh sách mã đang hoạt động"""
    try:
        codes = load_codes()
        now = datetime.now()
        
        active_codes = []
        for code, data in codes.items():
            expires_at = datetime.fromisoformat(data['expiresAt'])
            
            # Kiểm tra còn hiệu lực
            if (data['lockId'] == lock_id and 
                expires_at > now and 
                data['usedCount'] < data['maxUses']):
                active_codes.append(data)
        
        return jsonify(active_codes), 200
        
    except Exception as e:
        print(f"❌ Error getting active codes: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/temp-codes/revoke', methods=['POST'])
def revoke_code():
    """Thu hồi mã"""
    try:
        data = request.json
        code = data.get('code')
        
        if not code:
            return jsonify({"error": "Code is required"}), 400
        
        codes = load_codes()
        
        if code in codes:
            del codes[code]
            save_codes(codes)
            print(f"✅ Revoked code: {code}")
            return jsonify({"message": "Code revoked"}), 200
        else:
            return jsonify({"error": "Code not found"}), 404
            
    except Exception as e:
        print(f"❌ Error revoking code: {e}")
        return jsonify({"error": str(e)}), 500

def run_api_server():
    """Chạy API server"""
    print("🚀 Starting Temp Code API Server on http://localhost:3000")
    app.run(host='0.0.0.0', port=3000, debug=False)

if __name__ == '__main__':
    run_api_server()
