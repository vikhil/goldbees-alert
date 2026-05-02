import yfinance as yf
import requests
import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime
import pytz
#from gspread_formatting import format_cell_ranges, CellFormat, Color
import math
import time

# ===================== PRE-MARKET REPORT =====================
def send_premarket_report():
    try:
        import requests
        from datetime import datetime
        import pytz

        IST = pytz.timezone("Asia/Kolkata")
        today = datetime.now(IST).weekday()  # Monday = 0
        
        url = "https://www.nseindia.com/api/market-data-pre-open?key=ALL"

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept-Language": "en-US,en;q=0.9"
        }

        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers)  # important

        response = session.get(url, headers=headers)
        data = response.json()

        stocks = data.get('data', [])

        upper_circuit = []
        lower_circuit = []
        flat_open = []

        for stock in stocks:
            try:
                info = stock['metadata']
                symbol = info['symbol']
                change = float(info['pChange'])  # % change
    
                if change >= 5:
                    upper_circuit.append(symbol)
                elif change <= -5:
                    lower_circuit.append(symbol)
                elif -0.2 <= change <= 0.2:
                    flat_open.append(symbol)
    
            except:
                continue
        # ================= MESSAGE =================
        if today == 0:
            # MONDAY → SUMMARY
            msg = (
                "📊 *Pre-Market Weekly Snapshot*\n\n"
                f"🟢 Upper Circuit: {len(upper_circuit)}\n"
                f"🔴 Lower Circuit: {len(lower_circuit)}\n"
                f"⚖️ Flat Open: {len(flat_open)}"
            )
        else:
            # DAILY → FULL LIST
            msg = "*📊 Pre-Market Movers*\n\n"

            msg += f"🟢 Upper Circuit ({len(upper_circuit)}):\n"
            msg += ", ".join(upper_circuit[:25]) + "\n\n"

            msg += f"🔴 Lower Circuit ({len(lower_circuit)}):\n"
            msg += ", ".join(lower_circuit[:25]) + "\n\n"

            msg += f"⚖️ Flat Open ({len(flat_open)}):\n"
            msg += ", ".join(flat_open[:25])

        send_msg(msg)

    except Exception as e:
        print("Pre-market fetch failed:", e)
        
def safe_float(x):
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return 0.0
        return float(x)
    except:
        return 0.0

def safe_round(x):
    return round(safe_float(x), 2)
    
round = __builtins__.round

IST = pytz.timezone("Asia/Kolkata")
current_time = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    
# ===================== CONFIG =====================
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
print("TOKEN:", TOKEN)
print("CHAT_ID:", CHAT_ID)

BASE_CAPITAL = 100000
PROFIT_POOL = BASE_CAPITAL * 0.2

SECTOR_MAP = {
    "ICICIBANK.NS": "BANKING",
    "KOTAKBANK.NS": "BANKING",
    "YESBANK.NS": "BANKING",
    "SBIN.NS": "BANKING",

    "TCS.NS": "IT",
    "INFY.NS": "IT",

    "NATCOPHARM.NS": "PHARMA",
    "CIPLA.NS": "PHARMA",

    "COALINDIA.NS": "ENERGY",
    "NTPC.NS": "ENERGY",

    "TITAN.NS": "CONSUMPTION",
    "VBL.NS": "CONSUMPTION",

    "ADANIENT.NS": "INFRA",
    "RVNL.NS": "INFRA",
}

# ===================== TELEGRAM =====================
def send_msg(message_text):
    if not TOKEN or not CHAT_ID:
        print("Missing Telegram credentials")
        return

    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        res = requests.get(url, params={
            "chat_id": CHAT_ID,
            "text": message_text,
            "parse_mode": "Markdown"
        }, timeout=10)

        if res.status_code == 429:
            retry_after = res.json().get("parameters", {}).get("retry_after", 5)
            print(f"Rate limited. Retrying after {retry_after}s")
            time.sleep(retry_after)
            return send_msg(message_text)
            
        print("Telegram response:", res.status_code)

        if res.status_code != 200:
            print("Telegram error:", res.text)

    except Exception as e:
        print("Telegram exception:", e)
    
# ===================== RSI =====================
def calculate_rsi(data, period=14):
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

# ===================== SAFE FLOAT =====================
#def safe_float(val):
 #   try:
  #      if pd.isna(val):
   #         return 0
    #    if val == float("inf") or val == float("-inf"):
     #       return 0
      #  return float(val)
    #except:
     #   return 0
# ===================== TICKER CLEANER =====================
def format_ticker(ticker):
    ticker = str(ticker).strip().upper()
    if ticker == "" or ticker == "NAN":
        return None
    if not ticker.endswith(".NS") and not ticker.endswith(".BO"):
        ticker = ticker + ".NS"
    return ticker

# ===================== GOOGLE SHEETS =====================
creds_dict = json.loads(os.getenv("GOOGLE_CREDS"))

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open("Trading Signals").sheet1

data_rows = sheet.get_all_values()[1:]  # skip header

hour = datetime.now(IST).hour
minute = datetime.now(IST).minute

# Market time: 9:15 AM to 3:30 PM IST
# if not ((hour > 9 or (hour == 9 and minute >= 15)) and (hour < 15 or (hour == 15 and minute <= 30))):
#    send_msg("⏳ Market Closed - No update")
#    exit()

# ===================== NIFTY TREND (FIXED) =====================
nifty = yf.download("^NSEI", period="5d", interval="15m", progress=False)
nifty['EMA50'] = nifty['Close'].ewm(span=50).mean()

nifty_price = nifty['Close'].iloc[-1].item()
nifty_ema = nifty['EMA50'].iloc[-1].item()

market_trend = "BULLISH" if nifty_price > nifty_ema else "BEARISH"

# ===================== TRACKING =====================
messages = []
updates = []
invalid_tickers = []

sector_data = {}
sector_summary = []

print("Script started")

send_premarket_report()   # ✅ ADD THIS LINE HERE

total_invested = 0
total_value = 0
   
# ===================== MAIN LOOP =====================
for i, row in enumerate(data_rows, start=2):
   # time.sleep(0.2)
    
    try:
        actual_row = i
        ticker = format_ticker(row[0] if len(row) > 0 else "")
        if not ticker:
            updates.append({
                "row": actual_row,
                "data": ["", "", "❌ Invalid", "", "", "", "", "", "", "", "", ""]
            })
            continue

        # ===================== Handle empty qty/buy price gracefully =====================

        qty = safe_float(row[1]) if len(row) > 1 else 0
        buy_price = safe_float(row[2]) if len(row) > 2 else 0
        
        # ================= YAHOO DATA =================
        try:
            data = yf.download(ticker, period="5d", interval="15m", progress=False, group_by='column',threads=False)
            
            if data is None or data.empty or len(data) < 20:
                invalid_tickers.append(ticker)
                continue

            # FIX: flatten multi-level columns
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)
                
            #if data is None or data.empty:
                #invalid_tickers.append(ticker)
                #continue
            
            price = data['Close'].iloc[-1] if not data.empty else None

            if price is None or pd.isna(price):
                print(f"Skipping {ticker} due to invalid price")
                continue

        except Exception as e:
            print(f"Yahoo error for {ticker}: {e}")
            invalid_tickers.append(ticker)
            continue
    
        # ================= INDICATORS =================
        data['RSI'] = calculate_rsi(data)
        data['EMA50'] = data['Close'].ewm(span=50).mean()
        data['EMA20'] = data['Close'].ewm(span=20).mean()
        data['VOL_AVG'] = data['Volume'].rolling(20).mean()

        # ===== NEW: VWAP =====
        data['VWAP'] = (data['Volume'] * (data['High'] + data['Low'] + data['Close']) / 3).cumsum() / data['Volume'].cumsum()
        
        # ===== FIXED ADX (SAFE SINGLE COLUMN) =====
        high = data['High']
        low = data['Low']
        close = data['Close']
    
        # True Range
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs()
        ], axis=1).max(axis=1)
    
        atr = tr.rolling(14).mean()

        # Directional Movement
        plus_dm = high.diff()
        minus_dm = -low.diff()
    
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
        
        # DI
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr)
        
        # ADX
        dx = ((plus_di - minus_di).abs() / (plus_di + minus_di)) * 100
        # dx = dx.squeeze()
        data['ADX'] = dx.rolling(14).mean()
        
        # ================= VALUES =================
        #price = data['Close'].iloc[-1].item()
        price = safe_float(data['Close'].iloc[-1])
        rsi = safe_float(data['RSI'].iloc[-1])
        ema50 = safe_float(data['EMA50'].iloc[-1])
        ema20 = safe_float(data['EMA20'].iloc[-1])
        volume = safe_float(data['Volume'].iloc[-1])
        vol_avg = safe_float(data['VOL_AVG'].iloc[-1])
        recent_high = safe_float(data['High'].rolling(20).max().iloc[-2])
        vwap = safe_float(data['VWAP'].iloc[-1])  
        
        adx_val = data['ADX'].iloc[-1]
        adx = safe_float(data['ADX'].iloc[-1])
        
        # ================= TREND REGIME FILTER =================
        trend_regime_ok = (price > ema50) and (adx > 25)

        # ✅ ADD THIS BLOCK HERE
        if pd.isna(price) or pd.isna(rsi) or pd.isna(adx):
            print(f"Skipping {ticker} due to NaN values")
            continue
        
        # ================= SCORE =================
        score = 0
        if rsi > 60: score += 2
        elif rsi > 50: score += 1

        if price > ema50: score += 2
        elif price > ema20: score += 1

        if volume > vol_avg: score += 2
        if price > recent_high: score += 3

        # ===== SMART FILTERS =====
        if price > vwap:
            score += 1   # intraday strength
    
        if adx > 25:
            score += 2   # strong trend
        elif adx > 20:
            score += 1
        
        # ================= SCORE GATE =================
        #min_score_to_trade = 6
        #allow_trade = score >= min_score_to_trade

        # ===== FINAL signal_strength =====
        if score >= 9:
            signal_strength = "STRONG"
        elif score >= 6:
            signal_strength = "GOOD"
        elif score >= 3:
            signal_strength = "WEAK"
        else:
            signal_strength = "NOISE"

        # ================= P/L =================
        if buy_price > 0:
            pl_percent = ((price - buy_price) / buy_price) * 100
        else:
            pl_percent = 0
        # ================= SECTOR TRACKING =================
        sector = SECTOR_MAP.get(ticker, "OTHERS")

        if sector not in sector_data:
            sector_data[sector] = {
                "total_pl": 0,
                "count": 0
            }

        sector_data[sector]["total_pl"] += pl_percent
        sector_data[sector]["count"] += 1

        total_invested += qty * buy_price
        total_value += qty * price

        # ================= TARGET / SL =================
        if price > ema50 and rsi > 60:
            target = price * 1.06
        elif price > ema50:
            target = price * 1.04
        else:
            target = max(price * 1.02, ema50)  # prevent illogical targets

        stop_loss = buy_price * 0.98
        trail_stop = price * 0.97
    
        # ================= CONFIDENCE =================
        if price > ema50 and rsi > 60 and volume > vol_avg:
            confidence = "⭐⭐⭐"
        elif price > ema50:
            confidence = "⭐⭐"
        else:
            confidence = "⭐"

        # ===================== RISK ENGINE =====================
        #allow_trade = True
        
        # Hard loss protection
        if pl_percent < -15:
            allow_trade = False
            risk_block_reason = "HEAVY LOSS"
        
        # Score gate
        elif score < 6:
            allow_trade = False
            risk_block_reason = "LOW SCORE"
        
        # Market regime filter
        elif market_trend == "BEARISH":
            allow_trade = False
            risk_block_reason = "BEAR MARKET"
        
        # Drawdown protection (global safety)
        elif total_invested > 0 and portfolio_pl < -20:
        elif total_invested > 0 and ((total_value - total_invested) / total_invested) < -0.20:    
            allow_trade = False
            risk_block_reason = "MAX DRAWDOWN HIT"
        
        else:
            risk_block_reason = "OK"
        
        # ===================== LAYER 1: DECISION OR RISK FILTER =====================
        decision = "⏳ HOLD"
        allocation_pct = 0
        buy_qty = 0

        # ================= SCORE GATE =================
        #allow_trade = score >= 6   # define score gate here
        allow_trade = (score >= 6) and (pl_percent > -15)

        # ================= TREND REGIME FILTER =================
        trend_regime_ok = (market_trend == "BULLISH")

        # ================= MAX DRAWDOWN CONTROL =================
        allow_new_trades = True
        max_drawdown_limit = -20
        
        if total_invested > 0 and portfolio_pl < max_drawdown_limit:
            allow_new_trades = False
        
        # ================= RISK + SCORE GATE CHECK =================
        # BLOCKED PATH
        #if not allow_trade:
            #decision = f"⛔ BLOCKED ({risk_block_reason})"

        # ================= FINAL TRADE LOGIC =================
        if pl_percent < -15:
            decision = "⛔ BLOCKED (Heavy Loss)"
        
        elif not allow_new_trades:
            decision = "⛔ DRAWDOWN LOCK - NO TRADE"
        
        elif not allow_trade:
            decision = "❌ LOW SCORE - NO TRADE"
        
        elif market_trend == "BEARISH":
            decision = "⛔ NO TRADE (Market Weak)"
        
        elif pl_percent >= 10:
            decision = "BOOK PROFIT 💰"
        
        elif trend_regime_ok and price > recent_high and volume > vol_avg:
            decision = "🚀 BUY BREAKOUT"
        
        elif price > ema50 and rsi > 45 and price > vwap and pl_percent < 0:
            decision = "🟢 BUY ON DIP"
        
        elif price < trail_stop and pl_percent > 5:
            decision = "🔻 TRAIL STOP EXIT"
        
        else:
            decision = "⏳ HOLD"
        
        print(ticker, "Score:", score, "RSI:", rsi, "ADX:", adx, "Decision:", decision)

        # ===================== LAYER 3: ALLOCATION OR POSITION SIZING =====================
        if decision == "🚀 BUY BREAKOUT":
            allocation_pct = 0.20
        
        elif decision == "🟢 BUY ON DIP":
            allocation_pct = 0.10
        
        elif decision == "💰 BOOK PROFIT":
            allocation_pct = 0.0
        
        #elif decision == "⛔ NO TRADE (Market Weak)":
            #allocation_pct = 0.0

        #elif decision == "⛔ BLOCKED (Heavy Loss)":
            #allocation_pct = 0.0

        else:
            allocation_pct = 0.0
        
        # 🚫 final safety override
        #if "BLOCKED" in decision or "STOP ADDING" in decision:
            #allocation_pct = 0
    
        buy_amount = PROFIT_POOL * allocation_pct
        buy_qty = int(buy_amount / price) if price > 0 else 0
    
        #if "AVOID" in decision:
            #buy_qty = 0

        # ================= STORE ROW =================
        # status = "HOLDING" if qty > 0 else "WATCHLIST"
        # safe_round = lambda x: round(safe_float(x), 2)
        print("CHECK ROUND:", round(10.456, 2))
        updates.append({
            "row": actual_row,
            "data": [
                current_time,
                safe_round(target),
                safe_round(stop_loss),
                signal_strength,
                confidence,
                safe_round(price),
                safe_round(rsi),
                safe_round(ema50),
                safe_round(pl_percent),
                decision,
                f"{int(allocation_pct*100)}%",
                buy_qty,
                #sector
            ]
        })
        
        # ================= TELEGRAM =================
        # if ("BUY" in decision or "PROFIT" in decision) and signal_strength in ["🔥 Strong Buy", "👍 Good"]:
        if decision in ["🚀 BUY BREAKOUT", "🟢 BUY ON DIP", "BOOK PROFIT 💰"]:
            messages.append(
                f"📊 *{ticker}*\n"
                f"P/L: {round(pl_percent,2)}%\n"
                f"👉 {decision}\n"
                f"⭐ {signal_strength}"
            )
    except Exception as e:
        print(f"Main loop error at row {i}: {e}")
        continue

# print("Updates count:", len(updates))
# print("Messages count:", len(messages))
print(f"Updates count: {len(updates)}")
print(f"Messages count: {len(messages)}")

sector_summary = []

for sector, data in sector_data.items():
    avg_pl = data["total_pl"] / data["count"] if data["count"] > 0 else 0

    if avg_pl > 3:
        status = "🔥 Strong"
    elif avg_pl > 0:
        status = "👍 Positive"
    elif avg_pl > -3:
        status = "⚠️ Neutral"
    else:
        status = "🔻 Weak"

    sector_summary.append((sector, avg_pl, status))

sector_summary.sort(key=lambda x: x[1], reverse=True)

# ===================== TELEGRAM SECTOR SUMMARY =====================

sector_msg = "\n📊 *Sector Summary:*\n"

if sector_summary:
    for sec, pl, status in sector_summary:
        sector_msg += f"{sec}: {round(pl,2)}% {status}\n"
else:
    sector_msg += "No sector data available\n"

messages.append(sector_msg)

# ✅ ADD HERE (Telegram fix)
#if messages:
 #   message_text = "\n".join(messages)
  #  send_msg(message_text)
#else:
 #   print("No messages to send to Telegram")

# --- GOOGLE SHEETS UPDATE ---    
# print("Sending batch update to Google Sheets...")
# sheet.update(full_data)

# ===================== GOOGLE SHEETS (ROW SAFE BATCH UPDATE) =====================

batch_data = []

# ===================== BULK SHEET UPDATE =====================

# Get full sheet again (including header)
full_data = sheet.get_all_values(value_render_option="UNFORMATTED_VALUE")

# Ensure enough columns exist
required_cols = 15  # A to N
# required_cols = 16  # A to P
for r in range(len(full_data)):
    if len(full_data[r]) < required_cols:
        full_data[r].extend([""] * (required_cols - len(full_data[r])))

# Apply updates in memory
for u in updates:
    row_idx = u["row"] - 1  # zero-based index

    # ✅ Ensure row exists
    while len(full_data) <= row_idx:
        full_data.append([""] * required_cols)
        
    for col_offset, value in enumerate(u["data"]):
    # required_length = 3 + col_offset + 1
        col_idx = 3 + col_offset  # Column D = index 3
        
        # ✅ Ensure row has enough columns
        while len(full_data[row_idx]) <= col_idx:
            full_data[row_idx].append("")
        
        # ✅ Assign value
        # full_data[row_idx][3 + col_offset] = value   # Column D = index 3
        full_data[row_idx][col_idx] = value

# Push everything in ONE API call
for u in updates:
    batch_data.append({
        "range": f"D{u['row']}:P{u['row']}",
# "values": [u["data"]]
        "values": [[safe_float(x) if isinstance(x, (int, float)) else x for x in u["data"]]]
    })

if batch_data:
    print(f"Updating {len(batch_data)} rows in Google Sheet...")

    try:
        #sheet.batch_update([
            #{
               # "range": item["range"],
               # "values": item["values"]
            #}
            #for item in batch_data
        #])
        cell_updates = []

        for u in updates:
            row = u["row"]
            values = u["data"]
        
            for idx, val in enumerate(values):
                col = chr(68 + idx)  # D = 68 ASCII
                cell_updates.append({
                    "range": f"{col}{row}",
                    "values": [[val]]
                })
        if cell_updates:
            sheet.batch_update(cell_updates)
            print("✅ Sheet update successful")
        else:
            print("No updates to push")
            
    except Exception as e:
        print("❌ Google Sheets batch update failed:", e)

# ===================== SUMMARY =====================
if total_invested > 0:
    portfolio_pl = ((total_value - total_invested) / total_invested) * 100
else:
    portfolio_pl = 0
    
messages.append(f"\n📊 *Portfolio P/L:* {round(portfolio_pl,2)}%")

# ================= MAX DRAWDOWN CONTROL =================
max_drawdown_limit = -20  # %
allow_new_trades = True

if total_invested > 0 and portfolio_pl < max_drawdown_limit:
    allow_new_trades = False

if invalid_tickers:
    messages.append(f"⚠️ Invalid tickers: {', '.join(invalid_tickers)}")

# Always ensure portfolio summary exists
if len(messages) == 0:
    messages = ["No strong signals right now 📊"]

# Always append portfolio P/L last
messages.append(f"\n📊 *Portfolio P/L:* {round(portfolio_pl,2)}%")

#if not messages:
    #messages.append("No strong signals right now 📊")

# ===================== TELEGRAM =====================
try:
    #send_msg("🚨 *Portfolio Alerts*\n\n" + "\n\n".join(messages))
    if messages:
        final_message = "🚨 *Portfolio Alerts*\n\n" + "\n\n".join(messages)

        # Telegram max limit safety (4096 chars)
        if len(final_message) > 4000:
            final_message = final_message[:4000]

        send_msg(final_message)
    else:
        print("No messages to send")
except Exception as e:
    print("Final Telegram send failed:", e)
    
