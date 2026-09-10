import os
import requests
import time
from datetime import datetime

# =========================
# تنظیمات
# =========================

BASE_URL = "https://api.toobit.com"

MAX_SYMBOLS = 100
TIMEFRAME = "5m"
CANDLE_LIMIT = 100
SCAN_INTERVAL = 60

RSI_PERIOD = 14

# فقط واگرایی‌های 1 ساعت اخیر
MAX_SIGNAL_AGE = 12

# فاصله نقطه 1 و 2
MAX_PIVOT_DISTANCE = 50


# =========================
# تلگرام
# =========================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "6822304373")


def send_telegram(message):

    try:

        if not TELEGRAM_TOKEN:
            print("❌ TELEGRAM_TOKEN در Render تنظیم نشده")
            return False

        url = (
            "https://api.telegram.org/bot"
            + TELEGRAM_TOKEN
            + "/sendMessage"
        )

        response = requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message
            },
            timeout=10
        )

        if response.status_code == 200:

            print("📨 تلگرام: پیام ارسال شد")
            return True

        else:

            print("❌ خطای تلگرام:")
            print(response.text)
            return False

    except Exception as e:

        print("❌ خطای تلگرام:", e)
        return False


# =========================
# دریافت ارزها
# =========================

def get_symbols():

    try:

        url = BASE_URL + "/quote/v1/ticker/bookTicker"

        response = requests.get(
            url,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        symbols = []

        for item in data:

            symbol = item.get("s", "")

            if (
                symbol.endswith("USDT")
                and symbol.isalnum()
                and len(symbol) <= 20
            ):

                symbols.append(symbol)

        symbols = list(dict.fromkeys(symbols))

        return symbols[:MAX_SYMBOLS]

    except Exception as e:

        print("❌ خطا در دریافت ارزها:", e)

        return []


# =========================
# محاسبه RSI
# =========================

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

    rsi_values = []

    if avg_loss == 0:

        rsi = 100

    else:

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

    rsi_values.append(rsi)

    for i in range(period, len(gains)):

        avg_gain = (
            (avg_gain * (period - 1))
            + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1))
            + losses[i]
        ) / period

        if avg_loss == 0:

            rsi = 100

        else:

            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        rsi_values.append(rsi)

    return rsi_values


# =========================
# بررسی یک ارز
# =========================

def check_symbol(symbol):

    try:

        url = BASE_URL + "/quote/v1/klines"

        params = {
            "symbol": symbol,
            "interval": TIMEFRAME,
            "limit": CANDLE_LIMIT + 1
        }

        response = requests.get(
            url,
            params=params,
            timeout=8
        )

        data = response.json()

        if not isinstance(data, list):
            return []

        if len(data) < 40:
            return []


        # حذف کندل در حال تشکیل
        data = data[:-1]

        if len(data) < 30:
            return []


        closes = [
            float(candle[4])
            for candle in data
        ]

        times = [
            int(candle[0])
            for candle in data
        ]


        # =========================
        # RSI
        # =========================

        rsi = calculate_rsi(
            closes,
            RSI_PERIOD
        )

        if not rsi:
            return []


        # هماهنگ کردن RSI با کندل‌ها

        rsi_full = [None] * RSI_PERIOD
        rsi_full.extend(rsi)

        if len(rsi_full) > len(closes):

            rsi_full = rsi_full[-len(closes):]


        # =========================
        # آخرین کندل بسته‌شده
        # =========================

        last_idx = len(closes) - 1
        idx2 = last_idx

        signals = []


        # =========================
        # Bullish
        # =========================

        if (
            idx2 >= 2
            and
            closes[idx2] <= closes[idx2 - 1]
            and
            closes[idx2] <= closes[idx2 - 2]
        ):

            start = max(
                RSI_PERIOD,
                idx2 - MAX_PIVOT_DISTANCE
            )

            end = idx2 - 3

            if end >= start:

                best_idx1 = None

                for i in range(start, end + 1):

                    if (
                        closes[i] < closes[i - 1]
                        and
                        closes[i] <= closes[i + 1]
                    ):

                        if best_idx1 is None:

                            best_idx1 = i

                        elif closes[i] < closes[best_idx1]:

                            best_idx1 = i


                if best_idx1 is not None:

                    idx1 = best_idx1

                    if (
                        closes[idx2] < closes[idx1]
                        and
                        rsi_full[idx2] is not None
                        and
                        rsi_full[idx1] is not None
                        and
                        rsi_full[idx2] > rsi_full[idx1]
                    ):

                        signals.append({

                            "type": "Bullish",

                            "time": times[idx2],

                            "price": closes[idx2],

                            "rsi": rsi_full[idx2],

                            "p1_time": times[idx1],

                            "p1_price": closes[idx1],

                            "p1_rsi": rsi_full[idx1],

                            "p2_time": times[idx2],

                            "p2_price": closes[idx2],

                            "p2_rsi": rsi_full[idx2]

                        })


        # =========================
        # Bearish
        # =========================

        if (
            idx2 >= 2
            and
            closes[idx2] >= closes[idx2 - 1]
            and
            closes[idx2] >= closes[idx2 - 2]
        ):

            start = max(
                RSI_PERIOD,
                idx2 - MAX_PIVOT_DISTANCE
            )

            end = idx2 - 3

            if end >= start:

                best_idx1 = None

                for i in range(start, end + 1):

                    if (
                        closes[i] > closes[i - 1]
                        and
                        closes[i] >= closes[i + 1]
                    ):

                        if best_idx1 is None:

                            best_idx1 = i

                        elif closes[i] > closes[best_idx1]:

                            best_idx1 = i


                if best_idx1 is not None:

                    idx1 = best_idx1

                    if (
                        closes[idx2] > closes[idx1]
                        and
                        rsi_full[idx2] is not None
                        and
                        rsi_full[idx1] is not None
                        and
                        rsi_full[idx2] < rsi_full[idx1]
                    ):

                        signals.append({

                            "type": "Bearish",

                            "time": times[idx2],

                            "price": closes[idx2],

                            "rsi": rsi_full[idx2],

                            "p1_time": times[idx1],

                            "p1_price": closes[idx1],

                            "p1_rsi": rsi_full[idx1],

                            "p2_time": times[idx2],

                            "p2_price": closes[idx2],

                            "p2_rsi": rsi_full[idx2]

                        })


        return signals


    except Exception:

        return []


# =========================
# اسکن
# =========================

def scan():

    symbols = get_symbols()

    if not symbols:

        print("❌ هیچ ارزی دریافت نشد")
        return


    print()
    print("========================================")
    print("🔎 شروع اسکن")
    print("📊 تعداد ارز:", len(symbols))
    print("⏱ تایم‌فریم:", TIMEFRAME)
    print("🚫 کندل در حال تشکیل بررسی نمی‌شود")
    print("🕐 فقط آخرین کندل بسته‌شده")
    print("========================================")


    found = 0


    for number, symbol in enumerate(
        symbols,
        start=1
    ):

        signals = check_symbol(symbol)


        for signal in signals:

            key = (
                symbol
                + "_"
                + signal["type"]
                + "_"
                + str(signal["time"])
            )


            if key in sent_signals:

                continue


            sent_signals.add(key)

            found += 1


            p1_time = datetime.fromtimestamp(
                signal["p1_time"] / 1000
            ).strftime("%H:%M")


            p2_time = datetime.fromtimestamp(
                signal["p2_time"] / 1000
            ).strftime("%H:%M")


            if signal["type"] == "Bullish":

                emoji = "🟢"
                name = "Bullish Divergence"

            else:

                emoji = "🔴"
                name = "Bearish Divergence"


            message = (

                "🚨 واگرایی جدید\n\n"

                + emoji
                + " "
                + name
                + "\n\n"

                + "💰 ارز: "
                + symbol
                + "\n"

                + "⏱ تایم‌فریم: 5m\n"

                + "🕐 نقطه ۱: "
                + p1_time
                + "\n"

                + "💵 قیمت نقطه ۱: "
                + str(signal["p1_price"])
                + "\n"

                + "📊 RSI نقطه ۱: "
                + f"{signal['p1_rsi']:.2f}"
                + "\n\n"

                + "🕐 نقطه ۲: "
                + p2_time
                + "\n"

                + "💵 قیمت نقطه ۲: "
                + str(signal["p2_price"])
                + "\n"

                + "📊 RSI نقطه ۲: "
                + f"{signal['p2_rsi']:.2f}"
                + "\n\n"

                + "⚠️ فقط هشدار\n"
                + "❌ بدون معامله"
            )


            print()
            print(message)

            send_telegram(message)


        if number % 10 == 0:

            print(
                "✅ "
                + str(number)
                + "/"
                + str(len(symbols))
                + " ارز بررسی شد"
            )


    print()
    print("========================================")

    print(
        "🏁 اسکن تمام شد | واگرایی جدید:",
        found
    )

    print("========================================")


# =========================
# شروع
# =========================

sent_signals = set()


print("========================================")
print("🤖 TOOBIT DIVERGENCE SCANNER")
print("========================================")
print("📊 100 ارز")
print("⏱ تایم‌فریم: 5 دقیقه")
print("🚫 کندل در حال تشکیل بررسی نمی‌شود")
print("🕐 فقط آخرین کندل بسته‌شده")
print("🔁 اسکن مداوم")
print("📨 Telegram: ON")
print("========================================")


# تست تلگرام

if send_telegram(
    "✅ ربات واگرایی فعال شد\n"
    "📊 100 ارز\n"
    "⏱ تایم‌فریم 5m\n"
    "🚫 فقط کندل‌های بسته‌شده\n"
    "🚨 بررسی واگرایی جدید"
):

    print("✅ اتصال تلگرام موفق بود")

else:

    print("❌ اتصال تلگرام ناموفق است")


# =========================
# حلقه اصلی
# =========================

while True:

    try:

        scan()

    except Exception as e:

        print("❌ خطای اصلی:", e)


    print()

    print(
        "⏳ اسکن بعدی تا",
        SCAN_INTERVAL,
        "ثانیه دیگر..."
    )

    time.sleep(SCAN_INTERVAL)
