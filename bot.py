import requests
import asyncio
import threading
import time

from telegram import Bot
from flask import Flask
from datetime import datetime


# =========================================================
# SETTINGS
# =========================================================

TOKEN = "توکن_جدید_ربات_اینجا"

TIMEFRAME = "5m"
CANDLE_LIMIT = 100
MAX_SYMBOLS = 100

SCAN_INTERVAL = 60

# Pivot با 2 کندل قبل و 2 کندل بعد تأیید می‌شود
PIVOT_LEFT = 2
PIVOT_RIGHT = 2

# فقط اگر Pivot دوم حداکثر 3 کندل قبل باشد
# اجازه هشدار می‌دهیم.
MAX_PIVOT_AGE = 3

# فاصله حداکثر بین دو Pivot
MAX_PIVOT_DISTANCE = 50


# =========================================================
# FLASK
# =========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Trading Alert Bot is running!"


# =========================================================
# TOOBIT
# =========================================================

TOOBIT_TICKER_URL = (
    "https://api.toobit.com/quote/v1/ticker/bookTicker"
)

TOOBIT_KLINES_URL = (
    "https://api.toobit.com/quote/v1/klines"
)


def get_all_symbols():
    try:
        response = requests.get(
            TOOBIT_TICKER_URL,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        symbols = []

        for item in data:

            symbol = item.get("s", "")

            if symbol.endswith("USDT"):
                symbols.append(symbol)

        return symbols[:MAX_SYMBOLS]

    except Exception as e:

        print(f"❌ خطا در دریافت نمادها: {e}")

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
# CHECK SYMBOL
# =========================================================

def check_symbol(symbol):

    try:

        params = {
            "symbol": symbol,
            "interval": TIMEFRAME,
            "limit": CANDLE_LIMIT
        }

        response = requests.get(
            TOOBIT_KLINES_URL,
            params=params,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        if not isinstance(data, list):
            return None

        if len(data) < 40:
            return None


        # =================================================
        # حذف کندل در حال تشکیل
        # =================================================

        data = data[:-1]


        # =================================================
        # PRICE DATA
        # =================================================

        opens = [float(x[1]) for x in data]
        highs = [float(x[2]) for x in data]
        lows = [float(x[3]) for x in data]
        closes = [float(x[4]) for x in data]

        times = [int(x[0]) for x in data]


        # =================================================
        # RSI
        # =================================================

        rsi = calculate_rsi(
            closes,
            14
        )

        if not rsi:
            return None


        # RSI از کندل شماره 14 شروع می‌شود
        rsi_offset = len(closes) - len(rsi)


        # =================================================
        # PIVOTS
        # =================================================

        pivots_low = []
        pivots_high = []


        for i in range(
            PIVOT_LEFT,
            len(closes) - PIVOT_RIGHT
        ):

            # -----------------------------
            # Pivot Low
            # -----------------------------

            is_pivot_low = True

            for j in range(
                i - PIVOT_LEFT,
                i + PIVOT_RIGHT + 1
            ):

                if j == i:
                    continue

                if lows[i] >= lows[j]:

                    is_pivot_low = False
                    break

            if is_pivot_low:

                pivots_low.append(i)


            # -----------------------------
            # Pivot High
            # -----------------------------

            is_pivot_high = True

            for j in range(
                i - PIVOT_LEFT,
                i + PIVOT_RIGHT + 1
            ):

                if j == i:
                    continue

                if highs[i] <= highs[j]:

                    is_pivot_high = False
                    break

            if is_pivot_high:

                pivots_high.append(i)


        # =================================================
        # آخرین کندل بسته شده
        # =================================================

        last_closed_index = len(closes) - 1


        # =================================================
        # BULLISH DIVERGENCE
        # =================================================

        if len(pivots_low) >= 2:

            idx1 = pivots_low[-2]
            idx2 = pivots_low[-1]

            pivot_age = (
                last_closed_index - idx2
            )

            distance = idx2 - idx1


            # Pivot باید تازه باشد

            if (
                pivot_age <= MAX_PIVOT_AGE
                and distance > 0
                and distance <= MAX_PIVOT_DISTANCE
            ):

                rsi_idx1 = idx1 - rsi_offset
                rsi_idx2 = idx2 - rsi_offset

                if (
                    rsi_idx1 >= 0
                    and rsi_idx2 >= 0
                    and rsi_idx1 < len(rsi)
                    and rsi_idx2 < len(rsi)
                ):

                    rsi1 = rsi[rsi_idx1]
                    rsi2 = rsi[rsi_idx2]


                    # قیمت کف پایین‌تر
                    # RSI کف بالاتر

                    if (
                        lows[idx2] < lows[idx1]
                        and rsi2 > rsi1
                    ):

                        return {
                            "symbol": symbol,
                            "type": "صعودی 📈",
                            "signal_time": times[idx2],
                            "price": closes[-1],
                            "rsi": rsi[-1],

                            "p1_time": datetime.fromtimestamp(
                                times[idx1] / 1000
                            ).strftime("%H:%M"),

                            "p1_price": lows[idx1],
                            "p1_rsi": rsi1,

                            "p2_time": datetime.fromtimestamp(
                                times[idx2] / 1000
                            ).strftime("%H:%M"),

                            "p2_price": lows[idx2],
                            "p2_rsi": rsi2
                        }


        # =================================================
        # BEARISH DIVERGENCE
        # =================================================

        if len(pivots_high) >= 2:

            idx1 = pivots_high[-2]
            idx2 = pivots_high[-1]

            pivot_age = (
                last_closed_index - idx2
            )

            distance = idx2 - idx1


            if (
                pivot_age <= MAX_PIVOT_AGE
                and distance > 0
                and distance <= MAX_PIVOT_DISTANCE
            ):

                rsi_idx1 = idx1 - rsi_offset
                rsi_idx2 = idx2 - rsi_offset

                if (
                    rsi_idx1 >= 0
                    and rsi_idx2 >= 0
                    and rsi_idx1 < len(rsi)
                    and rsi_idx2 < len(rsi)
                ):

                    rsi1 = rsi[rsi_idx1]
                    rsi2 = rsi[rsi_idx2]


                    # قیمت سقف بالاتر
                    # RSI سقف پایین‌تر

                    if (
                        highs[idx2] > highs[idx1]
                        and rsi2 < rsi1
                    ):

                        return {
                            "symbol": symbol,
                            "type": "نزولی 📉",
                            "signal_time": times[idx2],
                            "price": closes[-1],
                            "rsi": rsi[-1],

                            "p1_time": datetime.fromtimestamp(
                                times[idx1] / 1000
                            ).strftime("%H:%M"),

                            "p1_price": highs[idx1],
                            "p1_rsi": rsi1,

                            "p2_time": datetime.fromtimestamp(
                                times[idx2] / 1000
                            ).strftime("%H:%M"),

                            "p2_price": highs[idx2],
                            "p2_rsi": rsi2
                        }


    except Exception as e:

        print(
            f"❌ Error {symbol}: {e}"
        )

    return None


# =========================================================
# TELEGRAM MESSAGE
# =========================================================

def build_message(signal):

    message = ""

    message += (
        f"🚨 واگرایی {signal['type']}\n\n"
    )

    message += (
        f"📊 ارز: {signal['symbol']}\n"
    )

    message += (
        f"⏱ تایم‌فریم: {TIMEFRAME}\n"
    )

    message += (
        f"💰 قیمت فعلی: "
        f"{signal['price']:.8f}\n"
    )

    message += (
        f"📊 RSI فعلی: "
        f"{signal['rsi']:.2f}\n\n"
    )

    message += (
        f"📍 نقطه اول: "
        f"{signal['p1_time']}\n"
    )

    message += (
        f"   قیمت: "
        f"{signal['p1_price']:.8f}\n"
    )

    message += (
        f"   RSI: "
        f"{signal['p1_rsi']:.2f}\n\n"
    )

    message += (
        f"📍 نقطه دوم: "
        f"{signal['p2_time']}\n"
    )

    message += (
        f"   قیمت: "
        f"{signal['p2_price']:.8f}\n"
    )

    message += (
        f"   RSI: "
        f"{signal['p2_rsi']:.2f}\n\n"
    )

    message += (
        "⚠️ این فقط هشدار واگرایی است؛ "
        "هیچ معامله‌ای انجام نمی‌شود."
    )

    return message


# =========================================================
# TELEGRAM BOT LOOP
# =========================================================

async def bot_loop():

    bot = Bot(TOKEN)

    chat_id = None

    sent_signals = set()

    print("🤖 Trading Alert Bot Started")

    print(
        f"⏱ Timeframe: {TIMEFRAME}"
    )

    print(
        f"📊 Max symbols: {MAX_SYMBOLS}"
    )


    while True:

        try:

            # =============================================
            # دریافت پیام‌های تلگرام
            # =============================================

            updates = await bot.get_updates(
                timeout=5
            )

            if updates:

                for update in updates:

                    if update.message:

                        chat_id = (
                            update.message.chat_id
                        )

                        print(
                            f"📱 Chat ID: {chat_id}"
                        )


                        # پیام شروع

                        if (
                            update.message.text
                            and
                            update.message.text.startswith(
                                "/start"
                            )
                        ):

                            await bot.send_message(
                                chat_id=chat_id,
                                text=(
                                    "✅ ربات هشدار "
                                    "واگرایی فعال است.\n\n"
                                    "📊 Toobit\n"
                                    "⏱ تایم‌فریم 5 دقیقه\n"
                                    "📈 RSI Divergence\n\n"
                                    "ربات فقط هشدار می‌دهد "
                                    "و معامله‌ای انجام نمی‌دهد."
                                )
                            )


            # =============================================
            # اگر هنوز Chat ID نداریم
            # =============================================

            if chat_id is None:

                print(
                    "⏳ هنوز پیام /start از تلگرام دریافت نشده."
                )

                await asyncio.sleep(
                    SCAN_INTERVAL
                )

                continue


            # =============================================
            # دریافت نمادها
            # =============================================

            symbols = get_all_symbols()


            if not symbols:

                print(
                    "❌ هیچ نمادی دریافت نشد."
                )

                await asyncio.sleep(
                    SCAN_INTERVAL
                )

                continue


            print(
                f"🔎 شروع اسکن {len(symbols)} ارز..."
            )


            signals_found = 0


            # =============================================
            # اسکن ارزها
            # =============================================

            for symbol in symbols:

                signal = check_symbol(
                    symbol
                )


                if signal:

                    # زمان Pivot دوم
                    signal_time = (
                        signal["signal_time"]
                    )

                    # کلید یکتا
                    signal_key = (
                        f"{symbol}_"
                        f"{signal['type']}_"
                        f"{signal_time}"
                    )


                    # فقط یک بار ارسال
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
                            f"🚨 SIGNAL: "
                            f"{symbol} "
                            f"{signal['type']} "
                            f"{signal['p2_time']}"
                        )


                # کمی مکث برای جلوگیری از فشار زیاد
                await asyncio.sleep(0.05)


            # =============================================
            # گزارش اسکن
            # =============================================

            print(
                f"✅ اسکن تمام شد | "
                f"{signals_found} سیگنال جدید | "
                f"{datetime.now().strftime('%H:%M:%S')}"
            )


            # =============================================
            # پاک کردن سیگنال‌های خیلی قدیمی
            # =============================================

            if len(sent_signals) > 5000:

                sent_signals = set(
                    list(sent_signals)[-2000:]
                )


            await asyncio.sleep(
                SCAN_INTERVAL
            )


        except Exception as e:

            print(
                f"❌ خطا در Bot Loop: {e}"
            )

            await asyncio.sleep(
                30
            )


# =========================================================
# RUN BOT
# =========================================================

def run_bot():

    asyncio.run(
        bot_loop()
    )


# =========================================================
# START
# =========================================================

threading.Thread(
    target=run_bot,
    daemon=True
).start()


if __name__ == "__main__":

    print(
        "🌐 Flask server starting..."
    )

    app.run(
        host="0.0.0.0",
        port=10000
    )
