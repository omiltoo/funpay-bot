import os
import threading
import time
from flask import Flask
import requests
from FunPayAPI import Account

# 1. Веб-сервер Flask для удерживания порта на Render
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is active!"

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
        print(f"[AI ERROR] Ошибка ИИ: {e}")
        return "Здравствуйте! Продавец скоро ответит вам."

# 3. Авторизация аккаунта
print("[SYSTEM] Подключение к FunPay...")
account = Account(GOLDEN_KEY).get()
print(f"[SYSTEM] Бот успешно запущен от имени: {account.username}")

last_msg_ids = {}

# 4. Основной цикл проверки входящих сообщений
while True:
    try:
        # Получаем актуальный список чатов
        chats = account.get_chats()
        
        for chat in chats:
            chat_id = chat.id
            
            # Получаем подробности диалога
            chat_details = account.get_chat(chat_id)
            messages = chat_details.messages
            
            if messages:
                last_msg = messages[-1]
                
                # Проверяем, что сообщение прислал покупатель (а не сам бот)
                if last_msg.author != account.username:
                    msg_id = last_msg.id
                    
                    # Проверяем, ответил ли бот уже на это конкретное сообщение
                    if last_msg_ids.get(chat_id) != msg_id:
                        print(f"[NEW MSG] Сообщение от {last_msg.author} (Чат {chat_id}): {last_msg.text}")
                        
                        # Генерируем ответ и отправляем
                        reply = get_ai_reply(last_msg.text)
                        account.send_message(chat_id, reply)
                        print(f"[REPLY SENT] Ответ в чат {chat_id}: {reply}")
                        
                        # Запоминаем ID отвеченного сообщения
                        last_msg_ids[chat_id] = msg_id

    except Exception as e:
        print(f"[LOOP ERROR] Ошибка в цикле: {e}")

    # Интервал проверки сообщений в секундах
    time.sleep(6)
