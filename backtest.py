import yfinance as yf
import pandas as pd

ticker = "GOLDBEES.NS"

data = yf.download(ticker, period="6mo", interval="1d")

# Indicators
data['EMA50'] = data['Close'].ewm(span=50).mean()

delta = data['Close'].diff()
gain = (delta.where(delta > 0, 0)).rolling(14).mean()
loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
rs = gain / loss
data['RSI'] = 100 - (100 / (1 + rs))

position = None
buy_price = 0
profits = []

for i in range(50, len(data)):

    price = float(data['Close'].iloc[i])
    rsi = float(data['RSI'].iloc[i])
    ema = float(data['EMA50'].iloc[i])

    # BUY
    if position is None:
        if rsi < 40 and price > ema:
            position = "BUY"
            buy_price = price

    # SELL
    elif position == "BUY":
        if rsi > 70 or price < ema:
            profit = price - buy_price
            profits.append(profit)
            position = None

# RESULTS
total_trades = len(profits)
wins = len([p for p in profits if p > 0])
win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
total_profit = sum(profits)

print("Total Trades:", total_trades)
print("Win Rate:", round(win_rate, 2), "%")
print("Total Profit:", round(total_profit, 2))
