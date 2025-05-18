from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
import serial
import os
from dotenv import load_dotenv

# Load biến môi trường
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env/config.env'))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_USER_ID = int(os.getenv("TELEGRAM_CHAT_ID"))

# Kết nối Serial
try:
    ser = serial.Serial("COM4", 115200, timeout=1)
    print("Kết nối Serial thành công")
except serial.SerialException as e:
    print(f"Lỗi kết nối Serial: {e}")
    exit(1)

# Biến trạng thái cửa (giả sử)
door_status = "Đóng"  # Mặc định cửa đóng

def open_door(update, context):
    global door_status
    if update.effective_user.id == AUTHORIZED_USER_ID:
        print("Gửi lệnh: SUCCESS")
        ser.write(b"SUCCESS\n")
        ser.flush()
        door_status = "Mở"
        update.message.reply_text("✅ Cửa đang mở!")
    else:
        update.message.reply_text("🚫 Bạn không có quyền!")

def close_door(update, context):
    global door_status
    if update.effective_user.id == AUTHORIZED_USER_ID:
        print("Gửi lệnh: CLOSE")
        ser.write(b"CLOSE\n")
        ser.flush()
        door_status = "Đóng"
        update.message.reply_text("🔒 Đã đóng cửa!")
    else:
        update.message.reply_text("🚫 Bạn không có quyền!")

def status(update, context):
    if update.effective_user.id == AUTHORIZED_USER_ID:
        update.message.reply_text(f"🚪 Trạng thái cửa hiện tại: {door_status}")
    else:
        update.message.reply_text("🚫 Bạn không có quyền!")

def send_photo(update, context):
    if update.effective_user.id == AUTHORIZED_USER_ID:
        # Đường dẫn ảnh hiện tại bạn muốn gửi
        photo_path = os.path.join(os.path.dirname(__file__), 'current_photo.jpg')
        if os.path.exists(photo_path):
            with open(photo_path, 'rb') as photo:
                update.message.reply_photo(photo=photo, caption="Ảnh hiện tại của cửa")
        else:
            update.message.reply_text("❌ Không tìm thấy ảnh để gửi.")
    else:
        update.message.reply_text("🚫 Bạn không có quyền!")

def echo_photo(update, context):
    # Phản hồi lại ảnh người dùng gửi (ví dụ)
    if update.effective_user.id == AUTHORIZED_USER_ID:
        photo_file = update.message.photo[-1].get_file()
        photo_file.download('received_photo.jpg')  # Lưu lại ảnh
        update.message.reply_text("Đã nhận ảnh của bạn. Đây là ảnh bạn gửi:")
        update.message.reply_photo(photo=open('received_photo.jpg', 'rb'))
    else:
        update.message.reply_text("🚫 Bạn không có quyền!")

def main():
    try:
        updater = Updater(BOT_TOKEN, use_context=True)
        dp = updater.dispatcher

        dp.add_handler(CommandHandler("open", open_door))
        dp.add_handler(CommandHandler("close", close_door))
        dp.add_handler(CommandHandler("status", status))
        dp.add_handler(CommandHandler("sendphoto", send_photo))

        # Nhận ảnh gửi đến
        dp.add_handler(MessageHandler(Filters.photo, echo_photo))

        updater.start_polling()
        updater.idle()
    except Exception as e:
        print(f"Lỗi khởi tạo bot: {e}")

if __name__ == "__main__":
    main()
