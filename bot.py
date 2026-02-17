import requests
import time
import traceback
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
TARGET_PERCENT = 0.01        # 1% تغییر قیمت یا 20% روی مارجین
STOP_LOSS_PERCENT = 0.025    # 2.5% روی قیمت یا 50% روی مارجین

SYMBOL = "NEAR-USDT"

# ==============================
# دریافت کندل‌ها از OKX
# ==============================
def get_okx_candles(interval="5m", limit=10):
    url = f"https://www.okx.com/api/v5/market/history-candles?instId={SYMBOL}&bar={interval}&limit={limit}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if "data" in data:
            return data["data"]
        else:
            return []
    except Exception as e:
        print("خطا در گرفتن داده:", e)
        return []

# ==============================
# کمک: پیدا کردن کندل مرجع ۴ ساعته
# ==============================
def get_4h_candle_for_now():
    now = datetime.utcnow()
    hour = (now.hour // 4) * 4
    start = datetime(now.year, now.month, now.day, hour, 0)
    end = start + timedelta(hours=4)
    return start, end

# ==============================
# محاسبه تارگت و استاپ‌لاس
# ==============================
def calculate_targets(entry_price):
    target_price = entry_price * (1 + TARGET_PERCENT)
    stop_loss_price = entry_price * (1 - STOP_LOSS_PERCENT)
    return target_price, stop_loss_price

# ==============================
# شروع ربات
# ==============================
print("🤖 ربات آنلاین شروع شد...")
send_telegram_message("🤖 ربات وصل شد و فعال است!")

last_5m_close = None

while True:
    try:
        # کندل ۵ دقیقه‌ای
        candles_5m = get_okx_candles(interval="5m", limit=2)
        if not candles_5m:
            time.sleep(10)
            continue

        # فقط کندل آخر (بسته شده)
        candle_5m = candles_5m[0]
        ts, o, h, l, c, v = candle_5m[:6]
        c = float(c)
        
        if last_5m_close is not None:
            # منطق ورود: افزایش یا کاهش قیمت نسبت به کندل قبلی
            if c > last_5m_close + DELTA:
                target, stop = calculate_targets(c)
                msg = f"📈 سیگنال خرید!\nورود: {c}\nتارگت: {target:.4f}\nاستاپ‌لاس: {stop:.4f}"
                send_telegram_message(msg)
            elif c < last_5m_close - DELTA:
                target, stop = calculate_targets(c)
                msg = f"📉 سیگنال فروش!\nورود: {c}\nتارگت: {target:.4f}\nاستاپ‌لاس: {stop:.4f}"
                send_telegram_message(msg)

        last_5m_close = c
        time.sleep(60)  # هر دقیقه

    except Exception:
        print("FULL ERROR:")
        traceback.print_exc()
        time.sleep(30)
