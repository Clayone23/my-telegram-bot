# bot.py — полная версия для Railway
import os
import json
import time
import base64
import io
from datetime import datetime

import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import requests
from duckduckgo_search import DDGS

# === Конфигурация ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not TELEGRAM_TOKEN or not GROQ_API_KEY:
    raise RuntimeError("Missing TELEGRAM_TOKEN or GROQ_API_KEY env vars")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# === Хранилище ===
user_histories = {}
user_roles = {}

# === Роли и их промпты ===
ROLE_PROMPTS = {
    "Обычный": "Ты — полезный AI-ассистент. Отвечай дружелюбно и по делу.",
    "Программист": "Ты — Senior Developer с 10+ годами опыта. Задавай уточняющие вопросы, объясняй архитектуру, давай код с комментариями.",
    "Учитель": "Ты — учитель. Объясняй сложное простыми словами с примерами. Не давай готовых ответов на учебные задачи, направляй наводящими вопросами.",
    "Психолог": "Ты — психолог. Используй активное слушание, задавай открытые вопросы. Не давай прямых советов, помогай человеку самому найти решение.",
    "СуперИИ": "Ты — СуперИИ. Отвечай максимально глубоко, структурированно, с выводами и практическими рекомендациями.",
    "Копирайтер": "Ты — копирайтер. Пиши продающие, цепляющие, убедительные тексты.",
    "Критик": "Ты — критик. Отвечай жёстко, с сарказмом, но конструктивно разбирай присланное."
}

# === Клавиатура ===
def main_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [
        "Обычный", "Программист", "Учитель",
        "Психолог", "СуперИИ", "Копирайтер",
        "Критик", "Картинка", "Поиск",
        "Голос", "Очистить"
    ]
    kb.add(*buttons)
    return kb

# === Прямой вызов Groq API (без библиотеки) ===
def groq_chat(user_id: int, user_message: str, image_base64: str = None) -> str:
    role = user_roles.get(user_id, "Обычный")
    system_prompt = ROLE_PROMPTS.get(role, ROLE_PROMPTS["Обычный"])
    
    # Получаем историю (последние 10 сообщений)
    history = user_histories.get(user_id, [])
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-10:])
    
    # Формируем запрос пользователя (с поддержкой изображений)
    if image_base64:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_message},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
            ]
        })
        model = "llama-3.2-90b-vision-preview"
    else:
        messages.append({"role": "user", "content": user_message})
        model = "llama-3.1-8b-instant"
    
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024
    }
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        
        if response.status_code != 200:
            return f"❌ Ошибка Groq API: {response.status_code} - {response.text[:200]}"
        
        result = response.json()
        reply = result["choices"][0]["message"]["content"]
        
        # Сохраняем историю
        user_histories.setdefault(user_id, []).append({"role": "user", "content": user_message})
        user_histories[user_id].append({"role": "assistant", "content": reply})
        
        # Ограничиваем историю 20 сообщениями (10 пар)
        if len(user_histories[user_id]) > 20:
            user_histories[user_id] = user_histories[user_id][-20:]
        
        return reply
        
    except requests.exceptions.Timeout:
        return "⏰ Таймаут. Groq API не ответил в течение 60 секунд. Попробуй позже."
    except Exception as e:
        return f"❌ Ошибка при запросе к Groq: {str(e)}"

# === Генерация картинки через Pollinations ===
def generate_image(prompt: str) -> str:
    try:
        encoded_prompt = requests.utils.quote(prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
        
        # Проверяем, что возвращается именно картинка
        response = requests.get(url, timeout=30)
        if response.status_code == 200 and response.headers.get('content-type', '').startswith('image/'):
            return url
        return None
    except Exception as e:
        print(f"Image gen error: {e}")
        return None

# === Поиск через DuckDuckGo ===
def search_web(query: str) -> str:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            if not results:
                return "🔍 Ничего не найдено."
            
            answer = ""
            for r in results:
                answer += f"🔹 *{r['title']}*\n{r['body'][:300]}\n{r['href']}\n\n"
            return answer
    except Exception as e:
        return f"❌ Ошибка поиска: {str(e)}"

# === Преобразование голоса через Groq Whisper ===
def transcribe_voice(file_bytes: bytes) -> str:
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }
    
    files = {
        "file": ("voice.ogg", file_bytes, "audio/ogg"),
        "model": (None, "whisper-large-v3-turbo"),
        "response_format": (None, "text")
    }
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/audio/transcriptions",
            headers=headers,
            files=files,
            timeout=60
        )
        
        if response.status_code != 200:
            return f"Ошибка распознавания: {response.status_code}"
        
        return response.text.strip()
    except Exception as e:
        return f"Ошибка: {str(e)}"

# === Обработчики команд ===
@bot.message_handler(commands=['start'])
def start_cmd(message):
    user_id = message.from_user.id
    user_histories[user_id] = []
    user_roles[user_id] = "Обычный"
    bot.send_message(
        user_id,
        "🌟 Привет! Я AI-бот с разными ролями.\n\n"
        "📌 Выбери режим кнопками ниже.\n"
        "🎨 /img описание — сгенерировать картинку\n"
        "🔍 /internet запрос — поиск в интернете\n"
        "🎤 Отправь голосовое — я распознаю речь\n"
        "📸 Отправь фото с вопросом — опишу что на нём",
        reply_markup=main_keyboard()
    )

@bot.message_handler(commands=['img'])
def img_cmd(message):
    prompt = message.text.replace('/img', '').strip()
    if not prompt:
        bot.reply_to(message, "📝 Напиши описание после /img\nПример: `/img кот в космосе`", parse_mode="Markdown")
        return
    
    bot.reply_to(message, "🎨 Генерирую картинку... (до 30 секунд)")
    url = generate_image(prompt)
    
    if url:
        bot.send_photo(message.chat.id, url, caption=f"🖼 *{prompt}*", parse_mode="Markdown")
    else:
        bot.reply_to(message, "❌ Не удалось сгенерировать картинку. Попробуй другое описание или позже.")

@bot.message_handler(commands=['internet'])
def internet_cmd(message):
    query = message.text.replace('/internet', '').strip()
    if not query:
        bot.reply_to(message, "📝 Введи запрос после /internet\nПример: `/internet новости ИИ 2025`", parse_mode="Markdown")
        return
    
    bot.reply_to(message, "🔍 Ищу в интернете...")
    result = search_web(query)
    bot.send_message(message.chat.id, result, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    user_id = message.from_user.id
    
    bot.reply_to(message, "🎤 Распознаю голосовое сообщение...")
    
    try:
        file_info = bot.get_file(message.voice.file_id)
        file_bytes = bot.download_file(file_info.file_path)
        
        text = transcribe_voice(file_bytes)
        
        if "Ошибка" in text or "error" in text.lower():
            bot.reply_to(message, f"❌ {text}")
            return
        
        bot.reply_to(message, f"📝 *Распознанный текст:*\n{text}", parse_mode="Markdown")
        
        # Отвечаем AI на распознанный текст
        bot.send_chat_action(user_id, 'typing')
        answer = groq_chat(user_id, text)
        bot.send_message(user_id, answer, reply_markup=main_keyboard())
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при обработке голосового: {str(e)}")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    user_id = message.from_user.id
    
    if not message.caption:
        bot.reply_to(message, "📝 Напиши вопрос к фото в подписи. Например: «Что здесь изображено?»")
        return
    
    bot.reply_to(message, "🖼 Анализирую фотографию... (до 30 секунд)")
    
    try:
        # Скачиваем фото
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_bytes = bot.download_file(file_info.file_path)
        
        # Конвертируем в base64
        base64_image = base64.b64encode(file_bytes).decode('utf-8')
        
        # Отправляем в Groq Vision
        answer = groq_chat(user_id, message.caption, image_base64=base64_image)
        bot.send_message(user_id, answer, reply_markup=main_keyboard())
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при анализе фото: {str(e)}")

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Переключение ролей
    if text in ROLE_PROMPTS:
        user_roles[user_id] = text
        bot.reply_to(message, f"✅ Режим переключён на: *{text}*", parse_mode="Markdown")
        return
    
    # Очистка истории
    if text == "Очистить":
        user_histories[user_id] = []
        bot.reply_to(message, "🧹 История диалога очищена!")
        return
    
    # Информационные кнопки
    if text == "Картинка":
        bot.reply_to(message, "🎨 *Генерация картинок*\n\nКоманда: `/img описание`\nПример: `/img закат над морем`\n\nСервис: Pollinations.ai (бесплатно)", parse_mode="Markdown")
        return
    
    if text == "Поиск":
        bot.reply_to(message, "🔍 *Поиск в интернете*\n\nКоманда: `/internet запрос`\nПример: `/internet рецепт пиццы`\n\nЧерез DuckDuckGo (без ключей)", parse_mode="Markdown")
        return
    
    if text == "Голос":
        bot.reply_to(message, "🎤 *Голосовые сообщения*\n\nПросто отправь мне голосовое сообщение, и я распознаю речь через Whisper AI.\n\nПосле распознавания я отвечу на текст как в обычном чате.", parse_mode="Markdown")
        return
    
    # Обычный диалог
    bot.send_chat_action(user_id, 'typing')
    answer = groq_chat(user_id, text)
    bot.send_message(user_id, answer, reply_markup=main_keyboard())

# === Запуск ===
if __name__ == "__main__":
    print("🤖 Бот запущен на Railway!")
    print(f"📡 Режим: polling (вебхук не используется)")
    print("✅ Готов к работе")
    
    # Для Railway не нужен health-сервер — он не засыпает
    # Но оставим на всякий случай для мониторинга
    from http.server import HTTPServer, BaseHTTPRequestHandler
    
    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/health':
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'OK')
            else:
                self.send_response(404)
        def log_message(self, format, *args):
            pass
    
    import threading
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: HTTPServer(('0.0.0.0', port), HealthHandler).serve_forever(), daemon=True).start()
    
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
