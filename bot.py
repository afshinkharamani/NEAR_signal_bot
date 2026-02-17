# bot_testnet.py
import json
import time
import requests
import pandas as pd
from websocket import create_connection
from datetime import datetime

# ================== تنظیمات ==================
BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"    # توکن ربات تلگرام
CHAT_ID = "7107618784"       # Chat ID تلگرام
SYMBOL = "NEARUSDT"
LEVERAGE = 20
DELTA = 0.001
TARGET_MOVE = 0.20   # 20% تارگت
STOP_MOVE = 0.50     # 50% استاپ

# دیتافریم‌ها برای کندل‌ها
df_4h = pd.DataFrame()
df_5m = pd.DataFrame()
df_1m = pd.DataFrame()

active_trade = None
last_signal_time = None

# ================== ارسال سیگنال تلگرام ==================
def send_signal(side, price, extra=""):
    global last_signal_time
    now = datetime.now()
    if last_signal_time and (now - last_signal_time).total_seconds() < 60:
        return
    last_signal_time = now

    text = f"""
🚨 SIGNAL ALERT 🚨
Symbol: {SYMBOL}
Side: {side}
Price: {price:.4f}
Time: {now.strftime('%Y-%m-%d %H:%M:%S')}
{extra}
"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text})
    except Exception as e:
        print("Telegram send error:", e)
    print(text)

# ================== منطق استراتژی ==================
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
        if price_high>=active_trade['entry_price']*(1+TARGET_MOVE):
            pnl = LEVERAGE * TARGET_MOVE
            active_trade.update({"exit_price":active_trade['entry_price']*(1+TARGET_MOVE),
                                 "pnl":pnl, "status":"closed"})
            trade_closed = True
        elif price_low<=active_trade['entry_price']*(1-STOP_MOVE):
            pnl = -LEVERAGE * STOP_MOVE
            active_trade.update({"exit_price":active_trade['entry_price']*(1-STOP_MOVE),
                                 "pnl":pnl, "status":"closed"})
            trade_closed = True

    elif active_trade['direction']=="SHORT":
        if price_low<=active_trade['entry_price']*(1-TARGET_MOVE):
            pnl = LEVERAGE * TARGET_MOVE
            active_trade.update({"exit_price":active_trade['entry_price']*(1-TARGET_MOVE),
                                 "pnl":pnl, "status":"closed"})
            trade_closed = True
        elif price_high>=active_trade['entry_price']*(1+STOP_MOVE):
            pnl = -LEVERAGE * STOP_MOVE
            active_trade.update({"exit_price":active_trade['entry_price']*(1+STOP_MOVE),
                                 "pnl":pnl, "status":"closed"})
            trade_closed = True

    if trade_closed:
        send_signal(active_trade['direction'], active_trade['entry_price'])
        print("Trade closed:", active_trade)
        active_trade = None

# ================== دریافت داده زنده از Bybit Testnet ==================
def start_bot():
    ws_url = "wss://stream-testnet.bybit.com/spot/quote/ws"
    try:
        ws = create_connection(ws_url)
    except Exception as e:
        print("WebSocket connection error:", e)
        return

    print("Connected to Bybit Testnet WebSocket")
    send_signal("INFO", 0, "ربات وصل شد ✅")

    # subscribe به کندل‌های 1m, 5m, 4h
    topics = [
        {"op":"subscribe","args":[f"klineV2.{SYMBOL}.1"]},
        {"op":"subscribe","args":[f"klineV2.{SYMBOL}.5"]},
        {"op":"subscribe","args":[f"klineV2.{SYMBOL}.240"]}
    ]
    for t in topics:
        ws.send(json.dumps(t))

    while True:
        try:
            raw = ws.recv()
            if not raw:
                continue
            data = json.loads(raw)
            if "topic" not in data or "data" not in data:
                continue

            topic = data["topic"]
            interval = topic.split(".")[-1]
            k = data["data"].get("kline", None)
            if not k:
                continue

            candle = {
                "time": pd.to_datetime(k["start"]*1000, unit="ms"),
                "open": float(k["open"]),
                "high": float(k["high"]),
                "low": float(k["low"]),
                "close": float(k["close"])
            }

            if interval == "240":
                df_4h.append(candle, ignore_index=True)
            elif interval == "5":
                df_5m.append(candle, ignore_index=True)
                if len(df_4h)>0:
                    last_4h = df_4h.iloc[-1]
                    alert_type = check_alert(candle, last_4h["high"], last_4h["low"])
                    if alert_type and not active_trade:
                        entry_dir = check_entry(candle, last_4h["high"], last_4h["low"], alert_type)
                        if entry_dir:
                            active_trade = open_trade(entry_dir, candle["close"], candle["time"])
                            send_signal(entry_dir, candle["close"])
            elif interval == "1":
                df_1m.append(candle, ignore_index=True)
                manage_trade(candle)

        except Exception as e:
            print("Error in main loop:", e)
            time.sleep(1)

if __name__ == "__main__":
    start_bot()
