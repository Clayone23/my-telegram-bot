import telebot
import google.generativeai as genai
import requests
import os
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from duckduckgo_search import DDGS

# ==================== НАСТРОЙКИ ====================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")
GROQ_KEY = os.getenv("GROQ_KEY")

genai.configure(api_key=GEMINI_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# ==================== РОЛИ ====================
ROLES = {
    "default": "Ты — полезный ассистент. Отвечай чётко, на русском языке. Помогай с любыми вопросами.",
    "programmer": """Ты Senior Developer с 15-летним опытом. Ты получаешь техническое задание и делаешь следующее:
1. Задаёшь уточняющие вопросы, если ТЗ размыто
2. Объясняешь архитектуру решения ДО написания кода
3. Пишешь чистый, документированный код с type hints и обработкой ошибок
4. Объясняешь, как запустить и протестировать код""",
    "teacher": "Ты — терпеливый школьный учитель. Объясняешь сложные вещи простым языком с примерами. Если ученик просит решить задачу — не даёшь готовый ответ, а направляешь наводящими вопросами. Хвалишь за успехи.",
    "psychologist": "Ты — эмпатичный психолог с 20-летним стажем. Используешь активное слушание. Не даёшь прямых советов, а задаёшь открытые вопросы. Помогаешь человеку самому найти решение. Всегда поддерживаешь.",
    "superai": "Ты — ИИ экспертного уровня. Отвечаешь максимально глубоко, структурированно. Используешь нумерованные списки и чёткие выводы. Думаешь на 10 шагов вперёд. Даёшь практические рекомендации.",
    "copywriter": "Ты — профессиональный копирайтер. Пишешь цепляющие, продающие тексты. Создаёшь качественные заголовки. Используешь AIDA и другие формулы. Адаптируешь стиль под аудиторию.",
    "critic": "Ты — суровый критик в стиле Гордона Рамзи. Жёстко, с сарказмом, но конструктивно разбираешь присланный текст или идею. Указываешь на все слабые места и говоришь как исправить.",
}

user_states = {}

# ==================== КЛАВИАТУРЫ ====================
def main_keyboard():
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("💻 Программист", "🤖 Обычный")
    kb.add("🎭 Роли", "🖼 Картинка")
    kb.add("🧠 СуперИИ", "🔍 Поиск")
    kb.add("🎤 Голос")
    return kb

def roles_keyboard():
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("👨‍🏫 Учитель", "🧑‍💻 Программист")
    kb.add("🧠 Психолог", "🦸 СуперИИ")
    kb.add("✍️ Копирайтер", "🔥 Критик")
    kb.add("🤖 Обычный", "⬅ Назад")
    return kb

# ==================== ВЕБ-СЕРВЕР ====================
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
    print(f"Health server on port {port}")
    server.serve_forever()

# ==================== КОМАНДЫ ====================
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    user_states[uid] = {"role": "default", "history": []}
    bot.send_message(uid,
        "👋 *Привет! Я твой AI-ассистент!*\n\n"
        "Выбери режим работы кнопками ниже:\n\n"
        "💻 Программист — пишет код как Senior\n"
        "🎭 Роли — учитель, психолог, критик и др.\n"
        "🖼 Картинка — анализ фото и генерация\n"
        "🔍 Поиск — ищет в интернете\n"
        "🎤 Голос — переводит речь в текст",
        parse_mode="Markdown",
        reply_markup=main_keyboard()
    )

@bot.message_handler(commands=['img'])
def cmd_img(message):
    prompt = message.text.replace("/img", "").strip()
    if not prompt:
        bot.reply_to(message, "⚠️ Напиши: /img <описание>\nПример: /img кот в очках")
        return
    msg = bot.reply_to(message, "🎨 Рисую...")
    try:
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true"
        resp = requests.get(url, timeout=30)
        bot.send_photo(message.chat.id, resp.content, caption=f"🖼 {prompt}")
        bot.delete_message(msg.chat.id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ Ошибка: {e}", msg.chat.id, msg.message_id)

@bot.message_handler(commands=['internet'])
def cmd_internet(message):
    query = message.text.replace("/internet", "").strip()
    if not query:
        bot.reply_to(message, "⚠️ Напиши: /internet <запрос>\nПример: /internet погода в Москве")
        return
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            bot.reply_to(message, "🔍 Ничего не найдено.")
            return
        answer = f"🔍 *Результаты по запросу: {query}*\n\n"
        for i, r in enumerate(results, 1):
            answer += f"{i}️⃣ [{r['title']}]({r['href']})\n{r['body'][:200]}...\n\n"
        bot.reply_to(message, answer, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['clear'])
def cmd_clear(message):
    uid = message.chat.id
    if uid in user_states:
        user_states[uid]["history"] = []
    bot.reply_to(message, "🧹 История диалога очищена.")

# ==================== НАВИГАЦИЯ ====================
@bot.message_handler(func=lambda m: m.text == "💻 Программист")
def nav_prog(m):
    user_states[m.chat.id] = {"role": "programmer", "history": []}
    bot.reply_to(m, "💻 *Режим Senior Developer.*\nОпиши задачу — объясню архитектуру и напишу код.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🤖 Обычный")
def nav_def(m):
    user_states[m.chat.id] = {"role": "default", "history": []}
    bot.reply_to(m, "🤖 *Обычный режим.* Задавай любой вопрос.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🧠 СуперИИ")
def nav_super(m):
    user_states[m.chat.id] = {"role": "superai", "history": []}
    bot.reply_to(m, "🧠 *СуперИИ активирован.* Отвечаю максимально глубоко.", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎭 Роли")
def nav_roles(m):
    bot.reply_to(m, "🎭 *Выбери роль для ИИ:*", parse_mode="Markdown", reply_markup=roles_keyboard())

@bot.message_handler(func=lambda m: m.text == "⬅ Назад")
def nav_back(m):
    bot.reply_to(m, "🏠 Главное меню:", reply_markup=main_keyboard())

@bot.message_handler(func=lambda m: m.text == "🖼 Картинка")
def nav_img(m):
    bot.reply_to(m, "🖼 *Работа с изображениями:*\n\n• Отправь описание — сгенерирую\n• Отправь фото — проанализирую\n• /img <описание> — быстрая генерация", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🔍 Поиск")
def nav_search(m):
    bot.reply_to(m, "🔍 *Поиск в интернете:*\n\nНапиши что найти или /internet <запрос>", parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "🎤 Голос")
def nav_voice(m):
    bot.reply_to(m, "🎤 *Распознавание речи:*\nОтправь голосовое сообщение — переведу в текст.", parse_mode="Markdown")

role_btns = ["👨‍🏫 Учитель", "🧑‍💻 Программист", "🧠 Психолог", "🦸 СуперИИ", "✍️ Копирайтер", "🔥 Критик", "🤖 Обычный"]
role_map = {
    "👨‍🏫 Учитель": "teacher", "🧑‍💻 Программист": "programmer",
    "🧠 Психолог": "psychologist", "🦸 СуперИИ": "superai",
    "✍️ Копирайтер": "copywriter", "🔥 Критик": "critic",
    "🤖 Обычный": "default"
}

@bot.message_handler(func=lambda m: m.text in role_btns)
def set_role(m):
    uid = m.chat.id
    user_states[uid] = {"role": role_map[m.text], "history": []}
    bot.reply_to(m, f"✅ *Роль:* {m.text}\nЖду вопрос.", parse_mode="Markdown", reply_markup=main_keyboard())

# ==================== ЧАТ ====================
@bot.message_handler(content_types=['text'])
def chat(message):
    uid = message.chat.id
    if uid not in user_states:
        user_states[uid] = {"role": "default", "history": []}

    state = user_states[uid]
    system_prompt = ROLES.get(state["role"], ROLES["default"])

    model = genai.GenerativeModel(
        model_name="gemini-2.0-flash",
        system_instruction=system_prompt
    )

    history = state["history"][-20:]
    chat_session = model.start_chat(history=history)

    try:
        resp = chat_session.send_message(message.text)
        bot.reply_to(message, resp.text, parse_mode="Markdown")
        state["history"].append({"role": "user", "parts": [message.text]})
        state["history"].append({"role": "model", "parts": [resp.text]})
    except Exception as e:
        bot.reply_to(message, f"⚠️ Ошибка: {e}")

# ==================== ФОТО ====================
@bot.message_handler(content_types=['photo'])
def photo(message):
    uid = message.chat.id
    if uid not in user_states:
        user_states[uid] = {"role": "default", "history": []}

    processing = bot.reply_to(message, "🔍 Анализирую фото...")
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded = bot.download_file(file_info.file_path)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(downloaded)
        tmp_path = tmp.name

    try:
        uploaded = genai.upload_file(tmp_path)
        model = genai.GenerativeModel("gemini-2.0-flash")
        caption = message.caption or "Опиши подробно, что на этом фото. Если есть текст — прочитай его."
        resp = model.generate_content([caption, uploaded])
        bot.edit_message_text(resp.text, uid, processing.message_id, parse_mode="Markdown")
    except Exception as e:
        bot.edit_message_text(f"⚠️ Ошибка: {e}", uid, processing.message_id)
    finally:
        os.unlink(tmp_path)

# ==================== ГОЛОСОВЫЕ ====================
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
        if GROQ_KEY:
            import groq
            client = groq.Groq(api_key=GROQ_KEY)
            with open(tmp_path, "rb") as f:
                transcription = client.audio.transcriptions.create(
                    model="whisper-large-v3-turbo", file=f, language="ru"
                )
            text = transcription.text
        else:
            text = "⚠️ Не указан ключ Groq."
        bot.edit_message_text(f"📝 *Распознано:*\n\n{text}", uid, processing.message_id, parse_mode="Markdown")
        if uid in user_states and GROQ_KEY:
            user_states[uid]["history"].append({"role": "user", "parts": [text]})
    except Exception as e:
        bot.edit_message_text(f"⚠️ Ошибка: {e}", uid, processing.message_id)
    finally:
        os.unlink(tmp_path)

# ==================== ДОКУМЕНТЫ ====================
@bot.message_handler(content_types=['document'])
def doc(message):
    uid = message.chat.id
    if uid not in user_states:
        user_states[uid] = {"role": "default", "history": []}

    file_info = bot.get_file(message.document.file_id)
    downloaded = bot.download_file(file_info.file_path)
    fname = message.document.file_name

    with tempfile.NamedTemporaryFile(suffix="." + fname.split(".")[-1], delete=False) as tmp:
        tmp.write(downloaded)
        tmp_path = tmp.name

    processing = bot.reply_to(message, f"📄 Читаю {fname}...")
    try:
        uploaded = genai.upload_file(tmp_path)
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = f"Проанализируй файл {fname}. Если CSV — опиши данные и предложи анализ. Если текст — перескажи суть."
        resp = model.generate_content([prompt, uploaded])
        bot.edit_message_text(resp.text, uid, processing.message_id, parse_mode="Markdown")
    except Exception as e:
        bot.edit_message_text(f"⚠️ Ошибка: {e}", uid, processing.message_id)
    finally:
        os.unlink(tmp_path)

# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    print("Запуск health-сервера...")
    threading.Thread(target=run_health, daemon=True).start()
    print("Запуск бота...")
    bot.infinity_polling()
