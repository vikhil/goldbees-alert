import yfinance as yf
import requests
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

STATE_FILE = "last_signal.txt"

def send_msg(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": msg})

def get_last_signal():
    try:
        with open(STATE_FILE, "r") as f:
            return f.read().strip()
    except:
        return ""

def save_signal(signal):
    with open(STATE_FILE, "w") as f:
        f.write(signal)

data = yf.download("GOLDBEES.NS", period="1d", interval="5m")
price = float(data['Close'].iloc[-1])

signal = "HOLD"

if 118 <= price <= 121:
    signal = "BUY"
elif price <= 115:
    signal = "STRONG BUY"
elif price >= 133:
    signal = "SELL"

last_signal = get_last_signal()

if signal != last_signal:
    send_msg(f"📊 GoldBees Signal: {signal} @ ₹{price}")
    save_signal(signal)
else:
    print("No new signal")
