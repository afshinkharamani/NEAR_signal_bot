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
last_alert_time = None
current_trade = None

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
            return pd.DataFrame()

        data = r.json()
        if not isinstance(data, list):
            return pd.DataFrame()

        df = pd.DataFrame(data, columns=[
            "open_time","open","high","low","close","volume",
            "close_time","quote_volume","count","taker_base","taker_quote"
        ])

        df["time"] = pd.to_datetime(df["open_time"], unit='ms', utc=True)

        for col in ["open","high","low","close"]:
            df[col] = df[col].astype(float)

        return df.sort_values("time").reset_index(drop=True)

    except:
        return pd.DataFrame()

# ===========================
# بررسی معاملات و ورود
# ===========================

def check_and_send_signals():
    global last_processed_4h_time, last_alert_time, current_trade

    df_4h = get_toobit_candles(SYMBOL, "4h", 10)
    df_5m = get_toobit_candles(SYMBOL, "5m", 250)
    df_1m = get_toobit_candles(SYMBOL, "1m", 500)

    if df_4h.empty or df_5m.empty or df_1m.empty:
        return

    reference_candle = df_4h.iloc[-2]
    high_4h = reference_candle["high"]
    low_4h = reference_candle["low"]

    current_4h_candle = df_4h.iloc[-1]
    start_4h = current_4h_candle["time"]
    end_4h_candle = start_4h + timedelta(hours=4)
    half_hour_before_end = end_4h_candle - timedelta(minutes=30)

    if last_processed_4h_time != reference_candle["time"]:
        last_processed_4h_time = reference_candle["time"]
        last_alert_time = None
        current_trade = None

    df_5m_since = df_5m[df_5m["time"] >= start_4h]

    alert_direction = None
    entry_done = current_trade is not None

    for _, row in df_5m_since.iterrows():
        t = row["time"]
        close = row["close"]

        if t >= half_hour_before_end:
            break

        # هشدار فقط با کلوز
        if not alert_direction:
            if close > high_4h:
                send_telegram_message("⚠️ شکست سقف ۴H با کلوز ۵ دقیقه")
                last_alert_time = t
                alert_direction = "SHORT"

            elif close < low_4h:
                send_telegram_message("⚠️ شکست کف ۴H با کلوز ۵ دقیقه")
                last_alert_time = t
                alert_direction = "LONG"

        # ورود فقط روی کلوز کندل برگشتی
        elif not entry_done and t > last_alert_time:

            if alert_direction == "SHORT" and close < high_4h:
                entry_price = close
                direction = "SHORT"
                stop = entry_price * (1 + STOP_MOVE_PRICE)
                target = entry_price * (1 - TARGET_MOVE_PRICE)

            elif alert_direction == "LONG" and close > low_4h:
                entry_price = close
                direction = "LONG"
                stop = entry_price * (1 - STOP_MOVE_PRICE)
                target = entry_price * (1 + TARGET_MOVE_PRICE)
            else:
                continue

            current_trade = {
                "entry_price": entry_price,
                "direction": direction,
                "stop": stop,
                "target": target,
                "entry_time": t
            }

            entry_done = True

            send_telegram_message(
                f"📊 سیگنال {direction}\n"
                f"ورود: {entry_price:.4f}\n"
                f"حد ضرر: {stop:.4f}\n"
                f"هدف: {target:.4f}"
            )

    # ===========================
    # بررسی خروج با های و لو ۱ دقیقه
    # ===========================

    if current_trade:
        trade = current_trade

        for _, row in df_1m[df_1m["time"] >= trade["entry_time"]].iterrows():
            high = row["high"]
            low = row["low"]
            t = row["time"]

            exit_trade = False
            result = None

            if trade["direction"] == "LONG":
                if high >= trade["target"]:
                    exit_trade = True
                    result = "WIN"
                elif low <= trade["stop"]:
                    exit_trade = True
                    result = "LOSS"

            else:  # SHORT
                if low <= trade["target"]:
                    exit_trade = True
                    result = "WIN"
                elif high >= trade["stop"]:
                    exit_trade = True
                    result = "LOSS"

            if exit_trade:
                send_telegram_message(
                    f"🏁 معامله بسته شد\n"
                    f"جهت: {trade['direction']}\n"
                    f"نتیجه: {result}"
                )
                current_trade = None
                break

# ===========================
# شروع ربات
# ===========================

send_telegram_message("🤖 ربات فعال شد")

while True:
    try:
        check_and_send_signals()
        time.sleep(60)
    except Exception as e:
        traceback.print_exc()
        time.sleep(30)
