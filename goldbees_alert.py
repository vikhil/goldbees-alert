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
    requests.get(url, params={"chat_id": CHAT_ID, "text": msg})

def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ✅ Setup Google Sheets ONCE
creds_dict = json.loads(os.getenv("GOOGLE_CREDS"))

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("Trading Signals").sheet1

ticker_list = sheet.col_values(1)  # Column A

# Remove header if present
if ticker_list[0] == "Ticker":
    ticker_list = ticker_list[1:]

# ✅ Load last signals
try:
    with open(LAST_SIGNAL_FILE, "r") as f:
        last_signals = json.load(f)
except:
    last_signals = {}

# 🔁 Main Loop
for i, ticker in enumerate(ticker_list, start=2):
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

    msg = f"""    
📊 {ticker}
Price: ₹{round(price,2)}
RSI: {round(rsi,2)}
Signal: {signal}
"""

    # ✅ Check previous signal
    prev_signal = last_signals.get(ticker)

    if signal != prev_signal:
        # Save to Google Sheet
        sheet.update(f"B{i}:F{i}", [[
            str(pd.Timestamp.now()),
            ticker,
            round(price, 2),
            round(rsi, 2),
            signal
        ]])

        # Send alert only if BUY/SELL
        if signal != "HOLD":
            send_msg(msg)

        # Update last signal
        last_signals[ticker] = signal

# ✅ Save updated signals (VERY IMPORTANT)
with open(LAST_SIGNAL_FILE, "w") as f:
    json.dump(last_signals, f)
