# PyCharm/src/api_server.py
from flask import Flask, request, jsonify
from flask_cors import CORS
from face_recognition import recognize_face, register_new_face
from firebase_control import upload_image_to_firebase

app = Flask(__name__)
CORS(app)  # Cho phép React (port 3000) gọi API

@app.route("/api/register", methods=["POST"])
def register_face_api():
    """
    API đăng ký khuôn mặt mới.
    Nhận form gồm: name, image (file)
    """
    try:
        name = request.form["name"]
        image_file = request.files["image"]
        # Gọi hàm xử lý trong face_recognition.py
        result = register_new_face(image_file, name)
        upload_image_to_firebase(image_file, name)
        return jsonify({"status": "success", "name": name, "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/recognize", methods=["POST"])
def recognize_face_api():
    """
    API nhận diện khuôn mặt
    """
    try:
        image_file = request.files["image"]
        result = recognize_face(image_file)
        return jsonify({"status": "success", "result": result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
