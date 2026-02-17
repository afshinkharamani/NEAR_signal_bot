import requests
import pandas as pd
import time
from datetime import datetime

# ===== تنظیمات تلگرام =====
TELEGRAM_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=payload)

# ===== تنظیمات استراتژی =====
DELTA = 0.001
SYMBOL = "near-usdt"
CURRENCY = "usd"

LEVERAGE = 20
TARGET_MOVE = 0.20 / LEVERAGE
STOP_MOVE = 0.50 / LEVERAGE

# ===== گرفتن داده از CoinGecko =====
def fetch_ohlc(symbol, currency, days, interval_minutes):
    url = f"https://api.coingecko.com/api/v3/coins/{symbol}/ohlc?vs_currency={currency}&days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data, columns=["time","open","high","low","close"])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df = df.sort_values("time").reset_index(drop=True)
        return df
    except Exception as e:
        print("خطا در گرفتن داده:", e)
        return pd.DataFrame(columns=["time","open","high","low","close"])

# ===== هشدار عبور از محدوده 4H =====
def check_alert(candle_5m, high_4h, low_4h):
    if candle_5m['close'] >= high_4h*(1+DELTA):
        return 'above'
    elif candle_5m['close'] <= low_4h*(1-DELTA):
        return 'below'
    return None

# ===== بررسی ورود =====
def check_entry(candle_5m, high_4h, low_4h, alert_type):
    if alert_type == 'above' and candle_5m['close'] <= high_4h*(1-DELTA):
        return 'SHORT'
    elif alert_type == 'below' and candle_5m['close'] >= low_4h*(1+DELTA):
        return 'LONG'
    return None

# ===== بررسی تارگت و استاپ با کندل 1 دقیقه =====
def check_target_stop(entry_price, direction, candle_1m):
    if direction == "LONG":
        if candle_1m['high'] >= entry_price*(1 + TARGET_MOVE):
            return "TARGET"
        elif candle_1m['low'] <= entry_price*(1 - STOP_MOVE):
            return "STOP"
    elif direction == "SHORT":
        if candle_1m['low'] <= entry_price*(1 - TARGET_MOVE):
            return "TARGET"
        elif candle_1m['high'] >= entry_price*(1 + STOP_MOVE):
            return "STOP"
    return None

# ===== حلقه اصلی =====
active_trade = None

while True:
    # داده‌های 5 دقیقه‌ای و 4 ساعته
    df_5m = fetch_ohlc(SYMBOL, CURRENCY, days=1, interval_minutes=5)
    df_4h = fetch_ohlc(SYMBOL, CURRENCY, days=7, interval_minutes=240)

    if df_5m.empty or df_4h.empty:
        time.sleep(30)
        continue

    latest_4h = df_4h.iloc[-1]
    high_4h = latest_4h['high']
    low_4h = latest_4h['low']

    latest_5m = df_5m.iloc[-1]

    # ===== بررسی هشدار =====
    if not active_trade:
        alert_type = check_alert(latest_5m, high_4h, low_4h)
        if alert_type:
            send_telegram(f"⚠️ هشدار عبور از محدوده 4H: {alert_type.upper()} در {latest_5m['time']}")
            
            entry = check_entry(latest_5m, high_4h, low_4h, alert_type)
            if entry:
                active_trade = {
                    "direction": entry,
                    "entry_price": latest_5m['close'],
                    "time": latest_5m['time']
                }
                send_telegram(f"🚀 ورود به معامله: {entry} | قیمت: {latest_5m['close']} | زمان: {latest_5m['time']}")

    # ===== بررسی تارگت یا استاپ اگر معامله باز است =====
    if active_trade:
        df_1m = fetch_ohlc(SYMBOL, CURRENCY, days=1, interval_minutes=1)
        if df_1m.empty:
            time.sleep(30)
            continue

        # کندل‌های 1 دقیقه بعد از ورود
        df_1m_slice = df_1m[df_1m['time'] >= active_trade['time']].reset_index(drop=True)
        for idx, candle_1m in df_1m_slice.iterrows():
            result = check_target_stop(active_trade['entry_price'], active_trade['direction'], candle_1m)
            if result:
                send_telegram(f"✅ معامله {active_trade['direction']} {result} | قیمت: {candle_1m['close']} | زمان: {candle_1m['time']}")
                active_trade = None
                break

    time.sleep(30)
