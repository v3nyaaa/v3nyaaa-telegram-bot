# Telegram-бот v3nyaaa

## Загрузка на Render

1. Создай **приватный** репозиторий на GitHub.
2. Загрузи в него только файлы бота: `main.py`, `requirements.txt`, `render.yaml`, `.gitignore`, `.env.example` и `README.md`.
3. Не загружай `.env`, файлы `*.session` и `*.session-journal`, `seen_users.json`, `known_users.json` или всю папку Desktop.
4. Перед запуском останови локального бота на компьютере (в окне, где он работает, нажми `Ctrl+C`), чтобы одновременно не запускались две копии.
5. На Render выбери создание нового Blueprint и подключи этот GitHub-репозиторий. Render прочитает `render.yaml` и создаст Background Worker.
6. Когда Render попросит переменные окружения, задай `TELEGRAM_BOT_TOKEN`, `GROQ_API_KEY` и `OWNER_TELEGRAM_ID`. Скопируй значения из своего локального `.env` прямо в защищённые настройки Render — не отправляй их в чат и не записывай в `render.yaml`.
7. Подтверди создание сервиса и дождись, пока в Render появится статус **Live**. Логи можно открыть на странице Background Worker.

Для постоянной работы конфигурация использует платный Background Worker и подключённый диск 1 GB. Render покажет стоимость и условия перед созданием сервиса; проверь их перед подтверждением.

## Команды

Работают `/start`, `/help`, `/myid`, `/time`, `/joke`, `/roll`, `/coin`, `/quiz`, `/translate` и `/tiktok`. Поиск чужих Telegram ID через личный аккаунт Telegram отключён.
