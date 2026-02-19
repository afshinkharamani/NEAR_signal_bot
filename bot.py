import requests
import time
import traceback
from datetime import datetime, timezone, timedelta
import pandas as pd

# ===========================
# تنظیمات ربات و استراتژی
# ===========================
BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"
SYMBOL = "NEAR-SWAP-USDT"
LEVERAGE = 20
TARGET_MOVE_PRICE = 0.01
STOP_MOVE_PRICE = 0.025
DELTA = 0.001

last_processed_4h_time = None
last_no_signal_time = None
last_alert_time = None
last_entry_time = None

# ===========================
# ارسال پیام تلگرام
# ===========================
def send_telegram_message(text, retries=3):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    now = datetime.now(timezone.utc)
    for attempt in range(retries):
        try:
            r = requests.post(url, data=payload, timeout=10)
            if r.status_code == 200:
                print(f"[{now}] Telegram: {text}")
                return True
        except Exception as e:
            print(f"[{now}] Telegram send error {attempt+1}: {e}")
        time.sleep(5)
    print(f"[{now}] Telegram failed after retries")
    return False

# ===========================
# دریافت کندل‌های فیوچرز Toobit
# ===========================
def get_toobit_candles(symbol, interval="5m", limit=200):
    url = "https://api.toobit.com/quote/v1/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            print(f"[{datetime.now(timezone.utc)}] Toobit HTTP error: {r.status_code}")
            return pd.DataFrame()
        data = r.json()
        if not isinstance(data, list):
            print(f"[{datetime.now(timezone.utc)}] Unexpected Toobit response")
            return pd.DataFrame()
        df = pd.DataFrame(data, columns=[
            "open_time","open","high","low","close","volume",
            "close_time","quote_volume","count","taker_base","taker_quote"
        ])
        df["time"] = pd.to_datetime(df["open_time"], unit='ms', utc=True)
        for col in ["open","high","low","close"]:
            df[col] = df[col].astype(float)
        return df.sort_values("time").reset_index(drop=True)
    except Exception as e:
        print(f"[{datetime.now(timezone.utc)}] Exception in get_toobit_candles: {e}")
        return pd.DataFrame()

# ===========================
# بررسی سیگنال‌ها
# ===========================
def check_and_send_signals():
    global last_processed_4h_time, last_no_signal_time, last_alert_time, last_entry_time

    df_4h = get_toobit_candles(SYMBOL, "4h", 10)
    df_5m = get_toobit_candles(SYMBOL, "5m", 250)
    df_1m = get_toobit_candles(SYMBOL, "1m", 500)

    if df_4h.empty or df_5m.empty or df_1m.empty:
        print(f"[{datetime.now(timezone.utc)}] دریافت داده‌ها ناموفق بود")
        return

    reference_candle = df_4h.iloc[-2]
    ref_time = reference_candle["time"]
    high_4h = reference_candle["high"]
    low_4h = reference_candle["low"]

    is_new_4h = last_processed_4h_time != ref_time
    if is_new_4h:
        last_processed_4h_time = ref_time
        last_alert_time = None
        last_entry_time = None
        print(f"[{datetime.now(timezone.utc)}] کندل ۴H جدید: {ref_time}")

    df_5m_since = df_5m[df_5m["time"] >= ref_time]

    alert_type = None
    alert_time = None
    entry_price = None
    entry_time = None
    direction = None

    for _, row in df_5m_since.iterrows():
        t = row["time"]
        if last_alert_time and t <= last_alert_time:
            continue
        close = row["close"]
        if close >= high_4h + DELTA:
            alert_type = "above"
            alert_time = t
            break
        elif close <= low_4h - DELTA:
            alert_type = "below"
            alert_time = t
            break

    if alert_type:
        send_telegram_message(f"⚠️ هشدار {alert_type.upper()} کندل ۴H قبلی!")
        last_alert_time = alert_time

    if alert_type and not last_entry_time:
        for _, row in df_5m_since.iterrows():
            t = row["time"]
            close = row["close"]
            if alert_type == "above" and close <= high_4h - DELTA:
                entry_price = close
                entry_time = t
                direction = "SHORT"
                break
            elif alert_type == "below" and close >= low_4h + DELTA:
                entry_price = close
                entry_time = t
                direction = "LONG"
                break

        if entry_price:
            last_entry_time = entry_time
            df_1m_since = df_1m[df_1m["time"] >= entry_time]

            if direction == "LONG":
                stop = entry_price * (1 - STOP_MOVE_PRICE)
                target = entry_price * (1 + TARGET_MOVE_PRICE)
            else:
                stop = entry_price * (1 + STOP_MOVE_PRICE)
                target = entry_price * (1 - TARGET_MOVE_PRICE)

            send_telegram_message(
                f"📊 سیگنال {direction}\nورود: {entry_price:.4f}\nحد ضرر: {stop:.4f}\nهدف: {target:.4f}"
            )

    now = datetime.now(timezone.utc)
    if last_no_signal_time is None:
        last_no_signal_time = now
    elif (now - last_no_signal_time).total_seconds() >= 1800:
        send_telegram_message("⏳ در حال حاضر سیگنالی وجود ندارد.")
        last_no_signal_time = now

# ===========================
# شروع ربات
# ===========================
send_telegram_message("🤖 ربات Toobit Futures NEAR وصل شد و فعال است!")
print("🤖 ربات Toobit Futures NEAR شروع شد و وارد حلقه اصلی شد")

while True:
    try:
        check_and_send_signals()
        time.sleep(60)
    except Exception as e:
        print(f"[{datetime.now(timezone.utc)}] Exception in main loop: {e}")
        traceback.print_exc()
        time.sleep(30)
