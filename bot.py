import os
import threading
from flask import Flask
import requests
from FunPayAPI import Account
from FunPayAPI.types import MessageTypes

# 1. Веб-сервер Flask для удержания порта на Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

# 2. Настройки бота и ИИ
GOLDEN_KEY = os.environ.get("GOLDEN_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

SYSTEM_PROMPT = (
    "Ты вежливый менеджер по продажам Lucky Arrow в YBA (Roblox) на FunPay. "
    "Цена: 6 руб. Выдача через Trade, требуется 1 престиж (Prestige 1). "
    "Отвечай кратко и вежливо."
)

def get_ai_reply(user_message):
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
        print(f"[AI ERROR] {e}")
        return "Здравствуйте! Продавец скоро ответит вам."

# 3. Авторизация и запуск прослушивания через Runner
print("[SYSTEM] Подключение к FunPay...")
account = Account(GOLDEN_KEY).get()
print(f"[SYSTEM] Бот успешно запущен от имени: {account.username}")

# Получаем объект ранера для отслеживания событий
runner = account.get_runner()

@runner.on_message()
def handle_new_message(message):
    # Игнорируем собственные сообщения бота
    if message.author == account.username:
        return
    
    # Обрабатываем только текстовые сообщения
    if message.type != MessageTypes.TEXT:
        return

    print(f"[NEW MESSAGE] От {message.author} в чате {message.chat_id}: {message.text}")
    
    # Генерируем ответ через ИИ
    reply_text = get_ai_reply(message.text)
    
    # Отправляем ответ в тот же чат
    account.send_message(message.chat_id, reply_text)
    print(f"[REPLY SENT] В чат {message.chat_id}: {reply_text}")

# Запуск постоянного прослушивания чата
runner.listen(requests_delay=5)
