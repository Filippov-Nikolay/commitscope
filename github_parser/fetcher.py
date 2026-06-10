"""
Модуль получения данных с GitHub API.

Здесь описаны три функции, каждая из которых отвечает ровно за один
эндпоинт GitHub REST API:

1. fetch_commits       - список коммитов ветки (GET /repos/{owner}/{repo}/commits)
2. fetch_commit_details - детали одного коммита  (GET /repos/{owner}/{repo}/commits/{sha})
3. fetch_commit_comments- комментарии к коммиту  (GET /repos/{owner}/{repo}/commits/{sha}/comments)

Функции возвращают сырые dict/list из API и ничего не знают
про финальный формат отчёта - эту работу делает report.py.
"""

import logging
from typing import Any, Optional, cast

from .client import BASE_URL, get

# Логгер модуля - используем для отладочных сообщений о пагинации
logger = logging.getLogger(__name__)


def fetch_commits(
    owner: str,
    repo: str,
    branch: str,
    token: str | None,
    max_commits: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Получает полный список коммитов ветки, обходя пагинацию.

    GitHub API отдаёт максимум 100 коммитов за один запрос (per_page=100).
    Функция автоматически запрашивает все страницы, пока они не закончатся.

    Args:
        owner:       Логин владельца или организации (например "microsoft").
        repo:        Название репозитория (например "vscode").
        branch:      Имя ветки (например "main" или "dev").
        token:       GitHub токен для авторизации или None.
        max_commits: Если задано - возвращает не более этого числа коммитов.
                     Полезно для тестирования или быстрого просмотра.

    Returns:
        Список сырых dict-ов от GitHub API, каждый описывает один коммит.
    """
    url = f"{BASE_URL}/repos/{owner}/{repo}/commits"
    commits: list[dict[str, Any]] = []
    page = 1

    while True:
        # Запрашиваем очередную страницу.
        # sha здесь - это имя ветки, не SHA коммита (параметр GitHub API так называется).
        batch: list[dict[str, Any]] = cast(
            list[dict[str, Any]],
            get(url, token, params={"sha": branch, "per_page": 100, "page": page}),
        )

        if not batch:
            # Пустой ответ - страниц больше нет
            break

        commits.extend(batch)
        logger.debug(
            "Страница %d: получено %d коммитов (всего накоплено: %d)",
            page, len(batch), len(commits),
        )

        # Проверяем ограничение на количество коммитов
        if max_commits and len(commits) >= max_commits:
            commits = commits[:max_commits]
            logger.debug("Достигнут лимит max_commits=%d, обрезаем список", max_commits)
            break

        # Если страница содержит меньше 100 элементов - она последняя
        if len(batch) < 100:
            break

        page += 1

    return commits


def fetch_commit_details(owner: str, repo: str, sha: str, token: str | None) -> dict[str, Any]:
    """
    Получает подробности одного коммита.

    В отличие от элементов из fetch_commits, ответ этого эндпоинта
    содержит полный список изменённых файлов и unified diff каждого файла.

    Поля ответа, которые нас интересуют:
    - stats.total / stats.additions / stats.deletions - суммарная статистика
    - files[].filename, files[].status, files[].additions, files[].deletions
    - files[].patch - текст unified diff (отсутствует у бинарных файлов)

    Args:
        sha: Полный SHA-хэш коммита (40 символов).
    """
    url = f"{BASE_URL}/repos/{owner}/{repo}/commits/{sha}"
    return cast(dict[str, Any], get(url, token))


def fetch_commit_comments(
    owner: str, repo: str, sha: str, token: str | None
) -> list[dict[str, Any]]:
    """
    Получает список комментариев к коммиту.

    Возвращает все виды комментариев:
    - Общие комментарии к коммиту (path=None, line=None)
    - Комментарии к конкретной строке файла (path и line заполнены)

    Если комментариев нет - GitHub возвращает пустой список [].
    """
    url = f"{BASE_URL}/repos/{owner}/{repo}/commits/{sha}/comments"
    return cast(list[dict[str, Any]], get(url, token))
