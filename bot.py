# bot.py
import os
import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler

import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
import requests
from groq import Groq
from duckduckgo_search import DDGS

# === Конфиги ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_KEY")
if not TELEGRAM_TOKEN or not GROQ_KEY:
    raise RuntimeError("Missing TELEGRAM_TOKEN or GROQ_KEY env vars")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
groq_client = Groq(api_key=GROQ_KEY)

# === Хранилище истории (in-memory) ===
user_histories = {}       # user_id -> list of messages
user_roles = {}           # user_id -> role_name

ROLE_PROMPTS = {
    "Обычный": "Ты — полезный AI-ассистент. Отвечай дружелюбно.",
    "Программист": "Ты — Senior Developer. Задавай уточняющие вопросы, объясняй архитектуру, давай код с комментариями.",
    "Учитель": "Ты — учитель. Объясняй сложное простыми словами, задавай наводящие вопросы. Не давай готовых ответов на учебные задачи.",
    "Психолог": "Ты — психолог. Используй активное слушание, задавай открытые вопросы. Не давай прямых советов.",
    "СуперИИ": "Ты — СуперИИ. Отвечай глубоко, структурированно, с выводами и практическими рекомендациями.",
    "Копирайтер": "Ты — копирайтер. Пиши продающие, цепляющие тексты.",
    "Критик": "Ты — критик. Отвечай жёстко, с сарказмом, но конструктивно."
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

# === Groq текстовый вызов ===
def groq_chat(user_id, user_message, image_url=None):
    role = user_roles.get(user_id, "Обычный")
    system_prompt = ROLE_PROMPTS.get(role, ROLE_PROMPTS["Обычный"])
    
    # история (последние 10 сообщений)
    history = user_histories.get(user_id, [])
    messages = [{"role": "system", "content": system_prompt}] + history[-10:] + [{"role": "user", "content": user_message}]
    
    try:
        if image_url:
            # vision-модель
            response = groq_client.chat.completions.create(
                model="llama-3.2-90b-vision-preview",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message, "image_url": image_url}
                ],
                temperature=0.7,
                max_tokens=1024
            )
        else:
            response = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=0.7,
                max_tokens=1024
            )
        reply = response.choices[0].message.content
        # сохранять историю
        user_histories.setdefault(user_id, []).append({"role": "user", "content": user_message})
        user_histories[user_id].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        return f"❌ Ошибка AI: {str(e)}"

# === Генерация картинки ===
def generate_image(prompt):
    url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
    # pollinations возвращает картинку, но иногда падает. Делаем проверку.
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code == 200 and resp.headers.get('content-type', '').startswith('image/'):
            return url  # возвращаем прямую ссылку (telegram умеет отправлять по ссылке)
        return None
    except:
        return None

# === Поиск DuckDuckGo ===
def search_web(query):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
            if not results:
                return "Ничего не найдено."
            answer = ""
            for r in results:
                answer += f"🔹 *{r['title']}*\n{r['body'][:300]}\n{r['href']}\n\n"
            return answer
    except Exception as e:
        return f"Ошибка поиска: {str(e)}"

# === Обработчики команд ===
@bot.message_handler(commands=['start'])
def start_cmd(msg):
    user_id = msg.from_user.id
    user_histories[user_id] = []
    user_roles[user_id] = "Обычный"
    bot.send_message(user_id, "Привет! Я AI-бот с ролями. Выбери режим кнопками.", reply_markup=main_keyboard())

@bot.message_handler(commands=['img'])
def img_cmd(msg):
    prompt = msg.text.replace('/img', '').strip()
    if not prompt:
        bot.reply_to(msg, "Напиши описание после /img, например: /img кот в космосе")
        return
    bot.reply_to(msg, "🖼 Генерирую картинку...")
    url = generate_image(prompt)
    if url:
        bot.send_photo(msg.chat.id, url, caption=f"🎨 {prompt}")
    else:
        bot.reply_to(msg, "Не удалось сгенерировать картинку. Попробуй другое описание.")

@bot.message_handler(commands=['internet'])
def internet_cmd(msg):
    query = msg.text.replace('/internet', '').strip()
    if not query:
        bot.reply_to(msg, "Введи запрос после /internet, например: /internet новости ИИ")
        return
    bot.reply_to(msg, "🔍 Ищу...")
    res = search_web(query)
    bot.send_message(msg.chat.id, res, parse_mode="Markdown")

@bot.message_handler(content_types=['voice'])
def handle_voice(msg):
    bot.reply_to(msg, "🎤 Распознаю голос...")
    try:
        file_info = bot.get_file(msg.voice.file_id)
        file_bytes = bot.download_file(file_info.file_path)
        # Groq whisper принимает файл
        temp_path = f"/tmp/voice_{msg.from_user.id}.ogg"
        with open(temp_path, "wb") as f:
            f.write(file_bytes)
        with open(temp_path, "rb") as f:
            transcription = groq_client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=f,
                response_format="text"
            )
        os.remove(temp_path)
        text = transcription if isinstance(transcription, str) else transcription.text
        bot.reply_to(msg, f"📝 Распознанный текст:\n{text}")
        # автоматически ответим тем же AI (чтобы история сохранилась)
        reply = groq_chat(msg.from_user.id, text)
        bot.send_message(msg.chat.id, reply, reply_markup=main_keyboard())
    except Exception as e:
        bot.reply_to(msg, f"Ошибка распознавания: {str(e)}")

@bot.message_handler(content_types=['photo'])
def handle_photo(msg):
    if not msg.caption:
        bot.reply_to(msg, "Напиши вопрос к фото (caption). Например: 'Что здесь изображено?'")
        return
    user_id = msg.from_user.id
    # получаем ссылку на фото (Telegram file_id -> прямой URL через API)
    file_id = msg.photo[-1].file_id
    file_info = bot.get_file(file_id)
    file_url = f"https://api.telegram.org/file/bot{TELEGRAM_TOKEN}/{file_info.file_path}"
    # Groq vision требует base64 или URL. Передадим URL напрямую (не public? но для groq работает если изображение доступно)
    # Иногда Telegram file_url недоступен извне — лучше пересохранить, но для простоты используем как есть
    bot.reply_to(msg, "🤖 Анализирую фото...")
    answer = groq_chat(user_id, msg.caption, image_url=file_url)
    bot.send_message(msg.chat.id, answer, reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: True)
def handle_text(msg):
    user_id = msg.from_user.id
    text = msg.text.strip()
    
    if text in ROLE_PROMPTS.keys():
        user_roles[user_id] = text
        bot.reply_to(msg, f"✅ Режим переключён на: {text}")
        return
    
    if text == "Очистить":
        user_histories[user_id] = []
        bot.reply_to(msg, "🧹 История диалога очищена.")
        return
    
    if text == "Картинка":
        bot.reply_to(msg, "🎨 Для генерации картинки используй команду:\n`/img описание картинки`\nПример: `/img закат над морем`", parse_mode="Markdown")
        return
    
    if text == "Поиск":
        bot.reply_to(msg, "🔎 Для поиска в интернете используй команду:\n`/internet запрос`\nПример: `/internet рецепт пиццы`", parse_mode="Markdown")
        return
    
    if text == "Голос":
        bot.reply_to(msg, "🎙 Отправь мне голосовое сообщение, я распознаю речь.")
        return
    
    # обычный чат
    bot.send_chat_action(user_id, 'typing')
    answer = groq_chat(user_id, text)
    bot.send_message(user_id, answer, reply_markup=main_keyboard())

# === HTTP-сервер для keep-alive ===
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'OK')
        else:
            self.send_response(404)
    
    def log_message(self, format, *args):
        pass  # тишина в логах

def run_http():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    server.serve_forever()

# === Запуск ===
if __name__ == "__main__":
    threading.Thread(target=run_http, daemon=True).start()
    print("Бот запущен, health-сервер на порту", os.environ.get("PORT", 10000))
    bot.infinity_polling()
