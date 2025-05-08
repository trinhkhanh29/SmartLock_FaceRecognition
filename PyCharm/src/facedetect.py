import cv2
import os
import firebase_admin
from firebase_admin import credentials, storage
from datetime import datetime


def initialize_firebase():
    # Đường dẫn tới file firebase_credentials.json
    cred_path = os.path.join(os.path.dirname(__file__), '../.env/firebase_credentials.json')

    # Kiểm tra xem file credentials có tồn tại không
    if not os.path.exists(cred_path):
        raise FileNotFoundError("[ERROR] Firebase credentials file not found.")

    # Khởi tạo Firebase
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred, {
        'storageBucket': 'smartlockfacerecognition.firebasestorage.app'  # Thay bằng Storage Bucket của bạn
    })

    return storage.bucket()


def upload_to_firebase(bucket, filepath, face_id, face_name, count):
    # Tạo tên file trên Firebase Storage
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    firebase_filename = f"faces/{face_id}/{face_name}_{count}_{timestamp}.jpg"

    # Tải file lên Firebase Storage
    blob = bucket.blob(firebase_filename)
    blob.upload_from_filename(filepath)

    # Lấy URL công khai của file (nếu cần)
    blob.make_public()
    return blob.public_url


def main():
    # Khởi tạo Firebase
    try:
        bucket = initialize_firebase()
    except Exception as e:
        print(f"[ERROR] Firebase initialization failed: {str(e)}")
        return

    # Initialize camera
    cam = cv2.VideoCapture(0)
    if not cam.isOpened():
        print("[ERROR] Could not open camera.")
        return

    # Set camera resolution
    cam.set(3, 640)  # width
    cam.set(4, 480)  # height

    # Load face detector
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    if face_cascade.empty():
        print("[ERROR] Could not load face detector.")
        cam.release()
        return

    # Get user ID and name
    face_id = input('\nEnter user ID (number) >> ')
    if not face_id.isdigit():
        print("[ERROR] ID must be a number.")
        cam.release()
        return

    face_name = input('Enter user name >> ').strip()

    print("\n[INFO] Initializing face capture...")

    # Create dataset directory
    dataset_path = os.path.join(os.path.dirname(__file__), '../dataset')
    os.makedirs(dataset_path, exist_ok=True)

    count = 0
    sample_limit = 30
    min_face_size = 100  # Minimum face size in pixels

    try:
        while count < sample_limit:
            ret, frame = cam.read()
            if not ret:
                print("[ERROR] Could not read frame.")
                break

            # Flip frame horizontally for more intuitive view
            frame = cv2.flip(frame, 1)

            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Equalize histogram to improve contrast
            gray = cv2.equalizeHist(gray)

            # Detect faces with more precise parameters
            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=6,
                minSize=(min_face_size, min_face_size),
                flags=cv2.CASCADE_SCALE_IMAGE
            )

            for (x, y, w, h) in faces:
                # Draw rectangle
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                # Save only properly detected faces
                if w > min_face_size and h > min_face_size:
                    count += 1
                    filename = f"dataset.{face_id}.{face_name}.{count}.jpg"
                    filepath = os.path.join(dataset_path, filename)

                    # Save face ROI locally
                    cv2.imwrite(filepath, gray[y:y + h, x:x + w])

                    # Upload to Firebase Storage
                    try:
                        public_url = upload_to_firebase(bucket, filepath, face_id, face_name, count)
                        print(f"[INFO] Uploaded face {count} to Firebase: {public_url}")
                    except Exception as e:
                        print(f"[ERROR] Failed to upload to Firebase: {str(e)}")

                    # Display count
                    cv2.putText(frame, f"Collected: {count}/{sample_limit}",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                                0.8, (0, 255, 0), 2)

                    # Show face area being captured
                    cv2.imshow('Capturing Face', gray[y:y + h, x:x + w])

            # Display main frame
            cv2.imshow('Face Collection', frame)

            # Exit on ESC or when enough samples collected
            key = cv2.waitKey(100) & 0xff
            if key == 27 or count >= sample_limit:  # ESC key
                break

    except Exception as e:
        print(f"[ERROR] {str(e)}")
    finally:
        cam.release()
        cv2.destroyAllWindows()
        print(f"\n[INFO] Collected {count} samples. Program exited.")


if __name__ == "__main__":
    main()