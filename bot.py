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
    global last_processed_4h_time, last_alert_time, last_entry_time

    df_4h = get_toobit_candles(SYMBOL, "4h", 10)
    df_5m = get_toobit_candles(SYMBOL, "5m", 250)

    if df_4h.empty or df_5m.empty:
        print(f"[{datetime.now(timezone.utc)}] دریافت داده‌ها ناموفق بود")
        return

    reference_candle = df_4h.iloc[-2]
    ref_time = reference_candle["time"]
    high_4h = reference_candle["high"]
    low_4h = reference_candle["low"]

    # شروع چرخه کندل ۴ ساعته جدید
    is_new_4h = last_processed_4h_time != ref_time
    if is_new_4h:
        last_processed_4h_time = ref_time
        last_alert_time = None
        last_entry_time = None
        print(f"[{datetime.now(timezone.utc)}] کندل ۴H جدید: {ref_time}")

    # کندل‌های ۵ دقیقه‌ای از زمان کندل ۴H جاری
    df_5m_since = df_5m[df_5m["time"] >= ref_time]

    now = datetime.now(timezone.utc)
    end_4h_candle = reference_candle["time"] + timedelta(hours=4)
    half_hour_before_end = end_4h_candle - timedelta(minutes=30)
    
    alert_given = False
    entry_done = last_entry_time is not None

    for _, row in df_5m_since.iterrows():
        t = row["time"]
        close = row["close"]

        # اگر تا پایان کندل ۴ ساعته، ورود داده شده است، هیچ سیگنالی داده نمی‌شود
        if entry_done and t >= last_entry_time:
            break

        # هشدار فقط بعد از بسته شدن کندل ۵ دقیقه‌ای
        if not last_alert_time:
            if t < half_hour_before_end:  # قبل از نیم ساعت پایانی
                if close >= high_4h + DELTA:
                    send_telegram_message(f"⚠️ هشدار بالای کندل ۴H قبلی!")
                    last_alert_time = t
                    alert_given = True
                elif close <= low_4h - DELTA:
                    send_telegram_message(f"⚠️ هشدار پایین کندل ۴H قبلی!")
                    last_alert_time = t
                    alert_given = True
            else:  # نیم ساعت آخر کندل ۴H، فقط هشدار داده می‌شود، ورود نمی‌شود
                if close >= high_4h + DELTA:
                    send_telegram_message(f"⚠️ هشدار نیم ساعت پایانی بالای کندل ۴H!")
                    last_alert_time = t
                    alert_given = True
                elif close <= low_4h - DELTA:
                    send_telegram_message(f"⚠️ هشدار نیم ساعت پایانی پایین کندل ۴H!")
                    last_alert_time = t
                    alert_given = True

        # ورود تنها اگر هشدار قبلی داده شده و هنوز ورود انجام نشده
        if alert_given and not entry_done and t > last_alert_time and t < half_hour_before_end:
            if last_alert_time and last_alert_time < t:
                if close > high_4h and close <= high_4h + DELTA:  # تایید ورود SHORT
                    entry_price = close
                    entry_time = t
                    direction = "SHORT"
                    entry_done = True
                elif close < low_4h and close >= low_4h - DELTA:  # تایید ورود LONG
                    entry_price = close
                    entry_time = t
                    direction = "LONG"
                    entry_done = True

                if entry_done:
                    last_entry_time = entry_time
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
