# Local Telegram Agent API

Локальный сервис для интеграции обычного пользовательского аккаунта Telegram (через Telethon MTProto) с ИИ-агентами (включая Google Antigravity) через защищённый loopback REST API и протокол MCP (Model Context Protocol).

> ⚠️ **ПРЕДУПРЕЖДЕНИЕ О БЕЗОПАСНОСТИ:**
> Файл сессии Telegram (`.session`) предоставляет **полный доступ к вашему аккаунту Telegram** (чтение переписок, отправка сообщений от вашего имени).
> - Никогда не передавайте файл сессии, API Hash, проверочные коды или 2FA пароли третьим лицам или в чаты с ИИ.
> - Сервис слушает **только** локальный адрес `127.0.0.1` (loopback). Запрещено пробрасывать этот порт наружу.
> - Все запросы к REST API защищены Bearer-токеном.

---

## 1. Архитектура и назначение

```
+-------------------------------------------------------------+
|                     Google Antigravity                      |
|      (или другой MCP-клиент / локальный агент)               |
+-------------------------------------------------------------+
                             |
                   stdio (MCP Protocol)
                             v
+-------------------------------------------------------------+
|                      mcp_server.py                          |
|             (MCP Tools, FastMCP, httpx)                     |
+-------------------------------------------------------------+
                             |
          HTTP / Bearer Token (127.0.0.1:8765)
                             v
+-------------------------------------------------------------+
|                        server.py                            |
|                 (FastAPI + Uvicorn)                         |
|         - Единственный владелец сессии Telegram             |
|         - asyncio.Lock для синхронизации запросов           |
+-------------------------------------------------------------+
                             |
                     MTProto (Telethon)
                             v
+-------------------------------------------------------------+
|                      Серверы Telegram                       |
+-------------------------------------------------------------+
```

### Ключевые архитектурные принципы:
1. **Разделение ответственности:** Только один процесс (`server.py`) открывает файл сессии и держит постоянное MTProto-соединение. Процесс MCP (`mcp_server.py`) запускается клиентом (Antigravity) и обращается к `server.py` через локальный REST API.
2. **Синхронизация:** Запросы к MTProto защищены `asyncio.Lock`, предотвращая состояние гонки в Telethon-клиенте. При длительном ожидании в `/wait` блокировка отпускается на время тайм-аута.
3. **Безопасность сетевого контура:** REST API жёстко привязан к `127.0.0.1`. При попытке указать внешний адрес сервер завершает работу с ошибкой. Публичные страницы документации (`/docs`, `/redoc`, `/openapi.json`) отключены.
4. **Безопасность секретов:** MCP-сервер читает токен авторизации из защищённого локального `.env` (права `600`), а не из командной строки.

---

## 2. Структура проекта

```text
telegram-agent-api/
├── README.md                   # Подробная документация
├── .env.example                # Шаблон конфигурации
├── .env                        # Локальная конфигурация с правами 600 (не коммитится!)
├── .gitignore                  # Исключения для Git (секреты, venv, сессии)
├── requirements.txt            # Зависимости Python
├── auth.py                     # Скрипт интерактивной авторизации в терминале
├── server.py                   # FastAPI REST API сервер
├── mcp_server.py               # MCP сервер (stdio)
├── tests/
│   └── test_validation.py     # Модульные тесты валидации, loopback и безопасности
├── data/                       # Каталог для сессии (права 700)
│   └── telegram.session        # Файл MTProto-сессии (секрет!)
├── telegram-agent-api.service  # systemd user unit для автозапуска
├── mcp_config.example.json     # Пример конфигурации MCP для Antigravity
└── .venv/                      # Виртуальное окружение Python
```

---

## 3. Системные требования

- **ОС:** Linux (Debian, Ubuntu, Fedora и др.)
- **Python:** 3.11, 3.12 или 3.13
- **Пакеты ОС:** `python3-venv`, `python3-pip`

---

## 4. Установка и настройка

### Шаг 1. Переход в каталог и создание окружения
```bash
cd /root/anti/teleapi/telegram-agent-api
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Шаг 2. Настройка `.env`
Файл `.env` создаётся с правами `600`. Случайный криптографический `API_TOKEN` уже сгенерирован при инициализации.

Пример содержимого:
```dotenv
TELEGRAM_API_ID=1234567
TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef
TELEGRAM_PHONE=+79991234567
TELEGRAM_SESSION=./data/telegram
API_HOST=127.0.0.1
API_PORT=8765
API_TOKEN=<случайно_сгенерированный_токен>
```

### Шаг 3. Получение API ID и API Hash в Telegram
1. Перейдите в браузере на официальный портал разработчиков Telegram: [https://my.telegram.org](https://my.telegram.org).
2. Авторизуйтесь под вашим телефонным номером (Telegram пришлёт код в приложение).
3. Перейдите в раздел **"API development tools"**.
4. Создайте новое приложение (в полях `App title` и `Short name` укажите, например, `teleagent`).
5. Скопируйте поля:
   - `App api_id` (число)
   - `App api_hash` (32-значная hex-строка)
6. Впишите их в файл `.env` в поля `TELEGRAM_API_ID` и `TELEGRAM_API_HASH`, а также укажите `TELEGRAM_PHONE`.

---

## 5. Авторизация Telegram (`auth.py`)

Авторизация выполняется строго интерактивно в терминале пользователем:

```bash
cd /root/anti/teleapi/telegram-agent-api
source .venv/bin/activate
python auth.py
```

### Что происходит:
1. Скрипт запрашивает у Telegram отправку кода подтверждения.
2. В терминале отображается запрос: `Введите код подтверждения из Telegram: `.
3. Если на аккаунте включён облачный 2FA пароль, скрипт запросит его через безопасный ввод (`getpass` без отображения символов).
4. После успешного входа создаётся файл `data/telegram.session` с правами `600`.
5. При повторном запуске `auth.py` проверяет валидность сессии без перезаписи.

---

## 6. Запуск и управление сервисом

### Вариант А: Ручной запуск в терминале (или tmux / nohup)
```bash
cd /root/anti/teleapi/telegram-agent-api
source .venv/bin/activate
python server.py
```
Сервис начнёт прослушивать `http://127.0.0.1:8765`.

### Вариант Б: Запуск в фоне
```bash
nohup /root/anti/teleapi/telegram-agent-api/.venv/bin/python /root/anti/teleapi/telegram-agent-api/server.py > /root/anti/teleapi/telegram-agent-api/server.log 2>&1 &
```
Остановка:
```bash
pkill -f "python.*server.py"
```

### Вариант В: Через `systemd --user` (на системах с поддержкой systemd user init)
1. Скопируйте unit-файл в каталог systemd пользователя:
   ```bash
   mkdir -p ~/.config/systemd/user
   cp telegram-agent-api.service ~/.config/systemd/user/
   ```
2. Управление службой:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now telegram-agent-api
   systemctl --user status telegram-agent-api
   journalctl --user -u telegram-agent-api -f
   systemctl --user stop telegram-agent-api
   systemctl --user disable --now telegram-agent-api
   ```

---

## 7. REST API Endpoints

Все endpoints требуют заголовок:
`Authorization: Bearer <API_TOKEN>`

| Метод | Путь | Описание |
| :--- | :--- | :--- |
| `GET` | `/health` | Проверка статуса REST API и Telegram MTProto подключения |
| `GET` | `/me` | Данные текущего аккаунта (ID, first_name, username, is_bot) |
| `GET` | `/dialogs?limit=30` | Список последних диалогов (1–100) |
| `GET` | `/history?chat=...&limit=20` | История сообщений чата (1–100) |
| `POST` | `/send` | Отправка сообщения: `{"chat": "@username", "text": "Привет"}` |
| `POST` | `/wait` | Ожидание нового сообщения после `after_message_id` (тайм-аут 1–60 с) |
| `POST` | `/click` | Нажатие inline-кнопки по индексу: `{"chat": "...", "message_id": 1, "button_index": 0}` |
| `GET` | `/search?chat=...&q=...&limit=20` | Поиск сообщений в чате по ключевому слову |

### Примеры вызовов через `curl`:

```bash
# Проверка здоровья
curl -s -H "Authorization: Bearer $API_TOKEN" http://127.0.0.1:8765/health

# Получение информации о себе
curl -s -H "Authorization: Bearer $API_TOKEN" http://127.0.0.1:8765/me

# Список диалогов
curl -s -H "Authorization: Bearer $API_TOKEN" "http://127.0.0.1:8765/dialogs?limit=10"

# Ожидание ответа от бота (например, после отправки команды)
curl -s -X POST -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"chat": "@testbot", "after_message_id": 1500, "timeout_seconds": 20}' \
  http://127.0.0.1:8765/wait
```

---

## 8. MCP Инструменты (для Antigravity)

MCP-сервер (`mcp_server.py`) работает через транспорт `stdio`.
Доступные инструменты:
- `telegram_health()` — статус сервиса и подключения MTProto.
- `telegram_me()` — информация о пользователе.
- `telegram_dialogs(limit=30)` — просмотр списка диалогов.
- `telegram_history(chat, limit=20)` — чтение истории сообщений.
- `telegram_send(chat, text)` — отправка сообщения.
- `telegram_wait_reply(chat, after_message_id, timeout_seconds=20)` — ожидание ответа в чате (полезно при тестировании ботов).
- `telegram_click_button(chat, message_id, button_index)` — нажатие inline-кнопки.
- `telegram_search(chat, query, limit=20)` — поиск в переписке.

---

## 9. Подключение к Google Antigravity

Antigravity считывает глобальную конфигурацию MCP из файла:
`~/.gemini/config/mcp_config.json`

Секция конфигурации:
```json
{
  "mcpServers": {
    "telegram-agent": {
      "command": "/root/anti/teleapi/telegram-agent-api/.venv/bin/python",
      "args": [
        "/root/anti/teleapi/telegram-agent-api/mcp_server.py"
      ],
      "cwd": "/root/anti/teleapi/telegram-agent-api"
    }
  }
}
```

> **Безопасность:** В конфигурационный JSON **не помещаются** API-токены или секреты. Скрипт `mcp_server.py` безопасно загружает `.env` при старте.

---

## 10. Диагностика и устранение неполадок

- **`Chat not found` (HTTP 404):**
  Убедитесь, что чат существует, username указан без опечаток (например, `@username`) или передан корректный числовой ID чата. При первой отправке новому пользователю убедитесь, что он доступен по номеру или username.
- **`FloodWaitError` (HTTP 429):**
  Telegram ограничил частоту запросов. Сервер возвращает заголовок `Retry-After: <секунды>` и JSON с полем `retry_after`. Подождите указанное количество секунд.
- **Истёкшая сессия / `SessionRevokedError`:**
  Если сессия была отозвана с другого устройства, удалите старый файл `data/telegram.session` и заново запустите `python auth.py`.
- **`Could not connect to Telegram Agent REST API` в MCP:**
  Убедитесь, что `server.py` запущен на `127.0.0.1:8765`.
- **401 Unauthorized:**
  Проверьте, что токен в заголовке `Authorization: Bearer ...` совпадает со значением `API_TOKEN` в файле `.env`.

---

## 11. Отзыв сессии и безопасность

- Чтобы отозвать доступ к аккаунту: откройте официальное приложение Telegram -> **Настройки** -> **Устройства** -> завершите активную сессию с именем вашего приложения.
- Для полного сброса локальных данных удалите каталог `data/` (`rm -rf data`).
