import yfinance as yf
import requests
import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

LAST_SIGNAL_FILE = "last_signal.json"

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_msg(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.get(url, params={
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    })

def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ✅ Google Sheets Setup
creds_dict = json.loads(os.getenv("GOOGLE_CREDS"))

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("Trading Signals").sheet1

# ✅ Read full data
data_rows = sheet.get_all_values()

# Remove header
header = data_rows[0]
rows = data_rows[1:]

messages = []

# 🔁 MAIN LOOP
for i, row in enumerate(rows, start=2):

    try:
        ticker = row[0]
        qty = float(row[1])
        buy_price = float(row[2])
    except:
        continue

    if not ticker:
        continue

    data = yf.download(ticker, period="5d", interval="15m")

    if data.empty:
        continue

    data['RSI'] = calculate_rsi(data)
    data['EMA'] = data['Close'].ewm(span=50).mean()

    price = float(data['Close'].iloc[-1])
    rsi = float(data['RSI'].iloc[-1])
    ema = float(data['EMA'].iloc[-1])

    # 📊 P/L Calculation
    pl_percent = ((price - buy_price) / buy_price) * 100

    # 🎯 Dynamic Target
    if price > ema and rsi > 60:
        target = price * 1.06
    elif price > ema:
        target = price * 1.04
    else:
        target = price * 1.02

    # 🛑 Stop Loss (reference)
    stop_loss = buy_price * 0.98

    # ⭐ Confidence
    if price > ema and rsi > 60:
        confidence = "⭐⭐⭐"
    elif price > ema:
        confidence = "⭐⭐"
    else:
        confidence = "⭐"

    # 🧠 DECISION ENGINE

    if pl_percent < 0:
        if price < ema and rsi < 35:
            decision = "AVOID ADD ❌"
        elif price > ema and rsi > 45:
            decision = "BUY ON DIP 🟢"
        elif rsi < 30:
            decision = "BUY ON DIP (Oversold) 🟢"
        else:
            decision = "HOLD ⏳"

    elif pl_percent >= 10:
        if price > ema and rsi > 55:
            decision = "HOLD 🚀"
        else:
            decision = "BOOK PROFIT 💰"

    else:
        if price > ema:
            decision = "HOLD 👍"
        else:
            decision = "HOLD ⚠️"

    # 📊 Update Google Sheet
    sheet.update(f"D{i}:K{i}", [[
        round(target, 2),
        round(stop_loss, 2),
        confidence,
        round(price, 2),
        round(rsi, 2),
        round(ema, 2),
        round(pl_percent, 2),
        decision
    ]])

    # 📲 Telegram Alerts (important only)
    if "BUY ON DIP" in decision or "BOOK PROFIT" in decision:
        messages.append(
            f"📊 *{ticker}*\nP/L: {round(pl_percent,2)}%\n👉 {decision}"
        )

# 🔥 Limit alerts
messages = messages[:5]

# Send Telegram
if messages:
    final_msg = "🚨 *Portfolio Alerts*\n\n" + "\n\n".join(messages)
    send_msg(final_msg)
