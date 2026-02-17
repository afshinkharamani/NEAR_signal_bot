import requests
import time
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
DELTA = 0.001
LEVERAGE = 20
TARGET_MOVE = 0.01        # 1% روی قیمت
STOP_MOVE = 0.025         # 2.5% روی قیمت

SYMBOL = "NEAR-USDT"

# ==============================
# گرفتن کندل از OKX (Futures)
# ==============================
def get_okx_candles(interval="1m", limit=50):
    url = f"https://www.okx.com/api/v5/market/candles?instId={SYMBOL}&bar={interval}&limit={limit}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if "data" in data:
            return data["data"]  # هر کندل: [ts, o, h, l, c, vol]
        return []
    except:
        print("خطا در گرفتن داده")
        return []

# ==============================
# منطق استراتژی
# ==============================
last_alert = None
active_trade = None

print("🤖 ربات آنلاین شروع شد...")

while True:
    try:
        # --- کندل ۴ ساعته (مرجع)
        candles_4h = get_okx_candles(interval="4H", limit=2)
        if not candles_4h:
            time.sleep(60)
            continue
        last_candle_4h = candles_4h[-2]  # کندل مرجع = کندل قبلی بسته شده
        ts_4h, o4, h4, l4, c4, v4 = last_candle_4h
        high_4h = float(h4)
        low_4h = float(l4)

        # --- کندل ۵ دقیقه‌ای (برای ورود)
        candles_5m = get_okx_candles(interval="5m", limit=5)
        if not candles_5m:
            time.sleep(60)
            continue
        last_candle_5m = candles_5m[-1]  # کندل آخر بسته شده
        ts_5m, o5, h5, l5, c5, v5 = last_candle_5m
        close_5m = float(c5)
        ts_5m_dt = datetime.fromtimestamp(int(ts_5m)/1000)

        # --- بررسی هشدار
        alert_type = None
        if close_5m >= high_4h * (1 + DELTA):
            alert_type = "above"
        elif close_5m <= low_4h * (1 - DELTA):
            alert_type = "below"

        if alert_type and last_alert != alert_type:
            last_alert = alert_type
            send_telegram_message(f"⚠️ هشدار کندل ۵ دقیقه‌ای: {alert_type.upper()} | زمان: {ts_5m_dt} | قیمت کلوز: {close_5m}")

        # --- بررسی ورود به معامله
        if alert_type and not active_trade:
            entry_price = close_5m
            direction = "SHORT" if alert_type=="above" else "LONG"
            if direction == "LONG":
                target = entry_price * (1 + TARGET_MOVE)
                stop = entry_price * (1 - STOP_MOVE)
            else:
                target = entry_price * (1 - TARGET_MOVE)
                stop = entry_price * (1 + STOP_MOVE)

            active_trade = {
                "direction": direction,
                "entry_price": entry_price,
                "target": target,
                "stop": stop,
                "start_time": ts_5m_dt
            }

            send_telegram_message(
                f"🚀 ورود به معامله {direction}\n"
                f"⏰ زمان: {ts_5m_dt}\n"
                f"💵 قیمت ورود: {entry_price}\n"
                f"🎯 تارگت: {target}\n"
                f"⛔ استاپ: {stop}"
            )

        # --- بررسی کندل ۱ دقیقه‌ای برای تارگت و استاپ
        if active_trade:
            candles_1m = get_okx_candles(interval="1m", limit=10)
            for c in candles_1m:
                ts1, o1, h1, l1, c1, v1 = c
                o1 = float(o1); h1=float(h1); l1=float(l1); c1=float(c1)
                ts1_dt = datetime.fromtimestamp(int(ts1)/1000)

                closed = False
                if active_trade["direction"] == "LONG":
                    if h1 >= active_trade["target"]:
                        send_telegram_message(f"✅ LONG تارگت رسید | زمان: {ts1_dt} | قیمت: {active_trade['target']}")
                        closed = True
                    elif l1 <= active_trade["stop"]:
                        send_telegram_message(f"❌ LONG استاپ خورد | زمان: {ts1_dt} | قیمت: {active_trade['stop']}")
                        closed = True
                else:
                    if l1 <= active_trade["target"]:
                        send_telegram_message(f"✅ SHORT تارگت رسید | زمان: {ts1_dt} | قیمت: {active_trade['target']}")
                        closed = True
                    elif h1 >= active_trade["stop"]:
                        send_telegram_message(f"❌ SHORT استاپ خورد | زمان: {ts1_dt} | قیمت: {active_trade['stop']}")
                        closed = True

                if closed:
                    active_trade = None
                    break

        time.sleep(60)  # هر ۱ دقیقه

    except Exception as e:
        print("FULL ERROR:", e)
        time.sleep(60)
