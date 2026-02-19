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

last_processed_4h_time = None
alert_triggered = False
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
# دریافت کندل‌ها از Toobit
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
    global last_processed_4h_time, alert_triggered, current_trade

    # کندل‌ها
    df_4h = get_toobit_candles(SYMBOL, "4h", 10)
    df_5m = get_toobit_candles(SYMBOL, "5m", 250)
    df_1m = get_toobit_candles(SYMBOL, "1m", 500)  # برای پیگیری معامله

    if df_4h.empty or df_5m.empty or df_1m.empty:
        print(f"[{datetime.now(timezone.utc)}] دریافت داده‌ها ناموفق بود")
        return

    reference_candle = df_4h.iloc[-2]  # کندل ۴H قبلی
    high_4h = reference_candle["high"]
    low_4h = reference_candle["low"]

    current_4h_candle = df_4h.iloc[-1]
    start_4h = current_4h_candle["time"]
    end_4h = start_4h + timedelta(hours=4)
    half_hour_before_end = end_4h - timedelta(minutes=30)

    if last_processed_4h_time != reference_candle["time"]:
        last_processed_4h_time = reference_candle["time"]
        alert_triggered = False
        current_trade = None
        print(f"[{datetime.now(timezone.utc)}] کندل ۴H جدید: {reference_candle['time']}")

    # بررسی کلوز کندل‌های ۵ دقیقه‌ای بعد از شروع ۴H جدید
    df_5m_since = df_5m[df_5m["time"] >= start_4h]
    for idx, row in df_5m_since.iterrows():
        t = row["time"]
        close = row["close"]

        # نیم ساعت پایانی
        if t >= half_hour_before_end:
            break  # ورود در نیم ساعت پایانی انجام نمی‌شود

        # فعال شدن هشدار بر اساس کلوز کندل ۵ دقیقه‌ای
        if not alert_triggered:
            if close > high_4h:
                send_telegram_message(f"⚠️ هشدار: شکست سقف کندل ۴H قبلی! کلوز کندل ۵m: {close}")
                alert_triggered = "SHORT"
                alert_time = t
            elif close < low_4h:
                send_telegram_message(f"⚠️ هشدار: شکست کف کندل ۴H قبلی! کلوز کندل ۵m: {close}")
                alert_triggered = "LONG"
                alert_time = t
            continue  # تا زمانی که هشدار فعال نشود، ورود بررسی نمی‌شود

        # ورود: فقط روی کلوز کندل‌های ۵ دقیقه‌ای بعد از هشدار
        if alert_triggered and current_trade is None and t > alert_time:
            if alert_triggered == "SHORT" and close < high_4h:
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
            elif alert_triggered == "LONG" and close > low_4h:
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

            # اگر معامله باز شد پیام بده
            if current_trade:
                send_telegram_message(
                    f"📊 سیگنال {direction}\nورود: {entry_price:.4f}\nحد ضرر: {stop:.4f}\nهدف: {target:.4f}\nزمان ورود: {entry_time}"
                )
                print(f"[DEBUG] Entry at {entry_price} | Direction: {direction} | Time: {entry_time}")

    # پیگیری معامله تا رسیدن به تارگت یا استاپ (های و لو کندل ۱ دقیقه‌ای)
    if current_trade:
        trade = current_trade
        for _, row in df_1m[df_1m["time"] >= trade["entry_time"]].iterrows():
            price = row["close"]
            t = row["time"]
            exit_trade = False
            result = None

            if trade["direction"] == "LONG":
                if price >= trade["target"]:
                    exit_trade = True
                    result = "WIN"
                elif price <= trade["stop"]:
                    exit_trade = True
                    result = "LOSS"
            else:  # SHORT
                if price <= trade["target"]:
                    exit_trade = True
                    result = "WIN"
                elif price >= trade["stop"]:
                    exit_trade = True
                    result = "LOSS"

            if exit_trade:
                duration = (t - trade["entry_time"]).total_seconds() / 60  # دقیقه
                send_telegram_message(
                    f"🏁 معامله بسته شد!\nجهت: {trade['direction']}\nورود: {trade['entry_price']:.4f}\n"
                    f"خروج: {price:.4f}\nنتیجه: {result}\nمدت زمان معامله: {duration:.1f} دقیقه\nزمان خروج: {t}"
                )
                print(f"[DEBUG] Trade {trade['direction']} | Entry: {trade['entry_price']} | Exit: {price} | Result: {result} | Duration: {duration:.1f} min")
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
