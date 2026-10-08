import json
import os
import random
import string
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from groq import APIError, APIStatusError, Groq


def load_local_keys():
    env_file = Path(__file__).with_name(".env")
    if not env_file.exists():
        return

    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


load_local_keys()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OWNER_ID_VALUE = os.getenv("OWNER_TELEGRAM_ID")
BOT_DATA_DIR = Path(os.getenv("BOT_DATA_DIR", str(Path(__file__).parent)))
SEEN_USERS_FILE = BOT_DATA_DIR / "seen_users.json"
TIKTOK_PROFILE_URL = "https://www.tiktok.com/@v3nyaaa0"
QUIZ_QUESTIONS = [
    ("Какая планета известна как Красная планета?", ("марс",)),
    ("Сколько будет 7 × 8?", ("56", "пятьдесят шесть")),
    ("Как называется столица Японии?", ("токио",)),
    ("Какой океан самый большой на Земле?", ("тихий океан", "тихий")),
    ("Сколько сторон у шестиугольника?", ("6", "шесть")),
]
active_quizzes = {}
translation_pending = set()
COMMAND_KEYBOARD = {
    "keyboard": [
        [{"text": "/start"}, {"text": "/help"}],
        [{"text": "/myid"}, {"text": "/time"}],
        [{"text": "/joke"}, {"text": "/roll"}, {"text": "/coin"}],
        [{"text": "/quiz"}, {"text": "/translate"}],
        [{"text": "/tiktok"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "Выбери команду или напиши вопрос",
}

try:
    OWNER_TELEGRAM_ID = int(OWNER_ID_VALUE) if OWNER_ID_VALUE else None
except ValueError as error:
    raise SystemExit("OWNER_TELEGRAM_ID должен быть числовым ID из команды /myid.") from error


def telegram_request(method, data):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/{method}"
    request = Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )

    with urlopen(request, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Ошибка Telegram API"))
    return result["result"]


def ask_groq(question, system_instruction=None):
    client = Groq(api_key=GROQ_API_KEY, timeout=60, max_retries=2)
    completion = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {
                "role": "system",
                "content": system_instruction
                or (
                    "Ты дружелюбный помощник. Отвечай по-русски, ясно и простыми словами. "
                    "Если не знаешь ответ, честно скажи об этом."
                ),
            },
            {"role": "user", "content": question},
        ],
    )
    answer = completion.choices[0].message.content or ""
    answer = answer.strip()
    if not answer:
        raise RuntimeError("ИИ не вернул текстовый ответ")
    return answer


def send_message(chat_id, text, reply_markup=None):
    for start in range(0, len(text), 4000):
        data = {"chat_id": chat_id, "text": text[start : start + 4000]}
        if reply_markup is not None:
            data["reply_markup"] = reply_markup
        telegram_request(
            "sendMessage",
            data,
        )


def set_bot_commands():
    commands = [
        {"command": "start", "description": "Запустить бота"},
        {"command": "help", "description": "Показать список команд"},
        {"command": "myid", "description": "Показать свой Telegram ID"},
        {"command": "time", "description": "Показать дату и время"},
        {"command": "joke", "description": "Рассказать случайную шутку"},
        {"command": "roll", "description": "Бросить кубик"},
        {"command": "coin", "description": "Подбросить монетку"},
        {"command": "quiz", "description": "Начать викторину"},
        {"command": "translate", "description": "Перевести текст"},
        {"command": "tiktok", "description": "Отправить TikTok-профиль"},
    ]
    telegram_request("setMyCommands", {"commands": commands})


def load_seen_user_ids():
    if not SEEN_USERS_FILE.exists():
        return set()

    saved_ids = json.loads(SEEN_USERS_FILE.read_text(encoding="utf-8"))
    if not isinstance(saved_ids, list) or not all(
        isinstance(user_id, str) and user_id.isdigit() for user_id in saved_ids
    ):
        raise RuntimeError(f"Неверный формат файла {SEEN_USERS_FILE.name}.")
    return set(saved_ids)


def save_seen_user_ids(user_ids):
    BOT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    temporary_file = SEEN_USERS_FILE.with_suffix(".tmp")
    temporary_file.write_text(
        json.dumps(sorted(user_ids), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_file.replace(SEEN_USERS_FILE)


def main():
    if not TELEGRAM_TOKEN or not GROQ_API_KEY:
        raise SystemExit(
            "Не найдены ключи. Проверь настройки окружения или файл .env рядом с main.py: "
            "нужны TELEGRAM_BOT_TOKEN и GROQ_API_KEY."
        )

    set_bot_commands()
    print("Бот запущен. Открой его в Telegram и отправь /start.")
    if OWNER_TELEGRAM_ID is None:
        print("Уведомления о новых пользователях выключены: задай OWNER_TELEGRAM_ID.")

    seen_user_ids = load_seen_user_ids()
    next_update_id = None

    while True:
        request_data = {"timeout": 30, "allowed_updates": ["message"]}
        if next_update_id is not None:
            request_data["offset"] = next_update_id

        try:
            updates = telegram_request("getUpdates", request_data)
        except (HTTPError, URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as error:
            print(f"Ошибка при получении сообщений Telegram: {error}")
            time.sleep(5)
            continue

        for update in updates:
            next_update_id = update["update_id"] + 1
            message = update.get("message", {})
            text = message.get("text", "").strip()
            chat_id = message.get("chat", {}).get("id")
            sender = message.get("from", {})
            sender_id = sender.get("id")

            if not text or chat_id is None:
                continue

            message_parts = text.split(maxsplit=1)
            command = message_parts[0].split("@", 1)[0].lower()
            command_text = message_parts[1].strip() if len(message_parts) > 1 else ""

            if command == "/myid":
                if sender_id is not None:
                    send_message(chat_id, f"Твой Telegram ID: {sender_id}")
                continue

            if command == "/id":
                send_message(chat_id, "Поиск чужих Telegram ID отключён.")
                continue

            if command == "/time":
                current_time = datetime.now().astimezone().strftime("%d.%m.%Y, %H:%M:%S")
                send_message(chat_id, f"Сейчас по времени компьютера: {current_time}")
                continue

            if command == "/joke":
                jokes = [
                    "Почему программист не любит природу? Там слишком много багов.",
                    "Компьютер попросил чай. Наверное, ему нужно было немного Java.",
                    "Почему книга по Python грустила? Её никто не открывал.",
                ]
                send_message(chat_id, random.choice(jokes))
                continue

            if command == "/roll":
                send_message(chat_id, f"Выпало: {random.randint(1, 6)} 🎲")
                continue

            if command == "/coin":
                side = random.choice(("Орёл", "Решка"))
                send_message(chat_id, f"Выпало: {side} 🪙")
                continue

            if command == "/tiktok":
                send_message(chat_id, f"Мой TikTok: {TIKTOK_PROFILE_URL}")
                continue

            if command == "/quiz":
                translation_pending.discard(chat_id)
                question, answers = random.choice(QUIZ_QUESTIONS)
                active_quizzes[chat_id] = answers
                send_message(chat_id, f"Викторина 🎯\n{question}\n\nНапиши ответ сообщением.")
                continue

            if command == "/translate":
                active_quizzes.pop(chat_id, None)
                if command_text:
                    text = command_text
                else:
                    translation_pending.add(chat_id)
                    send_message(
                        chat_id,
                        "Пришли текст для перевода. Переведу его на русский, "
                        "а русский текст — на английский.",
                    )
                    continue

                system_instruction = (
                    "Ты переводчик. Если текст пользователя на русском языке, переведи его "
                    "на английский. Для текста на любом другом языке переведи на русский. "
                    "Верни только перевод без пояснений и вступления."
                )
            else:
                system_instruction = None

            if command == "/start":
                if (
                    OWNER_TELEGRAM_ID is not None
                    and sender_id is not None
                    and sender_id != OWNER_TELEGRAM_ID
                    and str(sender_id) not in seen_user_ids
                ):
                    first_name = sender.get("first_name", "Без имени")
                    username = sender.get("username")
                    username_text = f"@{username}" if username else "не указан"
                    notification = (
                        "Новый пользователь запустил бота!\n"
                        f"Имя: {first_name}\n"
                        f"Username: {username_text}\n"
                        f"Telegram ID: {sender_id}"
                    )
                    try:
                        send_message(OWNER_TELEGRAM_ID, notification)
                    except (HTTPError, URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as error:
                        print(f"Не удалось уведомить владельца о новом пользователе: {error}")
                    else:
                        seen_user_ids.add(str(sender_id))
                        save_seen_user_ids(seen_user_ids)

                send_message(
                    chat_id,
                    "Привет! Я ИИ-бот и могу ответить на твои вопросы.\n"
                    "Просто напиши вопрос. Команды: /start, /help, /myid, /time, "
                    "/joke, /roll, /coin, /quiz, /translate и /tiktok.\n\n"
                    "Бот сделан v3nyaaa.",
                    reply_markup=COMMAND_KEYBOARD,
                )
                continue

            if command == "/help":
                send_message(
                    chat_id,
                    "Команды: /start, /help, /myid, /time, /joke, /roll, /coin, "
                    "/quiz, /translate и /tiktok.\n"
                    "Поиск чужих Telegram ID отключён. В викторине ответь обычным сообщением. "
                    "Для перевода отправь "
                    "/translate, а затем текст; или напиши текст после команды.",
                    reply_markup=COMMAND_KEYBOARD,
                )
                continue

            if chat_id in active_quizzes:
                accepted_answers = active_quizzes.pop(chat_id)
                normalized_text = text.casefold().strip().rstrip(string.punctuation + "؟،。")
                normalized_answers = {
                    answer.casefold().strip().rstrip(string.punctuation + "؟،。")
                    for answer in accepted_answers
                }
                if normalized_text in normalized_answers:
                    send_message(chat_id, "Правильно! Отличный ответ 🎉")
                else:
                    send_message(
                        chat_id,
                        f"Не совсем. Правильный ответ: {accepted_answers[0]}. "
                        "Хочешь сыграть ещё? Напиши /quiz.",
                    )
                continue

            if chat_id in translation_pending:
                translation_pending.discard(chat_id)
                system_instruction = (
                    "Ты переводчик. Если текст пользователя на русском языке, переведи его "
                    "на английский. Для текста на любом другом языке переведи на русский. "
                    "Верни только перевод без пояснений и вступления."
                )

            try:
                send_message(
                    chat_id,
                    "Перевожу…" if system_instruction else "Вопрос получил, сейчас подумаю над ответом…",
                )
                answer = ask_groq(text, system_instruction=system_instruction)
                send_message(chat_id, answer)
            except APIError as error:
                status = (
                    f"HTTP {error.status_code}"
                    if isinstance(error, APIStatusError)
                    else "ошибка соединения"
                )
                details = error.body
                if isinstance(details, dict):
                    nested_error = details.get("error", {})
                    if isinstance(nested_error, dict):
                        details = nested_error.get("message", details)
                if details:
                    detail = str(details)
                    detail = detail.replace(GROQ_API_KEY or "", "[ключ скрыт]")
                    detail = detail.replace(TELEGRAM_TOKEN or "", "[токен скрыт]")
                    detail = " ".join(detail.split())[:500]
                    print(f"Не удалось ответить через Groq API: {status}: {detail}")
                else:
                    print(f"Не удалось ответить через Groq API: {status}: {error}")
                send_message(
                    chat_id,
                    "Не получилось получить ответ от ИИ. "
                    "Подробности ошибки можно посмотреть в терминале.",
                )
            except (HTTPError, URLError, TimeoutError, RuntimeError, json.JSONDecodeError) as error:
                print(f"Не удалось обработать сообщение: {error}")
                send_message(
                    chat_id,
                    "Не получилось обработать сообщение. "
                    "Подробности ошибки можно посмотреть в терминале.",
                )


if __name__ == "__main__":
    main()