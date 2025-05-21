from telegram.ext import Updater, CommandHandler
import requests
import os
from dotenv import load_dotenv

# Load biến môi trường
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env/config.env'))

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
AUTHORIZED_USER_ID = int(os.getenv("TELEGRAM_CHAT_ID"))
ESP32_IP = "192.168.36.100"  # Địa chỉ IP của ESP32

def send_command_to_esp32(command):
    url = f"http://{ESP32_IP}/{command}"
    try:
        response = requests.get(url, timeout=5)
        print(f"ESP32 phản hồi: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Lỗi khi gửi lệnh đến ESP32: {e}")

def open_door(update, context):
    if update.effective_user.id == AUTHORIZED_USER_ID:
        print("Gửi lệnh: SUCCESS")
        send_command_to_esp32("SUCCESS")
        update.message.reply_text("✅ Cửa đang mở!")
    else:
        update.message.reply_text("🚫 Bạn không có quyền!")

def close_door(update, context):
    if update.effective_user.id == AUTHORIZED_USER_ID:
        print("Gửi lệnh: CLOSE")
        send_command_to_esp32("CLOSE")
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