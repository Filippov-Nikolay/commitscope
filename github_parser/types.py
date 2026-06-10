"""
Типы данных для отчёта о коммитах.

TypedDict - это обычный dict во время выполнения, но mypy и IDE
используют эти определения для статической проверки типов.
Это позволяет ловить ошибки (опечатки в ключах, неверные типы) ещё
до запуска кода.
"""

from typing import Optional, TypedDict


class FileChange(TypedDict):
    """Изменение одного файла в рамках коммита."""

    filename: str   # Путь к файлу относительно корня репозитория
    status: str     # Статус: added / modified / removed / renamed
    additions: int  # Количество добавленных строк
    deletions: int  # Количество удалённых строк
    patch: str      # Unified diff - текст изменений (пуст у бинарных файлов)


class CommitStats(TypedDict):
    """Суммарная статистика изменений строк по всему коммиту."""

    total: int      # Всего изменённых строк (additions + deletions)
    additions: int  # Добавленных строк
    deletions: int  # Удалённых строк


class CommitComment(TypedDict):
    """
    Комментарий к коммиту.

    Бывает двух видов:
    - Общий комментарий к коммиту (path и line равны None)
    - Привязанный к конкретной строке файла (path и line заполнены)
    """

    user: str                  # Логин GitHub-пользователя, оставившего комментарий
    avatar_url: Optional[str]  # URL аватарки пользователя (None если не определён)
    body: str                  # Текст комментария (поддерживает Markdown)
    created: str               # Дата создания в формате ISO 8601 (например "2024-01-15T10:00:00Z")
    path: Optional[str]        # Путь к файлу - None для общих комментариев
    line: Optional[int]        # Номер строки - None для общих комментариев


class CommitEntry(TypedDict):
    """
    Полная запись об одном коммите в итоговом отчёте.

    Объединяет данные из трёх запросов к GitHub API:
    1. Список коммитов (/commits) - основные метаданные
    2. Детали коммита (/commits/{sha}) - файлы и статистика
    3. Комментарии (/commits/{sha}/comments)
    """

    sha: str                        # Полный SHA-хэш коммита (40 символов)
    short: str                      # Сокращённый SHA (первые 7 символов) для отображения
    author: str                     # Имя автора коммита
    avatar_url: Optional[str]       # URL аватарки автора на GitHub (None если нет аккаунта)
    date: str                       # Дата коммита в формате ISO 8601
    message: str                    # Полное сообщение коммита (может быть многострочным)
    url: str                        # Прямая ссылка на коммит на GitHub
    stats: CommitStats              # Суммарная статистика изменений
    files: list[FileChange]         # Список изменённых файлов с diff-патчами
    comments: list[CommitComment]   # Комментарии к коммиту
