import pandas as pd
import requests
import time
import telegram
from datetime import datetime, timedelta
import websocket
import json

# -----------------------------
# تنظیمات تلگرام
TELEGRAM_BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"
bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)

# ارسال پیام آزمایشی برای تایید اتصال
bot.send_message(chat_id=CHAT_ID, text="ربات NEAR Signal Bot وصل شد ✅")

# -----------------------------
# تنظیمات استراتژی
DELTA = 0.001
TARGET_MOVE = 0.2   # 20% روی سرمایه (تنظیم به درصد دلخواه)
STOP_MOVE = 0.5     # 50% روی سرمایه
SYMBOL = "NEARUSDT"

# -----------------------------
# دریافت کندل‌های عمومی Binance
def get_klines(symbol, interval, limit=500):
    url = f'https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}'
    r = requests.get(url)
    data = r.json()
    df = pd.DataFrame(data, columns=['open_time','open','high','low','close','volume',
                                     'close_time','quote_asset_volume','number_of_trades',
                                     'taker_buy_base','taker_buy_quote','ignore'])
    df['time'] = pd.to_datetime(df['open_time'], unit='ms')
    df[['open','high','low','close','volume']] = df[['open','high','low','close','volume']].astype(float)
    return df

# -----------------------------
# بررسی کندل هشدار
def check_alert(candle_5m, high_4h, low_4h):
    if candle_5m['close'] >= high_4h * (1 + DELTA):
        return 'above'
    elif candle_5m['close'] <= low_4h * (1 - DELTA):
        return 'below'
    return None

# بررسی کندل ورود
def check_entry(candle_5m, high_4h, low_4h, alert_type):
    if alert_type == 'above' and candle_5m['close'] <= high_4h * (1 - DELTA):
        return 'SHORT'
    elif alert_type == 'below' and candle_5m['close'] >= low_4h * (1 + DELTA):
        return 'LONG'
    return None

# -----------------------------
# ردیابی معامله فعال
active_trade = None
alert_type_global = None
high_4h_global = None
low_4h_global = None

print("شروع ربات NEAR Signal...")

while True:
    try:
        # کندل 4 ساعته و 5 دقیقه‌ای
        df_4h = get_klines(SYMBOL, "4h", limit=2)
        df_5m = get_klines(SYMBOL, "5m", limit=50)
        df_1m = get_klines(SYMBOL, "1m", limit=200)

        # آخرین کندل 4 ساعت
        candle_4h = df_4h.iloc[-2]
        high_4h_global = candle_4h['high']
        low_4h_global = candle_4h['low']

        # بررسی کندل هشدار 5 دقیقه‌ای
        for i, candle_5m in df_5m.iterrows():
            alert = check_alert(candle_5m, high_4h_global, low_4h_global)
            if alert:
                alert_type_global = alert
                bot.send_message(chat_id=CHAT_ID, text=f"⚡ هشدار {alert.upper()} در کندل 5 دقیقه‌ای ساعت {candle_5m['time']}")
                break

        # بررسی ورود
        if alert_type_global and active_trade is None:
            for j in range(i+1, len(df_5m)):
                candle_5m = df_5m.iloc[j]
                entry = check_entry(candle_5m, high_4h_global, low_4h_global, alert_type_global)
                if entry:
                    active_trade = {
                        "direction": entry,
                        "entry_price": candle_5m['close'],
                        "start_time": candle_5m['time']
                    }
                    bot.send_message(chat_id=CHAT_ID, text=f"🚀 ورود {entry} در قیمت {candle_5m['close']} ساعت {candle_5m['time']}")
                    break

        # بررسی رسیدن به تارگت یا استاپ با کندل 1 دقیقه‌ای
        if active_trade:
            for k, candle_1m in df_1m.iterrows():
                price_high = candle_1m['high']
                price_low = candle_1m['low']

                trade_closed = False
                if active_trade['direction'] == "LONG":
                    if price_high >= active_trade['entry_price'] * (1 + TARGET_MOVE):
                        bot.send_message(chat_id=CHAT_ID, text=f"✅ تارگت LONG رسید به {active_trade['entry_price']*(1+TARGET_MOVE)}")
                        trade_closed = True
                    elif price_low <= active_trade['entry_price'] * (1 - STOP_MOVE):
                        bot.send_message(chat_id=CHAT_ID, text=f"❌ استاپ LONG فعال شد {active_trade['entry_price']*(1-STOP_MOVE)}")
                        trade_closed = True
                elif active_trade['direction'] == "SHORT":
                    if price_low <= active_trade['entry_price'] * (1 - TARGET_MOVE):
                        bot.send_message(chat_id=CHAT_ID, text=f"✅ تارگت SHORT رسید به {active_trade['entry_price']*(1-TARGET_MOVE)}")
                        trade_closed = True
                    elif price_high >= active_trade['entry_price'] * (1 + STOP_MOVE):
                        bot.send_message(chat_id=CHAT_ID, text=f"❌ استاپ SHORT فعال شد {active_trade['entry_price']*(1+STOP_MOVE)}")
                        trade_closed = True

                if trade_closed:
                    active_trade = None
                    alert_type_global = None
                    break

        time.sleep(60)  # هر 1 دقیقه بررسی کندل‌ها

    except Exception as e:
        bot.send_message(chat_id=CHAT_ID, text=f"⚠️ خطا در ربات: {str(e)}")
        time.sleep(60)
