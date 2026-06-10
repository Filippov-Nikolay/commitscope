"""
FastAPI-сервер GitHub Commits Parser.

Запуск:
    uvicorn api:app --reload

Документация (после запуска):
    http://localhost:8000/docs      - Swagger UI (можно тестировать прямо в браузере)
    http://localhost:8000/redoc     - ReDoc (альтернативный вид документации)

Пример запроса:
    GET http://localhost:8000/commits?owner=microsoft&repo=vscode&branch=main
    GET http://localhost:8000/commits?owner=myorg&repo=myrepo&branch=dev&max_commits=10
"""

import asyncio
import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from github_parser.fetcher import fetch_commit_comments, fetch_commit_details, fetch_commits
from github_parser.report import build_entry, build_report, print_summary

# Загружаем GITHUB_TOKEN из .env - нужно сделать до первого os.getenv()
load_dotenv()

# Создаём приложение FastAPI.
# title и description отображаются в /docs - это первое, что видит разработчик.
app = FastAPI(
    title="GitHub Commits Parser",
    description=(
        "Получает коммиты, diff и комментарии из GitHub-репозитория.\n\n"
        "Результат возвращается как JSON. Параллельно выводит "
        "отформатированный отчёт в консоль сервера."
    ),
    version="1.0.0",
)


@app.get(
    "/commits",
    summary="Получить коммиты ветки",
    response_description="Список коммитов с diff и комментариями",
)
def get_commits(
    owner: str = Query(..., description="Владелец репозитория (логин или организация)"),
    repo: str  = Query(..., description="Название репозитория"),
    branch: str = Query("main", description="Ветка (по умолчанию: main)"),
    max_commits: int | None = Query(
        None,
        description="Максимальное число коммитов (по умолчанию: все)",
        gt=0,
    ),
    author: str | None = Query(
        None,
        description=(
            "Фильтр по автору: git-имя или GitHub-логин. "
            "Несколько авторов — через запятую. Пример: Filippov-Nikolay,NF"
        ),
    ),
) -> list[dict]:
    """
    Возвращает список коммитов указанной ветки.

    Для каждого коммита включает:
    - Метаданные (SHA, автор, дата, сообщение, ссылка)
    - Статистику изменений (добавлено/удалено строк)
    - Список изменённых файлов с unified diff
    - Комментарии к коммиту

    **Параметры:**
    - `owner` / `repo` - обязательные. Например: `microsoft` / `vscode`
    - `branch` - ветка, по умолчанию `main`
    - `max_commits` - ограничение на число коммитов (полезно для тестирования)

    **Токен:** читается из переменной `GITHUB_TOKEN` в `.env`.
    Без токена лимит 60 запросов/час.
    """
    # Токен из переменной окружения - задаётся в .env, не передаётся в запросе
    token: str | None = os.getenv("GITHUB_TOKEN")

    authors = [a.strip() for a in author.split(",")] if author else None

    try:
        report = build_report(
            owner       = owner,
            repo        = repo,
            branch      = branch,
            token       = token,
            max_commits = max_commits,
            authors     = authors,
        )

        # Выводим красиво отформатированный отчёт в консоль сервера.
        # Это удобно на этапе разработки - видишь результат прямо в терминале
        # где запущен uvicorn, без открытия JSON-файла.
        print_summary(report, owner, repo, branch)

        # Возвращаем тот же отчёт как JSON-ответ API
        return report

    except RuntimeError as exc:
        # RuntimeError от нашего клиента (API недоступен, 404, таймаут и т.д.)
        # Преобразуем в HTTP 502 Bad Gateway - сервер не смог получить данные от GitHub
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/commits/stream", include_in_schema=False)
async def stream_commits(
    owner: str = Query(...),
    repo: str  = Query(...),
    branch: str = Query("main"),
    max_commits: int | None = Query(None, gt=0),
    author: str | None = Query(None),
) -> StreamingResponse:
    """
    SSE-эндпоинт (Server-Sent Events) - отдаёт коммиты по одному по мере загрузки.

    Браузер подключается через EventSource и получает события:
    - {"type": "total",    "total": N}           - сколько коммитов найдено
    - {"type": "progress", "current": i, "total": N, "entry": {...}} - очередной коммит
    - {"type": "done"}                            - всё загружено
    - {"type": "error",   "message": "..."}       - ошибка

    Это позволяет показывать «5 из 15 загружено» в реальном времени,
    не дожидаясь завершения всех запросов.
    """
    token = os.getenv("GITHUB_TOKEN")
    authors = [a.strip() for a in author.split(",")] if author else None

    async def generator():
        try:
            commits = await asyncio.to_thread(
                fetch_commits, owner, repo, branch, token, max_commits
            )

            if authors:
                authors_lower = {a.lower() for a in authors}
                commits = [
                    c for c in commits
                    if c["commit"]["author"]["name"].lower() in authors_lower
                    or (c.get("author") or {}).get("login", "").lower() in authors_lower
                ]

            total = len(commits)

            # Сообщаем фронтенду общее количество - он покажет «0 из N»
            yield f"data: {json.dumps({'type': 'total', 'total': total})}\n\n"

            if total == 0:
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            report = []  # Собираем все коммиты, чтобы потом передать в print_summary

            for i, raw in enumerate(commits, 1):
                sha = raw["sha"]

                # Детали и комментарии запрашиваем параллельно - экономим время
                details, comments_raw = await asyncio.gather(
                    asyncio.to_thread(fetch_commit_details, owner, repo, sha, token),
                    asyncio.to_thread(fetch_commit_comments, owner, repo, sha, token),
                )

                entry = build_entry(raw, details, comments_raw)
                report.append(entry)

                # Отправляем готовый коммит - фронтенд сразу его покажет
                yield f"data: {json.dumps({'type': 'progress', 'current': i, 'total': total, 'entry': entry})}\n\n"

            # Выводим Rich-отчёт в консоль сервера после завершения всей загрузки
            # to_thread нужен потому что print_summary использует синхронный Rich
            await asyncio.to_thread(print_summary, report, owner, repo, branch)

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Отключает буферизацию в nginx (если сервер за прокси)
            "X-Accel-Buffering": "no",
        },
    )


# Раздаём папку static/ по адресу /static/...
# Браузер будет запрашивать /static/css/main.css, /static/js/main.js и т.д.
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Главная страница - отдаём index.html из папки static/."""
    return FileResponse("static/index.html")


@app.get("/health", summary="Проверка работоспособности сервера")
def health_check() -> dict[str, str]:
    """
    Простой ping-эндпоинт. Возвращает {"status": "ok"}.

    Используется для проверки, что сервер запущен и отвечает.
    Полезен при деплое (healthcheck в Docker/CI).
    """
    return {"status": "ok"}
