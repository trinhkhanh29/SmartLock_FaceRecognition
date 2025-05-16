from telegram.ext import Updater, CommandHandler
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

def open_door(update, context):
    if update.effective_user.id == AUTHORIZED_USER_ID:
        print("Gửi lệnh: SUCCESS")
        ser.write(b"SUCCESS\n")
        ser.flush()
        update.message.reply_text("✅ Cửa đang mở!")
    else:
        update.message.reply_text("🚫 Bạn không có quyền!")

def close_door(update, context):
    if update.effective_user.id == AUTHORIZED_USER_ID:
        print("Gửi lệnh: CLOSE")
        ser.write(b"CLOSE\n")
        ser.flush()
        update.message.reply_text("🔒 Đã đóng cửa!")
    else:
        update.message.reply_text("🚫 Bạn không có quyền!")

def main():
    try:
        updater = Updater(BOT_TOKEN, use_context=True)
        dp = updater.dispatcher
        dp.add_handler(CommandHandler("open", open_door))
        dp.add_handler(CommandHandler("close", close_door))
        updater.start_polling()
        updater.idle()
    except Exception as e:
        print(f"Lỗi khởi tạo bot: {e}")

if __name__ == "__main__":
    main()