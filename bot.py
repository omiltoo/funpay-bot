import os
import time
import sqlite3
import logging
import threading

import requests
from flask import Flask
from FunPayAPI import Account


# ---------- НАСТРОЙКИ ----------

GOLDEN_KEY = os.getenv("GOLDEN_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv(
    "OPENROUTER_MODEL",
    "openai/gpt-4o-mini"
)

POLL_SECONDS = 8
ERROR_RETRY_SECONDS = 15
DB_PATH = "answered_messages.sqlite3"

SYSTEM_PROMPT = (
    "Ты вежливый менеджер по продажам Lucky Arrow "
    "в YBA (Roblox) на FunPay. "
    "Цена: 6 рублей. Выдача через Trade, "
    "требуется 1 престиж (Prestige 1). "
    "Отвечай кратко и вежливо. "
    "Не выдумывай условия продажи. "
    "Если не уверен в ответе, предложи дождаться продавца."
)


# ---------- ЛОГИ ----------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

log = logging.getLogger("funpay-bot")


# ---------- FLASK ДЛЯ RENDER ----------

app = Flask(__name__)


@app.route("/")
def home():
    return "Bot is alive!"


@app.route("/health")
def health():
    return {"status": "ok"}


def run_web():
    port = int(os.getenv("PORT", "10000"))
    app.run(
        host="0.0.0.0",
        port=port,
        use_reloader=False
    )


threading.Thread(
    target=run_web,
    daemon=True
).start()


# ---------- БАЗА ДАННЫХ ----------

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS answered (
                message_id TEXT PRIMARY KEY,
                answered_at INTEGER NOT NULL
            )
        """)


def was_answered(message_id):
    with sqlite3.connect(DB_PATH) as conn:
        result = conn.execute(
            "SELECT 1 FROM answered WHERE message_id = ?",
            (str(message_id),)
        ).fetchone()

    return result is not None


def mark_answered(message_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO answered VALUES (?, ?)",
            (str(message_id), int(time.time()))
        )


# ---------- ИИ ----------

def get_ai_reply(message_text):
    fallback = (
        "Здравствуйте! Спасибо за сообщение. "
        "Продавец скоро вам ответит."
    )

    if not OPENROUTER_API_KEY:
        log.error("Не задан OPENROUTER_API_KEY в Render.")
        return fallback

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": (
                    f"Bearer {OPENROUTER_API_KEY}"
                ),
                "Content-Type": "application/json",
                "HTTP-Referer": "https://funpay.com",
                "X-Title": "FunPay Assistant"
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": message_text[:4000]
                    }
                ],
                "temperature": 0.4,
                "max_tokens": 250
            },
            timeout=25
        )

        if response.status_code != 200:
            log.error(
                "OpenRouter HTTP %s: %s",
                response.status_code,
                response.text[:300]
            )
            return fallback

        data = response.json()

        return data["choices"][0]["message"]["content"].strip()

    except Exception:
        log.exception("Ошибка обращения к OpenRouter")
        return fallback


# ---------- ОШИБКИ FUNPAY ----------

def log_error(error):
    log.error(
        "Ошибка %s: %s",
        type(error).__name__,
        error
    )

    response = getattr(error, "response", None)

    if response is not None:
        log.error(
            "HTTP статус: %s",
            getattr(response, "status_code", "?")
        )

        try:
            log.error(
                "Ответ сервера: %s",
                response.text[:300]
            )
        except Exception:
            pass


def normalize_chats(chats):
    if isinstance(chats, dict):
        return list(chats.values())

    return list(chats or [])


# ---------- ОСНОВНОЙ БОТ ----------

def main():
    if not GOLDEN_KEY:
        log.error(
            "Не задан GOLDEN_KEY в Environment Render."
        )
        return

    init_db()

    log.info("Авторизация в FunPay...")

    account = Account(GOLDEN_KEY)

    # Попытка обновить PHPSESSID при авторизации.
    account.get(update_phpsessid=True)

    log.info(
        "Вход выполнен. Аккаунт: %s",
        account.username
    )

    last_refresh = time.time()

    while True:
        try:
            # Периодическое обновление сессии.
            if time.time() - last_refresh > 45 * 60:
                account.get(update_phpsessid=True)
                last_refresh = time.time()

                log.info("Сессия FunPay обновлена.")

            # Получение актуальных данных и чатов.
            account.get()

            chats_result = account.get_chats(update=True)
            chats = normalize_chats(chats_result)

            log.info(
                "Найдено чатов после обновления: %s",
                len(chats)
            )

            for chat in chats:
                chat_id = getattr(chat, "id", None)

                if chat_id is None:
                    continue

                try:
                    full_chat = account.get_chat(chat_id)

                    messages = (
                        getattr(full_chat, "messages", None)
                        or []
                    )

                    # Проверяем несколько последних сообщений.
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

                        # Не отвечаем на свои сообщения.
                        if author == account.username:
                            continue

                        # Не обрабатываем сообщение повторно.
                        if was_answered(message_id):
                            continue

                        log.info(
                            "Новое сообщение в чате %s",
                            chat_id
                        )

                        reply = get_ai_reply(message_text)

                        account.send_message(
                            chat_id,
                            reply
                        )

                        mark_answered(message_id)

                        log.info(
                            "Ответ отправлен в чат %s",
                            chat_id
                        )

                except Exception as error:
                    log_error(error)

                    # При ошибке cookie пробуем обновить сессию.
                    error_text = str(error).lower()

                    if (
                        "cookie" in error_text
                        or "400" in error_text
                    ):
                        try:
                            account.get(
                                update_phpsessid=True
                            )
                            last_refresh = time.time()

                            log.info(
                                "Выполнена попытка обновления сессии."
                            )

                        except Exception as refresh_error:
                            log_error(refresh_error)

        except Exception as error:
            log_error(error)

            try:
                account.get(update_phpsessid=True)
                last_refresh = time.time()

                log.info(
                    "Выполнена попытка обновления сессии."
                )

            except Exception as refresh_error:
                log_error(refresh_error)

            log.warning(
                "Повтор через %s секунд.",
                ERROR_RETRY_SECONDS
            )

            time.sleep(ERROR_RETRY_SECONDS)
            continue

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
