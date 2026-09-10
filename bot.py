import requests
import asyncio
from telegram import Bot
from flask import Flask
import threading
from datetime import datetime
import os
import time

app = Flask(__name__)

# =========================================================
# تنظیمات
# =========================================================

TOKEN = os.getenv("TOKEN", "توکن_فعلی_خودت")

TIMEFRAME = "5m"
CANDLE_LIMIT = 100
MAX_SYMBOLS = 100

# هر 60 ثانیه بررسی می‌کند
SCAN_INTERVAL = 60

# تعداد کندل برای تشخیص Pivot
PIVOT_LEFT = 2
PIVOT_RIGHT = 2

# فاصله حداکثری دو نقطه واگرایی
MAX_PIVOT_DISTANCE = 50

# فقط Pivot خیلی جدید قابل هشدار است
MAX_SIGNAL_AGE = 3


# =========================================================
# Flask
# =========================================================

@app.route("/")
def home():
    return "Trading Alert Bot is running!"


# =========================================================
# دریافت ارزها
# =========================================================

def get_all_symbols():

    url = "https://api.toobit.com/quote/v1/ticker/bookTicker"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        symbols = []

        for item in data:

            symbol = item.get("s", "")

            if symbol.endswith("USDT"):
                symbols.append(symbol)

        # حذف موارد تکراری
        symbols = list(dict.fromkeys(symbols))

        return symbols[:MAX_SYMBOLS]

    except Exception as e:

        print(f"❌ Error getting symbols: {e}")

        return []


# =========================================================
# RSI
# =========================================================

def calculate_rsi(closes, period=14):

    if len(closes) < period + 1:
        return []

    gains = []
    losses = []

    for i in range(1, len(closes)):

        change = closes[i] - closes[i - 1]

        if change > 0:

            gains.append(change)
            losses.append(0)

        else:

            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:

        rsi = 100

    else:

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    rsi_values = [rsi]

    for i in range(period, len(gains)):

        avg_gain = (
            (avg_gain * (period - 1)) + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1)) + losses[i]
        ) / period

        if avg_loss == 0:

            rsi = 100

        else:

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        rsi_values.append(rsi)

    return rsi_values


# =========================================================
# تشخیص واگرایی
# =========================================================

def check_symbol(symbol):

    try:

        url = "https://api.toobit.com/quote/v1/klines"

        params = {
            "symbol": symbol,
            "interval": TIMEFRAME,
            "limit": CANDLE_LIMIT
        }

        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        if len(data) < 40:
            return None

        # -------------------------------------------------
        # مهم:
        # آخرین کندل ممکن است هنوز در حال تشکیل باشد.
        # آن را حذف می‌کنیم.
        # -------------------------------------------------

        data = data[:-1]

        closes = [
            float(candle[4])
            for candle in data
        ]

        times = [
            int(candle[0])
            for candle in data
        ]

        if len(closes) < 30:
            return None

        # -------------------------------------------------
        # RSI
        # -------------------------------------------------

        rsi = calculate_rsi(closes, 14)

        if not rsi:
            return None

        rsi_offset = len(closes) - len(rsi)

        def get_rsi(index):

            rsi_index = index - rsi_offset

            if rsi_index < 0:
                return None

            if rsi_index >= len(rsi):
                return None

            return rsi[rsi_index]

        # -------------------------------------------------
        # Pivot ها
        # -------------------------------------------------

        pivots_low = []
        pivots_high = []

        for i in range(
            PIVOT_LEFT,
            len(closes) - PIVOT_RIGHT
        ):

            left = closes[
                i - PIVOT_LEFT:i
            ]

            right = closes[
                i + 1:i + PIVOT_RIGHT + 1
            ]

            # Pivot Low
            if (
                closes[i] < min(left)
                and closes[i] < min(right)
            ):

                pivots_low.append(i)

            # Pivot High
            if (
                closes[i] > max(left)
                and closes[i] > max(right)
            ):

                pivots_high.append(i)

        last_idx = len(closes) - 1

        # =================================================
        # واگرایی صعودی
        # =================================================

        if len(pivots_low) >= 2:

            idx1 = pivots_low[-2]
            idx2 = pivots_low[-1]

            age = last_idx - idx2
            distance = idx2 - idx1

            rsi1 = get_rsi(idx1)
            rsi2 = get_rsi(idx2)

            if (
                rsi1 is not None
                and rsi2 is not None
                and age <= MAX_SIGNAL_AGE
                and 0 < distance <= MAX_PIVOT_DISTANCE
            ):

                price1 = closes[idx1]
                price2 = closes[idx2]

                # قیمت کف جدیدتر پایین‌تر
                # RSI کف جدیدتر بالاتر
                if (
                    price2 < price1
                    and rsi2 > rsi1
                ):

                    return {
                        "symbol": symbol,
                        "type": "صعودی 📈",
                        "signal_time": times[idx2],
                        "price": closes[-1],
                        "rsi": rsi2,
                        "p1_time": datetime.fromtimestamp(
                            times[idx1] / 1000
                        ).strftime("%H:%M"),
                        "p1_price": price1,
                        "p1_rsi": rsi1,
                        "p2_time": datetime.fromtimestamp(
                            times[idx2] / 1000
                        ).strftime("%H:%M"),
                        "p2_price": price2,
                        "p2_rsi": rsi2
                    }

        # =================================================
        # واگرایی نزولی
        # =================================================

        if len(pivots_high) >= 2:

            idx1 = pivots_high[-2]
            idx2 = pivots_high[-1]

            age = last_idx - idx2
            distance = idx2 - idx1

            rsi1 = get_rsi(idx1)
            rsi2 = get_rsi(idx2)

            if (
                rsi1 is not None
                and rsi2 is not None
                and age <= MAX_SIGNAL_AGE
                and 0 < distance <= MAX_PIVOT_DISTANCE
            ):

                price1 = closes[idx1]
                price2 = closes[idx2]

                # قیمت سقف جدیدتر بالاتر
                # RSI سقف جدیدتر پایین‌تر
                if (
                    price2 > price1
                    and rsi2 < rsi1
                ):

                    return {
                        "symbol": symbol,
                        "type": "نزولی 📉",
                        "signal_time": times[idx2],
                        "price": closes[-1],
                        "rsi": rsi2,
                        "p1_time": datetime.fromtimestamp(
                            times[idx1] / 1000
                        ).strftime("%H:%M"),
                        "p1_price": price1,
                        "p1_rsi": rsi1,
                        "p2_time": datetime.fromtimestamp(
                            times[idx2] / 1000
                        ).strftime("%H:%M"),
                        "p2_price": price2,
                        "p2_rsi": rsi2
                    }

    except Exception as e:

        print(
            f"❌ {symbol} error: {e}"
        )

    return None


# =========================================================
# ساخت پیام تلگرام
# =========================================================

def build_message(signal):

    message = ""

    message += "🚨 واگرایی جدید پیدا شد!\n\n"

    message += f"📊 ارز: {signal['symbol']}\n"
    message += f"📈 نوع: {signal['type']}\n\n"

    message += (
        f"💰 قیمت فعلی: "
        f"{signal['price']}\n"
    )

    message += (
        f"📊 RSI: "
        f"{signal['rsi']:.2f}\n\n"
    )

    message += (
        f"📍 نقطه ۱: "
        f"{signal['p1_time']}\n"
    )

    message += (
        f"قیمت: "
        f"{signal['p1_price']:.8f}\n"
    )

    message += (
        f"RSI: "
        f"{signal['p1_rsi']:.2f}\n\n"
    )

    message += (
        f"📍 نقطه ۲: "
        f"{signal['p2_time']}\n"
    )

    message += (
        f"قیمت: "
        f"{signal['p2_price']:.8f}\n"
    )

    message += (
        f"RSI: "
        f"{signal['p2_rsi']:.2f}\n\n"
    )

    message += "⏱ تایم‌فریم: 5 دقیقه\n"
    message += "⚠️ فقط هشدار — بدون معامله"

    return message


# =========================================================
# ربات تلگرام
# =========================================================

async def bot_loop():

    if not TOKEN:

        print("❌ TOKEN پیدا نشد.")

        return

    bot = Bot(TOKEN)

    sent_signals = set()

    chat_id = None

    startup_sent = False

    print("")
    print("================================")
    print("🤖 Trading Alert Bot Started")
    print("⏱ Timeframe: 5m")
    print("📊 Symbols: 100")
    print("================================")
    print("")

    while True:

        try:

            # ---------------------------------------------
            # دریافت آخرین پیام‌های تلگرام
            # ---------------------------------------------

            updates = await bot.get_updates(
                timeout=5
            )

            if updates:

                for update in updates:

                    if update.message:

                        chat_id = update.message.chat_id

                        # اگر /start فرستاده شد
                        if (
                            update.message.text
                            == "/start"
                        ):

                            await bot.send_message(
                                chat_id=chat_id,
                                text=(
                                    "✅ ربات فعال است!\n\n"
                                    "واگرایی‌های تازه "
                                    "تایم‌فریم 5 دقیقه "
                                    "را بررسی می‌کنم."
                                )
                            )

            # ---------------------------------------------
            # پیام اجرای موفق
            # ---------------------------------------------

            if chat_id and not startup_sent:

                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "🚀 کد با موفقیت اجرا شد! ✅\n\n"
                        "🤖 ربات هشدار واگرایی فعال است.\n"
                        "⏱ تایم‌فریم: 5 دقیقه\n"
                        "📊 در حال اسکن 100 ارز\n\n"
                        "⚠️ فقط هشدار ارسال می‌شود؛ "
                        "هیچ معامله‌ای انجام نمی‌شود."
                    )
                )

                startup_sent = True

                print(
                    "✅ Startup message sent to Telegram"
                )

            # ---------------------------------------------
            # اگر هنوز Chat ID نداریم
            # ---------------------------------------------

            if not chat_id:

                print(
                    "⏳ Waiting for Telegram /start..."
                )

                await asyncio.sleep(5)

                continue

            # ---------------------------------------------
            # دریافت ارزها
            # ---------------------------------------------

            symbols = get_all_symbols()

            if not symbols:

                print(
                    "⚠️ No symbols received."
                )

                await asyncio.sleep(
                    SCAN_INTERVAL
                )

                continue

            print(
                f"🔎 Scanning {len(symbols)} symbols..."
            )

            signals_found = 0

            # ---------------------------------------------
            # اسکن ارزها
            # ---------------------------------------------

            for symbol in symbols:

                signal = check_symbol(symbol)

                if signal:

                    signal_key = (
                        f"{symbol}_"
                        f"{signal['type']}_"
                        f"{signal['signal_time']}"
                    )

                    # جلوگیری از ارسال دوباره
                    if signal_key not in sent_signals:

                        sent_signals.add(
                            signal_key
                        )

                        message = build_message(
                            signal
                        )

                        await bot.send_message(
                            chat_id=chat_id,
                            text=message
                        )

                        signals_found += 1

                        print(
                            f"🚨 NEW SIGNAL | "
                            f"{symbol} | "
                            f"{signal['type']}"
                        )

                # کمی فاصله برای جلوگیری از فشار
                await asyncio.sleep(0.05)

            print(
                f"⏰ Scan finished | "
                f"New signals: {signals_found} | "
                f"{datetime.now().strftime('%H:%M:%S')}"
            )

            print("")

            # ---------------------------------------------
            # انتظار تا اسکن بعدی
            # ---------------------------------------------

            await asyncio.sleep(
                SCAN_INTERVAL
            )

        except Exception as e:

            print(
                f"❌ Bot loop error: {e}"
            )

            await asyncio.sleep(30)


# =========================================================
# اجرای Bot
# =========================================================

def run_bot():

    asyncio.run(
        bot_loop()
    )


threading.Thread(
    target=run_bot,
    daemon=True
).start()


# =========================================================
# اجرای Flask برای Render
# =========================================================

if __name__ == "__main__":

    print(
        "🌐 Flask server starting..."
    )

    port = int(
        os.getenv("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
