import os
import time
import logging
import threading
from telebot import TeleBot, types

# === Cấu hình từ biến môi trường (Render.com sẽ dùng phần này) ===
TOKEN = os.getenv("TELEGRAM_TOKEN")  # Token bot Telegram
GROUP_ID_ENV = os.getenv("GROUP_ID")  # ID nhóm Telegram nhận tín hiệu
AUTHORIZED_USER_IDS = os.getenv("AUTHORIZED_USER_IDS", "")  # danh sách ID được phép gửi lệnh (tùy chọn)

# === Kiểm tra lỗi nếu thiếu biến ===
if not TOKEN:
    raise SystemExit("ERROR: TELEGRAM_TOKEN environment variable is not set.")
if not GROUP_ID_ENV:
    raise SystemExit("ERROR: GROUP_ID environment variable is not set.")

try:
    GROUP_ID = int(GROUP_ID_ENV)
except ValueError:
    raise SystemExit("ERROR: GROUP_ID must be an integer (set via environment variable).")

# === Phân tích danh sách user được phép gửi lệnh ===
authorized_users = set()
if AUTHORIZED_USER_IDS.strip():
    for s in AUTHORIZED_USER_IDS.split(","):
        s = s.strip()
        if s.isdigit():
            authorized_users.add(int(s))

# === Logging (ghi nhật ký hoạt động) ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

bot = TeleBot(TOKEN, parse_mode="HTML")

# === Tự động gửi tín hiệu định kỳ ===
def auto_send_signal(stop_event, interval_seconds=60):
    logging.info("Auto-signal thread started")
    while not stop_event.is_set():
        try:
            bot.send_message(GROUP_ID, "📊 Tín hiệu tự động: CALL BTCUSDT / PUT BTCUSDT")
        except Exception as e:
            logging.exception(f"❌ Lỗi khi gửi tín hiệu tự động: {e}")
        stop_event.wait(interval_seconds)

# === Lệnh /start để kiểm tra bot ===
@bot.message_handler(commands=["start"])
def start_message(message):
    bot.reply_to(message, "🤖 Bosss Trade AI đã hoạt động thành công!")

# === Lệnh /signal để gửi lệnh thủ công ===
@bot.message_handler(commands=["signal"])
def manual_signal(message):
    user_id = message.from_user.id
    if authorized_users and user_id not in authorized_users:
        bot.reply_to(message, "🚫 Bạn không có quyền gửi lệnh.")
        return

    payload = message.text.partition(" ")[2].strip() or "CALL BTCUSDT"
    try:
        bot.send_message(GROUP_ID, f"📈 Lệnh thủ công từ @{message.from_user.username or user_id}: {payload}")
        bot.reply_to(message, "✅ Lệnh đã gửi thành công.")
    except Exception as e:
        bot.reply_to(message, f"❌ Gửi lệnh thất bại: {e}")

# === Chạy bot ===
def main():
    stop_event = threading.Event()
    t = threading.Thread(target=auto_send_signal, args=(stop_event,))
    t.start()
    bot.infinity_polling()

if __name__ == "__main__":
    main()
  
