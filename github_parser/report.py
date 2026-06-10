"""
Модуль сборки и отображения отчёта о коммитах.

Содержит три публичные функции:

build_report  - обходит все коммиты ветки, собирает полный отчёт в виде
                списка CommitEntry. Показывает прогресс-бар во время работы.

print_summary - красиво выводит отчёт в консоль с помощью Rich:
                таблицы, цвета, иконки статусов файлов.

save_report   - сохраняет отчёт в JSON-файл.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .fetcher import fetch_commit_comments, fetch_commit_details, fetch_commits
from .types import CommitComment, CommitEntry, CommitStats, FileChange

logger = logging.getLogger(__name__)

# Глобальная консоль Rich - поддерживает цвета и Unicode на всех платформах.
# Один экземпляр на модуль, чтобы не создавать новые объекты при каждом вызове.
console = Console()

# Иконки для статуса файла в Rich-разметке (цвет + символ)
_FILE_STATUS_ICONS: dict[str, str] = {
    "added":    "[green]+[/green]",
    "modified": "[yellow]~[/yellow]",
    "removed":  "[red]-[/red]",
    "renamed":  "[cyan]->[/cyan]",
}


def build_entry(raw: dict, details: dict, comments_raw: list[dict]) -> CommitEntry:
    """
    Собирает один CommitEntry из трёх сырых словарей GitHub API.

    Вынесено в отдельную функцию, чтобы её мог использовать и build_report,
    и SSE-эндпоинт в api.py - без дублирования кода.

    Args:
        raw:          Элемент из /repos/{owner}/{repo}/commits (список коммитов)
        details:      Ответ /repos/{owner}/{repo}/commits/{sha} (детали + diff)
        comments_raw: Ответ /repos/{owner}/{repo}/commits/{sha}/comments
    """
    sha        = raw["sha"]
    author     = raw["commit"]["author"]["name"]
    date       = raw["commit"]["author"]["date"]
    avatar_url = (raw.get("author") or {}).get("avatar_url")

    files_diff: list[FileChange] = [
        FileChange(
            filename  = f["filename"],
            status    = f["status"],
            additions = f.get("additions", 0),
            deletions = f.get("deletions", 0),
            patch     = f.get("patch", ""),
        )
        for f in details.get("files", [])
    ]

    commit_comments: list[CommitComment] = [
        CommitComment(
            user       = c["user"]["login"],
            avatar_url = c["user"].get("avatar_url"),
            body       = c["body"],
            created    = c["created_at"],
            path       = c.get("path"),
            line       = c.get("line"),
        )
        for c in comments_raw
        if c.get("user")
    ]

    raw_stats = details.get("stats", {})

    return CommitEntry(
        sha        = sha,
        short      = sha[:7],
        author     = author,
        avatar_url = avatar_url,
        date       = date,
        message  = raw["commit"]["message"],
        url      = raw["html_url"],
        stats    = CommitStats(
            total     = raw_stats.get("total", 0),
            additions = raw_stats.get("additions", 0),
            deletions = raw_stats.get("deletions", 0),
        ),
        files    = files_diff,
        comments = commit_comments,
    )


def _matches_author(raw: dict, authors_lower: set[str]) -> bool:
    """Проверяет, совпадает ли автор коммита с одним из заданных (без учёта регистра)."""
    name  = raw["commit"]["author"]["name"].lower()
    login = (raw.get("author") or {}).get("login", "").lower()
    return name in authors_lower or login in authors_lower


def build_report(
    owner: str,
    repo: str,
    branch: str,
    token: str | None,
    max_commits: Optional[int] = None,
    authors: Optional[list[str]] = None,
) -> list[CommitEntry]:
    """
    Собирает полный отчёт по всем коммитам указанной ветки.

    Алгоритм:
    1. Получаем список коммитов (может быть несколько страниц).
    2. Если задан фильтр authors - отсеиваем лишние коммиты до детальных запросов.
    3. Для каждого коммита делаем ещё 2 запроса: детали + комментарии.
    4. Собираем всё в список CommitEntry.

    Отображает прогресс-бар в консоли, пока идёт обработка.

    Args:
        owner:       Владелец репозитория.
        repo:        Название репозитория.
        branch:      Ветка для анализа.
        token:       GitHub токен или None.
        max_commits: Ограничение по числу коммитов (None = без ограничения).
        authors:     Список имён/логинов авторов для фильтрации (None = все).
                     Сравнение без учёта регистра по git-имени и GitHub-логину.

    Returns:
        Список CommitEntry - готовый отчёт.

    Raises:
        RuntimeError: Если API недоступен или вернул ошибку.
    """
    console.print(
        f"\n[bold cyan]Получаем коммиты[/bold cyan] ветки "
        f"[bold]{branch!r}[/bold] из [bold]{owner}/{repo}[/bold]...\n"
    )

    raw_commits = fetch_commits(owner, repo, branch, token, max_commits)

    if not raw_commits:
        console.print("[yellow]Коммитов не найдено.[/yellow]")
        return []

    if authors:
        authors_lower = {a.lower() for a in authors}
        raw_commits = [c for c in raw_commits if _matches_author(c, authors_lower)]
        console.print(
            f"[dim]Фильтр по авторам:[/dim] [bold]{', '.join(authors)}[/bold]  "
            f"[dim]→ подходит [bold]{len(raw_commits)}[/bold] коммитов[/dim]\n"
        )
        if not raw_commits:
            console.print("[yellow]Коммитов от указанных авторов не найдено.[/yellow]")
            return []

    console.print(f"[green]Найдено коммитов: [bold]{len(raw_commits)}[/bold][/green]\n")

    report: list[CommitEntry] = []

    # Прогресс-бар показывает текущий коммит и сколько осталось.
    # transient=True - бар исчезает после завершения, не засоряя вывод.
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Обрабатываем коммиты...", total=len(raw_commits))

        for raw in raw_commits:
            sha    = raw["sha"]
            short  = sha[:7]
            # Берём первую строку сообщения - это «заголовок» коммита по соглашению Git
            msg    = raw["commit"]["message"].split("\n")[0]
            author = raw["commit"]["author"]["name"]
            date   = raw["commit"]["author"]["date"]

            # Обновляем описание в прогресс-баре, чтобы видеть текущий коммит
            progress.update(
                task,
                description=f"[cyan]{short}[/cyan] {author[:20]}: {msg[:40]}",
            )

            # Два дополнительных запроса на каждый коммит
            details      = fetch_commit_details(owner, repo, sha, token)
            comments_raw = fetch_commit_comments(owner, repo, sha, token)

            report.append(build_entry(raw, details, comments_raw))

            progress.advance(task)

    return report


def print_summary(
    report: list[CommitEntry],
    owner: str,
    repo: str,
    branch: str,
) -> None:
    """
    Выводит отчёт в консоль в виде форматированных таблиц (Rich).

    Для каждого коммита показывает:
    - SHA, автора, дату и ссылку на GitHub
    - Первую строку сообщения
    - Статистику (+добавлено / -удалено)
    - Список изменённых файлов (первые 5; остальные - счётчиком)
    - Комментарии (если есть)

    Args:
        report: Список CommitEntry из build_report().
        owner:  Владелец репозитория - для заголовка.
        repo:   Название репозитория - для заголовка.
        branch: Ветка - для заголовка.
    """
    if not report:
        console.print("[yellow]Отчёт пуст - нечего выводить.[/yellow]")
        return

    # Заголовочная панель с общей информацией
    console.print(Panel(
        f"[bold white]{owner}/{repo}[/bold white]  •  "
        f"ветка: [bold cyan]{branch}[/bold cyan]  •  "
        f"коммитов: [bold green]{len(report)}[/bold green]",
        title="[bold]ОТЧЁТ О КОММИТАХ[/bold]",
        border_style="bright_blue",
    ))

    for item in report:
        # Дата в читаемом формате - только дата, без времени
        date_short = item["date"][:10]

        # Таблица с метаданными коммита
        meta = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
        meta.add_column(style="bold dim", width=12)
        meta.add_column()

        meta.add_row("SHA",        f"[bold cyan]{item['short']}[/bold cyan]  [dim]{item['sha'][7:]}[/dim]")
        meta.add_row("Автор",      item["author"])
        meta.add_row("Дата",       date_short)
        meta.add_row("Ссылка",     f"[link={item['url']}][blue]{item['url']}[/blue][/link]")
        meta.add_row("Сообщение",  f"[bold]{item['message'].splitlines()[0]}[/bold]")
        meta.add_row(
            "Статистика",
            f"[green]+{item['stats']['additions']}[/green]  "
            f"[red]-{item['stats']['deletions']}[/red]  "
            f"[dim](всего: {item['stats']['total']})[/dim]",
        )
        console.print(meta)

        # Таблица изменённых файлов
        if item["files"]:
            files_table = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
            files_table.add_column("Ст.", justify="center", width=4)
            files_table.add_column("Файл")
            files_table.add_column("[green]+[/green]", justify="right", width=6)
            files_table.add_column("[red]-[/red]",     justify="right", width=6)

            # Показываем первые 5 файлов; для длинных коммитов это достаточно
            for f in item["files"][:5]:
                icon = _FILE_STATUS_ICONS.get(f["status"], "?")
                files_table.add_row(
                    icon,
                    f["filename"],
                    str(f["additions"]),
                    str(f["deletions"]),
                )

            if len(item["files"]) > 5:
                remaining = len(item["files"]) - 5
                files_table.add_row("", f"[dim]... и ещё {remaining} файлов[/dim]", "", "")

            console.print(files_table)

        # Комментарии к коммиту
        if item["comments"]:
            console.print(f"  [bold]Комментарии ({len(item['comments'])}):[/bold]")
            for c in item["comments"]:
                # Для комментариев к строкам показываем файл и номер строки
                path_info = (
                    f" [dim]{c['path']}:{c['line']}[/dim]"
                    if c.get("path") else ""
                )
                # Обрезаем длинные комментарии - полный текст есть в JSON
                body_preview = c["body"][:120] + ("…" if len(c["body"]) > 120 else "")
                console.print(f"  [cyan]{c['user']}[/cyan]{path_info}: {body_preview}")

        # Горизонтальный разделитель между коммитами
        console.rule(style="dim")


def save_report(report: list[CommitEntry], output_file: str) -> None:
    """
    Сохраняет отчёт в JSON-файл.

    Почему ensure_ascii=False:
    Без этого флага json.dump заменяет кириллицу и прочие не-ASCII символы
    на \\uXXXX-последовательности, что сильно затрудняет чтение файла вручную.
    С флагом символы сохраняются как есть - файл читается нормально.

    Args:
        report:      Список CommitEntry для сохранения.
        output_file: Путь к выходному файлу (относительный или абсолютный).

    Raises:
        RuntimeError: Если нет прав на запись или диск заполнен.
    """
    path = Path(output_file)
    try:
        with path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        console.print(
            f"\n[green]Отчёт сохранён:[/green] [bold]{path.resolve()}[/bold]"
        )
    except PermissionError as exc:
        raise RuntimeError(f"Нет прав на запись файла: {path}") from exc
    except OSError as exc:
        raise RuntimeError(f"Не удалось сохранить файл {path}: {exc}") from exc
