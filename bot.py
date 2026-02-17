import pandas as pd
import websocket
import json
from datetime import datetime, timedelta
from telegram import Bot

# ======= تنظیمات تلگرام =======
TELEGRAM_BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# پیام اول که ربات وصل شد
bot.send_message(chat_id=CHAT_ID, text="ربات وصل شد ✅")

# ======= تنظیمات استراتژی =======
DELTA = 0.001
TARGET_MOVE = 0.20    # 20% تارگت
STOP_MOVE = 0.50      # 50% استاپ
LEVERAGE = 20

# نمونه داده ۴ ساعته (برای مثال، می‌تونی آنلاین هم دریافت کنی)
high_4h = 1.0000
low_4h = 0.9900

# وضعیت معامله فعال
active_trade = None

# تابع بررسی سیگنال ورود
def check_signal(candle_5m_close):
    global active_trade
    if active_trade:
        return None
    if candle_5m_close > low_4h * (1 + DELTA):
        active_trade = {"direction": "LONG", "entry_price": candle_5m_close, "time": datetime.now()}
        bot.send_message(chat_id=CHAT_ID, text=f"⚡ LONG ENTRY: {candle_5m_close}")
    elif candle_5m_close < high_4h * (1 - DELTA):
        active_trade = {"direction": "SHORT", "entry_price": candle_5m_close, "time": datetime.now()}
        bot.send_message(chat_id=CHAT_ID, text=f"⚡ SHORT ENTRY: {candle_5m_close}")

# تابع بررسی استاپ و تارگت
def check_exit(candle_1m_high, candle_1m_low):
    global active_trade
    if not active_trade:
        return
    direction = active_trade["direction"]
    entry = active_trade["entry_price"]
    if direction == "LONG":
        if candle_1m_high >= entry * (1 + TARGET_MOVE):
            bot.send_message(chat_id=CHAT_ID, text=f"✅ LONG TARGET HIT: {entry * (1 + TARGET_MOVE)}")
            active_trade.clear()
        elif candle_1m_low <= entry * (1 - STOP_MOVE):
            bot.send_message(chat_id=CHAT_ID, text=f"❌ LONG STOP HIT: {entry * (1 - STOP_MOVE)}")
            active_trade.clear()
    elif direction == "SHORT":
        if candle_1m_low <= entry * (1 - TARGET_MOVE):
            bot.send_message(chat_id=CHAT_ID, text=f"✅ SHORT TARGET HIT: {entry * (1 - TARGET_MOVE)}")
            active_trade.clear()
        elif candle_1m_high >= entry * (1 + STOP_MOVE):
            bot.send_message(chat_id=CHAT_ID, text=f"❌ SHORT STOP HIT: {entry * (1 + STOP_MOVE)}")
            active_trade.clear()

# ======= اتصال به وب‌سوکت Binance =======
def on_message(ws, message):
    data = json.loads(message)
    candle = data['k']
    if candle['x']:  # کندل بسته شد
        close_5m = float(candle['c'])
        check_signal(close_5m)
        # بررسی استاپ و تارگت با کندل 1 دقیقه‌ای (می‌تونی جدا وصل کنی)
        # check_exit(high_1m, low_1m)

def on_error(ws, error):
    print("WebSocket Error:", error)

def on_close(ws, close_status_code, close_msg):
    print("WebSocket Closed")

def on_open(ws):
    print("WebSocket Opened")

# مثال اتصال به کندل ۵ دقیقه‌ای NEARUSDT
socket_url = "wss://stream.binance.com:9443/ws/nearusdt@kline_5m"
ws = websocket.WebSocketApp(socket_url, on_message=on_message, on_error=on_error, on_close=on_close)
ws.on_open = on_open
ws.run_forever()
