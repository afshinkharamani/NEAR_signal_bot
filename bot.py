# bot.py
import pandas as pd
from binance import ThreadedWebsocketManager
import requests
from datetime import datetime
import time

# ===== تنظیمات تلگرام =====
BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"

SYMBOL = "NEARUSDT"
LEVERAGE = 20
DELTA = 0.001
TARGET_MOVE = 0.20  # 20٪ تارگت
STOP_MOVE = 0.50    # 50٪ استاپ

df_4h = pd.DataFrame()
df_5m = pd.DataFrame()
df_1m = pd.DataFrame()

active_trade = None
last_signal_time = None

# ===== ارسال سیگنال تلگرام =====
def send_signal(side, price):
    global last_signal_time
    now = datetime.now()
    if last_signal_time and (now - last_signal_time).total_seconds() < 60:
        return
    last_signal_time = now

    if side == "BOT_STARTED":
        text = f"✅ ربات برای {SYMBOL} متصل شد.\nTime: {now}"
    else:
        text = f"🚨 SIGNAL ALERT 🚨\nSymbol: {SYMBOL}\nSide: {side}\nPrice: {price:.4f}\nTime: {now}"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})
    print(text)

# ===== منطق استراتژی =====
def check_alert(candle, high_4h, low_4h):
    if candle['close'] >= high_4h*(1+DELTA):
        return 'above'
    elif candle['close'] <= low_4h*(1-DELTA):
        return 'below'
    return None

def check_entry(candle, high_4h, low_4h, alert_type):
    if alert_type=='above' and candle['close'] <= high_4h*(1-DELTA):
        return 'SHORT'
    elif alert_type=='below' and candle['close'] >= low_4h*(1+DELTA):
        return 'LONG'
    return None

def open_trade(direction, price, start_time):
    return {"direction": direction, "entry_price": price, "start_time": start_time, "status":"open"}

def manage_trade(candle):
    global active_trade
    if not active_trade:
        return
    price_high = candle['high']
    price_low = candle['low']
    trade_closed = False
    if active_trade['direction']=="LONG":
        if price_high >= active_trade['entry_price']*(1+TARGET_MOVE):
            pnl = LEVERAGE*TARGET_MOVE
            active_trade.update({"exit_price": active_trade['entry_price']*(1+TARGET_MOVE),
                                 "pnl": pnl, "status": "closed", "exit_time": candle['time']})
            trade_closed = True
        elif price_low <= active_trade['entry_price']*(1-STOP_MOVE):
            pnl = -LEVERAGE*STOP_MOVE
            active_trade.update({"exit_price": active_trade['entry_price']*(1-STOP_MOVE),
                                 "pnl": pnl, "status": "closed", "exit_time": candle['time']})
            trade_closed = True
    elif active_trade['direction']=="SHORT":
        if price_low <= active_trade['entry_price']*(1-TARGET_MOVE):
            pnl = LEVERAGE*TARGET_MOVE
            active_trade.update({"exit_price": active_trade['entry_price']*(1-TARGET_MOVE),
                                 "pnl": pnl, "status": "closed", "exit_time": candle['time']})
            trade_closed = True
        elif price_high >= active_trade['entry_price']*(1+STOP_MOVE):
            pnl = -LEVERAGE*STOP_MOVE
            active_trade.update({"exit_price": active_trade['entry_price']*(1+STOP_MOVE),
                                 "pnl": pnl, "status": "closed", "exit_time": candle['time']})
            trade_closed = True
    if trade_closed:
        send_signal(active_trade['direction'], active_trade['entry_price'])
        print("Trade closed:", active_trade)
        active_trade = None

# ===== دریافت کندل‌ها =====
def handle_socket_message(msg):
    global df_4h, df_5m, df_1m, active_trade
    if msg['e'] != 'kline':
        return
    k = msg['k']
    candle = {
        "time": pd.to_datetime(k['t'], unit='ms'),
        "open": float(k['o']),
        "high": float(k['h']),
        "low": float(k['l']),
        "close": float(k['c'])
    }
    interval = k['i']
    if interval == "4h":
        df_4h = df_4h.append(candle, ignore_index=True)
    elif interval == "5m":
        df_5m = df_5m.append(candle, ignore_index=True)
        if len(df_4h) == 0:
            return
        last_4h = df_4h.iloc[-1]
        alert_type = check_alert(candle, last_4h['high'], last_4h['low'])
        if alert_type and not active_trade:
            entry_direction = check_entry(candle, last_4h['high'], last_4h['low'], alert_type)
            if entry_direction:
                active_trade = open_trade(entry_direction, candle['close'], candle['time'])
                send_signal(entry_direction, candle['close'])
                print("Trade opened:", active_trade)
    elif interval == "1m":
        df_1m = df_1m.append(candle, ignore_index=True)
        manage_trade(candle)

# ===== اجرای ربات =====
def start_bot():
    while True:
        try:
            twm = ThreadedWebsocketManager()
            twm.start()
            twm.start_kline_socket(callback=handle_socket_message, symbol=SYMBOL, interval="1m")
            twm.start_kline_socket(callback=handle_socket_message, symbol=SYMBOL, interval="5m")
            twm.start_kline_socket(callback=handle_socket_message, symbol=SYMBOL, interval="4h")
            print("Bot started for", SYMBOL)
            send_signal("BOT_STARTED", 0)  # پیام اتصال خودکار
            twm.join()
        except Exception as e:
            print("Error:", e)
            print("Reconnecting in 5 seconds...")
            time.sleep(5)

if __name__ == "__main__":
    start_bot()
