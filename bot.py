import telebot
import requests
import os
import tempfile
import threading
import base64
from http.server import HTTPServer, BaseHTTPRequestHandler
from duckduckgo_search import DDGS
from groq import Groq

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GROQ_KEY = os.getenv("GROQ_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = Groq(api_key=GROQ_KEY)

ROLES = {
    "default": "Ты — полезный ассистент. Отвечай чётко, на русском языке.",
    "programmer": "Ты Senior Developer. Получаешь ТЗ, задаёшь уточняющие вопросы, объясняешь архитектуру, потом пишешь чистый код с комментариями.",
    "teacher": "Ты — терпеливый учитель. Объясняешь сложное простым языком, не даёшь готовых ответов, а направляешь вопросами.",
    "psychologist": "Ты — эмпатичный психолог. Активно слушаешь, задаёшь открытые вопросы, не даёшь советов.",
    "superai": "Ты — ИИ экспертного уровня. Отвечаешь глубоко, структурированно, с выводами.",
    "copywriter": "Ты — профессиональный копирайтер. Пишешь цепляющие, продающие тексты.",
    "critic": "Ты — суровый критик. Жёстко и конструктивно разбираешь текст или идею.",
}

user_states = {}

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

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_health():
    port = int(os.getenv("PORT", 10000))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    server.serve_forever()

def ask_groq(system_prompt, user_text):
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        temperature=0.7,
        max_tokens=2048
    )
    return response.choices[0].message.content

@bot.message_handler(commands=['start'])
def start(message):
    uid = message.chat.id
    user_states[uid] = {"role": "default", "history": []}
    bot.send_message(uid, "Привет! Я твой AI-ассистент.\nВыбери режим:", reply_markup=main_keyboard())

@bot.message_handler(commands=['img'])
def cmd_img(message):
    prompt = message.text.replace("/img", "").strip()
    if not prompt:
        bot.reply_to(message, "Напиши: /img <описание>")
        return
    msg = bot.reply_to(message, "Рисую...")
    try:
        url = f"https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true"
        resp = requests.get(url, timeout=30)
        bot.send_photo(message.chat.id, resp.content, caption=prompt)
        bot.delete_message(msg.chat.id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"Ошибка: {e}", msg.chat.id, msg.message_id)

@bot.message_handler(commands=['internet'])
def cmd_internet(message):
    query = message.text.replace("/internet", "").strip()
    if not query:
        bot.reply_to(message, "Напиши: /internet <запрос>")
        return
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))
        if not results:
            bot.reply_to(message, "Ничего не найдено.")
            return
        answer = f"Результаты: {query}\n\n"
        for i, r in enumerate(results, 1):
            answer += f"{i}. {r['title']}\n{r['body'][:200]}...\n{r['href']}\n\n"
        bot.reply_to(message, answer, disable_web_page_preview=True)
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

@bot.message_handler(func=lambda m: m.text == "💻 Программист")
def nav_prog(m):
    user_states[m.chat.id] = {"role": "programmer", "history": []}
    bot.reply_to(m, "Режим Senior Developer. Опиши задачу.")

@bot.message_handler(func=lambda m: m.text == "🤖 Обычный")
def nav_def(m):
    user_states[m.chat.id] = {"role": "default", "history": []}
    bot.reply_to(m, "Обычный режим. Задавай вопрос.")

@bot.message_handler(func=lambda m: m.text == "🧠 СуперИИ")
def nav_super(m):
    user_states[m.chat.id] = {"role": "superai", "history": []}
    bot.reply_to(m, "СуперИИ активирован.")

@bot.message_handler(func=lambda m: m.text == "🎭 Роли")
def nav_roles(m):
    bot.reply_to(m, "Выбери роль:", reply_markup=roles_keyboard())

@bot.message_handler(func=lambda m: m.text == "⬅ Назад")
def nav_back(m):
    bot.reply_to(m, "Главное меню:", reply_markup=main_keyboard())

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
    bot.reply_to(m, f"Роль: {m.text}. Жду вопрос.")

@bot.message_handler(content_types=['text'])
def chat(message):
    uid = message.chat.id
    if uid not in user_states:
        user_states[uid] = {"role": "default", "history": []}

    state = user_states[uid]
    system_prompt = ROLES.get(state["role"], ROLES["default"])

    state["history"].append({"role": "user", "content": message.text})

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(state["history"][-20:])

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.7,
            max_tokens=2048
        )
        answer = response.choices[0].message.content
        bot.reply_to(message, answer)
        state["history"].append({"role": "assistant", "content": answer})
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")

@bot.message_handler(content_types=['photo'])
def photo(message):
    uid = message.chat.id
    if uid not in user_states:
        user_states[uid] = {"role": "default", "history": []}

    processing = bot.reply_to(message, "Анализирую фото...")
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded = bot.download_file(file_info.file_path)

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(downloaded)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        response = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": message.caption or "Опиши подробно это изображение."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_data}"}}
                    ]
                }
            ],
            temperature=0.7,
            max_tokens=1024
        )
        answer = response.choices[0].message.content
        bot.edit_message_text(answer, uid, processing.message_id)
    except Exception as e:
        bot.edit_message_text(f"Ошибка: {e}", uid, processing.message_id)
    finally:
        os.unlink(tmp_path)

@bot.message_handler(content_types=['voice', 'audio'])
def voice(message):
    uid = message.chat.id
    processing = bot.reply_to(message, "Распознаю речь...")

    file_id = message.voice.file_id if message.voice else message.audio.file_id
    file_info = bot.get_file(file_id)
    downloaded = bot.download_file(file_info.file_path)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp.write(downloaded)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=f,
                language="ru"
            )
        text = transcription.text
        bot.edit_message_text(f"Распознано:\n\n{text}", uid, processing.message_id)
        if uid in user_states:
            user_states[uid]["history"].append({"role": "user", "content": text})
    except Exception as e:
        bot.edit_message_text(f"Ошибка: {e}", uid, processing.message_id)
    finally:
        os.unlink(tmp_path)

if __name__ == "__main__":
    threading.Thread(target=run_health, daemon=True).start()
    bot.infinity_polling()
