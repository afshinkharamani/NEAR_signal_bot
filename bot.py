import requests
import time
import traceback
from datetime import datetime, timedelta
import pandas as pd

# ===========================
# تنظیمات ربات و استراتژی
# ===========================
BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"  # رشته کامل، به صورت عددی یا -100xxxxxxxxxx برای گروه‌ها

SYMBOL = "NEAR-USDT"
LEVERAGE = 20
TARGET_MOVE_PRICE = 0.01   # 1٪ حرکت قیمت × اهرم = 20٪ سود
STOP_MOVE_PRICE = 0.025    # 2.5٪ حرکت ضد جهت = 50٪ ضرر
DELTA = 0.001              # حاشیه عددی برای شکست

last_processed_4h_time = None
last_no_signal_time = None
last_alert_time = None
last_entry_time = None

# ===========================
# ارسال پیام تلگرام با Retry
# ===========================
def send_telegram_message(text, retries=3):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    for attempt in range(retries):
        try:
            r = requests.post(url, data=payload, timeout=10)
            if r.status_code == 200:
                print(f"[{datetime.utcnow()}] Telegram: {text}")
                return True
            else:
                print(f"[{datetime.utcnow()}] Telegram HTTP {r.status_code}")
        except Exception as e:
            print(f"[{datetime.utcnow()}] Telegram send error {attempt+1}: {e}")
        time.sleep(5)
    print(f"[{datetime.utcnow()}] Telegram failed after retries")
    return False

# ===========================
# دریافت کندل‌ها از OKX
# ===========================
def get_okx_candles(interval="5m", limit=200):
    url = f"https://www.okx.com/api/v5/market/history-candles?instId={SYMBOL}&bar={interval}&limit={limit}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            print(f"[{datetime.utcnow()}] OKX HTTP error: {r.status_code}")
            return pd.DataFrame()
        data = r.json()
        if "data" not in data:
            print(f"[{datetime.utcnow()}] OKX returned unexpected JSON")
            return pd.DataFrame()
        df = pd.DataFrame(data["data"], columns=[
            "time","open","high","low","close","volume","quote_volume","count","unknown"
        ])
        df['time'] = pd.to_datetime(df['time'], unit='ms', errors='coerce')
        df = df.dropna(subset=['time'])
        for col in ['open','high','low','close']:
            df[col] = df[col].astype(float)
        return df.sort_values("time").reset_index(drop=True)
    except Exception as e:
        print(f"[{datetime.utcnow()}] Exception in get_okx_candles: {e}")
        return pd.DataFrame()

# ===========================
# بررسی سیگنال‌ها و ارسال پیام
# ===========================
def check_and_send_signals():
    global last_processed_4h_time, last_no_signal_time, last_alert_time, last_entry_time

    df_4h = get_okx_candles("4h", 5)
    df_5m = get_okx_candles("5m", 200)
    df_1m = get_okx_candles("1m", 500)

    if df_4h.empty or df_5m.empty or df_1m.empty:
        print(f"[{datetime.utcnow()}] دریافت داده‌ها ناموفق بود")
        return

    reference_candle = df_4h.iloc[-2]
    ref_time = reference_candle['time']

    high_4h = reference_candle['high']
    low_4h = reference_candle['low']

    # بررسی کندل جدید
    is_new_4h = last_processed_4h_time != ref_time
    if is_new_4h:
        last_processed_4h_time = ref_time
        last_alert_time = None
        last_entry_time = None
        print(f"[{datetime.utcnow()}] کندل ۴H جدید: {ref_time}")

    # بازه کندل ۵ دقیقه‌ای بعد از کندل ۴H قبلی
    df_5m_slice = df_5m[df_5m['time'] >= ref_time]

    alert_type = None
    alert_time = None
    entry_price = None
    entry_time = None
    direction = None

    # بررسی هشدار شکست فقط اگر هنوز هشدار داده نشده
    for _, row in df_5m_slice.iterrows():
        close = row['close']
        current_time = row['time']

        if last_alert_time and current_time <= last_alert_time:
            continue  # قبلاً بررسی شده

        if close >= high_4h + DELTA:
            alert_type = "above"
            alert_time = current_time
            break
        elif close <= low_4h - DELTA:
            alert_type = "below"
            alert_time = current_time
            break

    if alert_type:
        # بررسی ۳۰ دقیقه پایانی
        start_4h_current = ref_time + timedelta(hours=4)
        end_4h_current = start_4h_current + timedelta(hours=4)
        if (end_4h_current - alert_time).total_seconds() <= 30*60:
            send_telegram_message(f"⚠️ هشدار {alert_type.upper()} کندل ۴H قبلی، ورود انجام نمی‌شود (۳۰ دقیقه پایانی)")
        else:
            send_telegram_message(f"⚠️ هشدار {alert_type.upper()} کندل ۴H قبلی!")
        last_alert_time = alert_time

    # بررسی ورود بعد از برگشت
    if alert_type and not last_entry_time:
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

        if entry_price:
            last_entry_time = entry_time

            # محاسبه استاپ و تارگت
            df_1m_slice = df_1m[df_1m['time'] >= entry_time]

            if direction == "LONG":
                stop = entry_price * (1 - STOP_MOVE_PRICE)
                target = entry_price * (1 + TARGET_MOVE_PRICE)
            else:
                stop = entry_price * (1 + STOP_MOVE_PRICE)
                target = entry_price * (1 - TARGET_MOVE_PRICE)

            profit = None
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

            # ارسال پیام ورود حتی اگر تارگت یا استاپ هنوز نخورد
            profit_text = f"{profit*100:.2f}%" if profit is not None else "–"
            send_telegram_message(
                f"📊 سیگنال {direction}\nورود: {entry_price:.4f}\nسود/ضرر نهایی: {profit_text}"
            )

    # پیام سیگنال نبود هر ۳۰ دقیقه
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
    except Exception as e:
        print(f"[{datetime.utcnow()}] Exception in main loop: {e}")
        traceback.print_exc()
        time.sleep(30)
