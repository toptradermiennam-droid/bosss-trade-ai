import os
import time
import requests
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timezone, timedelta
from telebot import TeleBot

# === ENV ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
GROUP_ID = int(os.getenv("GROUP_ID", "0"))
AUTHORIZED_USER_IDS = os.getenv("AUTHORIZED_USER_IDS", "")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
INTERVAL = os.getenv("INTERVAL", "1m")

# === LOGGING ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

bot = TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")

# === Binance API endpoint (nhiều vùng để tránh lỗi 451) ===
BINANCE_ENDPOINTS = [
    "https://api.binance.com/api/v3/klines",
    "https://api-gcp.binance.com/api/v3/klines",
    "https://data-api.binance.vision/api/v3/klines",
    "https://api1.binance.com/api/v3/klines"
]

# === Hàm lấy dữ liệu từ Binance ===
def fetch_klines(symbol="BTCUSDT", interval="1m", limit=200):
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    for endpoint in BINANCE_ENDPOINTS:
        try:
            url = f"{endpoint}?symbol={symbol}&interval={interval}&limit={limit}"
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                df = pd.DataFrame(data, columns=[
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_asset_volume", "num_trades",
                    "taker_buy_base", "taker_buy_quote", "ignore"
                ])
                df["close"] = df["close"].astype(float)
                return df
        except Exception as e:
            logging.warning(f"Lỗi kết nối {endpoint}: {e}")
    raise SystemExit("❌ Không thể lấy dữ liệu từ Binance (thử lại sau).")

# === Chỉ báo kỹ thuật ===
def calculate_indicators(df):
    df["EMA200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["RSI"] = compute_rsi(df["close"])
    df["MA20"] = df["close"].rolling(window=20).mean()
    df["STD20"] = df["close"].rolling(window=20).std()
    df["BB_upper"] = df["MA20"] + (df["STD20"] * 2)
    df["BB_lower"] = df["MA20"] - (df["STD20"] * 2)
    return df

def compute_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

# === Phân tích tín hiệu ===
def analyze_signal(df):
    latest = df.iloc[-1]
    rsi = latest["RSI"]
    close = latest["close"]
    ema = latest["EMA200"]
    upper = latest["BB_upper"]
    lower = latest["BB_lower"]

    signal = "NEUTRAL"
    reason = ""

    if rsi > 65 and close > upper:
        signal = "PUT"
        reason = "RSI cao + Giá chạm BB trên → khả năng đảo chiều giảm"
    elif rsi < 35 and close < lower:
        signal = "CALL"
        reason = "RSI thấp + Giá chạm BB dưới → khả năng bật tăng"
    elif close > ema and rsi < 60:
        signal = "CALL"
        reason = "Giá trên EMA200 + RSI ổn định → xu hướng tăng"
    elif close < ema and rsi > 40:
        signal = "PUT"
        reason = "Giá dưới EMA200 + RSI ổn định → xu hướng giảm"

    return signal, reason, rsi, ema, upper, lower, close

# === Gửi tín hiệu Telegram ===
def send_signal():
    try:
        df = fetch_klines(SYMBOL, INTERVAL)
        df = calculate_indicators(df)
        signal, reason, rsi, ema, upper, lower, close = analyze_signal(df)

        now = datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M %d/%m/%Y")
        msg = (
            f"📊 <b>Bosss Trade AI Signal</b>\n"
            f"Cặp: <b>{SYMBOL}</b>\n"
            f"RSI: <b>{rsi:.2f}</b> | EMA200: <b>{ema:.2f}</b>\n"
            f"BB trên: <b>{upper:.2f}</b> | BB dưới: <b>{lower:.2f}</b>\n"
            f"➡️ Đề xuất: <b>{'🟢 MUA (CALL)' if signal == 'CALL' else '🔴 BÁN (PUT)' if signal == 'PUT' else '⚪ TRUNG LẬP'}</b>\n"
            f"🧠 Lý do: {reason}\n"
            f"💰 Giá hiện tại: {close:.2f}\n"
            f"⏰ Thời gian: {now} (UTC+7)"
        )
        bot.send_message(GROUP_ID, msg)
        logging.info("✅ Gửi tín hiệu thành công!")
    except Exception as e:
        logging.error(f"Lỗi khi gửi tín hiệu: {e}")

# === Chạy bot liên tục ===
if __name__ == "__main__":
    logging.info("🚀 Bosss Trade AI khởi động (RSI + EMA + BB + Biểu đồ)...")
    while True:
        send_signal()
        time.sleep(60)
