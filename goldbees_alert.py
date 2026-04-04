import yfinance as yf
import requests
import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TICKERS = ["GOLDBEES.NS", "CANBK.NS"]  # Add more later

def send_msg(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": msg})

def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

for ticker in TICKERS:
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

    if signal != "HOLD":
        send_msg(msg)
