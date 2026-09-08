import requests
import asyncio
from telegram import Bot
from flask import Flask
import threading

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

def find_divergence_complete(closes, rsi_values):
    if len(closes) < 5 or len(rsi_values) < 5:
        return None
    
    pivots_low = []
    pivots_high = []
    
    for i in range(2, len(closes) - 2):
        if closes[i] == min(closes[i-2:i+3]):
            pivots_low.append(i)
        if closes[i] == max(closes[i-2:i+3]):
            pivots_high.append(i)
    
    last_idx = len(closes) - 1
    
    # واگرایی مثبت: نقطه آخر باید کندل آخر باشه
    for i in range(len(pivots_low) - 1):
        idx1 = pivots_low[i]
        idx2 = pivots_low[i + 1]
        
        if idx2 == last_idx or idx2 == last_idx - 1:
            if closes[idx2] < closes[idx1] and rsi_values[idx2] > rsi_values[idx1]:
                return {
                    "type": "positive",
                    "idx1": idx1,
                    "idx2": idx2,
                    "rsi1": rsi_values[idx1],
                    "rsi2": rsi_values[idx2]
                }
    
    # واگرایی منفی
    for i in range(len(pivots_high) - 1):
        idx1 = pivots_high[i]
        idx2 = pivots_high[i + 1]
        
        if idx2 == last_idx or idx2 == last_idx - 1:
            if closes[idx2] > closes[idx1] and rsi_values[idx2] < rsi_values[idx1]:
                return {
                    "type": "negative",
                    "idx1": idx1,
                    "idx2": idx2,
                    "rsi1": rsi_values[idx1],
                    "rsi2": rsi_values[idx2]
                }
    
    return None

def check_symbol(symbol):
    try:
        url = "https://api.toobit.com/quote/v1/klines"
        params = {"symbol": symbol, "interval": "5m", "limit": 200}
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
        
        divergence = find_divergence_complete(closes_for_rsi, rsi_14)
        
        if divergence:
            max_rsi_with_div = 14
            divergence_type = divergence["type"]
            
            for period in range(15, 101):
                rsi_test = calculate_rsi(closes, period)
                rsi_test = rsi_test[:len(closes_for_rsi)]
                div_test = find_divergence_complete(closes_for_rsi, rsi_test)
                
                if div_test and div_test["type"] == divergence_type:
                    max_rsi_with_div = period
                else:
                    break
            
            rsi_diff = abs(divergence["rsi2"] - divergence["rsi1"])
            distance = divergence["idx2"] - divergence["idx1"]
            
            score_rsi_strength = min((max_rsi_with_div - 14) / 86 * 100, 100)
            score_rsi_diff = min(rsi_diff / 20 * 100, 100)
            
            if distance <= 10:
                score_distance = 100
            elif distance <= 20:
                score_distance = 70
            elif distance <= 40:
                score_distance = 50
            else:
                score_distance = 30
            
            if divergence_type == "positive":
                if rsi_14[-1] < 40:
                    score_position = 100
                elif rsi_14[-1] < 50:
                    score_position = 70
                else:
                    score_position = 40
            else:
                if rsi_14[-1] > 60:
                    score_position = 100
                elif rsi_14[-1] > 50:
                    score_position = 70
                else:
                    score_position = 40
            
            power_score = (
                score_rsi_strength * 0.4 +
                score_rsi_diff * 0.3 +
                score_distance * 0.15 +
                score_position * 0.15
            )
            
            if power_score >= 70:
                power_label = "قوی 💪"
            elif power_score >= 50:
                power_label = "متوسط 👍"
            else:
                power_label = "ضعیف ⚠️"
            
            return {
                "symbol": symbol,
                "type": divergence_type,
                "current_price": closes[-1],
                "rsi_current": rsi_14[-1],
                "max_rsi": max_rsi_with_div,
                "power_score": power_score,
                "power_label": power_label
            }
    except:
        pass
    return None

async def bot_loop():
    bot = Bot(TOKEN)
    symbols = get_all_symbols()[:500]
    sent_signals = set()
    test_sent = False
    
    while True:
        try:
            updates = await bot.get_updates()
            if updates:
                chat_id = updates[-1].message.chat_id
                
                if not test_sent:
                    await bot.send_message(chat_id=chat_id, text="✅ ربات واگرایی کامل فعال شد!")
                    print("✅ پیام تست فرستاده شد")
                    test_sent = True
                
                for symbol in symbols:
                    signal = check_symbol(symbol)
                    if signal:
                        key = f"{signal['symbol']}_{signal['type']}"
                        if key not in sent_signals:
                            sent_signals.add(key)
                            
                            type_str = "صعودی 📈" if signal['type'] == "positive" else "نزولی 📉"
                            message = f"🚨 **واگرایی {type_str}**\n\n"
                            message += f"📊 {signal['symbol']}\n"
                            message += f"💰 قیمت: {signal['current_price']}\n"
                            message += f"📊 RSI: {signal['rsi_current']:.2f}\n"
                            message += f"💪 قوی‌ترین RSI: {signal['max_rsi']}\n"
                            message += f"🎯 قدرت سیگنال: {signal['power_score']:.1f}٪ ({signal['power_label']})\n"
                            
                            await bot.send_message(chat_id=chat_id, text=message)
                            print(f"✅ سیگنال: {signal['symbol']} - {signal['type']} - {signal['power_score']:.1f}%")
            
            await asyncio.sleep(300)
            
        except Exception as e:
            print(f"❌ خطا: {e}")
            await asyncio.sleep(300)

def run():
    asyncio.run(bot_loop())

threading.Thread(target=run, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
