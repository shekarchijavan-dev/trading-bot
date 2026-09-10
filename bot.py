import os
import time
import threading
import requests
from flask import Flask

# =========================
# تنظیمات
# =========================

BASE_URL = "https://api.toobit.com"

MAX_SYMBOLS = 100
TIMEFRAME = "5m"
CANDLE_LIMIT = 101

SCAN_INTERVAL = 60

RSI_PERIOD = 14
MAX_SIGNAL_AGE = 12
MAX_PIVOT_DISTANCE = 50

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID", "6822304373")

# =========================
# Flask برای Render
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is running!"


# =========================
# Telegram
# =========================

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

        print("❌ خطای تلگرام:")
        print(response.text)

        return False

    except Exception as e:
        print("❌ خطای ارسال تلگرام:", e)
        return False


# =========================
# دریافت ارزها
# =========================

def get_symbols():
    try:
        url = BASE_URL + "/quote/v1/ticker/bookTicker"

        response = requests.get(url, timeout=15)

        if response.status_code != 200:
            print("❌ خطا در دریافت لیست ارزها:", response.status_code)
            return []

        data = response.json()

        symbols = []

        for item in data:
            symbol = item.get("symbol", "")

            if (
                symbol.endswith("USDT")
                and symbol.isalnum()
                and len(symbol) <= 20
            ):
                symbols.append(symbol)

        return symbols[:MAX_SYMBOLS]

    except Exception as e:
        print("❌ خطا در get_symbols:", e)
        return []


# =========================
# دریافت کندل‌ها
# =========================

def get_klines(symbol):
    try:
        url = BASE_URL + "/quote/v1/klines"

        params = {
            "symbol": symbol,
            "interval": TIMEFRAME,
            "limit": CANDLE_LIMIT
        }

        response = requests.get(
            url,
            params=params,
            timeout=15
        )

        if response.status_code != 200:
            return []

        data = response.json()

        if not data:
            return []

        # حذف آخرین کندل چون هنوز در حال تشکیل است
        data = data[:-1]

        return data

    except Exception as e:
        print(f"❌ خطا در کندل {symbol}: {e}")
        return []


# =========================
# RSI
# =========================

def calculate_rsi(closes, period=14):

    if len(closes) <= period:
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

    rsi = [None] * period

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        rsi.append(100)
    else:
        rs = avg_gain / avg_loss
        rsi.append(100 - (100 / (1 + rs)))

    for i in range(period, len(gains)):

        avg_gain = (
            (avg_gain * (period - 1)) + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1)) + losses[i]
        ) / period

        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            value = 100 - (100 / (1 + rs))
            rsi.append(value)

    return rsi


# =========================
# تشخیص واگرایی
# =========================

def check_symbol(symbol):

    data = get_klines(symbol)

    if len(data) < RSI_PERIOD + 10:
        return []

    closes = []

    for candle in data:
        try:
            closes.append(float(candle[4]))
        except:
            return []

    rsi = calculate_rsi(closes, RSI_PERIOD)

    if len(rsi) != len(closes):
        return []

    signals = []

    # آخرین کندل بسته‌شده
    idx2 = len(closes) - 1

    if rsi[idx2] is None:
        return []

    price2 = closes[idx2]
    rsi2 = rsi[idx2]

    # =========================
    # واگرایی صعودی
    # قیمت: کف پایین‌تر
    # RSI: کف بالاتر
    # =========================

    is_low = (
        closes[idx2] <= closes[idx2 - 1]
        and
        closes[idx2] <= closes[idx2 - 2]
    )

    if is_low:

        start = max(
            RSI_PERIOD,
            idx2 - MAX_PIVOT_DISTANCE
        )

        for idx1 in range(idx2 - 3, start - 1, -1):

            if rsi[idx1] is None:
                continue

            is_low1 = (
                closes[idx1] <= closes[idx1 - 1]
                and
                closes[idx1] <= closes[idx1 + 1]
            )

            if not is_low1:
                continue

            price1 = closes[idx1]
            rsi1 = rsi[idx1]

            if (
                price2 < price1
                and
                rsi2 > rsi1
            ):

                strength = abs(rsi2 - rsi1)

                signals.append({
                    "type": "BULLISH",
                    "symbol": symbol,
                    "price": price2,
                    "rsi": rsi2,
                    "rsi1": rsi1,
                    "strength": strength,
                    "idx1": idx1,
                    "idx2": idx2
                })

                break

    # =========================
    # واگرایی نزولی
    # قیمت: سقف بالاتر
    # RSI: سقف پایین‌تر
    # =========================

    is_high = (
        closes[idx2] >= closes[idx2 - 1]
        and
        closes[idx2] >= closes[idx2 - 2]
    )

    if is_high:

        start = max(
            RSI_PERIOD,
            idx2 - MAX_PIVOT_DISTANCE
        )

        for idx1 in range(idx2 - 3, start - 1, -1):

            if rsi[idx1] is None:
                continue

            is_high1 = (
                closes[idx1] >= closes[idx1 - 1]
                and
                closes[idx1] >= closes[idx1 + 1]
            )

            if not is_high1:
                continue

            price1 = closes[idx1]
            rsi1 = rsi[idx1]

            if (
                price2 > price1
                and
                rsi2 < rsi1
            ):

                strength = abs(rsi1 - rsi2)

                signals.append({
                    "type": "BEARISH",
                    "symbol": symbol,
                    "price": price2,
                    "rsi": rsi2,
                    "rsi1": rsi1,
                    "strength": strength,
                    "idx1": idx1,
                    "idx2": idx2
                })

                break

    return signals


# =========================
# پیام سیگنال
# =========================

def format_signal(signal):

    if signal["type"] == "BULLISH":
        emoji = "🟢"
        title = "واگرایی صعودی"
    else:
        emoji = "🔴"
        title = "واگرایی نزولی"

    message = (
        f"{emoji} {title}\n\n"
        f"💰 ارز: {signal['symbol']}\n"
        f"⏱ تایم‌فریم: 5 دقیقه\n"
        f"💵 قیمت: {signal['price']}\n"
        f"📊 RSI فعلی: {signal['rsi']:.2f}\n"
        f"📊 RSI نقطه 1: {signal['rsi1']:.2f}\n"
        f"💪 قدرت واگرایی: {signal['strength']:.2f}\n\n"
        f"✅ فقط هشدار — بدون معامله"
    )

    return message


# =========================
# اسکنر
# =========================

sent_signals = set()


def scanner():

    print("🚀 Scanner started")
    print("📊 Timeframe:", TIMEFRAME)
    print("🪙 Max symbols:", MAX_SYMBOLS)
    print("⏱ Scan interval:", SCAN_INTERVAL, "seconds")

    while True:

        try:

            print("\n" + "=" * 50)
            print("🔄 شروع اسکن...")

            symbols = get_symbols()

            if not symbols:
                print("❌ هیچ ارزی دریافت نشد")
                time.sleep(SCAN_INTERVAL)
                continue

            print(f"📊 در حال بررسی {len(symbols)} ارز...")

            total_signals = 0

            for number, symbol in enumerate(symbols, start=1):

                try:

                    signals = check_symbol(symbol)

                    if signals:

                        for signal in signals:

                            total_signals += 1

                            # شناسه یکتا برای جلوگیری از ارسال تکراری
                            signal_id = (
                                signal["symbol"],
                                signal["type"],
                                signal["idx2"]
                            )

                            if signal_id in sent_signals:
                                continue

                            print(
                                f"🚨 سیگنال جدید: "
                                f"{symbol} - "
                                f"{signal['type']}"
                            )

                            message = format_signal(signal)

                            success = send_telegram(message)

                            if success:
                                sent_signals.add(signal_id)

                except Exception as e:

                    print(
                        f"❌ خطا در بررسی {symbol}: {e}"
                    )

                # نمایش پیشرفت
                if number % 10 == 0:
                    print(
                        f"📈 پیشرفت: "
                        f"{number}/{len(symbols)}"
                    )

            print(
                f"✅ اسکن تمام شد | "
                f"سیگنال‌های پیدا شده: {total_signals}"
            )

            print(
                f"⏳ اسکن بعدی در "
                f"{SCAN_INTERVAL} ثانیه..."
            )

            time.sleep(SCAN_INTERVAL)

        except Exception as e:

            print("❌ خطای اصلی Scanner:", e)

            time.sleep(SCAN_INTERVAL)


# =========================
# اجرای برنامه
# =========================

if __name__ == "__main__":

    print("=" * 50)
    print("🤖 TOOBIT DIVERGENCE SCANNER")
    print("=" * 50)

    # اجرای Scanner در Thread جدا
    scanner_thread = threading.Thread(
        target=scanner,
        daemon=True
    )

    scanner_thread.start()

    # پورت مخصوص Render
    port = int(
        os.environ.get("PORT", 10000)
    )

    print(f"🌐 Flask running on port {port}")

    app.run(
        host="0.0.0.0",
        port=port
    )
