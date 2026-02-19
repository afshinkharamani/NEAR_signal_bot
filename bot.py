import requests
import time
import traceback
from datetime import datetime, timedelta, timezone
import pandas as pd

# ===========================
# تنظیمات ربات و استراتژی
# ===========================
BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"

SYMBOL = "NEAR-USDT"
LEVERAGE = 20
TARGET_MOVE_PRICE = 0.01   # 1٪ حرکت قیمت × اهرم = 20٪ سود
STOP_MOVE_PRICE = 0.025    # 2.5٪ حرکت ضد جهت = 50٪ ضرر
DELTA = 0.001              # حاشیه عددی برای شکست

last_processed_4h_time = None
last_alert_time = None
in_trade = False

# ===========================
# ارسال پیام تلگرام
# ===========================
def send_telegram_message(text, retries=3):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    for attempt in range(retries):
        try:
            r = requests.post(url, data=payload, timeout=10)
            if r.status_code == 200:
                print(f"[{datetime.now(timezone.utc)}] Telegram: {text}")
                return True
        except Exception as e:
            print(f"[{datetime.now(timezone.utc)}] Telegram send error {attempt+1}: {e}")
        time.sleep(5)
    print(f"[{datetime.now(timezone.utc)}] Telegram failed after retries")
    return False

# ===========================
# دریافت کندل‌ها از Toobit (فیوچرز)
# ===========================
def get_toobit_candles(interval="5m", limit=200):
    # این URL باید مطابق API رسمی Toobit اصلاح شود
    url = f"https://api.toobit.com/futures/market/history-candles?symbol={SYMBOL}&interval={interval}&limit={limit}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if "data" in data:
            df = pd.DataFrame(data["data"], columns=[
                "time","open","high","low","close","volume"
            ])
            df['time'] = pd.to_datetime(df['time'], unit='ms', errors='coerce', utc=True)
            df = df.dropna(subset=['time'])
            for col in ['open','high','low','close','volume']:
                df[col] = df[col].astype(float)
            return df.sort_values("time").reset_index(drop=True)
        return pd.DataFrame()
    except:
        print(f"[{datetime.now(timezone.utc)}] دریافت داده‌ها ناموفق بود")
        return pd.DataFrame()

# ===========================
# بررسی هشدار و ورود
# ===========================
def check_and_send_signals():
    global last_processed_4h_time, last_alert_time, in_trade

    df_4h = get_toobit_candles("4h", 5)
    df_5m = get_toobit_candles("5m", 200)

    if df_4h.empty or df_5m.empty:
        return

    # کندل ۴H بسته شده قبلی
    reference_candle = df_4h.iloc[-2]
    ref_time = reference_candle['time']

    if last_processed_4h_time == ref_time:
        return  # جلوگیری از پردازش دوباره
    last_processed_4h_time = ref_time
    in_trade = False
    last_alert_time = None

    high_4h = reference_candle['high']
    low_4h = reference_candle['low']

    # بازه کندل ۴H فعلی
    start_4h_current = ref_time + timedelta(hours=4)
    end_4h_current = start_4h_current + timedelta(hours=4)

    # کندل‌های ۵ دقیقه‌ای فعلی
    df_5m_slice = df_5m[(df_5m['time'] >= start_4h_current) & (df_5m['time'] < end_4h_current)]

    alert_type = None
    entry_price = None
    direction = None

    # -------------------------
    # بررسی هشدار (بر اساس کلوز ۵m)
    # -------------------------
    for _, row in df_5m_slice.iterrows():
        close = row['close']
        current_time = row['time']

        # نیم ساعت آخر ۴H: فقط هشدار بدون ورود
        last_30m = (end_4h_current - current_time).total_seconds() <= 30*60

        if last_alert_time is None:  # هنوز هشداری صادر نشده
            if close >= high_4h + DELTA:
                alert_type = "ABOVE"
            elif close <= low_4h - DELTA:
                alert_type = "BELOW"

            if alert_type:
                if last_30m:
                    send_telegram_message(f"⚠️ هشدار {alert_type} کندل ۴H قبلی (۳۰ دقیقه پایانی، ورود فعال نیست)")
                else:
                    send_telegram_message(f"⚠️ هشدار {alert_type} کندل ۴H قبلی!")
                last_alert_time = current_time
                break  # فقط یک هشدار برای هر کندل ۴H صادر شود

    # -------------------------
    # بررسی ورود پس از هشدار
    # -------------------------
    if last_alert_time and not in_trade:
        for _, row in df_5m_slice[df_5m_slice['time'] >= last_alert_time].iterrows():
            close = row['close']
            current_time = row['time']

            if alert_type == "ABOVE" and close <= high_4h - DELTA and (end_4h_current - current_time).total_seconds() > 30*60:
                direction = "SHORT"
                entry_price = close
                break
            elif alert_type == "BELOW" and close >= low_4h + DELTA and (end_4h_current - current_time).total_seconds() > 30*60:
                direction = "LONG"
                entry_price = close
                break

    # -------------------------
    # تعیین حد ضرر و تارگت
    # -------------------------
    if entry_price:
        in_trade = True
        if direction == "LONG":
            stop = entry_price * (1 - STOP_MOVE_PRICE)
            target = entry_price * (1 + TARGET_MOVE_PRICE)
        else:
            stop = entry_price * (1 + STOP_MOVE_PRICE)
            target = entry_price * (1 - TARGET_MOVE_PRICE)

        send_telegram_message(
            f"📊 سیگنال {direction}\nورود: {entry_price:.4f}\nحد ضرر: {stop:.4f}\nهدف: {target:.4f}"
        )

# ===========================
# حلقه اصلی ربات
# ===========================
send_telegram_message(f"🤖 ربات Toobit Futures NEAR وصل شد و فعال است!")
print("🤖 ربات شروع شد و وارد حلقه اصلی شد")

while True:
    try:
        check_and_send_signals()
        time.sleep(60)
    except Exception:
        traceback.print_exc()
        time.sleep(30)
