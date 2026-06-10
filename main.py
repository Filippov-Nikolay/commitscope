"""
Точка входа GitHub Commits Parser.

Этот файл отвечает только за три вещи:
1. Разбор аргументов командной строки (argparse)
2. Загрузку переменных окружения из .env (python-dotenv)
3. Вызов функций из пакета github_parser

Вся бизнес-логика находится в github_parser/.

Примеры запуска:
    python main.py --owner microsoft --repo vscode --branch main
    python main.py --owner myorg --repo myrepo --branch dev --max-commits 50
    python main.py --owner myorg --repo myrepo --no-save --verbose
    python main.py --help
"""

import argparse
import logging
import os
import sys

# python-dotenv читает файл .env и загружает переменные в os.environ.
# Если .env не существует - просто ничего не делает, ошибки нет.
# Это позволяет хранить токен в .env, а не хардкодить в коде.
from dotenv import load_dotenv

load_dotenv()

# Импортируем только после load_dotenv, чтобы переменные уже были в окружении
from github_parser.report import build_report, print_summary, save_report


def setup_logging(verbose: bool) -> None:
    """
    Настраивает систему логирования для всего приложения.

    Два режима:
    - Обычный (verbose=False): выводим только WARNING и ERROR.
      Пользователь видит только предупреждения о rate limit и ошибках.
    - Расширенный (verbose=True): добавляем DEBUG-сообщения.
      Полезно при отладке - видно каждый запрос, каждую страницу пагинации.
    """
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        # Формат: УРОВЕНЬ [модуль] сообщение
        format="%(levelname)s [%(name)s] %(message)s",
    )


def parse_args() -> argparse.Namespace:
    """
    Разбирает аргументы командной строки.

    Почему argparse вместо хардкода в коде:
    - Не нужно редактировать исходный код для смены репозитория
    - Работает с --help из коробки
    - Легко запускать из скриптов и CI с разными параметрами
    """
    parser = argparse.ArgumentParser(
        description="GitHub Commits Parser - получает коммиты, diff и комментарии.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
примеры:
  python main.py --owner microsoft --repo vscode --branch main
  python main.py --owner myorg --repo myrepo --branch dev --max-commits 50
  python main.py --owner myorg --repo myrepo --author Filippov-Nikolay,NF
  python main.py --owner myorg --repo myrepo --output report.json --verbose
  python main.py --owner myorg --repo myrepo --no-save
        """,
    )

    # Обязательные аргументы - без них запуск невозможен
    parser.add_argument(
        "--owner",
        required=True,
        help="Владелец репозитория: логин пользователя или название организации",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Название репозитория",
    )

    # Необязательные аргументы с разумными значениями по умолчанию
    parser.add_argument(
        "--branch",
        default="main",
        help="Ветка для анализа (по умолчанию: main)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help=(
            "GitHub Personal Access Token. "
            "Если не указан - читается из переменной GITHUB_TOKEN в .env. "
            "Без токена лимит: 60 запросов/час."
        ),
    )
    parser.add_argument(
        "--max-commits",
        type=int,
        default=None,
        metavar="N",
        help="Максимальное число коммитов (по умолчанию: все)",
    )
    parser.add_argument(
        "--author",
        default=None,
        metavar="NAME[,NAME...]",
        help=(
            "Фильтр по автору: git-имя или GitHub-логин. "
            "Несколько авторов — через запятую без пробелов. "
            "Пример: --author Filippov-Nikolay,NF"
        ),
    )
    parser.add_argument(
        "--output",
        default="commits_report.json",
        help="Путь к выходному JSON-файлу (по умолчанию: commits_report.json)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Не сохранять отчёт в файл - только вывести в консоль",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Расширенный вывод: показывать DEBUG-логи (пагинация, детали запросов)",
    )

    return parser.parse_args()


def main() -> int:
    """
    Основная функция приложения.

    Порядок работы:
    1. Разбираем аргументы CLI
    2. Настраиваем логирование
    3. Определяем токен (CLI -> переменная окружения -> None)
    4. Запускаем сборку отчёта
    5. Выводим в консоль и сохраняем в файл

    Returns:
        Код выхода: 0 - успех, 1 - ошибка.
        Стандартное соглашение Unix: sys.exit(main()).
    """
    args = parse_args()
    setup_logging(args.verbose)

    # Определяем токен: аргумент CLI имеет приоритет над .env
    token: str | None = args.token or os.getenv("GITHUB_TOKEN")

    if not token:
        # Предупреждаем, но не прерываем - публичные репозитории работают без токена
        print(
            "GITHUB_TOKEN не задан. Лимит: 60 запросов/час. "
            "Задайте токен в файле .env или передайте --token.",
            file=sys.stderr,
        )

    authors = [a.strip() for a in args.author.split(",")] if args.author else None

    try:
        # Собираем отчёт - может занять несколько минут для больших репозиториев
        report = build_report(
            owner       = args.owner,
            repo        = args.repo,
            branch      = args.branch,
            token       = token,
            max_commits = args.max_commits,
            authors     = authors,
        )

        # Выводим красиво отформатированную сводку в консоль
        print_summary(report, args.owner, args.repo, args.branch)

        # Сохраняем полный отчёт в JSON (если не передан --no-save)
        if not args.no_save:
            save_report(report, args.output)

    except RuntimeError as exc:
        # RuntimeError - ожидаемые ошибки: API, сеть, файловая система.
        # Выводим понятное сообщение без трейсбека.
        print(f"\nОШИБКА: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        # Пользователь нажал Ctrl+C - завершаем чисто
        print("\nПрервано пользователем.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
