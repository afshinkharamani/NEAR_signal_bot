import requests
import time
from datetime import datetime

# =============================
# Telegram Settings
# =============================

BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print("Telegram send error:", e)

# =============================
# Strategy Settings
# =============================

SYMBOL = "NEAR-USDT"
DELTA = 0.001
LEVERAGE = 20
TARGET_MOVE = 0.01     # 1% price move
STOP_MOVE = 0.025      # 2.5% price move

active_trade = None
alert_type = None

send_telegram_message("🤖 OKX Bot Online Started!")

# =============================
# OKX Public API Candles
# =============================

def get_okx_candles(bar):
    """
    Fetch candles from OKX public REST API
    bar: "1m", "5m", "4h"
    """
    url = f"https://www.okx.com/api/v5/market/candles?instId={SYMBOL}&bar={bar}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if "data" in data:
            return data["data"]
        return []
    except Exception as e:
        print("Error fetching OKX candles:", e)
        return []

# =============================
# Main Loop
# =============================

while True:
    try:
        # get fresh market candles
        candles_4h = get_okx_candles("4h")
        candles_5m = get_okx_candles("5m")
        candles_1m = get_okx_candles("1m")

        if not candles_4h or not candles_5m or not candles_1m:
            time.sleep(15)
            continue

        # =================================
        # 4H Reference (last completed candle)
        # =================================
        # index 1 is last complete candle if 0 is possibly incomplete
        candle_4h = candles_4h[1]  
        high_4h = float(candle_4h[2])
        low_4h  = float(candle_4h[3])

        # =================================
        # 5m Close
        # =================================
        candle_5m = candles_5m[1]
        close_5m = float(candle_5m[4])
        time_5m = datetime.utcfromtimestamp(int(candle_5m[0])/1000)

        # ===== Alert Logic =====
        if active_trade is None:
            if close_5m >= high_4h*(1 + DELTA):
                alert_type = "above"
                send_telegram_message(f"⚠️ Alert ABOVE 4H (5m close)\nTime: {time_5m}\nPrice: {close_5m}")
            elif close_5m <= low_4h*(1 - DELTA):
                alert_type = "below"
                send_telegram_message(f"⚠️ Alert BELOW 4H (5m close)\nTime: {time_5m}\nPrice: {close_5m}")

        # ===== Entry Logic =====
        if active_trade is None and alert_type:
            if alert_type=="above" and close_5m <= high_4h*(1 - DELTA):
                entry = close_5m
                tgt = entry * (1 - TARGET_MOVE)
                stp = entry * (1 + STOP_MOVE)
                send_telegram_message(
                    f"🚀 ENTRY SHORT\nEntry: {entry:.4f}\nTarget: {tgt:.4f}\nStop: {stp:.4f}"
                )
                active_trade = {"dir":"SHORT","entry":entry,"target":tgt,"stop":stp}
                alert_type=None

            elif alert_type=="below" and close_5m >= low_4h*(1 + DELTA):
                entry = close_5m
                tgt = entry * (1 + TARGET_MOVE)
                stp = entry * (1 - STOP_MOVE)
                send_telegram_message(
                    f"🚀 ENTRY LONG\nEntry: {entry:.4f}\nTarget: {tgt:.4f}\nStop: {stp:.4f}"
                )
                active_trade = {"dir":"LONG","entry":entry,"target":tgt,"stop":stp}
                alert_type=None

        # ===== Target / Stop Monitoring with 1m candles =====
        if active_trade:
            for c in candles_1m:
                price_high = float(c[2])
                price_low  = float(c[3])
                if active_trade["dir"]=="LONG":
                    if price_high >= active_trade["target"]:
                        send_telegram_message(f"✅ LONG TARGET REACHED\nTarget: {active_trade['target']:.4f}")
                        active_trade = None
                        break
                    elif price_low <= active_trade["stop"]:
                        send_telegram_message(f"❌ LONG STOP HIT\nStop: {active_trade['stop']:.4f}")
                        active_trade = None
                        break
                else:  # SHORT
                    if price_low <= active_trade["target"]:
                        send_telegram_message(f"✅ SHORT TARGET REACHED\nTarget: {active_trade['target']:.4f}")
                        active_trade = None
                        break
                    elif price_high >= active_trade["stop"]:
                        send_telegram_message(f"❌ SHORT STOP HIT\nStop: {active_trade['stop']:.4f}")
                        active_trade = None
                        break

        # wait before next check
        time.sleep(30)

    except Exception as e:
        print("Error Loop:", e)
        time.sleep(30)
