"""
Пакет github_parser - инструмент для получения данных коммитов из GitHub API.

Экспортирует три основные функции:
- build_report  - получить и собрать отчёт
- print_summary - вывести отчёт в консоль
- save_report   - сохранить отчёт в JSON

Пример использования:
    from github_parser import build_report, print_summary, save_report

    report = build_report("microsoft", "vscode", "main", token="ghp_...")
    print_summary(report, "microsoft", "vscode", "main")
    save_report(report, "report.json")
"""

from .report import build_report, print_summary, save_report

__all__ = ["build_report", "print_summary", "save_report"]
__version__ = "1.0.0"
