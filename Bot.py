import os
import time
import logging
import requests
import pandas as pd
from datetime import datetime
from telebot import TeleBot

# === ENV CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))
AUTHORIZED_USER_IDS = os.getenv("AUTHORIZED_USER_IDS", "").split(",")
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
INTERVAL = os.getenv("INTERVAL", "1m")

# Dùng API công khai không cần key
BINANCE_API = "https://data-api.binance.vision/api/v3/klines"
bot = TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# === Hàm lấy dữ liệu nến từ Binance ===
def fetch_data():
    try:
        params = {"symbol": SYMBOL, "interval": INTERVAL, "limit": 100}
        r = requests.get(BINANCE_API, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        df = pd.DataFrame(data, columns=[
            "time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_base_vol", "taker_quote_vol", "ignore"
        ])
        df["close"] = df["close"].astype(float)
        return df
    except Exception as e:
        logging.error(f"Lỗi lấy dữ liệu Binance: {e}")
        return None

# === Tính RSI ===
def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(period).mean()
    avg_loss = loss.rolling(period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# === Kiểm tra tín hiệu và gửi lên Telegram ===
def check_signal():
    df = fetch_data()
    if df is None or len(df) < 20:
        return

    df["rsi"] = calculate_rsi(df["close"])
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["bb_mid"] = df["close"].rolling(20).mean()
    df["bb_std"] = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - 2 * df["bb_std"]

    last = df.iloc[-1]
    rsi, ema, price = last["rsi"], last["ema200"], last["close"]
    bb_upper, bb_lower = last["bb_upper"], last["bb_lower"]

    # === Bộ lọc khung xấu ===
    if rsi is None or rsi < 40 or rsi > 60:
        signal_strength = "Tốt"
    else:
        logging.info("⚠️ Bỏ qua nến yếu (RSI trung tính)")
        return  # bỏ qua nến không rõ xu hướng

    # === Logic tín hiệu ===
    if price > ema and rsi > 50 and price < bb_upper:
        action = "🟢 MUA (CALL)"
        reason = "Giá trên EMA200 + RSI ổn định → xu hướng tăng"
    elif price < ema and rsi < 50 and price > bb_lower:
        action = "🔴 BÁN (PUT)"
        reason = "Giá dưới EMA200 + RSI yếu → xu hướng giảm"
    else:
        logging.info("⏸ Không có tín hiệu rõ ràng.")
        return

    # === Gửi lên Telegram ===
    message = (
        f"🇻🇳 <b>Bosss Trade AI Signal</b>\n"
        f"📊 Cặp: <b>{SYMBOL}</b>\n"
        f"RSI: {rsi:.2f} | EMA200: {ema:.2f}\n"
        f"BB trên: {bb_upper:.2f} | BB dưới: {bb_lower:.2f}\n\n"
        f"➡️ Đề xuất: {action}\n"
        f"🧠 Lý do: {reason}\n\n"
        f"💰 Giá hiện tại: {price:.2f}\n"
        f"⏰ Thời gian: {datetime.now().strftime('%H:%M %d/%m/%Y (UTC+7)')}"
    )

    bot.send_message(GROUP_ID, message)
    logging.info("✅ Gửi tín hiệu thành công!")

# === Vòng lặp chính ===
if __name__ == "__main__":
    logging.info("🚀 Bosss Trade AI v3.4 – Đồng bộ Binance 1m (+5s delay)")
    while True:
        now = datetime.now()
        if now.second == 5:  # sau khi nến mới mở được 5s
            check_signal()
            time.sleep(55)  # chờ đến phút kế tiếp
        else:
            time.sleep(1)
