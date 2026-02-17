# bot_safe.py
import requests
import pandas as pd
import time
from datetime import datetime

# ===== تنظیمات =====
BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"
SYMBOL = "NEARUSDT"
LEVERAGE = 20
DELTA = 0.001
TARGET_MOVE = 0.20
STOP_MOVE = 0.50

active_trade = None
last_signal_time = None

# ===== ارسال تلگرام =====
def send_signal(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})
    print(text)

# ===== گرفتن کندل از Binance (پایدارتر) =====
def get_kline(interval):
    url = f"https://api.binance.com/api/v3/klines?symbol={SYMBOL}&interval={interval}&limit=2"
    r = requests.get(url)
    data = r.json()
    last = data[-1]
    return {
        "time": pd.to_datetime(last[0], unit="ms"),
        "open": float(last[1]),
        "high": float(last[2]),
        "low": float(last[3]),
        "close": float(last[4])
    }

# ===== مدیریت معامله =====
def manage_trade(candle):
    global active_trade

    if not active_trade:
        return

    entry = active_trade["entry"]

    if active_trade["side"] == "LONG":
        if candle["high"] >= entry * (1+TARGET_MOVE):
            send_signal("✅ TP LONG")
            active_trade = None
        elif candle["low"] <= entry * (1-STOP_MOVE):
            send_signal("❌ SL LONG")
            active_trade = None

    if active_trade and active_trade["side"] == "SHORT":
        if candle["low"] <= entry * (1-TARGET_MOVE):
            send_signal("✅ TP SHORT")
            active_trade = None
        elif candle["high"] >= entry * (1+STOP_MOVE):
            send_signal("❌ SL SHORT")
            active_trade = None

# ===== اجرای ربات =====
def start():
    global active_trade

    send_signal("🤖 ربات روشن شد")

    while True:
        try:
            candle_4h = get_kline("4h")
            candle_5m = get_kline("5m")
            candle_1m = get_kline("1m")

            high_4h = candle_4h["high"]
            low_4h = candle_4h["low"]

            # شرط ورود
            if not active_trade:
                if candle_5m["close"] > high_4h*(1+DELTA):
                    active_trade = {"side":"SHORT","entry":candle_5m["close"]}
                    send_signal(f"🚨 SHORT @ {candle_5m['close']}")
                elif candle_5m["close"] < low_4h*(1-DELTA):
                    active_trade = {"side":"LONG","entry":candle_5m["close"]}
                    send_signal(f"🚨 LONG @ {candle_5m['close']}")

            manage_trade(candle_1m)

            time.sleep(10)

        except Exception as e:
            print("Error:", e)
            time.sleep(5)

if __name__ == "__main__":
    start()
