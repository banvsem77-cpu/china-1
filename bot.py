import os
import urllib.parse
import tempfile

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from huggingface_hub import InferenceClient

# =================================
# ENV
# =================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")

# =================================
# AI
# =================================

client = InferenceClient(
    model="HuggingFaceH4/zephyr-7b-beta",
    token=HF_TOKEN
)

# =================================
# TELEGRAM
# =================================

telegram_app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

# =================================
# FASTAPI
# =================================

api = FastAPI()

# =================================
# КАЛЬКУЛЯТОР
# =================================

CHINA_DELIVERY = 0.35
INTL_DELIVERY = 4.5
SERVICE_FEE = 0.10

# =================================
# КИТАЙСКИЙ ЗАПРОС
# =================================

def translate_to_chinese(text):

    prompt = f"""
Переведи товар на китайский для поиска на 1688.

Товар:
{text}

Ответ только китайским словом.
"""

    try:
        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50
        )

        return resp.choices[0].message.content.strip()

    except:
        return text

# =================================
# ССЫЛКИ ПОСТАВЩИКОВ
# =================================

def generate_supplier_links(query):

    q_cn = urllib.parse.quote(query.encode("gb18030"))
    q_utf = urllib.parse.quote(query)

    return f"""
ТОП поставщиков

1688
https://s.1688.com/selloffer/offer_search.htm?keywords={q_cn}

Taobao
https://s.taobao.com/search?q={q_cn}

Alibaba
https://www.alibaba.com/trade/search?SearchText={q_utf}

Tmall
https://list.tmall.com/search_product.htm?q={q_cn}

Made-in-China
https://www.google.com/search?q=site%3Amade-in-china.com%20{q_utf}
"""

# =================================
# START
# =================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """
Привет! Я бот закупщика.

Что умею:

1. Поиск по названию
2. Поиск по фото
3. Китайский запрос
4. Ссылки на поставщиков
5. /calc цена вес количество

Пример:
силиконовая форма для льда

/calc 0.42 18 1000
"""

    await update.message.reply_text(text)

# =================================
# КАЛЬКУЛЯТОР
# =================================

async def calc(update: Update, context: ContextTypes.DEFAULT_TYPE):

    try:

        _, price, weight, qty = update.message.text.split()

        price = float(price)
        weight = float(weight)
        qty = int(qty)

        goods = price * qty
        china = weight * CHINA_DELIVERY
        intl = weight * INTL_DELIVERY

        subtotal = goods + china + intl
        fee = subtotal * SERVICE_FEE
        total = subtotal + fee

        per_unit = total / qty

        text = f"""
Расчет готов:

Товар: ${round(goods,2)}
Доставка по Китаю: ${round(china,2)}
Международная доставка: ${round(intl,2)}
Комиссия: ${round(fee,2)}

ИТОГО: ${round(total,2)}
Себестоимость за 1 шт: ${round(per_unit,3)}
"""

        await update.message.reply_text(text)

    except:
        await update.message.reply_text("Пример: /calc 0.42 18 1000")

# =================================
# ПОИСК ТОВАРА
# =================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = update.message.text

    await update.message.reply_text("Ищу поставщиков...")

    chinese = translate_to_chinese(text)

    links = generate_supplier_links(chinese)

    result = f"""
КИТАЙСКИЙ ЗАПРОС
{chinese}

{links}
"""

    await update.message.reply_text(result)

# =================================
# ФОТО
# =================================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("Анализирую фото...")

    caption = update.message.caption

    if caption:
        query = translate_to_chinese(caption)
    else:
        query = "product"

    links = generate_supplier_links(query)

    await update.message.reply_text(links)

# =================================
# РЕГИСТРАЦИЯ
# =================================

telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(CommandHandler("calc", calc))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
telegram_app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

# =================================
# WEBHOOK
# =================================

@api.post("/telegram")
async def telegram_webhook(req: Request):

    data = await req.json()

    update = Update.de_json(data, telegram_app.bot)

    await telegram_app.process_update(update)

    return {"ok": True}

# =================================
# HEALTH
# =================================

@api.get("/health")
async def health():
    return {"status": "ok"}

# =================================
# STARTUP
# =================================

@api.on_event("startup")
async def startup():

    await telegram_app.initialize()
    await telegram_app.start()

    await telegram_app.bot.set_webhook(
        f"{PUBLIC_BASE_URL}/telegram"
    )
