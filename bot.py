import os
import requests
import urllib.parse
from bs4 import BeautifulSoup

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

from fastapi import FastAPI, Request
from telegram import Bot
from huggingface_hub import InferenceClient

# =========================================
# ENV
# =========================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")

if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Не задан TELEGRAM_BOT_TOKEN")

if not PUBLIC_BASE_URL:
    raise RuntimeError("Не задан PUBLIC_BASE_URL")

# =========================================
# AI CLIENT
# =========================================

client = InferenceClient(
    provider="hf-inference",
    model="HuggingFaceH4/zephyr-7b-beta",
    token=HF_TOKEN,
)

# =========================================
# TELEGRAM
# =========================================

bot = Bot(token=TELEGRAM_BOT_TOKEN)
app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

# =========================================
# FASTAPI
# =========================================

api = FastAPI()

# =========================================
# SEARCH SUPPLIERS
# =========================================

def search_suppliers(query):

    q = urllib.parse.quote(query)
    url = f"https://www.google.com/search?q={q}&num=50"

    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")

    links = []

    for a in soup.select("a"):
        href = a.get("href")

        if href and "url?q=" in href:
            link = href.split("url?q=")[1].split("&")[0]
            links.append(link)

    suppliers = {
        "1688": [],
        "taobao": [],
        "alibaba": [],
        "tmall": [],
        "made": []
    }

    for link in links:

        if "1688.com" in link and len(suppliers["1688"]) < 7:
            suppliers["1688"].append(link)

        elif "taobao.com" in link and len(suppliers["taobao"]) < 2:
            suppliers["taobao"].append(link)

        elif "alibaba.com" in link and len(suppliers["alibaba"]) < 2:
            suppliers["alibaba"].append(link)

        elif "tmall.com" in link and len(suppliers["tmall"]) < 2:
            suppliers["tmall"].append(link)

        elif "made-in-china.com" in link and len(suppliers["made"]) < 2:
            suppliers["made"].append(link)

    return suppliers


# =========================================
# FORMAT RESULT
# =========================================

def format_suppliers(data):

    text = "ТОП поставщиков\n\n"

    if data["1688"]:
        text += "1688\n"
        for i, link in enumerate(data["1688"], 1):
            text += f"{i}️⃣ {link}\n"
        text += "\n"

    if data["taobao"]:
        text += "Taobao\n"
        for link in data["taobao"]:
            text += f"{link}\n"
        text += "\n"

    if data["alibaba"]:
        text += "Alibaba\n"
        for link in data["alibaba"]:
            text += f"{link}\n"
        text += "\n"

    if data["tmall"]:
        text += "Tmall\n"
        for link in data["tmall"]:
            text += f"{link}\n"
        text += "\n"

    if data["made"]:
        text += "Made-in-China\n"
        for link in data["made"]:
            text += f"{link}\n"

    return text


# =========================================
# AI KEYWORDS
# =========================================

def generate_chinese_query(product):

    prompt = f"""
переведи товар на китайский для поиска на 1688:

{product}

ответ только одно слово
"""

    try:

        resp = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50
        )

        return resp.choices[0].message.content.strip()

    except:
        return product


# =========================================
# COMMAND START
# =========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = """
Привет! Я бот закупщика.

Что умею:
1. Поиск по названию
2. Поиск по фото
3. Китайский перевод
4. Поставщики 1688 / Taobao / Alibaba / Tmall / Made-in-China

Пример:
силиконовая форма для льда
"""

    await update.message.reply_text(text)


# =========================================
# HANDLE TEXT
# =========================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):

    product = update.message.text

    await update.message.reply_text("Ищу товар...")

    chinese = generate_chinese_query(product)

    suppliers = search_suppliers(chinese)

    result = format_suppliers(suppliers)

    await update.message.reply_text(result)


# =========================================
# HANDLE PHOTO
# =========================================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("Анализирую фото...")

    caption = update.message.caption

    if caption:
        query = generate_chinese_query(caption)
    else:
        query = "product"

    suppliers = search_suppliers(query)

    result = format_suppliers(suppliers)

    await update.message.reply_text(result)


# =========================================
# REGISTER HANDLERS
# =========================================

app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))


# =========================================
# WEBHOOK
# =========================================

@api.post("/telegram")
async def telegram_webhook(req: Request):

    data = await req.json()
    update = Update.de_json(data, bot)

    await app.process_update(update)

    return {"ok": True}


@api.get("/health")
async def health():
    return {"status": "ok"}


# =========================================
# START
# =========================================

@app.on_event("startup")
async def startup():

    webhook_url = f"{PUBLIC_BASE_URL}/telegram"
    await bot.set_webhook(webhook_url)


# =========================================
# RUN
# =========================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("bot:api", host="0.0.0.0", port=10000)
