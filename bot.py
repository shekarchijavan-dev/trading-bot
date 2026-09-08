import requests
import asyncio
from telegram import Bot
from telegram.request import HTTPXRequest
from flask import Flask
import threading
import time

app = Flask(__name__)

TOKEN = "8641335650:AAHBn5i6xShvQg4ljtjealgLlCqvf0YGSeE"
PROXY_URL = "http://157.180.69.178:8080"

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

def find_divergence_details(closes, rsi_values, max_distance=30):
    if len(closes) < 5 or len(rsi_values) < 5:
        return None
    pivots_low = []
    pivots_high = []
    for i in range(2, len(closes) - 2):
        if closes[i] == min(closes[i-2:i+3]):
            pivots_low.append(i)
        if closes[i] == max(closes[i-2:i+3]):
            pivots_high.append(i)
    for i in range(len(pivots_low) - 1):
        idx1 = pivots_low[i]
        idx2 = pivots_low[i + 1]
        if len(closes) - idx2 <= 3:
            if 0 < idx2 - idx1 <= max_distance:
                if closes[idx2] < closes[idx1] and rsi_values[idx2] > rsi_values[idx1]:
                    return {"type": "positive"}
    for i in range(len(pivots_high) - 1):
        idx1 = pivots_high[i]
        idx2 = pivots_high[i + 1]
        if len(closes) - idx2 <= 3:
            if 0 < idx2 - idx1 <= max_distance:
                if closes[idx2] > closes[idx1] and rsi_values[idx2] < rsi_values[idx1]:
                    return {"type": "negative"}
    return None

def check_symbol(symbol):
    try:
        url = "https://api.toobit.com/quote/v1/klines"
        params = {"symbol": symbol, "interval": "1m", "limit": 200}
        response = requests.get(url, params=params, timeout=5)
        data = response.json()
        if len(data) < 50:
            return None
        closes = [float(c[4]) for c in data]
        rsi_14 = calculate_rsi(closes, 14)
        if len(rsi_14) < 5:
            return None
        closes_for_rsi = closes[1:]
        rsi_14 = rsi_14[:len(closes_for_rsi)]
        divergence = find_divergence_details(closes_for_rsi, rsi_14, max_distance=30)
        if divergence:
            return {
                "symbol": symbol,
                "type": divergence["type"],
                "current_price": closes[-1],
                "rsi_current": rsi_14[-1]
            }
    except:
        pass
    return None

async def bot_loop():
    request = HTTPXRequest(proxy=PROXY_URL)
    bot = Bot(TOKEN, request=request)
    symbols = get_all_symbols()[:100]
    sent_signals = set()
    test_sent = False
    
    while True:
        try:
            updates = await bot.get_updates()
            if updates:
                chat_id = updates[-1].message.chat_id
                
                if not test_sent:
                    await bot.send_message(chat_id=chat_id, text="✅ ربات فعال شد و داره چک می‌کنه!")
                    print("✅ پیام تست فرستاده شد")
                    test_sent = True
                
                for symbol in symbols:
                    signal = check_symbol(symbol)
                    if signal:
                        key = f"{signal['symbol']}_{signal['type']}"
                        if key not in sent_signals:
                            sent_signals.add(key)
                            type_str = "صعودی 📈" if signal['type'] == "positive" else "نزولی 📉"
                            message = f"🚨 **واگرایی فعال {type_str}**\n\n"
                            message += f"📊 {signal['symbol']}\n"
                            message += f"💰 قیمت: {signal['current_price']}\n"
                            message += f"📊 RSI: {signal['rsi_current']:.2f}\n"
                            await bot.send_message(chat_id=chat_id, text=message)
                            print(f"✅ سیگنال: {signal['symbol']}")
            
            await asyncio.sleep(60)
        except Exception as e:
            print(f"❌ خطا: {e}")
            await asyncio.sleep(60)

def run_bot():
    asyncio.run(bot_loop())

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
