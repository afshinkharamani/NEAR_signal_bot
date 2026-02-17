import time
import requests
from tradingview_ta import TA_Handler, Interval

# ======== تنظیمات ربات ========
API_TELEGRAM = "تو اینجا API رباتت رو بذار"
CHAT_ID = "تو اینجا Chat ID خودت رو بذار"
SYMBOL = "NEARUSDT"
EXCHANGE = "BINANCE"

# ======== تنظیمات استراتژی ========
DELTA = 0.001
LEVERAGE = 20
TARGET_MOVE = 0.10 / LEVERAGE
STOP_MOVE = 0.40 / LEVERAGE

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{API_TELEGRAM}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=data)
    except Exception as e:
        print("ارسال تلگرام مشکل داشت:", e)

# ======== ساخت Handler ========
handler = TA_Handler(
    symbol=SYMBOL,
    screener="crypto",
    exchange=EXCHANGE,
    interval=Interval.INTERVAL_5_MINUTES
)

last_signal = None

while True:
    try:
        analysis = handler.get_analysis()
        close = analysis.indicators["close"]

        # بررسی سیگنال ساده با DELTA
        high_5m = analysis.indicators["high"]
        low_5m = analysis.indicators["low"]

        signal = None
        if close >= high_5m * (1 + DELTA):
            signal = "SHORT"
        elif close <= low_5m * (1 - DELTA):
            signal = "LONG"

        if signal and signal != last_signal:
            msg = f"سیگنال جدید: {signal} برای {SYMBOL} در قیمت {close}"
            print(msg)
            send_telegram_message(msg)
            last_signal = signal

    except Exception as e:
        print("خطا:", e)

    time.sleep(60)  # هر 60 ثانیه بررسی می‌کنه