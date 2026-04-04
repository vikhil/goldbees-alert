import yfinance as yf
import requests
import os

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_msg(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.get(url, params={"chat_id": CHAT_ID, "text": msg})

data = yf.download("GOLDBEES.NS", period="1d", interval="5m")

price = float(data['Close'].iloc[-1])
send_msg(f"✅ Bot is working! Current Price: ₹{price}")

print("Current Price:", price)

if 118 <= price <= 121:
    send_msg(f"🟢 BUY GoldBees @ ₹{price}")

elif price <= 115:
    send_msg(f"🔥 STRONG BUY GoldBees @ ₹{price}")

elif price >= 133:
    send_msg(f"🔴 SELL GoldBees @ ₹{price}")

else:
    print("No signal")
