import telebot
import google.generativeai as genai
import requests
import os
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ==================== НАСТРОЙКИ ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")
GROQ_KEY = os.getenv("GROQ_KEY", "")

genai.configure(api_key=GEMINI_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ==================== УНИВЕРСАЛЬНЫЙ СИСТЕМНЫЙ ПРОМПТ ====================
SYSTEM_PROMPT = """Ты — универсальный AI-ассистент. Ты умеешь всё:

1. **Сочинения и тексты** — пишешь грамотно, с аргументами и примерами.
2. **Задачи (математика, физика, химия)** — решаешь пошагово с пояснениями.
3. **Таблицы** — если просят таблицу, то делай как надо. 

4. **Программирование** — пишешь чистый код с комментариями.
5. **Объяснения** — объясняешь сложное простым языком.
6. **Фото** — если пользователь прислал фото, анализируешь его.

Ты всегда отвечаешь на русском языке. Отвечай чётко, структурированно, по делу."""

# Хранилище истории диалогов
user_states = {}

# ==================== ВЕБ-СЕРВЕР ДЛЯ UPTIMEROBOT ====================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK - bot is alive")
    def log_message(self, format, *args):
        pass

def run_health():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    server.serve_forever()

# ======================================================================
#                           КОМАНДЫ
# ======================================================================

@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    user_states[uid] = {"history": []}
    
    # Убираем ReplyKeyboardRemove — клавиатура не нужна
    kb = telebot.types.ReplyKeyboardRemove()
    
    bot.send_message(uid,
        "👋 *Привет! Я — универсальный AI-ассистент!*\n\n"
        "Я умею:\n"
        "📝 Писать сочинения и тексты\n"
        "🔢 Решать задачи по математике, физике, химии\n"
        "📊 Делать таблицы\n"
        "💻 Писать код\n"
        "🖼 Анализировать фото (просто пришли мне картинку)\n"
        "🎤 Переводить голосовые в текст\n"
        "📄 Читать файлы (txt, csv, pdf)\n\n"
        "*Просто напиши мне любой вопрос или пришли фото!*",
        parse_mode="Markdown",
        reply_markup=kb
    )

@bot.message_handler(commands=['clear'])
def cmd_clear(message):
    uid = message.chat.id
    if uid in user_states:
        user_states[uid]["history"] = []
    bot.reply_to(message, "🧹 История диалога очищена.")

@bot.message_handler(commands=['img'])
def cmd_img(message):
    prompt = message.text.replace("/img", "").strip()
    if not prompt:
        bot.reply_to(message, "⚠️ Используй: /img <описание>\nПример: /img кот в очках")
        return
    msg = bot.reply_to(message, "🎨 Генерирую изображение...")
    try:
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true"
        resp = requests.get(url, timeout=30)
        bot.send_photo(message.chat.id, resp.content, caption=f"🖼 {prompt}")
        bot.delete_message(msg.chat.id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка генерации: {e}", msg.chat.id, msg.message_id)

# ======================================================================
#                      ОСНОВНОЙ ЧАТ (ТЕКСТ)
# ======================================================================

@bot.message_handler(content_types=['text'])
def chat(message):
    uid = message.chat.id
    if uid not in user_states:
        user_states[uid] = {"history": []}

    state = user_states[uid]

    # Создаём модель с системным промптом
    model = genai.GenerativeModel(
        model_name="models/gemini-2.0-flash",
        system_instruction=SYSTEM_PROMPT
    )

    # История диалога (последние 30 сообщений)
    history = state["history"][-30:]
    chat_session = model.start_chat(history=history)

    try:
        resp = chat_session.send_message(message.text)
        bot.reply_to(message, resp.text, parse_mode="Markdown")

        # Сохраняем в историю
        state["history"].append({"role": "user", "parts": [message.text]})
        state["history"].append({"role": "model", "parts": [resp.text]})

    except Exception as e:
        error_str = str(e)
        if "not found" in error_str:
            bot.reply_to(message, "⚠️ Ошибка модели. Попробуй ещё раз через минуту.")
        else:
            bot.reply_to(message, f"⚠️ Ошибка: {e}")

# ======================================================================
#                      АНАЛИЗ ФОТО
# ======================================================================

@bot.message_handler(content_types=['photo'])
def photo(message):
    uid = message.chat.id
    if uid not in user_states:
        user_states[uid] = {"history": []}

    processing = bot.reply_to(message, "🔍 Анализирую фото...")

    # Скачиваем
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded = bot.download_file(file_info.file_path)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(downloaded)
        tmp_path = tmp.name

    try:
        uploaded = genai.upload_file(tmp_path)

        model = genai.GenerativeModel(
            model_name="models/gemini-2.0-flash",
            system_instruction=SYSTEM_PROMPT
        )

        # Если есть подпись к фото — используем как задание
        if message.caption:
            prompt = message.caption
        else:
            prompt = "Опиши подробно, что на этом фото. Если там текст — прочитай его полностью. Если там задача — реши её. Если таблица — проанализируй данные."

        resp = model.generate_content([prompt, uploaded])
        bot.edit_message_text(resp.text, uid, processing.message_id, parse_mode="Markdown")

    except Exception as e:
        bot.edit_message_text(f"⚠️ Ошибка анализа: {e}", uid, processing.message_id)
    finally:
        os.unlink(tmp_path)

# ======================================================================
#                      ГОЛОСОВЫЕ В ТЕКСТ
# ======================================================================

@bot.message_handler(content_types=['voice', 'audio'])
def voice(message):
    uid = message.chat.id
    processing = bot.reply_to(message, "🎤 Распознаю речь...")

    file_id = message.voice.file_id if message.voice else message.audio.file_id
    file_info = bot.get_file(file_id)
    downloaded = bot.download_file(file_info.file_path)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp.write(downloaded)
        tmp_path = tmp.name

    try:
        if GROQ_KEY and GROQ_KEY != "none":
            import groq
            client = groq.Groq(api_key=GROQ_KEY)
            with open(tmp_path, "rb") as f:
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo", file=f, language="ru"
                )
            text = transcription.text
        else:
            text = "⚠️ Ключ Groq не указан. Распознавание недоступно."

        bot.edit_message_text(f"📝 *Распознано:*\n\n{text}", uid, processing.message_id, parse_mode="Markdown")

        if uid in user_states and text and not text.startswith("⚠️"):
            user_states[uid]["history"].append({"role": "user", "parts": [text]})
    except Exception as e:
        bot.edit_message_text(f"⚠️ Ошибка распознавания: {e}", uid, processing.message_id)
    finally:
        os.unlink(tmp_path)

# ======================================================================
#                      ЧТЕНИЕ ДОКУМЕНТОВ
# ======================================================================

@bot.message_handler(content_types=['document'])
def doc(message):
    uid = message.chat.id
    if uid not in user_states:
        user_states[uid] = {"history": []}

    file_info = bot.get_file(message.document.file_id)
    downloaded = bot.download_file(file_info.file_path)
    fname = message.document.file_name

    with tempfile.NamedTemporaryFile(suffix="." + fname.split(".")[-1], delete=False) as tmp:
        tmp.write(downloaded)
        tmp_path = tmp.name

    processing = bot.reply_to(message, f"📄 Читаю файл *{fname}*...", parse_mode="Markdown")

    try:
        uploaded = genai.upload_file(tmp_path)

        model = genai.GenerativeModel(
            model_name="models/gemini-2.0-flash",
            system_instruction=SYSTEM_PROMPT
        )

        caption = message.caption or f"Проанализируй содержимое файла {fname}. Если это CSV или таблица — опиши данные и предложи анализ. Если текстовый файл — перескажи суть."
        resp = model.generate_content([caption, uploaded])
        bot.edit_message_text(resp.text, uid, processing.message_id, parse_mode="Markdown")
    except Exception as e:
        bot.edit_message_text(f"⚠️ Ошибка: {e}", uid, processing.message_id)
    finally:
        os.unlink(tmp_path)

# ======================================================================
#                           ЗАПУСК
# ======================================================================

if __name__ == "__main__":
    print("Запуск health-сервера...")
    threading.Thread(target=run_health, daemon=True).start()
    print("Запуск бота...")
    bot.infinity_polling()
