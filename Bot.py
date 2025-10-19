import os
import time
import logging
import requests
import pandas as pd
from datetime import datetime
from telebot import TeleBot

# === ENV CONFIG ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
INTERVAL = os.getenv("INTERVAL", "1m")

BINANCE_API BINANCE_API = "https://data-api.binance.vision/api/v3/klines"
bot = TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")

# === Fetch dữ liệu từ Binance ===
def fetch_data():
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json"
        }
        url = f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval={INTERVAL}&limit=100"
        r = requests.get(url, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()

        df = pd.DataFrame(data, columns=[
            "time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])

        df["close"] = df["close"].astype(float)
        return df

    except Exception as e:
        logging.error(f"❌ Lỗi lấy dữ liệu Binance: {e}")
        return None
        data = r.json()
        df = pd.DataFrame(data, columns=[
            "time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "trades", "tbb", "tbq", "ignore"
        ])
        df["close"] = df["close"].astype(float)
        return df
    except Exception as e:
        logging.error(f"Lỗi lấy dữ liệu Binance: {e}")
        return None

# === Tính RSI ===
def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# === Tính EMA ===
def calculate_ema(prices, period=200):
    return prices.ewm(span=period, adjust=False).mean()

# === Tính Bollinger Bands ===
def calculate_bollinger(prices, period=20):
    sma = prices.rolling(period).mean()
    std = prices.rolling(period).std()
    return sma + 2 * std, sma - 2 * std

# === Gửi tín hiệu Telegram ===
def send_signal():
    df = fetch_data()
    if df is None or len(df) < 20:
        return

    close = df["close"]
    rsi = calculate_rsi(close).iloc[-1]
    ema200 = calculate_ema(close).iloc[-1]
    bb_upper, bb_lower = calculate_bollinger(close)
    bb_up = bb_upper.iloc[-1]
    bb_low = bb_lower.iloc[-1]
    last_price = close.iloc[-1]

    # Bỏ qua nến yếu (RSI trong vùng 45–55, không rõ hướng)
    if 45 < rsi < 55:
        logging.info("⚠️ Nến yếu (RSI trung tính) → Bỏ qua tín hiệu.")
        return

    # Xác định tín hiệu
    if last_price > ema200 and rsi > 50:
        direction = "🟢 MUA (CALL)"
        reason = "Giá trên EMA200 + RSI ổn định → xu hướng tăng"
    elif last_price < ema200 and rsi < 50:
        direction = "🔴 BÁN (PUT)"
        reason = "Giá dưới EMA200 + RSI yếu → xu hướng giảm"
    else:
        direction = "⚪️ TRUNG LẬP"
        reason = "Tín hiệu không rõ ràng, bỏ qua."

    msg = f"""
🇮🇹 <b>Bosss Trade AI Signal</b>
📊 Cặp: {SYMBOL}
📈 RSI: {rsi:.2f} | EMA200: {ema200:.2f}
📊 BB trên: {bb_up:.2f} | BB dưới: {bb_low:.2f}
➡️ Đề xuất: {direction}
🧠 Lý do: {reason}
💰 Giá hiện tại: {last_price:.2f}
🕒 Thời gian: {datetime.now().strftime('%H:%M %d/%m/%Y (UTC+7)')}
"""
    bot.send_message(GROUP_ID, msg)
    logging.info(f"✅ Đã gửi tín hiệu: {direction}")

# === MAIN LOOP ===
if __name__ == "__main__":
    logging.info("🚀 Bosss Trade AI v3.3 – Đồng bộ Binance 1m +5s khởi động...")
    while True:
        now = datetime.now()
        if now.second == 5:  # Sau khi Binance đóng nến 5 giây
            try:
                send_signal()
            except Exception as e:
                logging.error(f"Lỗi khi gửi tín hiệu: {e}")
            time.sleep(55)
        else:
            time.sleep(0.5)
