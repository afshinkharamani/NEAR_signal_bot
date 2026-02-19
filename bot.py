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
last_report_time = None

# وضعیت معامله جاری
current_trade = None  # {'entry_price', 'direction', 'stop', 'target', 'entry_time'}
alert_given = None  # ⚡ هشدار High/Low برای جلوگیری از ارسال مکرر

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
# دریافت کندل‌های Toobit
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
# بررسی معاملات و ورود (نسخه اصلاح شده)
# ===========================
def check_and_send_signals():
    global last_processed_4h_time, last_alert_time, last_entry_time, current_trade, last_report_time
    global alert_given

    df_4h = get_toobit_candles(SYMBOL, "4h", 10)
    df_5m = get_toobit_candles(SYMBOL, "5m", 500)
    df_1m = get_toobit_candles(SYMBOL, "1m", 500)

    if df_4h.empty or df_5m.empty or df_1m.empty:
        print(f"[{datetime.now(timezone.utc)}] دریافت داده‌ها ناموفق بود")
        return

    reference_candle = df_4h.iloc[-2]  # کندل ۴H قبلی
    high_4h = reference_candle["high"]
    low_4h = reference_candle["low"]

    current_4h_candle = df_4h.iloc[-1]
    start_4h = current_4h_candle["time"]
    end_4h_candle = start_4h + timedelta(hours=4)
    half_hour_before_end = end_4h_candle - timedelta(minutes=30)

    # ⚡ شروع کندل جدید ۴H → ریست هشدار
    if last_processed_4h_time != reference_candle["time"]:
        last_processed_4h_time = reference_candle["time"]
        last_alert_time = None
        last_entry_time = None
        current_trade = None
        last_report_time = None
        alert_given = None
        print(f"[{datetime.now(timezone.utc)}] کندل ۴H جدید: {reference_candle['time']}")

    df_5m_since = df_5m[df_5m["time"] >= start_4h]

    entry_done = current_trade is not None

    for i, row in df_5m_since.iterrows():
        t = row["time"]
        close = row["close"]

        # نیم ساعت پایانی
        if t >= half_hour_before_end:
            if not last_alert_time and current_trade is None:
                send_telegram_message(f"⚠️ هشدار نیم ساعت پایانی کندل ۴H جاری!")
                last_alert_time = t
            break

        # ⚡ اصلاح هشدار High/Low کندل ۴H → فقط یکبار قبل از ورود معامله
        if alert_given is None and current_trade is None:
            if close > high_4h:
                send_telegram_message(f"⚠️ هشدار: کندل پنج دقیقه بسته بالای سقف کندل ۴H قبلی!")
                last_alert_time = t
                alert_given = "SHORT"
            elif close < low_4h:
                send_telegram_message(f"⚠️ هشدار: کندل پنج دقیقه بسته زیر کف کندل ۴H قبلی!")
                last_alert_time = t
                alert_given = "LONG"

        # ورود بعد از کلوز کندل ۵ دقیقه‌ای بعد از هشدار (بدون تغییر)
        if alert_given and not entry_done and last_alert_time is not None and t > last_alert_time:
            if alert_given == "SHORT" and close < high_4h:
                entry_price = close
                direction = "SHORT"
                stop = entry_price * (1 + STOP_MOVE_PRICE)
                target = entry_price * (1 - TARGET_MOVE_PRICE)
                entry_time = t
                current_trade = {
                    "entry_price": entry_price,
                    "direction": direction,
                    "stop": stop,
                    "target": target,
                    "entry_time": entry_time
                }
                entry_done = True
            elif alert_given == "LONG" and close > low_4h:
                entry_price = close
                direction = "LONG"
                stop = entry_price * (1 - STOP_MOVE_PRICE)
                target = entry_price * (1 + TARGET_MOVE_PRICE)
                entry_time = t
                current_trade = {
                    "entry_price": entry_price,
                    "direction": direction,
                    "stop": stop,
                    "target": target,
                    "entry_time": entry_time
                }
                entry_done = True

            if entry_done:
                send_telegram_message(
                    f"📊 سیگنال {direction}\nورود: {entry_price:.4f}\nحد ضرر: {stop:.4f}\nهدف: {target:.4f}\nزمان ورود: {entry_time}"
                )
                print(f"[DEBUG] Entry at {entry_price} | Direction: {direction} | Time: {entry_time}")

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
