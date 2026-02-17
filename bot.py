import requests
import time
import traceback

# ==============================
# تنظیمات تلگرام
# ==============================

BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"

# ==============================
# ارسال پیام تلگرام
# ==============================

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text
    }
    try:
        requests.post(url, data=payload, timeout=10)
    except:
        print("Telegram send error")

# ==============================
# گرفتن قیمت از CoinGecko
# ==============================

def get_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=near&vs_currencies=usd"
    
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    r = requests.get(url, headers=headers, timeout=10)
    data = r.json()

    return float(data["near"]["usd"])

# ==============================
# شروع ربات
# ==============================

print("🤖 Bot started...")
send_telegram_message("🤖 ربات وصل شد و فعال است!")

last_price = None

while True:
    try:
        price = get_price()
        print("Price:", price)

        # سیگنال ساده تغییر قیمت
        if last_price is not None:
            if price > last_price:
                send_telegram_message(f"📈 قیمت در حال افزایش است: {price}")
            elif price < last_price:
                send_telegram_message(f"📉 قیمت در حال کاهش است: {price}")

        last_price = price

        time.sleep(30)  # هر 30 ثانیه

    except Exception:
        print("FULL ERROR:")
        traceback.print_exc()
        time.sleep(30)
