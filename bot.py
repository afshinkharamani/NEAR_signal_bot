# bot_coingecko.py
import requests
import time
from datetime import datetime

BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"

DELTA = 0.001
TARGET_MOVE = 0.20
STOP_MOVE = 0.50

active_trade = None
reference_high = None
reference_low = None

def send(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    print(msg)

def get_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd"
    r = requests.get(url, timeout=10)
    data = r.json()
    return float(data["near"]["usd"])

def start():
    global active_trade, reference_high, reference_low

    send("🤖 ربات فعال شد (CoinGecko)")

    while True:
        try:
            price = get_price()
            print("Price:", price)

            if reference_high is None:
                reference_high = price
                reference_low = price

            reference_high = max(reference_high, price)
            reference_low = min(reference_low, price)

            # ورود
            if not active_trade:
                if price > reference_high * (1 + DELTA):
                    active_trade = {"side": "SHORT", "entry": price}
                    send(f"🚨 SHORT @ {price}")

                elif price < reference_low * (1 - DELTA):
                    active_trade = {"side": "LONG", "entry": price}
                    send(f"🚨 LONG @ {price}")

            # مدیریت معامله
            if active_trade:
                entry = active_trade["entry"]

                if active_trade["side"] == "LONG":
                    if price >= entry * (1+TARGET_MOVE):
                        send("✅ TP LONG")
                        active_trade = None
                    elif price <= entry * (1-STOP_MOVE):
                        send("❌ SL LONG")
                        active_trade = None

                elif active_trade["side"] == "SHORT":
                    if price <= entry * (1-TARGET_MOVE):
                        send("✅ TP SHORT")
                        active_trade = None
                    elif price >= entry * (1+STOP_MOVE):
                        send("❌ SL SHORT")
                        active_trade = None

            time.sleep(10)

        except Exception as e:
            print("Error:", e)
            time.sleep(5)

if __name__ == "__main__":
    start()
