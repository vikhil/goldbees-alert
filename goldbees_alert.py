import yfinance as yf
import requests
import os
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from datetime import datetime
import pytz
from gspread_formatting import format_cell_ranges, CellFormat, Color
import math

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

# ===================== COLOR FUNCTION =====================
def get_color(decision):
    if "BUY" in decision or "BREAKOUT" in decision:
        return {"red": 0.8, "green": 1, "blue": 0.8}   # Light Green
    elif "PROFIT" in decision or "EXIT" in decision:
        return {"red": 1, "green": 0.8, "blue": 0.8}   # Light Red
    elif "HOLD" in decision:
        return {"red": 1, "green": 1, "blue": 0.6}     # Yellow
    else:
        return {"red": 0.9, "green": 0.9, "blue": 0.9} # Grey
        
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

format_requests = []

print("Script started")

total_invested = 0
total_value = 0

# ===================== MAIN LOOP =====================
for i, row in enumerate(data_rows, start=2):
    
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
        try:
            qty = float(row[1]) if row[1] else 0
            buy_price = float(row[2]) if row[2] else price
        except:
            qty = 0
            buy_price = price
            
        # ================= YAHOO DATA =================
        try:
            data = yf.download(ticker, period="1d", interval="5m", progress=False, group_by='column')

            if data is None or data.empty:
                invalid_tickers.append(ticker)
                continue

            # FIX: flatten multi-level columns
            if isinstance(data.columns, pd.MultiIndex):
                data.columns = data.columns.get_level_values(0)

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
        price = data['Close'].iloc[-1].item()
        rsi = safe_float(data['RSI'].iloc[-1])
        ema50 = safe_float(data['EMA50'].iloc[-1])
        ema20 = safe_float(data['EMA20'].iloc[-1])
        volume = safe_float(data['Volume'].iloc[-1])
        vol_avg = safe_float(data['VOL_AVG'].iloc[-1])
        recent_high = data['High'].rolling(20).max().iloc[-2].item()
        vwap = safe_float(data['VWAP'].iloc[-1])  
        
        adx_val = data['ADX'].iloc[-1]
       # adx = float(adx_val) if pd.notna(adx_val) else 0
        adx = safe_float(data['ADX'].iloc[-1])

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
    
        # ===== FINAL RANK =====
        if score >= 7:
            rank = "🔥 Strong Buy"
        elif score >= 5:
            rank = "👍 Good"
        elif score >= 3:
            rank = "⚠️ Weak"
        else:
            rank = "❌ Avoid"

        # ================= P/L =================
        if buy_price > 0:
            pl_percent = ((price - buy_price) / buy_price) * 100
        else:
            pl_percent = 0

        total_invested += qty * buy_price
        total_value += qty * price

        # ================= TARGET / SL =================
        if price > ema50 and rsi > 60:
            target = price * 1.06
        elif price > ema50:
            target = price * 1.04
        else:
            target = price * 1.02

        stop_loss = buy_price * 0.98
        trail_stop = price * 0.97
    
        # ================= CONFIDENCE =================
        if price > ema50 and rsi > 60 and volume > vol_avg:
            confidence = "⭐⭐⭐"
        elif price > ema50:
            confidence = "⭐⭐"
        else:
            confidence = "⭐"

        # ================= DECISION =================
        decision = "HOLD"
    
        if market_trend == "BEARISH":
            decision = "⛔ NO TRADE (Market Weak)"
            if pl_percent >= 10:
                decision = "BOOK PROFIT 💰"
        
        if price > recent_high and volume > vol_avg and adx > 20:
            decision = "🚀 BUY BREAKOUT"
        elif pl_percent < 0:
            if price < ema50 and rsi < 35:
                decision = "❌ AVOID ADD"
            elif price > ema50 and rsi > 45 and price > vwap:
                decision = "🟢 BUY ON DIP"
            else:
                decision = "⏳ HOLD"
                
        elif pl_percent >= 10:
            decision = "💰 BOOK PROFIT"
            
        elif price < trail_stop and pl_percent > 5:
            decision = "🔻 TRAIL STOP EXIT"
        else:
            decision = "⏳ HOLD"
    
        print(ticker, "Score:", score, "RSI:", rsi, "ADX:", adx, "Decision:", decision)

        # ================= ALLOCATION =================
        if "BREAKOUT" in decision:
            allocation_pct = 0.20
        elif "Strong" in rank:
            allocation_pct = 0.15
        elif "BUY ON DIP" in decision:
            allocation_pct = 0.10
        else:
            allocation_pct = 0.0
    
        if pl_percent < -15:
            allocation_pct += 0.05
    
        buy_amount = PROFIT_POOL * allocation_pct
        buy_qty = int(buy_amount / price) if price > 0 else 0
    
        if "AVOID" in decision:
            buy_qty = 0

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
                rank,
                confidence,
                safe_round(price),
                safe_round(rsi),
                safe_round(ema50),
                safe_round(pl_percent),
                decision,
                f"{int(allocation_pct*100)}%",
                buy_qty
            ]
        })
        # ===================== COLOR TRACK =====================
        row_color = get_color(decision)

        format_requests.append({
            "range": f"M{actual_row}",
            "format": {
                "backgroundColor": row_color
            }
        })
        # ================= TELEGRAM =================
        # if ("BUY" in decision or "PROFIT" in decision) and rank in ["🔥 Strong Buy", "👍 Good"]:
        if "BUY" in decision or "PROFIT" in decision:
            messages.append(
                f"📊 *{ticker}*\n"
                f"P/L: {round(pl_percent,2)}%\n"
                f"👉 {decision}\n"
                f"⭐ {rank}"
            )
    except Exception as e:
        print(f"Main loop error at row {i}: {e}")
        continue

# print("Updates count:", len(updates))
# print("Messages count:", len(messages))
print(f"Updates count: {len(updates)}")
print(f"Messages count: {len(messages)}")

 # ===================== APPLY COLORS =====================
        #from gspread_formatting import format_cell_ranges, CellFormat, Color
        
        if format_requests:
            print(f"Applying colors to {len(format_requests)} rows...")
            try:
                formatted_ranges = []

                for req in format_requests:
                    r = req["range"]
                    c = req["format"]["backgroundColor"]

                    formatted_ranges.append((
                        r,
                        CellFormat(
                            backgroundColor=Color(c["red"], c["green"], c["blue"])
                        )
                    ))

                format_cell_ranges(sheet, formatted_ranges)

                print("✅ Color formatting applied")

            except Exception as e:
                print("❌ Color formatting failed:", e)

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
required_cols = 14  # A to N
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
        "range": f"D{u['row']}:O{u['row']}",
# "values": [u["data"]]
        "values": [[safe_float(x) if isinstance(x, (int, float)) else x for x in u["data"]]]
    })

if batch_data:
    print(f"Updating {len(batch_data)} rows in Google Sheet...")

    try:
        sheet.batch_update([
            {
                "range": item["range"],
                "values": item["values"]
            }
            for item in batch_data
        ])

        print("✅ Sheet update successful")

    except Exception as e:
        print("❌ Google Sheets batch update failed:", e)

# ===================== SUMMARY =====================
if total_invested > 0:
    portfolio_pl = ((total_value - total_invested) / total_invested) * 100
    messages.append(f"\n📊 *Portfolio P/L:* {round(portfolio_pl,2)}%")

if invalid_tickers:
    messages.append(f"⚠️ Invalid tickers: {', '.join(invalid_tickers)}")

if not messages:
    messages.append("No strong signals right now 📊")

try:
    send_msg("🚨 *Portfolio Alerts*\n\n" + "\n\n".join(messages))
except Exception as e:
    print("Final Telegram send failed:", e)
