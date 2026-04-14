import yfinance as yf
import requests
import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
"^NSEI"

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

BASE_CAPITAL = 100000   # Your capital
PROFIT_POOL = 0         # Tracks booked profit

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

# Google Sheets Setup
creds_dict = json.loads(os.getenv("GOOGLE_CREDS"))

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("Trading Signals").sheet1

data_rows = sheet.get_all_values()
rows = data_rows[1:]
# 📊 NIFTY MARKET TREND
nifty_data = yf.download("^NSEI", period="5d", interval="15m")

nifty_data['EMA50'] = nifty_data['Close'].ewm(span=50).mean()

nifty_price = float(nifty_data['Close'].iloc[-1].item())
nifty_ema = float(nifty_data['EMA50'].iloc[-1].item())

# 🧠 Market Trend
if nifty_price > nifty_ema:
    market_trend = "BULLISH"
else:
    market_trend = "BEARISH"

messages = []

# Portfolio tracking
total_invested = 0
total_value = 0

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

    # Indicators
    data['RSI'] = calculate_rsi(data)
    data['EMA50'] = data['Close'].ewm(span=50).mean()
    data['EMA20'] = data['Close'].ewm(span=20).mean()
    data['VOL_AVG'] = data['Volume'].rolling(window=20).mean()

    price = float(data['Close'].iloc[-1].item())
    rsi = float(data['RSI'].iloc[-1].item())
    ema50 = float(data['EMA50'].iloc[-1].item())
    ema20 = float(data['EMA20'].iloc[-1].item())
    volume = float(data['Volume'].iloc[-1].item())
    vol_avg = float(data['VOL_AVG'].iloc[-1].item())
    
    recent_high = float(data['High'].rolling(window=20).max().iloc[-2])

    # Portfolio calc
    pl_percent = ((price - buy_price) / buy_price) * 100
    total_invested += qty * buy_price
    total_value += qty * price

    # Target Logic
    if price > ema50 and rsi > 60:
        target = price * 1.06
    elif price > ema50:
        target = price * 1.04
    else:
        target = price * 1.02

    # Stop Loss
    stop_loss = buy_price * 0.98

    # Confidence
    if price > ema50 and rsi > 60 and volume > vol_avg:
        confidence = "⭐⭐⭐"
    elif price > ema50:
        confidence = "⭐⭐"
    else:
        confidence = "⭐"

    # Decision Engine
    # decision = "HOLD"
    
    # 🚫 MARKET FILTER (VERY IMPORTANT)
    if market_trend == "BEARISH":
        if pl_percent >= 10:
            decision = "BOOK PROFIT 💰"
        else:
            decision = "HOLD ❌ (Market Weak)"
        
    # Breakout
    if price > recent_high:
        decision = "BUY BREAKOUT 🚀"

    elif pl_percent < 0:
        if price < ema50 and rsi < 35:
            decision = "AVOID ADD ❌"
        elif price > ema50 and rsi > 45 and volume > vol_avg:
            decision = "BUY ON DIP 🟢 (Strong)"
        elif rsi < 30:
            decision = "BUY ON DIP 🟢 (Oversold)"
        else:
            decision = "HOLD ⏳"

    elif pl_percent >= 10:
        if price > ema50 and rsi > 55:
            decision = "HOLD 🚀"
        else:
            decision = "BOOK PROFIT 💰"
            
            # 💰 ADD THIS LINE
            profit = (price - buy_price) * qty
            PROFIT_POOL += profit

    else:
        if price > ema50:
            decision = "HOLD 👍"
        else:
            decision = "HOLD ⚠️"

    # 💰 SMART ALLOCATION (NEW)

    if "BREAKOUT" in decision:
        allocation_pct = 0.20

    elif "Strong" in decision:
        allocation_pct = 0.15

    elif "BUY ON DIP" in decision:
        allocation_pct = 0.10

    else:
        allocation_pct = 0.0


    # 🔻 LOSS BOOST (ADD THIS JUST BELOW 👇)

    if pl_percent < -15:
        allocation_pct += 0.05
    elif pl_percent < -10:
        allocation_pct += 0.03

    # 🧮 CALCULATE BUY AMOUNT
    TOTAL_CAPITAL = 100000  # Change as per your budget
    usable_capital = max(PROFIT_POOL, 0)
    buy_amount = usable_capital * allocation_pct
    usable_capital = min(PROFIT_POOL, BASE_CAPITAL * 0.3)
    
    # 📦 CALCULATE BUY QUANTITY
    if price > 0:
        buy_qty = int(buy_amount / price)
    else:
        buy_qty = 0

    # 🛑 SAFETY FILTER (VERY IMPORTANT)
    if "AVOID" in decision or price < ema50:
        buy_qty = 0
    
    # Update Google Sheet (D to L)
    sheet.update(f"D{i}:M{i}", [[
        round(target, 2),
        round(stop_loss, 2),
        confidence,
        round(price, 2),
        round(rsi, 2),
        round(ema50, 2),
        round(pl_percent, 2),
        decision,
        f"{int(allocation_pct*100)}%",
        buy_qty
    ]])
    # Telegram alerts
    if "BUY" in decision or "PROFIT" in decision:
        messages.append(
            f"📊 *{ticker}*\n"
            f"P/L: {round(pl_percent,2)}%\n"
            f"👉 {decision}\n"
            f"💰 Allocation: {int(allocation_pct*100)}%\n"
            f"📦 Buy Qty: {buy_qty}\n"
            f"📈 Market: {market_trend}"
)
        
# Portfolio Summary
if total_invested > 0:
    portfolio_pl = ((total_value - total_invested) / total_invested) * 100
    messages.append(f"\n📊 *Portfolio P/L:* {round(portfolio_pl,2)}%")

# Limit alerts
messages = messages[:5]

# 🧪 If no signals, send default message
if not messages:
    messages.append("No strong signals right now 📊")

# 🚀 Send Telegram (forced for testing)
if messages:
    final_msg = "🚨 *Portfolio Alerts*\n\n" + "\n\n".join(messages)
    send_msg(final_msg)
