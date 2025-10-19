import os
import time
import threading
import logging
from datetime import datetime, timezone, timedelta
import requests
import pandas as pd
from telebot import TeleBot

# --- ENV ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
GROUP_ID_ENV = os.getenv("GROUP_ID", "")
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
INTERVAL = os.getenv("INTERVAL", "1m")

# Check token
if not TELEGRAM_TOKEN or not GROUP_ID_ENV:
    raise SystemExit("❌ Thiếu TELEGRAM_TOKEN hoặc GROUP_ID trong biến môi trường.")
GROUP_ID = int(GROUP_ID_ENV)

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

bot = TeleBot(TELEGRAM_TOKEN, parse_mode="HTML")

BINANCE_API = "https://api.binance.com/api/v3/klines"

# --- Indicator functions ---
def fetch_klines(symbol="BTCUSDT", interval="1m", limit=300):
    try:
        r = requests.get(BINANCE_API, params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=10)
        r.raise_for_status()
        data = r.json()
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        return df
    except Exception as e:
        logging.error("Lỗi lấy dữ liệu Binance: %s", e)
        return pd.DataFrame()

def ema(series, period=200):
    return series.ewm(span=period, adjust=False).mean()

def rsi(series, period=14):
    delta = series.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(com=period - 1, adjust=False).mean()
    ma_down = down.ewm(com=period - 1, adjust=False).mean()
    rs = ma_up / (ma_down + 1e-10)
    return 100 - (100 / (1 + rs))

def macd(series, fast=12, slow=26, signal=9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def bollinger_bands(series, period=20, std_dev=2):
    mid = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return mid, upper, lower

# --- Decision logic ---
def analyze(df):
    if len(df) < 50:
        return None

    close = df["close"]
    ema200 = ema(close, 200)
    rsi_val = rsi(close, 14)
    macd_line, signal_line, hist = macd(close)
    mid, upper, lower = bollinger_bands(close, 20, 2)

    latest = {
        "price": close.iloc[-1],
        "ema200": ema200.iloc[-1],
        "rsi": rsi_val.iloc[-1],
        "macd": macd_line.iloc[-1],
        "macd_signal": signal_line.iloc[-1],
        "macd_hist": hist.iloc[-1],
        "bb_upper": upper.iloc[-1],
        "bb_lower": lower.iloc[-1],
        "bb_mid": mid.iloc[-1],
    }

    signal = "⚪ Chờ"  # Default
    strength = "Trung lập"

    # --- Conditions for CALL / PUT ---
    if (
        latest["price"] <= latest["bb_lower"]
        and latest["rsi"] < 35
        and latest["macd_hist"] > 0
    ):
        signal = "🟢 CALL (MUA)"
        strength = "Tín hiệu mạnh - chạm dải BB dưới & RSI thấp"
    elif (
        latest["price"] >= latest["bb_upper"]
        and latest["rsi"] > 65
        and latest["macd_hist"] < 0
    ):
        signal = "🔴 PUT (BÁN)"
        strength = "Tín hiệu mạnh - chạm dải BB trên & RSI cao"

    # --- Return ---
    latest["decision"] = signal
    latest["strength"] = strength
    return latest

# --- Send Telegram ---
def send_signal(data):
    t = datetime.now(timezone.utc) + timedelta(hours=7)
    text = (
        f"📊 <b>Bosss Trade AI - BO Signal</b>\n"
        f"💱 Cặp: BTC/USDT\n"
        f"💰 Giá hiện tại: {data['price']:.2f}\n"
        f"📈 RSI: {data['rsi']:.1f} | EMA200: {data['ema200']:.2f}\n"
        f"📉 MACD hist: {data['macd_hist']:.4f}\n"
        f"📊 Bollinger:\n"
        f" ├ Biên trên: {data['bb_upper']:.2f}\n"
        f" ├ Biên giữa: {data['bb_mid']:.2f}\n"
        f" └ Biên dưới: {data['bb_lower']:.2f}\n\n"
        f"➡️ <b>{data['decision']}</b>\n"
        f"🧠 {data['strength']}\n"
        f"⏰ {t.strftime('%H:%M:%S %d/%m/%Y')} (UTC+7)"
    )
    bot.send_message(GROUP_ID, text)

# --- Main loop ---
def main_loop():
    logging.info("🚀 Bosss Trade AI (BB+RSI+MACD+EMA) bắt đầu chạy...")
    last_signal = None
    while True:
        df = fetch_klines(SYMBOL, INTERVAL)
        if df.empty:
            time.sleep(30)
            continue

        info = analyze(df)
        if not info:
            logging.info("Dữ liệu chưa đủ để phân tích.")
            time.sleep(60)
            continue

        if info["decision"] != last_signal:
            send_signal(info)
            last_signal = info["decision"]
            logging.info("✅ Gửi tín hiệu: %s", info["decision"])
        else:
            logging.info("⏳ Không có tín hiệu mới...")

        time.sleep(60)

if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        logging.info("⛔ Dừng bot thủ công.")
