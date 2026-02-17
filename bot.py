import requests
import time
import traceback
from datetime import datetime, timedelta
import pandas as pd

# ==============================
# تنظیمات تلگرام
# ==============================
BOT_TOKEN = "8448021675:AAE0Z4jRdHZKLVXxIBEfpCb9lUbkkxmlW-k"
CHAT_ID = "7107618784"

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        requests.post(url, data=payload, timeout=10)
    except:
        print("Telegram send error")

# ==============================
# تنظیمات استراتژی
# ==============================
LEVERAGE = 20
TARGET_MOVE_PRICE = 0.01   # 1% هدف سود
STOP_MOVE_PRICE = 0.025    # 2.5% استاپ
DELTA = 0.001              # حاشیه کوچک برای عبور از high/low
SYMBOL = "NEAR-USDT"

# ==============================
# توابع استراتژی (کد x)
# ==============================

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

def open_trade(direction, price, start_time):
    return {
        "direction": direction,
        "entry_price": price,
        "start_time": start_time,
        "status": "open"
    }

def get_4h_candle_for_now():
    now = datetime.utcnow()
    hour = (now.hour // 4) * 4
    start = datetime(now.year, now.month, now.day, hour, 0)
    end = start + timedelta(hours=4)
    return start, end

# ==============================
# دریافت کندل‌ها از OKX
# ==============================
def get_okx_candles(interval="5m", limit=50):
    url = f"https://www.okx.com/api/v5/market/history-candles?instId={SYMBOL}&bar={interval}&limit={limit}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if "data" in data:
            # تبدیل به DataFrame
            df = pd.DataFrame(data["data"], columns=["time","open","high","low","close","volume","extra1","extra2","extra3","extra4"])
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            for col in ['open','high','low','close','volume']:
                df[col] = df[col].astype(float)
            return df
        else:
            return pd.DataFrame()
    except Exception as e:
        print("خطا در گرفتن داده:", e)
        return pd.DataFrame()

# ==============================
# بررسی سیگنال‌ها و ارسال تلگرام
# ==============================
def check_and_send_signals():
    df_4h = get_okx_candles(interval="4h", limit=10)
    df_5m = get_okx_candles(interval="5m", limit=50)
    df_1m = get_okx_candles(interval="1m", limit=50)

    if df_4h.empty or df_5m.empty or df_1m.empty:
        return

    signals = get_signals(df_4h, df_5m, df_1m)

    for trade in signals:
        if trade['status'] == 'closed':
            dir_icon = "📈" if trade['direction'] == "LONG" else "📉"
            msg = (f"{dir_icon} سیگنال {trade['direction']} بسته شد!\n"
                   f"ورود: {trade['entry_price']:.4f}\n"
                   f"سود/ضرر درصد: {trade['profit_pct']*100/LEVERAGE:.2f}%\n")
            send_telegram_message(msg)

# ==============================
# تابع اصلی استراتژی (کد x)
# ==============================
def get_signals(df_4h, df_5m, df_1m):
    df_4h = df_4h.sort_values("time").reset_index(drop=True)
    df_5m = df_5m.sort_values("time").reset_index(drop=True)
    df_1m = df_1m.sort_values("time").reset_index(drop=True)

    signals = []

    for idx in range(len(df_4h)-1):
        candle_prev = df_4h.iloc[idx]
        high_4h = candle_prev['high']
        low_4h = candle_prev['low']

        candle_next = df_4h.iloc[idx+1]
        start_next = candle_next['time']
        end_next = start_next + timedelta(hours=4)

        df_5m_slice = df_5m[(df_5m['time'] >= start_next) & (df_5m['time'] < end_next)].reset_index(drop=True)
        df_1m_slice_full = df_1m[(df_1m['time'] >= start_next) & (df_1m['time'] < end_next)].reset_index(drop=True)

        alert_type = None
        entry_found = False
        active_trade = None

        for i, row5m in df_5m_slice.iterrows():
            alert = check_alert(row5m, high_4h, low_4h)
            if alert and (end_next - row5m['time']).total_seconds() > 30*60:
                alert_type = alert
                alert_index = i
                break

        if alert_type is None:
            continue

        for j in range(alert_index+1, len(df_5m_slice)):
            row5m = df_5m_slice.iloc[j]
            entry_signal = check_entry(row5m, high_4h, low_4h, alert_type)
            if entry_signal:
                active_trade = open_trade(entry_signal, row5m['close'], row5m['time'])
                entry_found = True
                break

        if not active_trade:
            continue

        df_1m_slice = df_1m_slice_full[df_1m_slice_full['time'] >= active_trade['start_time']]

        for _, row1m in df_1m_slice.iterrows():
            trade_closed = False
            profit_pct = 0

            if active_trade['direction'] == "LONG":
                if row1m['high'] >= active_trade['entry_price'] * (1 + TARGET_MOVE_PRICE):
                    trade_closed = True
                    profit_pct = TARGET_MOVE_PRICE * LEVERAGE
                elif row1m['low'] <= active_trade['entry_price'] * (1 - STOP_MOVE_PRICE):
                    trade_closed = True
                    profit_pct = -STOP_MOVE_PRICE * LEVERAGE

            elif active_trade['direction'] == "SHORT":
                if row1m['low'] <= active_trade['entry_price'] * (1 - TARGET_MOVE_PRICE):
                    trade_closed = True
                    profit_pct = TARGET_MOVE_PRICE * LEVERAGE
                elif row1m['high'] >= active_trade['entry_price'] * (1 + STOP_MOVE_PRICE):
                    trade_closed = True
                    profit_pct = -STOP_MOVE_PRICE * LEVERAGE

            if trade_closed:
                active_trade['profit_pct'] = profit_pct
                active_trade['status'] = 'closed'
                signals.append(active_trade)
                break

    return signals

# ==============================
# شروع ربات
# ==============================
print("🤖 ربات آنلاین شروع شد...")
send_telegram_message("🤖 ربات وصل شد و فعال است!")

while True:
    try:
        check_and_send_signals()
        time.sleep(60)
    except Exception:
        print("FULL ERROR:")
        traceback.print_exc()
        time.sleep(30)
