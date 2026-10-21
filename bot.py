import os
import threading
from flask import Flask
import requests
from FunPayAPI import Account
from FunPayAPI.types import MessageTypes

# ==========================================
# 1. Веб-сервер Flask (для обхода ограничений Render)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is active and running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Запускаем сайт в отдельном фоновом потоке
threading.Thread(target=run_flask, daemon=True).start()

# ==========================================
# 2. Переменные окружения и ИИ
# ==========================================
GOLDEN_KEY = os.environ.get("GOLDEN_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

SYSTEM_PROMPT = (
    "Ты вежливый менеджер по продажам Lucky Arrow в YBA (Roblox) на FunPay. "
    "Цена: 6 руб. Выдача происходит через Trade в игре, для сделки требуется 1 престиж (Prestige 1). "
    "Отвечай кратко, вежливо и понятно."
)

def get_ai_reply(user_message):
    """Отправляет запрос к OpenRouter и возвращает ответ от AI."""
    try:
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ]
        }
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=10
        )
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"Ошибка получения ответа от ИИ: {e}")
        return "Здравствуйте! Продавец сейчас занят, но скоро ответит вам."

# ==========================================
# 3. Основная логика бота FunPay
# ==========================================
print("Инициализация аккаунта FunPay...")
acc = Account(GOLDEN_KEY).get()
print(f"Бот успешно запущен от имени: {acc.username}")

# Создаем прослушиватель событий (runner)
runner = acc.get_runner()

# Подписываемся на новые сообщения
@runner.on_message()
def handle_message(message):
    # Игнорируем собственные сообщения бота и системные уведомления
    if message.author == acc.username or message.type != MessageTypes.TEXT:
        return

    chat_id = message.chat_id
    user_text = message.text
    print(f"Новое сообщение в чате {chat_id} от {message.author}: {user_text}")

    # Генерируем ответ через ИИ
    reply_text = get_ai_reply(user_text)

    # Отправляем ответ покупателю
    acc.send_message(chat_id, reply_text)
    print(f"Отправлен ответ в чат {chat_id}: {reply_text}")

# Запускаем бесконечный прослушиватель чатов
runner.listen()
