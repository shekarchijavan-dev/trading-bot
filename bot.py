import requests
import asyncio
from telegram import Bot
from flask import Flask
import threading
from datetime import datetime

app = Flask(__name__)

TOKEN = "8641335650:AAHBn5i6xShvQg4ljtjealgLlCqvf0YGSeE"

@app.route('/')
def home():
    return "Bot is running!"

def get_all_symbols():
    url = "https://api.toobit.com/quote/v1/ticker/bookTicker"
    response = requests.get(url)
    data = response.json()
    symbols = [item["s"] for item in data if item["s"].endswith("USDT")]
    return symbols

def calculate_rsi(closes, period=14):
    if len(closes) < period + 1:
        return []
    gains = []
    losses = []
    for i in range(1, len(closes)):
        change = closes[i] - closes[i-1]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    rsi_values = []
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        rsi = 100
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    rsi_values.append(rsi)
    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        if avg_loss == 0:
            rsi = 100
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
        rsi_values.append(rsi)
    return rsi_values

def check_divergence(symbol):
    try:
        url = "https://api.toobit.com/quote/v1/klines"
        params = {"symbol": symbol, "interval": "5m", "limit": 100}
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        
        if len(data) < 30:
            return None
        
        closes = [float(c[4]) for c in data]
        times = [int(c[0]) for c in data]
        rsi = calculate_rsi(closes, 14)
        
        min_len = min(len(closes), len(rsi), len(times))
        closes = closes[-min_len:]
        times = times[-min_len:]
        rsi = rsi[-min_len:]
        
        pivots_low = []
        pivots_high = []
        
        for i in range(2, len(closes) - 2):
            if closes[i] == min(closes[i-2:i+3]):
                pivots_low.append(i)
            if closes[i] == max(closes[i-2:i+3]):
                pivots_high.append(i)
        
        last_time = times[-1]
        last_idx = len(closes) - 1
        max_age_ms = 1 * 5 * 60 * 1000  # فقط ۵ دقیقه اخیر
        
        # صعودی
        for i in range(len(pivots_low) - 1):
            idx1 = pivots_low[i]
            idx2 = pivots_low[i + 1]
            age = last_time - times[idx2]
            
            if 0 <= age <= max_age_ms and idx2 >= last_idx - 1:
                if closes[idx2] < closes[idx1] and rsi[idx2] > rsi[idx1]:
                    t1 = datetime.fromtimestamp(times[idx1]/1000).strftime('%H:%M')
                    t2 = datetime.fromtimestamp(times[idx2]/1000).strftime('%H:%M')
                    return {
                        "type": "صعودی 📈",
                        "price": closes[-1],
                        "rsi": rsi[-1],
                        "p1_time": t1,
                        "p1_price": closes[idx1],
                        "p1_rsi": rsi[idx1],
                        "p2_time": t2,
                        "p2_price": closes[idx2],
                        "p2_rsi": rsi[idx2]
                    }
        
        # نزولی
        for i in range(len(pivots_high) - 1):
            idx1 = pivots_high[i]
            idx2 = pivots_high[i + 1]
            age = last_time - times[idx2]
            
            if 0 <= age <= max_age_ms and idx2 >= last_idx - 1:
                if closes[idx2] > closes[idx1] and rsi[idx2] < rsi[idx1]:
                    t1 = datetime.fromtimestamp(times[idx1]/1000).strftime('%H:%M')
                    t2 = datetime.fromtimestamp(times[idx2]/1000).strftime('%H:%M')
                    return {
                        "type": "نزولی 📉",
                        "price": closes[-1],
                        "rsi": rsi[-1],
                        "p1_time": t1,
                        "p1_price": closes[idx1],
                        "p1_rsi": rsi[idx1],
                        "p2_time": t2,
                        "p2_price": closes[idx2],
                        "p2_rsi": rsi[idx2]
                    }
    except:
        pass
    return None

async def bot_loop():
    bot = Bot(TOKEN)
    symbols = get_all_symbols()[:200]
    sent_signals = set()
    test_sent = False
    
    while True:
        try:
            updates = await bot.get_updates()
            if updates:
                chat_id = updates[-1].message.chat_id
                
                if not test_sent:
                    await bot.send_message(chat_id=chat_id, text="✅ ربات واگرایی فعال شد!")
                    test_sent = True
                
                for symbol in symbols:
                    signal = check_divergence(symbol)
                    if signal:
                        key = f"{symbol}_{signal['type']}_{signal['p2_time']}"
                        if key not in sent_signals:
                            sent_signals.add(key)
                            
                            message = f"🚨 **واگرایی {signal['type']}**\n\n"
                            message += f"📊 {symbol}\n"
                            message += f"💰 قیمت الان: {signal['price']}\n"
                            message += f"📊 RSI الان: {signal['rsi']:.2f}\n\n"
                            message += f"📍 نقطه ۱: {signal['p1_time']}\n"
                            message += f"   قیمت: {signal['p1_price']:.6f} | RSI: {signal['p1_rsi']:.2f}\n\n"
                            message += f"📍 نقطه ۲: {signal['p2_time']}\n"
                            message += f"   قیمت: {signal['p2_price']:.6f} | RSI: {signal['p2_rsi']:.2f}\n"
                            
                            await bot.send_message(chat_id=chat_id, text=message)
                            print(f"✅ سیگنال: {symbol}")
            
            await asyncio.sleep(300)
            
        except Exception as e:
            print(f"❌ خطا: {e}")
            await asyncio.sleep(300)

def run():
    asyncio.run(bot_loop())

threading.Thread(target=run, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
