"""
HTTP-клиент для работы с GitHub REST API.

Этот модуль - единственное место в проекте, которое реально делает
HTTP-запросы. Все остальные модули вызывают функцию get() отсюда.

Что умеет клиент:
- Формировать правильные заголовки авторизации
- Выставлять таймаут, чтобы не зависать при медленном сервере
- Повторять запрос при временных сетевых сбоях (до 3 раз, с паузой 1->2->4с)
- Автоматически ждать сброса rate limit и повторять запрос
- Выдавать понятное RuntimeError вместо трейсбека при любой ошибке
"""

import logging
import time
from typing import Any

import requests

# Логгер модуля - inherit-ует настройки из корневого логгера main.py
logger = logging.getLogger(__name__)

# Базовый адрес GitHub REST API - фиксируем, чтобы не дублировать в каждом модуле
BASE_URL = "https://api.github.com"

# Таймауты запроса в секундах: (установка соединения, ожидание данных)
# Разделяем на два числа: короткий connect-timeout защищает от зависания
# при недоступном сервере, длинный read-timeout - при медленной передаче данных
REQUEST_TIMEOUT = (10, 30)

# Максимум повторных попыток при сетевых ошибках.
# Rate limit НЕ считается попыткой - там мы ждём и пробуем снова сколько угодно.
MAX_RETRIES = 3


def get_headers(token: str | None) -> dict[str, str]:
    """
    Формирует заголовки для каждого запроса к GitHub API.

    Почему важен токен:
    - Без токена:  лимит 60 запросов/час (заканчивается при ~20 коммитах)
    - С токеном:   лимит 5000 запросов/час (обычно достаточно)

    Версию API фиксируем явно, чтобы будущие изменения GitHub
    не сломали парсер без предупреждения.
    """
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get(url: str, token: str | None, params: dict[str, Any] | None = None) -> Any:
    """
    Выполняет GET-запрос к GitHub API с полной обработкой ошибок.

    Логика повторов:
    - Сетевые сбои (ConnectionError): максимум MAX_RETRIES попыток,
      задержка экспоненциально растёт (1с, 2с, 4с).
    - Rate limit (HTTP 403 + "rate limit" в теле): ждём до X-RateLimit-Reset
      и повторяем - без ограничения по числу попыток и без инкремента счётчика.
    - Таймаут и все прочие HTTP-ошибки (404, 401, 500...): немедленно RuntimeError.

    Args:
        url:    Полный URL запроса.
        token:  GitHub Personal Access Token или None.
        params: Query-параметры (например {"sha": "dev", "per_page": 100}).

    Returns:
        Разобранный JSON - dict или list, в зависимости от эндпоинта.

    Raises:
        RuntimeError: При любой неустранимой ошибке (сеть, HTTP, JSON).
    """
    # Счётчик именно сетевых ошибок (ConnectionError).
    # Rate limit не увеличивает этот счётчик.
    attempt = 0

    while True:
        # --- Попытка выполнить запрос ---
        try:
            response = requests.get(
                url,
                headers=get_headers(token),
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.exceptions.Timeout:
            # Сервер не ответил в отведённое время.
            # Повторять бессмысленно - скорее всего, сервер перегружен.
            raise RuntimeError(
                f"Запрос завис (таймаут {REQUEST_TIMEOUT[1]}с): {url}"
            )
        except requests.exceptions.ConnectionError as exc:
            # Временный сетевой сбой (DNS, разрыв соединения и т.п.).
            # Повторяем с экспоненциальной задержкой.
            attempt += 1
            if attempt > MAX_RETRIES:
                raise RuntimeError(
                    f"Не удалось подключиться к GitHub API после {MAX_RETRIES} "
                    f"попыток: {exc}"
                ) from exc
            wait = 2 ** (attempt - 1)  # 1с -> 2с -> 4с
            logger.warning(
                "Сетевая ошибка, повтор через %dс (попытка %d/%d): %s",
                wait, attempt, MAX_RETRIES, exc,
            )
            time.sleep(wait)
            continue

        # --- Обработка rate limit ---
        # GitHub возвращает 403 с текстом "rate limit" когда исчерпан лимит запросов.
        # X-RateLimit-Reset - Unix timestamp момента сброса счётчика.
        if response.status_code == 403 and "rate limit" in response.text.lower():
            reset_at = int(response.headers.get("X-RateLimit-Reset", time.time() + 60))
            wait_sec = max(reset_at - int(time.time()), 5)
            logger.warning("Rate limit достигнут. Ждём %dс до сброса...", wait_sec)
            time.sleep(wait_sec)
            continue  # Повторяем запрос - attempt НЕ увеличиваем

        # --- Обработка HTTP-ошибок (404, 401, 500 и т.д.) ---
        try:
            response.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            raise RuntimeError(
                f"GitHub API вернул ошибку {response.status_code} "
                f"для {url}: {response.text[:300]}"
            ) from exc

        # --- Разбор JSON ---
        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Не удалось разобрать JSON-ответ от {url}"
            ) from exc
