import logging
import requests
import asyncio
import nest_asyncio
import re
import os
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from telegram.error import InvalidToken

# --- Данные ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ALLOWED_CHAT_ID = int(os.getenv("ALLOWED_CHAT_ID"))

logging.basicConfig(level=logging.INFO)

# История чатов
chat_history = {}
keyword_mode = {}  # Режим для каждого чата

# --- Функция автоформатирования ответа ---
def format_keywords(text):
    # Если это стандартный ответ "Пожалуйста отправьте...", возвращаем без изменений
    if "пожалуйста отправьте" in text.lower():
        return "Пожалуйста отправьте название категории, я подберу ключевые слова"

    # Удаляем лишние пробелы и приводим к нижнему регистру
    text = text.strip().lower()

    # Заменяем пробелы на /
    text = text.replace(" ", "/")

    # Убираем повторяющиеся слэши
    text = re.sub(r'/+', '/', text)

    # Разделяем на слова
    words = text.split("/")

    # Убираем повторы слов и дублирующиеся предлоги
    prepositions = {"для", "под", "в", "на", "с", "к"}
    seen = set()
    seen_preps = set()
    cleaned_words = []
    for word in words:
        if word in prepositions:
            if word not in seen_preps:
                cleaned_words.append(word)
                seen_preps.add(word)
        else:
            if word not in seen:
                cleaned_words.append(word)
                seen.add(word)

    # Склеиваем обратно
    result = "/".join(cleaned_words)

    # Финальная очистка
    result = re.sub(r'/+', '/', result).strip("/")

    return result

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    user_text = update.message.text.strip()

    # Ограничение доступа
    if chat_id != ALLOWED_CHAT_ID:
        await update.message.reply_text("⛔ У вас нет доступа к этому боту.")
        return

    # --- Управление режимами ---
    if user_text.lower() == "profbs admin":
        keyword_mode[chat_id] = False
        await update.message.reply_text("🔓 Бот переведен в обычный режим GPT.")
        return

    if user_text.lower() == "profbs admin start":
        keyword_mode[chat_id] = True
        await update.message.reply_text("🎯 Бот снова в режиме подбора ключевых слов.")
        return

    # Устанавливаем режим по умолчанию
    if chat_id not in keyword_mode:
        keyword_mode[chat_id] = True

    # Инициализация истории
    if chat_id not in chat_history:
        chat_history[chat_id] = []

    # --- Режим подбора ключевых слов ---
    if keyword_mode[chat_id]:
        system_prompt = """
🎯 Промт: Помощник по подбору ключевых слов
Ты — специализированный помощник по подбору ключевых слов для категорий товаров.

📌 Как формируются ключевые слова:
Ключевые слова формируются на основе реальных поисковых запросов с маркетплейсов (Wildberries, Ozon и др.) и поисковых систем.

Приоритет: высокочастотные и среднечастотные запросы, отражающие реальную речь покупателей.

Включаем:
- Сленг: бытовые сокращения и разговорные формы.
- Популярные ошибки.
- Родственные поиски: часто встречающиеся слова по контексту категории.

Исключаем: бренды, модели, дубли по смыслу.

Количество: 18–20 ключей.

🖋 Формат ответа:
- Только одна строка.
- Каждое слово или часть словосочетания разделяется / (например: "беспроводные/наушники", "наушники/для/музыки").
- Предлоги (для, в, на, под, с) используются только 1 раз.
- Запрещены повторы слов.
- Начинаем с названия категории.

🔒 Ограничения:
На все запросы, не являющиеся названием категории, отвечай:
"Пожалуйста отправьте название категории, я подберу ключевые слова".
"""
    else:
        system_prompt = "Ты — умный и дружелюбный помощник на GPT-4o."

    chat_history[chat_id].append({"role": "user", "content": user_text})

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4o",
                "messages": [{"role": "system", "content": system_prompt}] + chat_history[chat_id],
                "max_tokens": 500
            }
        )

        logging.info(f"API ответ: {response.text}")
        data = response.json()

        if "choices" in data:
            bot_reply = data["choices"][0]["message"]["content"]
            bot_reply = format_keywords(bot_reply)
            chat_history[chat_id].append({"role": "assistant", "content": bot_reply})
        else:
            bot_reply = f"Ошибка API: {data}"

    except Exception as e:
        bot_reply = f"Ошибка: {e}"

    await update.message.reply_text(bot_reply)

async def main():
    nest_asyncio.apply()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
