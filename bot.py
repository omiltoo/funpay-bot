import os
import threading
import time
from flask import Flask
import requests
from FunPayAPI import Account

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

print("Инициализация аккаунта FunPay...")
try:
    account = Account(GOLDEN_KEY).get()
    print(f"Бот успешно запущен: {account.username}")
except Exception as e:
    print(f"Ошибка авторизации: {e}")

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
        print(f"Ошибка ИИ: {e}")
        return "Здравствуйте! Продавец скоро ответит вам."

# 3. Основной цикл проверки чатов
last_msg_ids = {}

print("Запуск цикла проверки сообщений...")
while True:
    try:
        chats = account.get_chats()
        for chat in chats:
            chat_id = chat.id
            if chat.unread:
                chat_details = account.get_chat(chat_id)
                messages = chat_details.messages
                if messages:
                    last_msg = messages[-1]
                    # Отвечаем только если последнее сообщение написал не бот
                    if last_msg.author != account.username:
                        msg_id = last_msg.id
                        if last_msg_ids.get(chat_id) != msg_id:
                            print(f"Новое сообщение от {last_msg.author}: {last_msg.text}")
                            
                            # Получаем ответ от ИИ и отправляем
                            reply = get_ai_reply(last_msg.text)
                            account.send_message(chat_id, reply)
                            print(f"Отправлен ответ: {reply}")
                            
                            last_msg_ids[chat_id] = msg_id
    except Exception as e:
        print(f"Ошибка в цикле чатов: {e}")
        
    time.sleep(5)
