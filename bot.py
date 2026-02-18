import requests
import time
import traceback
from datetime import datetime, timedelta
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
last_no_signal_time = None

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
                print(f"Telegram: {text}")
                return True
        except Exception as e:
            print(f"Telegram send error {attempt+1}: {e}")
        time.sleep(5)
    print("Telegram failed after retries")
    return False

# ===========================
# دریافت کندل‌ها از OKX
# ===========================
def get_okx_candles(interval="5m", limit=200):
    url = f"https://www.okx.com/api/v5/market/history-candles?instId={SYMBOL}&bar={interval}&limit={limit}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if "data" in data:
            df = pd.DataFrame(data["data"], columns=[
                "time","open","high","low","close","volume","quote_volume","count","unknown"
            ])
            df['time'] = pd.to_datetime(df['time'], unit='ms', errors='coerce')
            df = df.dropna(subset=['time'])
            for col in ['open','high','low','close']:
                df[col] = df[col].astype(float)
            return df.sort_values("time").reset_index(drop=True)
        return pd.DataFrame()
    except:
        return pd.DataFrame()

# ===========================
# بررسی سیگنال‌ها
# ===========================
def check_and_send_signals():
    global last_processed_4h_time, last_no_signal_time

    df_4h = get_okx_candles("4h", 5)
    df_5m = get_okx_candles("5m", 200)
    df_1m = get_okx_candles("1m", 500)

    if df_4h.empty or df_5m.empty or df_1m.empty:
        return

    # 1️⃣ مرجع کندل ۴H بسته شده قبلی
    reference_candle = df_4h.iloc[-2]
    ref_time = reference_candle['time']

    # جلوگیری از پردازش دوباره همان کندل
    if last_processed_4h_time == ref_time:
        return
    last_processed_4h_time = ref_time

    high_4h = reference_candle['high']
    low_4h = reference_candle['low']

    # بازه کندل ۴H فعلی
    start_4h_current = ref_time + timedelta(hours=4)
    end_4h_current = start_4h_current + timedelta(hours=4)

    # 2️⃣ کندل‌های ۵ دقیقه‌ای فعلی
    df_5m_slice = df_5m[(df_5m['time'] >= start_4h_current) & (df_5m['time'] < end_4h_current)]

    alert_type = None
    alert_time = None
    entry_price = None
    entry_time = None
    direction = None

    # 3️⃣ هشدار شکست عددی
    for _, row in df_5m_slice.iterrows():
        close = row['close']
        current_time = row['time']

        if close >= high_4h + DELTA:
            alert_type = "above"
            alert_time = current_time
            break
        elif close <= low_4h - DELTA:
            alert_type = "below"
            alert_time = current_time
            break

    # فقط هشدار در ۳۰ دقیقه پایانی کندل ۴H
    if alert_type and (end_4h_current - alert_time).total_seconds() <= 30*60:
        send_telegram_message(f"⚠️ هشدار {alert_type.upper()} کندل ۴H قبلی، ورود انجام نمی‌شود (۳۰ دقیقه پایانی)")
        alert_type = None
    elif alert_type:
        send_telegram_message(f"⚠️ هشدار {alert_type.upper()} کندل ۴H قبلی!")

    # 4️⃣ ورود به معامله بعد از برگشت
    if alert_type:
        for _, row in df_5m_slice.iterrows():
            close = row['close']
            time_5m = row['time']

            if alert_type == "above" and close <= high_4h - DELTA:
                entry_price = close
                entry_time = time_5m
                direction = "SHORT"
                break
            elif alert_type == "below" and close >= low_4h + DELTA:
                entry_price = close
                entry_time = time_5m
                direction = "LONG"
                break

    # 5️⃣ معامله روی کندل‌های ۱ دقیقه‌ای تا رسیدن تارگت یا استاپ
    if entry_price:
        df_1m_slice = df_1m[df_1m['time'] >= entry_time]

        if direction == "LONG":
            stop = entry_price * (1 - STOP_MOVE_PRICE)
            target = entry_price * (1 + TARGET_MOVE_PRICE)
        else:
            stop = entry_price * (1 + STOP_MOVE_PRICE)
            target = entry_price * (1 - TARGET_MOVE_PRICE)

        for _, row in df_1m_slice.iterrows():
            high = row['high']
            low = row['low']

            if direction == "LONG":
                if low <= stop:
                    profit = -STOP_MOVE_PRICE * LEVERAGE
                    break
                elif high >= target:
                    profit = TARGET_MOVE_PRICE * LEVERAGE
                    break
            else:
                if high >= stop:
                    profit = -STOP_MOVE_PRICE * LEVERAGE
                    break
                elif low <= target:
                    profit = TARGET_MOVE_PRICE * LEVERAGE
                    break

        send_telegram_message(
            f"📊 سیگنال {direction}\nورود: {entry_price:.4f}\nسود/ضرر نهایی: {profit*100:.2f}%"
        )
        last_no_signal_time = None
        return

    # 6️⃣ پیام سیگنال نبود هر ۳۰ دقیقه
    now = datetime.utcnow()
    if last_no_signal_time is None:
        last_no_signal_time = now
    elif (now - last_no_signal_time).total_seconds() >= 1800:
        send_telegram_message("⏳ در حال حاضر سیگنالی وجود ندارد.")
        last_no_signal_time = now

# ===========================
# شروع ربات
# ===========================
send_telegram_message("🤖 ربات وصل شد و فعال است!")
print("🤖 ربات شروع شد و وارد حلقه اصلی شد")

while True:
    try:
        check_and_send_signals()
        time.sleep(60)
    except Exception:
        traceback.print_exc()
        time.sleep(30)
