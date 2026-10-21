import os
import time
import threading
import logging
import sqlite3
from pathlib import Path

import requests
from flask import Flask
from FunPayAPI import Account

# ---------- Logging ----------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("funpay-bot")

# ---------- Render health-check web server ----------
app = Flask(__name__)

@app.get("/")
def home():
    return "FunPay AI bot is running.", 200

@app.get("/health")
def health():
    return {"status": "ok"}, 200

def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, use_reloader=False)

threading.Thread(target=run_flask, daemon=True, name="health-server").start()

# ---------- Configuration: set these in Render -> Environment ----------
GOLDEN_KEY = os.getenv("GOLDEN_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini").strip()
POLL_SECONDS = max(3, int(os.getenv("POLL_SECONDS", "5")))
DB_PATH = os.getenv("DB_PATH", "bot_state.sqlite3")

SYSTEM_PROMPT = os.getenv(
    "SYSTEM_PROMPT",
    "Ты вежливый менеджер по продажам Lucky Arrow в YBA (Roblox) на FunPay. "
    "Цена: 6 рублей. Выдача через Trade, требуется Prestige 1. "
    "Отвечай по-русски, кратко и вежливо. Не выдумывай условия, наличие товара "
    "или сроки. Если информации недостаточно, скажи, что уточнишь у продавца. "
    "Не проси покупателя присылать пароли, коды или секретные данные."
)

if not GOLDEN_KEY:
    raise RuntimeError("Не задана переменная GOLDEN_KEY в Render → Environment.")
if not OPENROUTER_API_KEY:
    raise RuntimeError("Не задана переменная OPENROUTER_API_KEY в Render → Environment.")

# ---------- Persistent message deduplication ----------
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
db = sqlite3.connect(DB_PATH, check_same_thread=False)
db.execute("""
    CREATE TABLE IF NOT EXISTS processed_messages (
        message_id TEXT PRIMARY KEY,
        chat_id TEXT NOT NULL,
        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
db.commit()
db_lock = threading.Lock()

def was_processed(message_id):
    with db_lock:
        row = db.execute(
            "SELECT 1 FROM processed_messages WHERE message_id = ?",
            (str(message_id),)
        ).fetchone()
        return row is not None

def mark_processed(message_id, chat_id):
    with db_lock:
        db.execute(
            "INSERT OR IGNORE INTO processed_messages (message_id, chat_id) VALUES (?, ?)",
            (str(message_id), str(chat_id))
        )
        db.commit()

# ---------- OpenRouter ----------
def get_ai_reply(user_text):
    if not user_text or not user_text.strip():
        return None

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://render.com",
                "X-Title": "FunPay AI Assistant",
            },
            json={
                "model": OPENROUTER_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_text[:6000]},
                ],
                "temperature": 0.4,
                "max_tokens": 250,
            },
            timeout=(8, 25),
        )
        if not response.ok:
            log.error("OpenRouter вернул HTTP %s: %s", response.status_code, response.text[:500])
            return None

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            log.error("OpenRouter не вернул choices: %s", str(data)[:500])
            return None

        answer = (choices[0].get("message", {}).get("content") or "").strip()
        return answer or None

    except requests.RequestException as exc:
        log.exception("Ошибка соединения с OpenRouter: %s", exc)
    except (ValueError, KeyError, TypeError) as exc:
        log.exception("Некорректный ответ OpenRouter: %s", exc)
    return None

# ---------- FunPay helpers ----------
def get_chat_shortcuts(account):
    """Поддерживает версии библиотеки, где get_chats() возвращает dict или list."""
    try:
        chats = account.get_chats(update=True)
    except TypeError:
        chats = account.get_chats()

    if isinstance(chats, dict):
        return list(chats.values())
    return list(chats or [])

def get_attr(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)

def author_name(message):
    author = get_attr(message, "author", "")
    if isinstance(author, str):
        return author.strip()
    # На случай версий API, где author — объект пользователя.
    for field in ("username", "name", "login"):
        value = get_attr(author, field)
        if value:
            return str(value).strip()
    return str(author).strip() if author else ""

def message_id(message):
    value = get_attr(message, "id")
    return str(value) if value is not None else None

def message_text(message):
    value = get_attr(message, "text", "")
    return str(value or "").strip()

def handle_chat(account, shortcut):
    chat_id = get_attr(shortcut, "id")
    if chat_id is None:
        log.warning("Пропускаю чат: у объекта нет id (%s)", type(shortcut).__name__)
        return

    chat = account.get_chat(chat_id)
    messages = get_attr(chat, "messages", []) or []
    if not messages:
        return

    # Обычно библиотека уже возвращает историю в хронологическом порядке.
    last_msg = messages[-1]
    msg_id = message_id(last_msg)
    if not msg_id:
        log.warning("В чате %s у последнего сообщения нет ID; пропуск ради защиты от дублей.", chat_id)
        return

    sender = author_name(last_msg)
    text = message_text(last_msg)

    # Сначала игнорируем и отмечаем свои сообщения, чтобы не отвечать на них.
    if sender.casefold() == str(account.username).casefold():
        mark_processed(msg_id, chat_id)
        return

    if was_processed(msg_id):
        return

    if not text:
        # Не отвечаем на изображения/пустые сообщения автоматически, но отмечаем,
        # чтобы бот не зацикливался на одном сообщении.
        log.info("Пустое/медиа-сообщение в чате %s; пропускаю.", chat_id)
        mark_processed(msg_id, chat_id)
        return

    log.info("Новое сообщение в чате %s от %s: %s", chat_id, sender or "покупатель", text[:250])
    reply = get_ai_reply(text)

    if not reply:
        # Не помечаем сообщение обработанным: бот попробует снова в следующем цикле.
        log.warning("Ответ ИИ не получен для чата %s; попробую повторить позже.", chat_id)
        return

    try:
        account.send_message(chat_id, reply)
        mark_processed(msg_id, chat_id)
        log.info("Ответ отправлен в чат %s.", chat_id)
    except Exception:
        # Не помечаем как обработанное: следующая итерация повторит попытку.
        log.exception("Не удалось отправить ответ в чат %s.", chat_id)

def main():
    log.info("Авторизация в FunPay...")
    account = Account(GOLDEN_KEY).get()
    log.info("Авторизация успешна. Аккаунт: %s", getattr(account, "username", "unknown"))

    while True:
        try:
            shortcuts = get_chat_shortcuts(account)
            log.info("Проверяю чаты: найдено %s.", len(shortcuts))
            for shortcut in shortcuts:
                try:
                    handle_chat(account, shortcut)
                except Exception:
                    chat_id = get_attr(shortcut, "id", "unknown")
                    log.exception("Ошибка обработки чата %s.", chat_id)
            time.sleep(POLL_SECONDS)

        except KeyboardInterrupt:
            log.info("Остановка по запросу.")
            break
        except Exception:
            log.exception("Ошибка основного цикла; повтор через %s сек.", POLL_SECONDS)
            time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
