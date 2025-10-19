import os
import time
import logging
import requests
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timezone, timedelta
from telebot import TeleBot

# --- Cấu hình ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET")
SYMBOL = os.getenv("SYMBOL", "BTCUSDT")
INTERVAL = os.getenv("INTERVAL", "1m")

bot = TeleBot(TELEGRAM_TOKEN)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

BINANCE_URL = "https://api.binance.com/api/v3/klines"

# --- Lấy dữ liệu Binance ---
def get_binance_data(symbol=SYMBOL, interval=INTERVAL, limit=200):
    try:
        headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        response = requests.get(BINANCE_URL, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "num_trades",
            "taker_buy_base", "taker_buy_quote", "ignore"
        ])
        df["close"] = df["close"].astype(float)
        df["time"] = pd.to_datetime(df["close_time"], unit="ms") + timedelta(hours=7)
        return df
    except Exception as e:
        logging.error(f"Lỗi lấy dữ liệu Binance: {e}")
        return pd.DataFrame()

# --- Chỉ báo ---
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

def bollinger_bands(series, period=20, std_dev=2):
    mid = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = mid + std_dev * std
    lower = mid - std_dev * std
    return mid, upper, lower

# --- Phân tích xu hướng ---
def analyze(df):
    close = df["close"]
    ema200 = ema(close, 200)
    rsi_val = rsi(close, 14)
    mid, upper, lower = bollinger_bands(close)

    last = {
        "price": close.iloc[-1],
        "ema200": ema200.iloc[-1],
        "rsi": rsi_val.iloc[-1],
        "bb_mid": mid.iloc[-1],
        "bb_upper": upper.iloc[-1],
        "bb_lower": lower.iloc[-1],
    }

    if last["price"] < last["bb_lower"] and last["rsi"] < 35:
        decision = "🟢 CALL (MUA)"
        reason = "Giá chạm BB dưới & RSI thấp"
    elif last["price"] > last["bb_upper"] and last["rsi"] > 65:
        decision = "🔴 PUT (BÁN)"
        reason = "Giá chạm BB trên & RSI cao"
    else:
        decision = "⚪ CHỜ"
        reason = "Chưa có tín hiệu rõ ràng"

    last["decision"] = decision
    last["reason"] = reason
    return last

# --- Vẽ biểu đồ và gửi ảnh ---
def plot_and_send(df, result):
    try:
        close = df["close"]
        ema200 = ema(close, 200)
        mid, upper, lower = bollinger_bands(close)
        rsi_val = rsi(close, 14)

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), gridspec_kw={'height_ratios': [3, 1]})
        plt.subplots_adjust(hspace=0.25)

        # Biểu đồ giá + EMA + BB
        ax1.plot(df["time"], close, label="Giá", linewidth=1.5)
        ax1.plot(df["time"], ema200, label="EMA 200", linestyle="--")
        ax1.plot(df["time"], upper, color='r', linestyle=':')
        ax1.plot(df["time"], mid, color='gray', linestyle=':')
        ax1.plot(df["time"], lower, color='g', linestyle=':')
        ax1.set_title(f"{SYMBOL} - {INTERVAL} ({result['decision']})", fontsize=11)
        ax1.legend(loc="upper left")

        # RSI
        ax2.plot(df["time"], rsi_val, color="orange", label="RSI(14)")
        ax2.axhline(70, color="red", linestyle="--")
        ax2.axhline(30, color="green", linestyle="--")
        ax2.legend(loc="upper left")
        ax2.set_ylim(0, 100)

        # Lưu hình
        chart_path = "/tmp/chart.png"
        plt.savefig(chart_path, bbox_inches="tight")
        plt.close(fig)

        # Gửi ảnh + text
        t = datetime.now(timezone.utc) + timedelta(hours=7)
        msg = (
            f"📊 <b>Bosss Trade AI - Binance Signal</b>\n"
            f"💱 Cặp: {SYMBOL}\n"
            f"💰 Giá hiện tại: {result['price']:.2f}\n"
            f"📈 RSI: {result['rsi']:.1f} | EMA200: {result['ema200']:.2f}\n"
            f"📊 Bollinger: {result['bb_lower']:.2f} - {result['bb_upper']:.2f}\n\n"
            f"➡️ <b>{result['decision']}</b>\n"
            f"🧠 {result['reason']}\n"
            f"⏰ {t.strftime('%H:%M:%S %d/%m/%Y')} (UTC+7)"
        )

        with open(chart_path, "rb") as photo:
            bot.send_photo(GROUP_ID, photo, caption=msg, parse_mode="HTML")

        logging.info("📤 Đã gửi tín hiệu và biểu đồ thành công.")
    except Exception as e:
        logging.error(f"Lỗi khi vẽ/gửi biểu đồ: {e}")

# --- Main loop ---
def main():
    logging.info("🚀 Bosss Trade AI khởi động (RSI+EMA+BB + Biểu đồ)...")
    last_signal = None
    while True:
        df = get_binance_data()
        if df.empty:
            time.sleep(60)
            continue

        result = analyze(df)
        if result["decision"] != last_signal:
            plot_and_send(df, result)
            last_signal = result["decision"]
        else:
            logging.info("⏳ Không có tín hiệu mới.")
        time.sleep(60)

if __name__ == "__main__":
    main()
