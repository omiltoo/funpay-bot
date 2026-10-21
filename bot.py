import os
import threading
import time
from flask import Flask
import requests
from FunPayAPI import Account

# 1. Запуск веб-сервера для Render (чтобы открылся порт)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Запускаем сайт в отдельном фоновом потоке
threading.Thread(target=run_flask, daemon=True).start()

# 2. Основная логика FunPay бота
GOLDEN_KEY = os.environ.get("GOLDEN_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

SYSTEM_PROMPT = "Ты вежливый менеджер по продажам Lucky Arrow в YBA (Roblox) на FunPay. Цена 6 руб. Выдача через Trade, требуется 1 престиж (Prestige 1). Отвечай кратко и вежливо."

print("Инициализация аккаунта...")
try:
    account = Account(GOLDEN_KEY).get()
    print(f"Бот успешно запущен: {account.username}")
except Exception as e:
    print(f"Ошибка входа: {e}")

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
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"Ошибка ИИ: {e}")
        return "Здравствуйте! Продавец скоро ответит вам."

while True:
    time.sleep(1)
