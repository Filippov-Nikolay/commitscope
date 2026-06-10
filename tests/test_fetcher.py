"""
Тесты модуля получения данных с GitHub API (github_parser/fetcher.py).

Проверяем три функции:
- fetch_commits       - пагинация, ограничение max_commits, пустой репозиторий
- fetch_commit_details- правильный URL и возврат данных
- fetch_commit_comments-список комментариев и пустой ответ

Запуск:
    pytest tests/test_fetcher.py -v
"""

import responses as resp_mock
import pytest

from github_parser.client import BASE_URL
from github_parser.fetcher import (
    fetch_commit_comments,
    fetch_commit_details,
    fetch_commits,
)


# =============================================================================
# fetch_commits - получение списка коммитов
# =============================================================================

@resp_mock.activate
def test_fetch_commits_returns_all_from_single_page():
    """Если коммитов меньше 100 - возвращает их все без лишних запросов."""
    commits = [{"sha": f"sha{i}", "commit": {"message": "msg"}} for i in range(5)]

    # Первая страница - 5 коммитов (< 100, значит последняя)
    resp_mock.add(
        resp_mock.GET,
        f"{BASE_URL}/repos/owner/repo/commits",
        json=commits,
        status=200,
    )

    result = fetch_commits("owner", "repo", "main", token=None)

    assert len(result) == 5
    # Должен быть ровно один запрос - страница одна
    assert len(resp_mock.calls) == 1


@resp_mock.activate
def test_fetch_commits_paginates_multiple_pages():
    """
    Если на первой странице ровно 100 коммитов - запрашивает следующую страницу.

    GitHub API сигнализирует о наличии следующей страницы тем, что
    текущая страница содержит ровно per_page (100) элементов.
    """
    page1 = [{"sha": f"sha{i}"} for i in range(100)]  # Полная страница -> есть ещё
    page2 = [{"sha": f"sha{i}"} for i in range(100, 110)]  # Неполная -> последняя

    resp_mock.add(resp_mock.GET, f"{BASE_URL}/repos/owner/repo/commits", json=page1, status=200)
    resp_mock.add(resp_mock.GET, f"{BASE_URL}/repos/owner/repo/commits", json=page2, status=200)

    result = fetch_commits("owner", "repo", "main", token=None)

    assert len(result) == 110
    assert len(resp_mock.calls) == 2


@resp_mock.activate
def test_fetch_commits_respects_max_commits():
    """Ограничение max_commits обрезает список до нужного количества."""
    commits = [{"sha": f"sha{i}"} for i in range(50)]

    resp_mock.add(
        resp_mock.GET,
        f"{BASE_URL}/repos/owner/repo/commits",
        json=commits,
        status=200,
    )

    result = fetch_commits("owner", "repo", "main", token=None, max_commits=10)

    assert len(result) == 10
    # Коммиты возвращаются в исходном порядке
    assert result[0]["sha"] == "sha0"
    assert result[9]["sha"] == "sha9"


@resp_mock.activate
def test_fetch_commits_returns_empty_for_empty_repo():
    """Пустой ответ API возвращает пустой список без ошибок."""
    resp_mock.add(
        resp_mock.GET,
        f"{BASE_URL}/repos/owner/repo/commits",
        json=[],
        status=200,
    )

    result = fetch_commits("owner", "repo", "main", token=None)

    assert result == []


@resp_mock.activate
def test_fetch_commits_passes_branch_as_sha_param():
    """Имя ветки передаётся в параметре sha (так работает GitHub API)."""
    resp_mock.add(
        resp_mock.GET,
        f"{BASE_URL}/repos/owner/repo/commits",
        json=[{"sha": "abc"}],
        status=200,
    )

    fetch_commits("owner", "repo", "my-feature-branch", token=None)

    # Проверяем, что параметр sha содержит имя ветки
    assert "sha=my-feature-branch" in resp_mock.calls[0].request.url


# =============================================================================
# fetch_commit_details - детали одного коммита
# =============================================================================

@resp_mock.activate
def test_fetch_commit_details_returns_stats_and_files():
    """Возвращает словарь со статистикой и списком файлов."""
    details = {
        "sha": "abc123",
        "stats": {"total": 5, "additions": 3, "deletions": 2},
        "files": [
            {"filename": "src/main.py", "status": "modified", "additions": 3, "deletions": 2}
        ],
    }

    resp_mock.add(
        resp_mock.GET,
        f"{BASE_URL}/repos/owner/repo/commits/abc123",
        json=details,
        status=200,
    )

    result = fetch_commit_details("owner", "repo", "abc123", token=None)

    assert result["sha"] == "abc123"
    assert result["stats"]["total"] == 5
    assert len(result["files"]) == 1


@resp_mock.activate
def test_fetch_commit_details_uses_correct_url():
    """Запрос идёт на правильный эндпоинт с SHA в пути."""
    resp_mock.add(
        resp_mock.GET,
        f"{BASE_URL}/repos/myorg/myrepo/commits/deadbeef",
        json={"sha": "deadbeef", "stats": {}, "files": []},
        status=200,
    )

    fetch_commit_details("myorg", "myrepo", "deadbeef", token=None)

    assert f"/repos/myorg/myrepo/commits/deadbeef" in resp_mock.calls[0].request.url


# =============================================================================
# fetch_commit_comments - комментарии к коммиту
# =============================================================================

@resp_mock.activate
def test_fetch_commit_comments_returns_list():
    """Возвращает список комментариев в исходном виде."""
    comments = [
        {
            "user": {"login": "alice"},
            "body": "Looks good!",
            "created_at": "2024-01-01T10:00:00Z",
        },
        {
            "user": {"login": "bob"},
            "body": "Please fix the typo.",
            "created_at": "2024-01-01T11:00:00Z",
            "path": "src/app.py",
            "line": 42,
        },
    ]

    resp_mock.add(
        resp_mock.GET,
        f"{BASE_URL}/repos/owner/repo/commits/abc123/comments",
        json=comments,
        status=200,
    )

    result = fetch_commit_comments("owner", "repo", "abc123", token=None)

    assert len(result) == 2
    assert result[0]["user"]["login"] == "alice"
    assert result[1]["path"] == "src/app.py"


@resp_mock.activate
def test_fetch_commit_comments_returns_empty_list():
    """Если комментариев нет - возвращает пустой список, не ошибку."""
    resp_mock.add(
        resp_mock.GET,
        f"{BASE_URL}/repos/owner/repo/commits/abc123/comments",
        json=[],
        status=200,
    )

    result = fetch_commit_comments("owner", "repo", "abc123", token=None)

    assert result == []
