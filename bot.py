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
current_trade = None  # {'entry_price', 'direction', 'stop', 'target', 'entry_time'}

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
# بررسی معاملات و ورود
# ===========================
def check_and_send_signals():
    global last_processed_4h_time, last_alert_time, current_trade

    # دریافت کندل‌ها
    df_4h = get_toobit_candles(SYMBOL, "4h", 10)
    df_5m = get_toobit_candles(SYMBOL, "5m", 500)  # برای بررسی ورود بعد از بسته شدن
    df_1m = get_toobit_candles(SYMBOL, "1m", 500)  # برای پیگیری معامله

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

    # کندل ۴H جدید
    if last_processed_4h_time != reference_candle["time"]:
        last_processed_4h_time = reference_candle["time"]
        last_alert_time = None
        current_trade = None
        print(f"[{datetime.now(timezone.utc)}] کندل ۴H جدید: {reference_candle['time']}")

    df_5m_since = df_5m[df_5m["time"] >= start_4h]

    # بررسی کندل‌های ۵ دقیقه ای
    for i in range(1, len(df_5m_since)):
        prev_row = df_5m_since.iloc[i-1]
        row = df_5m_since.iloc[i]
        close = prev_row["close"]  # استفاده از کلوز کندل بسته شده
        t = prev_row["time"]

        # نیم ساعت پایانی
        if t >= half_hour_before_end:
            break

        # هشدار فقط یک بار
        if not last_alert_time:
            if close > high_4h:
                send_telegram_message(f"⚠️ هشدار: سقف کندل ۴H قبلی شکسته شد!")
                last_alert_time = t
                alert_direction = "SHORT"
            elif close < low_4h:
                send_telegram_message(f"⚠️ هشدار: کف کندل ۴H قبلی شکسته شد!")
                last_alert_time = t
                alert_direction = "LONG"

        # ورود بعد از بسته شدن کندل ۵ دقیقه‌ای
        if last_alert_time and current_trade is None and t > last_alert_time:
            if alert_direction == "SHORT" and close < high_4h:
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
                send_telegram_message(
                    f"📊 سیگنال {direction}\nورود: {entry_price:.4f}\nحد ضرر: {stop:.4f}\nهدف: {target:.4f}\nزمان ورود: {entry_time}"
                )
            elif alert_direction == "LONG" and close > low_4h:
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
                send_telegram_message(
                    f"📊 سیگنال {direction}\nورود: {entry_price:.4f}\nحد ضرر: {stop:.4f}\nهدف: {target:.4f}\nزمان ورود: {entry_time}"
                )

    # پیگیری معامله باز با کندل‌های ۱ دقیقه‌ای
    if current_trade:
        trade = current_trade
        for _, row in df_1m[df_1m["time"] >= trade["entry_time"]].iterrows():
            price = row["close"]
            t = row["time"]
            exit_trade = False
            result = None

            if trade["direction"] == "LONG":
                if row["high"] >= trade["target"]:
                    exit_trade = True
                    result = "WIN"
                elif row["low"] <= trade["stop"]:
                    exit_trade = True
                    result = "LOSS"
            else:  # SHORT
                if row["low"] <= trade["target"]:
                    exit_trade = True
                    result = "WIN"
                elif row["high"] >= trade["stop"]:
                    exit_trade = True
                    result = "LOSS"

            if exit_trade:
                duration = (t - trade["entry_time"]).total_seconds() / 60
                send_telegram_message(
                    f"🏁 معامله بسته شد!\nجهت: {trade['direction']}\nورود: {trade['entry_price']:.4f}\n"
                    f"خروج: {price:.4f}\nنتیجه: {result}\nمدت زمان معامله: {duration:.1f} دقیقه\nزمان خروج: {t}"
                )
                current_trade = None
                break

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
