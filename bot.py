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

async def send_btc_price():
    bot = Bot(TOKEN)
    
    # اول ببینیم چت آیدی چیه
    updates = await bot.get_updates()
    if not updates:
        print("❌ اول به رباتت پیام بده!")
        return
    
    chat_id = updates[-1].message.chat_id
    print(f"✅ چت آیدی: {chat_id}")
    
    while True:
        try:
            # گرفتن قیمت بیت‌کوین از توبیت
            url = "https://api.toobit.com/quote/v1/ticker/bookTicker"
            response = requests.get(url)
            data = response.json()
            
            btc_price = None
            for item in data:
                if item["s"] == "BTCUSDT":
                    btc_price = item["b"]
                    break
            
            if btc_price:
                message = f"📊 BTCUSDT\n💰 قیمت: {btc_price}"
                await bot.send_message(chat_id=chat_id, text=message)
                print(f"✅ پیام فرستاده شد: {btc_price}")
            else:
                print("❌ BTCUSDT پیدا نشد")
            
            await asyncio.sleep(60)  # ۱ دقیقه صبر کن
            
        except Exception as e:
            print(f"❌ خطا: {e}")
            await asyncio.sleep(60)

def run():
    asyncio.run(send_btc_price())

threading.Thread(target=run, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
