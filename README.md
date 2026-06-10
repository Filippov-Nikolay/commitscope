# GitHub Commits Parser

Инструмент для получения коммитов, diff-патчей и комментариев из GitHub-репозитория.  
Работает в трёх режимах: **CLI** (консоль), **API + Веб-интерфейс** (браузер и JSON), **Docker**.

---

## Быстрый старт

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Настройка токена

```bash
cp .env.example .env
# Откройте .env и вставьте свой GitHub Personal Access Token
```

> **Зачем нужен токен?** Без токена лимит 60 запросов/час - хватает примерно на 20 коммитов. С токеном - 5000 запросов/час.  
> Создать токен: [github.com/settings/tokens](https://github.com/settings/tokens) → `public_repo` для публичных, `repo` для приватных репозиториев.

---

## Режим 1 - CLI (командная строка)

```bash
python main.py --owner microsoft --repo vscode --branch main
```

Выводит отчёт в консоль через Rich (цветные таблицы, прогресс-бар) и сохраняет JSON-файл.

### Параметры

| Параметр | Описание | По умолчанию |
|---|---|---|
| `--owner` | Владелец репозитория (логин или организация) | обязательный |
| `--repo` | Название репозитория | обязательный |
| `--branch` | Ветка для анализа | `main` |
| `--author NAME[,NAME...]` | Фильтр по автору: git-имя или GitHub-логин, несколько через запятую | все авторы |
| `--max-commits N` | Максимальное число коммитов | все |
| `--output FILE` | Путь к JSON-файлу с отчётом | `commits_report.json` |
| `--no-save` | Не сохранять отчёт в файл | - |
| `--token TOKEN` | GitHub токен (или задайте `GITHUB_TOKEN` в `.env`) | - |
| `--verbose` | Показывать DEBUG-логи | - |

### Примеры

```bash
# Получить все коммиты ветки dev
python main.py --owner myorg --repo myrepo --branch dev

# Только коммиты конкретного автора (по GitHub-логину)
python main.py --owner myorg --repo myrepo --author NF

# Несколько авторов через запятую (логин или git-имя)
python main.py --owner myorg --repo myrepo --author Filippov-Nikolay,NF

# Фильтр по автору + ограничение числа коммитов
python main.py --owner myorg --repo myrepo --author NF --max-commits 50

# Только первые 50 коммитов, сохранить в custom.json
python main.py --owner myorg --repo myrepo --max-commits 50 --output custom.json

# Только вывод в консоль, без сохранения в файл
python main.py --owner myorg --repo myrepo --no-save

# Расширенный вывод для отладки
python main.py --owner myorg --repo myrepo --verbose
```

> **Как работает фильтр `--author`:** сравнение без учёта регистра по двум полям одновременно — git-имени автора коммита (`Filippov Nikolay`) и GitHub-логину (`NF`). Достаточно совпадения по одному из них. Несколько авторов перечисляются через запятую без пробелов.

---

## Режим 2 - Docker

Самый простой способ запустить - без установки Python и зависимостей вручную.

```bash
# Скопируйте .env и вставьте токен
cp .env.example .env

# Собрать образ и запустить
docker compose up --build
```

Приложение поднимется на `http://localhost:8000`.

Остановить: `docker compose down`

---

## Режим 3 - API + Веб-интерфейс

Запустите сервер:

```bash
uvicorn api:app --reload
```

Сервер поднимается на `http://localhost:8000`.

**Веб-интерфейс** — откройте `http://localhost:8000` в браузере.

#### Форма поиска

Введите владельца, репозиторий, ветку (необязательно) и максимальное число коммитов (необязательно), затем нажмите **«Анализировать»**.

- **История ввода** — каждое поле запоминает последние введённые значения. При фокусе или вводе появляется выпадающий список с подсказками. Значения сохраняются в `localStorage` и переживают перезагрузку страницы. Удалить конкретную подсказку можно кнопкой **✕** рядом с ней.
- **Восстановление формы** — значения полей восстанавливаются автоматически после перезагрузки страницы.
- **Кнопка «Очистить»** — скрывает результаты последнего поиска (поля формы и история подсказок не затрагиваются). Доступна только при наличии результатов; открывает диалог подтверждения перед очисткой.

#### Процесс загрузки

Во время анализа кнопка переходит в режим загрузки (иконка → спиннер). Под формой плавно появляется счётчик прогресса «Загружаем коммиты: 5 из 42», который обновляется в реальном времени по мере получения данных через SSE.

#### Карточки коммитов

Каждая карточка содержит:

- аватар автора (реальное фото с GitHub, если есть аккаунт, иначе инициал);
- SHA-хэш, имя автора, дату и ссылку на коммит на GitHub;
- строку статистики (+добавлено / −удалено) с визуальной полоской;
- раскрываемый блок **«Описание»** — полный текст коммита (body), если он есть;
- раскрываемый блок **«Файлы (N)»** — список изменённых файлов с иконками статуса (A/M/D/R), счётчиками строк и кнопкой **diff** для просмотра патча каждого файла;
- комментарии к коммиту (если есть), с аватаром и привязкой к файлу/строке.

#### Сохранение результатов

Результаты последнего поиска автоматически сохраняются в `localStorage`. После перезагрузки страницы они восстанавливаются — повторный запрос к API не нужен.

**REST API** - запрашивайте напрямую из кода или Swagger UI:

### Эндпоинты

| Метод | URL | Описание |
|---|---|---|
| `GET` | `/commits` | Все коммиты одним JSON-ответом |
| `GET` | `/commits/stream` | То же через SSE - отдаёт коммиты по одному в реальном времени |
| `GET` | `/health` | Проверка работоспособности: `{"status": "ok"}` |
| `GET` | `/docs` | Swagger UI - интерактивная документация API |
| `GET` | `/redoc` | ReDoc - альтернативный вид документации |

### GET /commits

```
GET http://localhost:8000/commits?owner=microsoft&repo=vscode&branch=main&max_commits=10
```

| Параметр | Тип | Обязательный | Описание |
|---|---|---|---|
| `owner` | string | да | Владелец репозитория |
| `repo` | string | да | Название репозитория |
| `branch` | string | нет (`main`) | Ветка |
| `author` | string | нет | Фильтр по автору: git-имя или GitHub-логин, несколько через запятую |
| `max_commits` | integer > 0 | нет | Ограничение числа коммитов |

Ответ - массив объектов CommitEntry (см. раздел «Формат JSON»). Параллельно выводит Rich-отчёт в консоль сервера.

### GET /commits/stream (SSE)

```
GET http://localhost:8000/commits/stream?owner=microsoft&repo=vscode&branch=main&author=NF
```

Принимает те же параметры, что и `/commits` (`owner`, `repo`, `branch`, `author`, `max_commits`).

Использует [Server-Sent Events](https://developer.mozilla.org/ru/docs/Web/API/Server-sent_events). Браузер подключается через `EventSource` и получает события по мере загрузки каждого коммита:

```
data: {"type": "total",    "total": 42}
data: {"type": "progress", "current": 1, "total": 42, "entry": {...}}
data: {"type": "progress", "current": 2, "total": 42, "entry": {...}}
...
data: {"type": "done"}
```

В случае ошибки: `data: {"type": "error", "message": "описание ошибки"}`

---

## Структура проекта

```
github/
├── github_parser/          # Основной пакет
│   ├── __init__.py         # Публичный API пакета
│   ├── types.py            # TypedDict-типы данных (CommitEntry, FileChange и др.)
│   ├── client.py           # HTTP-клиент: запросы, retry, rate limit
│   ├── fetcher.py          # Функции для каждого эндпоинта GitHub API
│   └── report.py           # Сборка отчёта и вывод через Rich
├── static/                 # Фронтенд (отдаётся сервером по /static/...)
│   ├── css/main.css        # Стили (GitHub Dark тема)
│   └── js/main.js          # Логика: SSE, рендер карточек
├── tests/                  # Тесты
│   ├── test_client.py      # Тесты HTTP-клиента
│   ├── test_fetcher.py     # Тесты получения данных
│   └── test_report.py      # Тесты сборки и сохранения отчёта
├── api.py                  # FastAPI-сервер (REST API + раздача фронтенда)
├── main.py                 # Точка входа CLI (argparse + .env)
├── Dockerfile              # Образ для запуска в контейнере
├── docker-compose.yml      # Оркестрация: один сервис, порт 8000
├── requirements.txt        # Зависимости для запуска
├── requirements-dev.txt    # Зависимости для разработки
├── pyproject.toml          # Настройки проекта, ruff, mypy, pytest
├── .env.example            # Шаблон файла с секретами
├── .dockerignore           # Что не копировать в Docker-образ
├── .gitignore
└── LICENSE                 # MIT
```

---

## Формат JSON-отчёта

```json
[
  {
    "sha": "abc1234567890...",
    "short": "abc1234",
    "author": "Имя Автора",
    "avatar_url": "https://avatars.githubusercontent.com/u/12345678",
    "date": "2024-01-15T10:00:00Z",
    "message": "feat: добавить новую функцию\n\nПодробное описание изменений",
    "url": "https://github.com/owner/repo/commit/abc1234...",
    "stats": { "total": 42, "additions": 30, "deletions": 12 },
    "files": [
      {
        "filename": "src/main.py",
        "status": "modified",
        "additions": 30,
        "deletions": 12,
        "patch": "@@ -1,5 +1,8 @@\n ..."
      }
    ],
    "comments": [
      {
        "user": "reviewer",
        "avatar_url": "https://avatars.githubusercontent.com/u/87654321",
        "body": "Текст комментария",
        "created": "2024-01-15T11:00:00Z",
        "path": "src/main.py",
        "line": 42
      }
    ]
  }
]
```

| Поле | Тип | Описание |
|---|---|---|
| `sha` | string | Полный SHA-хэш коммита (40 символов) |
| `short` | string | Сокращённый SHA (первые 7 символов) |
| `author` | string | Git-имя автора |
| `avatar_url` | string \| null | URL аватарки автора на GitHub; `null` если у автора нет GitHub-аккаунта |
| `date` | string | Дата коммита в формате ISO 8601 |
| `message` | string | Полное сообщение коммита (первая строка — заголовок, остальное — body) |
| `url` | string | Прямая ссылка на коммит на GitHub |
| `stats.total` | integer | Всего изменённых строк |
| `stats.additions` | integer | Добавленных строк |
| `stats.deletions` | integer | Удалённых строк |
| `files[].filename` | string | Путь к файлу от корня репозитория |
| `files[].status` | string | Статус: `added`, `modified`, `removed`, `renamed` |
| `files[].patch` | string | Unified diff; пустая строка для бинарных файлов |
| `comments[].user` | string | GitHub-логин автора комментария |
| `comments[].avatar_url` | string \| null | URL аватарки автора комментария |
| `comments[].path` | string \| null | Файл, к которому привязан комментарий; `null` для общих |
| `comments[].line` | integer \| null | Номер строки; `null` для общих комментариев |

---

## Разработка

```bash
# Установить все зависимости включая dev-инструменты
pip install -r requirements-dev.txt

# Запустить тесты
pytest

# Тесты с отчётом о покрытии кода
pytest --cov --cov-report=term-missing

# Линтер
ruff check .

# Проверка типов
mypy github_parser/
```
