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

async def test_loop():
    bot = Bot(TOKEN)
    
    while True:
        try:
            updates = await bot.get_updates()
            if updates:
                chat_id = updates[-1].message.chat_id
                
                # تست ساده: فقط قیمت بیت‌کوین
                url = "https://api.toobit.com/quote/v1/ticker/bookTicker"
                response = requests.get(url)
                data = response.json()
                
                for item in data:
                    if item["s"] == "BTCUSDT":
                        price = item["b"]
                        await bot.send_message(chat_id=chat_id, text=f"📊 BTCUSDT: {price}")
                        print(f"✅ فرستاده شد: {price}")
                        break
            
            await asyncio.sleep(60)
        except Exception as e:
            print(f"❌ خطا: {e}")
            await asyncio.sleep(60)

def run():
    asyncio.run(test_loop())

threading.Thread(target=run, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
