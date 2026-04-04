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

# ✅ Setup Google Sheets
creds_dict = json.loads(os.getenv("GOOGLE_CREDS"))

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("Trading Signals").sheet1

# ✅ Read tickers from Column A
ticker_list = sheet.col_values(1)

# Remove header if present
if ticker_list and ticker_list[0] in ["Ticker", "Input Ticker"]:
    ticker_list = ticker_list[1:]

# ✅ Load last signals
try:
    with open(LAST_SIGNAL_FILE, "r") as f:
        last_signals = json.load(f)
except:
    last_signals = {}

# ✅ Store messages
messages = []

# 🔁 Main Loop
for i, ticker in enumerate(ticker_list, start=2):
    if not ticker.strip():
        continue

    data = yf.download(ticker, period="5d", interval="15m")

    if data.empty:
        continue

    data['RSI'] = calculate_rsi(data)
    price = float(data['Close'].iloc[-1])
    rsi = float(data['RSI'].iloc[-1])

    signal = "HOLD"

    # SMART LOGIC
    if rsi < 30:
        signal = "STRONG BUY"
    elif 30 <= rsi <= 40:
        signal = "BUY"
    elif rsi > 70:
        signal = "SELL"

    # Check previous signal
    prev_signal = last_signals.get(ticker)

    if signal != prev_signal:
        # Update same row in sheet
        sheet.update(f"B{i}:F{i}", [[
            str(pd.Timestamp.now()),
            ticker,
            round(price, 2),
            round(rsi, 2),
            signal
        ]])

        # Collect Telegram messages (only BUY/SELL)
        if signal != "HOLD":
            messages.append(f"📊 {ticker} → {signal} @ ₹{round(price,2)}")

        # Update last signal
        last_signals[ticker] = signal

# ✅ Send ONE combined message
if messages:
    final_msg = "🚨 *Trading Alerts*\n\n" + "\n".join(messages)
    send_msg(final_msg)

# ✅ Save signals
with open(LAST_SIGNAL_FILE, "w") as f:
    json.dump(last_signals, f)
