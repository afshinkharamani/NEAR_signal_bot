import requests
import pandas as pd
import time
from datetime import datetime, timedelta

# ====== تنظیمات تلگرام ======
TELEGRAM_BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print("Error sending Telegram:", e)

# ====== تنظیمات سیگنال ======
DELTA = 0.001
TARGET_MOVE = 0.20   # 20٪ تارگت
STOP_MOVE = 0.50     # 50٪ استاپ

SYMBOL = "NEARUSDT"

# ====== توابع کمکی ======
def get_klines(symbol, interval, limit=500):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    data = requests.get(url).json()
    df = pd.DataFrame(data, columns=[
        'open_time','open','high','low','close','volume',
        'close_time','quote_asset_volume','num_trades',
        'taker_buy_base','taker_buy_quote','ignore'
    ])
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)
    df['time'] = pd.to_datetime(df['open_time'], unit='ms')
    return df

def check_alert(candle_5m, high_4h, low_4h):
    if candle_5m['close'] >= high_4h * (1 + DELTA):
        return 'above'
    elif candle_5m['close'] <= low_4h * (1 - DELTA):
        return 'below'
    return None

def check_entry(candle_5m, high_4h, low_4h, alert_type):
    if alert_type == 'above' and candle_5m['close'] <= high_4h * (1 - DELTA):
        return 'SHORT'
    elif alert_type == 'below' and candle_5m['close'] >= low_4h * (1 + DELTA):
        return 'LONG'
    return None

def monitor_trade(direction, entry_price):
    while True:
        df_1m = get_klines(SYMBOL, '1m', limit=10)
        last = df_1m.iloc[-1]
        price_high = last['high']
        price_low = last['low']

        if direction == "LONG":
            if price_high >= entry_price*(1 + TARGET_MOVE):
                send_telegram(f"LONG NEARUSDT → تارگت رسید! قیمت: {price_high:.4f}")
                break
            elif price_low <= entry_price*(1 - STOP_MOVE):
                send_telegram(f"LONG NEARUSDT → استاپ رسید! قیمت: {price_low:.4f}")
                break
        elif direction == "SHORT":
            if price_low <= entry_price*(1 - TARGET_MOVE):
                send_telegram(f"SHORT NEARUSDT → تارگت رسید! قیمت: {price_low:.4f}")
                break
            elif price_high >= entry_price*(1 + STOP_MOVE):
                send_telegram(f"SHORT NEARUSDT → استاپ رسید! قیمت: {price_high:.4f}")
                break
        time.sleep(10)  # هر 10 ثانیه بررسی می‌کنه

# ====== حلقه اصلی ======
def main():
    print("شروع مانیتورینگ NEARUSDT...")
    while True:
        try:
            # کندل 4H و 5m را دریافت کن
            df_4h = get_klines(SYMBOL, '4h', limit=50)
            df_5m = get_klines(SYMBOL, '5m', limit=50)

            last_4h = df_4h.iloc[-2]  # کندل 4H قبلی
            high_4h = last_4h['high']
            low_4h = last_4h['low']

            # بررسی آخرین کندل 5m
            last_5m = df_5m.iloc[-1]
            alert = check_alert(last_5m, high_4h, low_4h)

            if alert:
                # پیدا کردن کندل ورود
                df_5m_after = df_5m[df_5m['time'] > last_5m['time']].reset_index(drop=True)
                for i, row in df_5m_after.iterrows():
                    entry = check_entry(row, high_4h, low_4h, alert)
                    if entry:
                        send_telegram(f"🚨 سیگنال {entry} NEARUSDT → ورود تایید شد! قیمت: {row['close']:.4f}")
                        monitor_trade(entry, row['close'])
                        break

            time.sleep(15)  # هر 15 ثانیه بررسی می‌کنه

        except Exception as e:
            print("Error:", e)
            time.sleep(30)

if __name__ == "__main__":
    main()
