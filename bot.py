import os
import threading
import time
from flask import Flask
import requests
from FunPayAPI import Account

# 1. Веб-сервер, чтобы Render не отключал бота
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run_flask, daemon=True).start()

# 2. Ключи и настройки
GOLDEN_KEY = os.environ.get("GOLDEN_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

SYSTEM_PROMPT = (
    "Ты вежливый менеджер по продажам Lucky Arrow в YBA (Roblox) на FunPay. "
    "Цена: 6 руб. Выдача через Trade, требуется 1 престиж (Prestige 1). "
    "Отвечай кратко и вежливо."
)

def get_ai_reply(text):
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text}
                ]
            },
            timeout=10
        )
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"Ошибка ИИ: {e}")
        return "Здравствуйте! Продавец скоро вам ответит."

# 3. Подключение к FunPay
print("Авторизация в FunPay...")
acc = Account(GOLDEN_KEY).get()
print(f"Успешный вход! Логин: {acc.username}")

answered_messages = set()

# 4. Бесконечный цикл проверки
while True:
    try:
        # Принудительно обновляем данные аккаунта
        acc.get()
        chats = acc.get_chats()
        
        for chat in chats:
            # Получаем диалог
            full_chat = acc.get_chat(chat.id)
            if full_chat.messages:
                last_msg = full_chat.messages[-1]
                
                # Если сообщение от покупателя и мы на него еще не отвечали
                if last_msg.author != acc.username and last_msg.id not in answered_messages:
                    print(f"Новое сообщение от {last_msg.author}: {last_msg.text}")
                    
                    # Генерируем и отправляем ответ
                    reply = get_ai_reply(last_msg.text)
                    acc.send_message(chat.id, reply)
                    print(f"Ответ отправлен: {reply}")
                    
                    # Запоминаем ID сообщения
                    answered_messages.add(last_msg.id)
                    
    except Exception as e:
        print(f"Ошибка цикла: {e}")
        
    time.sleep(4)
