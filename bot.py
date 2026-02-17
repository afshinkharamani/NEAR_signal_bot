import requests
import time
import traceback
import pandas as pd
from datetime import datetime, timedelta

# ==============================
# تنظیمات تلگرام
# ==============================
BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload, timeout=10)
    except:
        print("Telegram send error")

# ==============================
# تنظیمات استراتژی
# ==============================
LEVERAGE = 20
DELTA = 0.001
TARGET_MOVE = 0.01   # 1% تغییر قیمت برای تارگت
STOP_MOVE = 0.025    # 2.5% تغییر قیمت برای استاپ
CANDLE_5M_INTERVAL = 300  # ثانیه
CANDLE_1M_INTERVAL = 60   # ثانیه

active_trade = None
alert_type = None
last_5m_close = None

# ==============================
# گرفتن قیمت و کندل از OKX
# ==============================
def get_5m_candle():
    url = "https://www.okx.com/api/v5/market/history-candles?instId=NEAR-USDT&bar=5m&limit=2"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if 'data' in data and len(data['data']) > 0:
            # آخرین کندل بسته شده
            return data['data'][0]  # [ts, open, high, low, close, volume]
        else:
            return None
    except Exception as e:
        print("خطا در گرفتن کندل 5 دقیقه‌ای:", e)
        return None

def get_1m_candle():
    url = "https://www.okx.com/api/v5/market/history-candles?instId=NEAR-USDT&bar=1m&limit=2"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if 'data' in data and len(data['data']) > 0:
            return data['data'][0]  # [ts, open, high, low, close, volume]
        else:
            return None
    except Exception as e:
        print("خطا در گرفتن کندل 1 دقیقه‌ای:", e)
        return None

# ==============================
# منطق هشدار و ورود
# ==============================
def check_alert_and_entry(candle):
    global alert_type
    high_4h = candle['high']
    low_4h = candle['low']
    close = candle['close']

    if close >= high_4h * (1 + DELTA):
        alert_type = 'above'
        return 'ALERT'
    elif close <= low_4h * (1 - DELTA):
        alert_type = 'below'
        return 'ALERT'
    return None

def check_entry(candle, high_4h, low_4h):
    close = candle['close']
    if alert_type == 'above' and close <= high_4h * (1 - DELTA):
        return 'SHORT'
    elif alert_type == 'below' and close >= low_4h * (1 + DELTA):
        return 'LONG'
    return None

# ==============================
# باز کردن معامله
# ==============================
def open_trade(direction, entry_price):
    return {
        "direction": direction,
        "entry_price": entry_price,
        "target": entry_price * (1 + TARGET_MOVE if direction=="LONG" else 1 - TARGET_MOVE),
        "stop": entry_price * (1 - STOP_MOVE if direction=="LONG" else 1 + STOP_MOVE)
    }

# ==============================
# حلقه اصلی
# ==============================
print("🤖 ربات آنلاین شروع شد...")

while True:
    try:
        # ==============================
        # کندل 5 دقیقه‌ای
        # ==============================
        candle_5m_data = get_5m_candle()
        if candle_5m_data:
            ts, o, h, l, c, v = candle_5m_data
            candle_5m = {"time": datetime.fromtimestamp(int(ts)/1000), "open": float(o), "high": float(h), "low": float(l), "close": float(c)}
            
            # فقط وقتی کلوز 5 دقیقه‌ای تغییر کرده
            if last_5m_close != candle_5m['close']:
                last_5m_close = candle_5m['close']

                alert = check_alert_and_entry(candle_5m)
                if alert:
                    send_telegram_message(f"⚠️ هشدار ۵ دقیقه‌ای! کندل بسته شد: {candle_5m['time']}\nنوع هشدار: {alert_type}")

                    # بررسی ورود
                    entry_signal = check_entry(candle_5m, candle_5m['high'], candle_5m['low'])
                    if entry_signal:
                        active_trade = open_trade(entry_signal, candle_5m['close'])
                        send_telegram_message(
                            f"🚀 ورود {entry_signal}!\nقیمت ورود: {active_trade['entry_price']}\nتارگت: {active_trade['target']}\nاستاپ: {active_trade['stop']}"
                        )

        # ==============================
        # کندل 1 دقیقه‌ای برای رسیدن به تارگت یا استاپ
        # ==============================
        if active_trade:
            candle_1m_data = get_1m_candle()
            if candle_1m_data:
                ts, o, h, l, c, v = candle_1m_data
                candle_1m = {"high": float(h), "low": float(l)}
                
                closed = False
                if active_trade['direction'] == "LONG":
                    if candle_1m['high'] >= active_trade['target']:
                        send_telegram_message(f"✅ LONG به تارگت رسید! ({active_trade['target']})")
                        closed = True
                    elif candle_1m['low'] <= active_trade['stop']:
                        send_telegram_message(f"❌ LONG به استاپ رسید! ({active_trade['stop']})")
                        closed = True
                elif active_trade['direction'] == "SHORT":
                    if candle_1m['low'] <= active_trade['target']:
                        send_telegram_message(f"✅ SHORT به تارگت رسید! ({active_trade['target']})")
                        closed = True
                    elif candle_1m['high'] >= active_trade['stop']:
                        send_telegram_message(f"❌ SHORT به استاپ رسید! ({active_trade['stop']})")
                        closed = True
                
                if closed:
                    active_trade = None  # معامله بسته شد

        time.sleep(30)  # هر 30 ثانیه

    except Exception:
        print("FULL ERROR:")
        traceback.print_exc()
        time.sleep(30)
