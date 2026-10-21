import os
import time
import requests
from FunPayAPI import Account

# Ключи будут автоматически подтягиваться из Render (Environment Variables)
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
        # Бесконечный цикл, чтобы бот не выключался на Render
while True:
    time.sleep(1)

