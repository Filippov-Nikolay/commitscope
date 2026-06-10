"""
Тесты модуля сборки и сохранения отчёта (github_parser/report.py).

Тестируем:
- save_report: создание файла, корректный JSON, кириллица, ошибки прав доступа
- build_report: пустой репозиторий, базовый сценарий сборки

Для build_report мокируем функции из fetcher.py - не делаем реальных HTTP-запросов.

Запуск:
    pytest tests/test_report.py -v
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from github_parser.report import build_report, save_report
from github_parser.types import CommitEntry, CommitStats, FileChange


# =============================================================================
# Тестовые данные (фикстуры)
# =============================================================================

# Минимальный корректный CommitEntry для использования в тестах
SAMPLE_COMMIT: CommitEntry = CommitEntry(
    sha      = "abc1234567890abcdef",
    short    = "abc1234",
    author   = "Test User",
    date     = "2024-01-15T10:00:00Z",
    message  = "feat: add new feature\n\nDetailed description here",
    url      = "https://github.com/owner/repo/commit/abc1234567890abcdef",
    stats    = CommitStats(total=10, additions=8, deletions=2),
    files    = [
        FileChange(
            filename  = "src/main.py",
            status    = "modified",
            additions = 8,
            deletions = 2,
            patch     = "@@ -1,2 +1,3 @@\n+new line",
        )
    ],
    comments = [],
)


# =============================================================================
# save_report - сохранение отчёта в JSON
# =============================================================================

def test_save_report_creates_file(tmp_path: Path):
    """Функция создаёт файл по указанному пути."""
    output = tmp_path / "report.json"

    save_report([SAMPLE_COMMIT], str(output))

    assert output.exists(), "Файл должен быть создан"


def test_save_report_writes_valid_json(tmp_path: Path):
    """Содержимое файла является валидным JSON."""
    output = tmp_path / "report.json"

    save_report([SAMPLE_COMMIT], str(output))

    # json.loads не выбрасывает - значит JSON корректный
    data = json.loads(output.read_text(encoding="utf-8"))
    assert isinstance(data, list)


def test_save_report_preserves_all_fields(tmp_path: Path):
    """Все поля CommitEntry сохраняются без потерь."""
    output = tmp_path / "report.json"

    save_report([SAMPLE_COMMIT], str(output))

    data = json.loads(output.read_text(encoding="utf-8"))
    entry = data[0]

    assert entry["sha"]    == "abc1234567890abcdef"
    assert entry["author"] == "Test User"
    assert entry["stats"]["additions"] == 8
    assert entry["files"][0]["filename"] == "src/main.py"


def test_save_report_preserves_cyrillic(tmp_path: Path):
    """
    Кириллица сохраняется как есть, а не как \\uXXXX-последовательности.

    ensure_ascii=False в json.dump - ключевое условие для читаемого файла.
    """
    commit = CommitEntry(**{**SAMPLE_COMMIT, "author": "Иван Петров"})
    output = tmp_path / "report.json"

    save_report([commit], str(output))

    # Читаем как обычный текст и ищем кириллицу напрямую
    content = output.read_text(encoding="utf-8")
    assert "Иван Петров" in content, "Кириллица должна храниться без эскейпинга"
    assert "\\u" not in content or "Иван" in content


def test_save_report_saves_multiple_commits(tmp_path: Path):
    """Список из нескольких коммитов сохраняется полностью."""
    output = tmp_path / "report.json"

    save_report([SAMPLE_COMMIT, SAMPLE_COMMIT], str(output))

    data = json.loads(output.read_text(encoding="utf-8"))
    assert len(data) == 2


def test_save_report_raises_on_permission_error(tmp_path: Path):
    """
    PermissionError при записи преобразуется в RuntimeError с понятным сообщением.

    Мокируем Path.open, так как именно его вызывает save_report.
    """
    output = tmp_path / "report.json"

    with patch.object(Path, "open", side_effect=PermissionError("нет прав")):
        with pytest.raises(RuntimeError, match="прав"):
            save_report([SAMPLE_COMMIT], str(output))


def test_save_report_raises_on_os_error(tmp_path: Path):
    """OSError (диск заполнен и т.п.) преобразуется в RuntimeError."""
    output = tmp_path / "report.json"

    with patch.object(Path, "open", side_effect=OSError("no space left")):
        with pytest.raises(RuntimeError, match="сохранить"):
            save_report([SAMPLE_COMMIT], str(output))


# =============================================================================
# build_report - сборка отчёта
# =============================================================================

def test_build_report_returns_empty_list_for_empty_repo():
    """
    Если репозиторий не содержит коммитов - возвращается пустой список.

    Мокируем fetch_commits внутри report.py - не делаем HTTP-запросов.
    """
    with patch("github_parser.report.fetch_commits", return_value=[]):
        result = build_report("owner", "repo", "main", token=None)

    assert result == []


def test_build_report_processes_commits_correctly():
    """
    build_report правильно собирает CommitEntry из ответов API.

    Мокируем все три функции из fetcher, подставляя тестовые данные.
    """
    # Сырой ответ из эндпоинта /commits (список)
    raw_commit = {
        "sha": "abc1234567890",
        "html_url": "https://github.com/owner/repo/commit/abc1234567890",
        "commit": {
            "message": "fix: resolve issue\n\nMore details",
            "author": {
                "name": "Jane Doe",
                "date": "2024-03-01T12:00:00Z",
            },
        },
    }

    # Сырой ответ из эндпоинта /commits/{sha} (детали)
    raw_details = {
        "stats": {"total": 6, "additions": 4, "deletions": 2},
        "files": [
            {
                "filename": "app/utils.py",
                "status": "modified",
                "additions": 4,
                "deletions": 2,
                "patch": "@@ -1 +1,2 @@\n+fix",
            }
        ],
    }

    # Ответ из эндпоинта /commits/{sha}/comments
    raw_comments = [
        {
            "user": {"login": "reviewer"},
            "body": "Good fix!",
            "created_at": "2024-03-01T13:00:00Z",
        }
    ]

    with (
        patch("github_parser.report.fetch_commits",        return_value=[raw_commit]),
        patch("github_parser.report.fetch_commit_details", return_value=raw_details),
        patch("github_parser.report.fetch_commit_comments", return_value=raw_comments),
    ):
        result = build_report("owner", "repo", "main", token=None)

    # Проверяем структуру результата
    assert len(result) == 1
    entry = result[0]

    assert entry["sha"]    == "abc1234567890"
    assert entry["short"]  == "abc1234"
    assert entry["author"] == "Jane Doe"
    assert entry["stats"]["additions"] == 4
    assert entry["stats"]["deletions"] == 2

    assert len(entry["files"]) == 1
    assert entry["files"][0]["filename"] == "app/utils.py"
    assert entry["files"][0]["status"]   == "modified"

    assert len(entry["comments"]) == 1
    assert entry["comments"][0]["user"] == "reviewer"
    assert entry["comments"][0]["body"] == "Good fix!"


def test_build_report_skips_comments_without_user():
    """
    Комментарии без поля user пропускаются (защита от некорректных ответов API).
    """
    raw_commit = {
        "sha": "aaabbb123456",
        "html_url": "https://github.com/o/r/commit/aaabbb123456",
        "commit": {
            "message": "chore: update deps",
            "author": {"name": "Dev", "date": "2024-01-01T00:00:00Z"},
        },
    }

    raw_details = {"stats": {"total": 0, "additions": 0, "deletions": 0}, "files": []}

    # Один комментарий без user, один нормальный
    raw_comments = [
        {"body": "ghost comment", "created_at": "2024-01-01T00:00:00Z"},  # нет user
        {"user": {"login": "alice"}, "body": "ok", "created_at": "2024-01-01T01:00:00Z"},
    ]

    with (
        patch("github_parser.report.fetch_commits",         return_value=[raw_commit]),
        patch("github_parser.report.fetch_commit_details",  return_value=raw_details),
        patch("github_parser.report.fetch_commit_comments", return_value=raw_comments),
    ):
        result = build_report("owner", "repo", "main", token=None)

    # Должен остаться только один комментарий (с user)
    assert len(result[0]["comments"]) == 1
    assert result[0]["comments"][0]["user"] == "alice"
