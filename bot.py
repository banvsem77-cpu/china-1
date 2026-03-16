import urllib.parse
import json
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from huggingface_hub import InferenceClient

# =========================================================
# ВСТАВЬТЕ СВОИ КЛЮЧИ
# =========================================================
import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

# =========================================================
# HUGGING FACE CLIENT
# =========================================================
client = InferenceClient(
    provider="hf-inference",
    model="katanemo/Arch-Router-1.5B",
    token=HF_TOKEN,
)

# =========================================================
# КАЛЬКУЛЯТОР
# =========================================================
CHINA_LOCAL_DELIVERY_PER_KG = 0.35
INTERNATIONAL_DELIVERY_PER_KG = 4.50
SERVICE_FEE_PERCENT = 10

# =========================================================
# СЛУЖЕБНЫЕ ФУНКЦИИ
# =========================================================
def contains_chinese(text: str) -> bool:
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff':
            return True
    return False


def encode_cn_query(text: str) -> str:
    # Для 1688 / Taobao / Tmall используем китайскую кодировку
    return urllib.parse.quote(text.encode("gb18030"))


def encode_utf8_query(text: str) -> str:
    return urllib.parse.quote(text)


def build_market_links(main_query_cn: str):
    cn_query = encode_cn_query(main_query_cn)
    utf8_query = encode_utf8_query(main_query_cn)

    return {
        "1688": f"https://s.1688.com/selloffer/offer_search.htm?keywords={cn_query}",
        "Alibaba": f"https://www.alibaba.com/trade/search?SearchText={utf8_query}",
        "Taobao": f"https://s.taobao.com/search?q={cn_query}",
        "Tmall": f"https://list.tmall.com/search_product.htm?q={cn_query}",
    }

# =========================================================
# РЕЗЕРВНЫЙ СЛОВАРЬ
# =========================================================
def fallback_keywords(product_text: str):
    text = product_text.lower().strip()

    presets = {
        "силиконовая форма для льда": {
            "short": "硅胶冰块模具",
            "queries": [
                "硅胶冰块模具",
                "食品级硅胶制冰模具",
                "硅胶冰格模具",
                "创意冰块模具",
                "家用制冰模具",
            ],
            "main": "硅胶冰块模具",
        },
        "форма для льда": {
            "short": "冰块模具",
            "queries": [
                "冰块模具",
                "制冰模具",
                "硅胶冰格",
                "家用冰块模具",
                "创意冰块模具",
            ],
            "main": "冰块模具",
        },
        "термокружка": {
            "short": "保温杯",
            "queries": [
                "保温杯",
                "不锈钢保温杯",
                "便携保温水杯",
                "双层保温杯",
                "定制保温杯",
            ],
            "main": "保温杯",
        },
        "кружка с подогревом": {
            "short": "恒温加热杯",
            "queries": [
                "恒温加热杯",
                "电热保温杯",
                "加热马克杯",
                "暖杯器套装",
                "桌面恒温杯",
            ],
            "main": "恒温加热杯",
        },
        "бутылка для воды": {
            "short": "水杯",
            "queries": [
                "水杯",
                "运动水杯",
                "便携水壶",
                "塑料水杯",
                "不锈钢水壶",
            ],
            "main": "水杯",
        },
        "рюкзак": {
            "short": "背包",
            "queries": [
                "背包",
                "双肩包",
                "旅行背包",
                "学生书包",
                "定制背包",
            ],
            "main": "背包",
        },
        "сумка": {
            "short": "包",
            "queries": [
                "包",
                "手提包",
                "单肩包",
                "女包",
                "定制包",
            ],
            "main": "包",
        },
        "тапочки": {
            "short": "拖鞋",
            "queries": [
                "拖鞋",
                "家居拖鞋",
                "浴室拖鞋",
                "EVA拖鞋",
                "男女拖鞋",
            ],
            "main": "拖鞋",
        },
        "носки": {
            "short": "袜子",
            "queries": [
                "袜子",
                "棉袜",
                "男袜",
                "女袜",
                "运动袜",
            ],
            "main": "袜子",
        },
        "контейнер для еды": {
            "short": "饭盒",
            "queries": [
                "饭盒",
                "保鲜盒",
                "便当盒",
                "食品收纳盒",
                "塑料饭盒",
            ],
            "main": "饭盒",
        },
    }

    for key, value in presets.items():
        if key in text:
            return value

    # Если нет в словаре — не подставляем русский в китайские сайты
    return {
        "short": product_text,
        "queries": [],
        "main": "",
    }

# =========================================================
# AI-ПАРСИНГ ТОВАРА
# =========================================================
def ask_ai_for_keywords(product_text: str):
    prompt = (
        "Верни только JSON без пояснений.\n"
        "Нужно подготовить китайские запросы для поиска товара на 1688.\n\n"
        f"Товар: {product_text}\n\n"
        "Строгий формат ответа:\n"
        "{\n"
        '  "short": "китайское короткое название",\n'
        '  "queries": ["китайский запрос 1", "китайский запрос 2", "китайский запрос 3", "китайский запрос 4", "китайский запрос 5"],\n'
        '  "main": "лучший китайский запрос"\n'
        "}\n\n"
        "Правила:\n"
        "- short должен быть на китайском\n"
        "- queries только на китайском\n"
        "- main только на китайском\n"
        "- не используй русский\n"
        "- не используй английский\n"
        "- без markdown\n"
        "- без текста до JSON и после JSON"
    )

    output = client.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        max_tokens=220,
        temperature=0.2,
    )

    raw_text = output.choices[0].message.content.strip()

    start = raw_text.find("{")
    end = raw_text.rfind("}")

    if start != -1 and end != -1 and end > start:
        json_text = raw_text[start:end + 1]
        data = json.loads(json_text)

        short = str(data.get("short", "")).strip()
        queries = data.get("queries", [])
        main = str(data.get("main", "")).strip()

        if not isinstance(queries, list):
            queries = []

        queries = [str(q).strip() for q in queries if str(q).strip()]

        # Проверяем, что AI реально дал китайский
        if short and contains_chinese(short) and len(queries) >= 1 and contains_chinese(main):
            clean_queries = [q for q in queries if contains_chinese(q)]
            if clean_queries:
                return {
                    "short": short,
                    "queries": clean_queries[:5],
                    "main": main,
                }

    # Если AI ответил криво — используем резерв
    return fallback_keywords(product_text)

# =========================================================
# ФОРМАТИРОВАНИЕ ОТВЕТА
# =========================================================
def format_result(result: dict):
    short = result.get("short", "").strip()
    queries = result.get("queries", [])
    main = result.get("main", "").strip()

    if not queries:
        queries_text = "Китайские запросы не найдены"
    else:
        queries_text = "\n".join(queries)

    return (
        f"КРАТКО:\n{short}\n\n"
        f"ЗАПРОСЫ:\n{queries_text}\n\n"
        f"ОСНОВНОЙ_ЗАПРОС:\n{main}"
    )

# =========================================================
# /calc
# =========================================================
def parse_calc_text(text: str):
    parts = text.strip().split()
    if len(parts) != 4:
        return None

    try:
        unit_price = float(parts[1])
        total_weight_kg = float(parts[2])
        quantity = int(parts[3])
        return unit_price, total_weight_kg, quantity
    except ValueError:
        return None


def calculate_total(unit_price: float, total_weight_kg: float, quantity: int):
    goods_total = unit_price * quantity
    china_delivery = total_weight_kg * CHINA_LOCAL_DELIVERY_PER_KG
    intl_delivery = total_weight_kg * INTERNATIONAL_DELIVERY_PER_KG
    subtotal = goods_total + china_delivery + intl_delivery
    service_fee = subtotal * (SERVICE_FEE_PERCENT / 100)
    grand_total = subtotal + service_fee
    per_unit_total = grand_total / quantity if quantity else 0

    return {
        "goods_total": round(goods_total, 2),
        "china_delivery": round(china_delivery, 2),
        "intl_delivery": round(intl_delivery, 2),
        "service_fee": round(service_fee, 2),
        "grand_total": round(grand_total, 2),
        "per_unit_total": round(per_unit_total, 4),
    }

# =========================================================
# TELEGRAM
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "Привет! Я AI-бот закупщика.\n\n"
        "Что я умею:\n"
        "1. Делаю 5 китайских запросов для товара\n"
        "2. Даю основной китайский запрос\n"
        "3. Строю ссылки для 1688 / Alibaba / Taobao / Tmall\n"
        "4. Считаю примерную себестоимость\n\n"
        "Как пользоваться:\n"
        "— просто отправьте название товара\n"
        "— для расчета напишите: /calc цена вес количество\n\n"
        "Пример:\n"
        "силиконовая форма для льда\n\n"
        "Пример расчета:\n"
        "/calc 0.42 18 1000"
    )
    await update.message.reply_text(text)


async def calc_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parsed = parse_calc_text(update.message.text)

    if not parsed:
        await update.message.reply_text(
            "Неверный формат.\nИспользуйте так:\n/calc 0.42 18 1000"
        )
        return

    unit_price, total_weight_kg, quantity = parsed
    result = calculate_total(unit_price, total_weight_kg, quantity)

    text = (
        "Расчет готов:\n\n"
        f"Товар: ${result['goods_total']}\n"
        f"Доставка по Китаю: ${result['china_delivery']}\n"
        f"Международная доставка: ${result['intl_delivery']}\n"
        f"Комиссия: ${result['service_fee']}\n\n"
        f"ИТОГО: ${result['grand_total']}\n"
        f"Себестоимость за 1 шт: ${result['per_unit_total']}"
    )

    await update.message.reply_text(text)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    product_name = update.message.text.strip()

    if product_name.startswith("/"):
        return

    try:
        await update.message.reply_text("Ищу китайские запросы, подождите...")

        result = ask_ai_for_keywords(product_name)

        # Если AI не дал нормальный китайский запрос — резерв
        if not result.get("main") or not contains_chinese(result.get("main", "")):
            result = fallback_keywords(product_name)

        main_query = result.get("main", "").strip()

        if not main_query:
            await update.message.reply_text(
                "Не удалось подобрать китайский запрос автоматически.\n"
                "Попробуйте сформулировать товар точнее."
            )
            return

        links = build_market_links(main_query)
        ai_text = format_result(result)

        text = (
            f"{ai_text}\n\n"
            f"Ссылки для поиска:\n\n"
            f"1688:\n{links['1688']}\n\n"
            f"Alibaba:\n{links['Alibaba']}\n\n"
            f"Taobao:\n{links['Taobao']}\n\n"
            f"Tmall:\n{links['Tmall']}"
        )

        await update.message.reply_text(text)

    except Exception as e:
        fallback = fallback_keywords(product_name)

        if fallback.get("main"):
            links = build_market_links(fallback["main"])
            ai_text = format_result(fallback)

            text = (
                f"AI временно сработал некачественно, использую резервный режим.\n\n"
                f"{ai_text}\n\n"
                f"Ссылки для поиска:\n\n"
                f"1688:\n{links['1688']}\n\n"
                f"Alibaba:\n{links['Alibaba']}\n\n"
                f"Taobao:\n{links['Taobao']}\n\n"
                f"Tmall:\n{links['Tmall']}"
            )
            await update.message.reply_text(text)
        else:
            await update.message.reply_text(f"Ошибка AI: {str(e)}")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    print("Ошибка:", context.error)


def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("calc", calc_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()