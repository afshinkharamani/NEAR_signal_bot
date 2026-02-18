import requests
import time
import traceback
from datetime import datetime, timedelta
import pandas as pd

BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"

LEVERAGE = 20
TARGET_MOVE_PRICE = 0.01
STOP_MOVE_PRICE = 0.025
DELTA = 0.001
SYMBOL = "NEAR-USDT"

last_processed_4h_time = None
last_no_signal_time = None

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload, timeout=10)
    except:
        print("Telegram send error")

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

def check_and_send_signals():
    global last_processed_4h_time, last_no_signal_time

    df_4h = get_okx_candles("4h", 5)
    df_5m = get_okx_candles("5m", 200)
    df_1m = get_okx_candles("1m", 500)

    if df_4h.empty or df_5m.empty or df_1m.empty:
        return

    reference_candle = df_4h.iloc[-2]
    ref_time = reference_candle['time']

    # جلوگیری از تکرار بررسی همان کندل
    if last_processed_4h_time == ref_time:
        signal_found = False
    else:
        last_processed_4h_time = ref_time
        signal_found = False

        high_4h = reference_candle['high']
        low_4h = reference_candle['low']

        start = ref_time + timedelta(hours=4)
        end = start + timedelta(hours=4)

        df_5m_slice = df_5m[(df_5m['time'] >= start) & (df_5m['time'] < end)]

        alert_type = None
        entry_price = None
        entry_time = None
        direction = None

        # شکست عددی
        for _, row in df_5m_slice.iterrows():
            close = row['close']

            if close >= high_4h + DELTA:
                alert_type = "above"
                break
            elif close <= low_4h - DELTA:
                alert_type = "below"
                break

        # برگشت عددی
        if alert_type:
            for _, row in df_5m_slice.iterrows():
                close = row['close']

                if alert_type == "above" and close <= high_4h - DELTA:
                    entry_price = close
                    entry_time = row['time']
                    direction = "SHORT"
                    break

                if alert_type == "below" and close >= low_4h + DELTA:
                    entry_price = close
                    entry_time = row['time']
                    direction = "LONG"
                    break

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
                        signal_found = True
                        break
                    elif high >= target:
                        profit = TARGET_MOVE_PRICE * LEVERAGE
                        signal_found = True
                        break
                else:
                    if high >= stop:
                        profit = -STOP_MOVE_PRICE * LEVERAGE
                        signal_found = True
                        break
                    elif low <= target:
                        profit = TARGET_MOVE_PRICE * LEVERAGE
                        signal_found = True
                        break

            if signal_found:
                msg = (
                    f"📊 سیگنال {direction}\n"
                    f"ورود: {entry_price:.4f}\n"
                    f"سود/ضرر نهایی: {profit*100:.2f}%"
                )
                send_telegram_message(msg)
                last_no_signal_time = None
                return

    # ===== اگر سیگنال نبود هر 30 دقیقه اطلاع بده =====
    now = datetime.utcnow()

    if last_no_signal_time is None:
        last_no_signal_time = now

    elif (now - last_no_signal_time).total_seconds() >= 1800:
        send_telegram_message("⏳ در حال حاضر سیگنالی وجود ندارد.")
        last_no_signal_time = now


print("🤖 ربات شروع شد")

while True:
    try:
        check_and_send_signals()
        time.sleep(60)
    except Exception:
        traceback.print_exc()
        time.sleep(30)
