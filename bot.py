
import os
import time
import logging
import threading
import sqlite3

import requests
from flask import Flask
from FunPayAPI import Account

# Настройки
GOLDEN_KEY = os.getenv("GOLDEN_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL", "openai/gpt-4o-mini"
)

POLL_SECONDS = 10
ERROR_RETRY_SECONDS = 30
DB_PATH = "answered_messages.sqlite3"

SYSTEM_PROMPT = (
    "Ты вежливый менеджер по продажам Lucky Arrow в YBA (Roblox) "
    "на FunPay. Цена: 6 рублей. Выдача через Trade, требуется "
    "1 престиж (Prestige 1). Отвечай кратко и вежливо."
)

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("funpay-bot")

# Flask для Render
app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is alive!", 200


@app.route("/health")
def health():
    return {"status": "ok"}, 200


def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False,
    )


threading.Thread(
    target=run_flask,
    daemon=True,
).start()


# База данных для защиты от повторных ответов
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS answered (
                message_id TEXT PRIMARY KEY
            )
        """)
        conn.commit()


def was_answered(message_id):
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute(
            "SELECT 1 FROM answered WHERE message_id = ?",
            (str(message_id),),
        ).fetchone()
        return result is not None


def mark_answered(message_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO answered (message_id) VALUES (?)",
            (str(message_id),),
        )
        conn.commit()


# Ответ ИИ
def get_ai_reply(message):
    fallback = "Здравствуйте! Продавец скоро вам ответит."

    if not OPENROUTER_API_KEY:
        log.error("Не задан OPENROUTER_API_KEY.")
        return fallback

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": (
                    f"Bearer {OPENROUTER_API_KEY}"
                ),
                "Content-Type": "application/json",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT,
                    },
                    {
                        "role": "user",
                        "content": message,
                    },
                ],
            },
            timeout=25,
        )

        if not response.ok:
            log.error(
                "OpenRouter HTTP %s: %s",
                response.status_code,
                response.text[:300],
            )
            return fallback

        data = response.json()
        answer = data["choices"][0]["message"]["content"]

        if isinstance(answer, str) and answer.strip():
            return answer.strip()

        return fallback

    except Exception as e:
        log.error(
            "Ошибка ИИ: %s: %s",
            type(e).__name__,
            str(e)[:300],
        )
        return fallback


# Диагностика ошибок FunPay
def log_funpay_error(error):
    log.error("Тип ошибки: %s", type(error).__name__)
    log.error("Текст ошибки: %s", str(error))

    # Некоторые версии библиотеки хранят HTTP-ответ
    # внутри аргументов исключения.
    for item in getattr(error, "args", ()):
        if hasattr(item, "status_code"):
            try:
                log.error(
                    "HTTP статус: %s",
                    item.status_code,
                )
                log.error(
                    "Ответ сервера: %s",
                    item.text[:500],
                )
            except Exception:
                pass

    response = getattr(error, "response", None)
    if response is not None:
        try:
            log.error(
                "HTTP статус ответа: %s",
                response.status_code,
            )
            log.error(
                "Ответ сервера: %s",
                response.text[:500],
            )
        except Exception:
            pass

    log.exception("Ошибка при работе с FunPay")


# Основной цикл
def main():
    if not GOLDEN_KEY:
        log.error(
            "В Render не задан GOLDEN_KEY. "
            "Открой Environment и добавь переменную."
        )
        return

    if not OPENROUTER_API_KEY:
        log.warning(
            "OPENROUTER_API_KEY не задан. "
            "ИИ будет отвечать запасным сообщением."
        )

    init_db()

    log.info("Подключение к FunPay...")

    try:
        account = Account(GOLDEN_KEY)
account.get(update_phpsessid=True)
    except Exception as e:
        log.error("Не удалось войти в FunPay.")
        log_funpay_error(e)
        return

    log.info(
        "Вход выполнен. Аккаунт: %s",
        getattr(account, "username", "неизвестно"),
    )

    while True:
        try:
            account.get()

            chats = account.get_chats(update=True)
            chats = (
                list(chats.values())
                if isinstance(chats, dict)
                else list(chats or [])
            )

            log.info(
                "Найдено чатов после обновления: %s",
                len(chats),
            )

            for chat in chats:
                try:
                    full_chat = account.get_chat(chat.id)
                    messages = getattr(
                        full_chat, "messages", []
                    ) or []

                    log.info(
                        "Чат %s: найдено сообщений: %s",
                        chat.id,
                        len(messages),
                    )

                    if not messages:
                        continue

                    for msg in messages[-10:]:
                        message_id = getattr(msg, "id", None)
                        author = getattr(msg, "author", None)
                        message_text = getattr(msg, "text", "")

                        if message_id is None:
                            continue

                        if not isinstance(message_text, str):
                            continue

                        if not message_text.strip():
                            continue

                        if author == account.username:
                            continue

                        if was_answered(message_id):
                            continue

                        log.info(
                            "Новое сообщение в чате %s",
                            chat.id,
                        )

                        reply = get_ai_reply(message_text)
                        account.send_message(chat.id, reply)
                        mark_answered(message_id)

                        log.info(
                            "Ответ отправлен в чат %s",
                            chat.id,
                        )

                except Exception as e:
                    log.error(
                        "Ошибка обработки чата %s",
                        getattr(chat, "id", "?"),
                    )
                    log_funpay_error(e)

        except Exception as e:
            log_funpay_error(e)
            log.warning(
                "Повторная попытка через %s секунд.",
                ERROR_RETRY_SECONDS,
            )
            time.sleep(ERROR_RETRY_SECONDS)
            continue

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
