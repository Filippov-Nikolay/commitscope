"""
Тесты HTTP-клиента (github_parser/client.py).

Используем библиотеку responses для мокирования HTTP:
- Она перехватывает вызовы requests.get() и возвращает заданные нами ответы
- Реальных запросов к GitHub API не происходит
- Тесты работают офлайн и не зависят от rate limit

Запуск:
    pytest tests/test_client.py -v
"""

import time

import pytest
import requests
import responses as resp_mock

from github_parser.client import get

# =============================================================================
# Успешные запросы
# =============================================================================

@resp_mock.activate
def test_get_returns_dict():
    """Успешный ответ с JSON-словарём возвращается как dict."""
    resp_mock.add(resp_mock.GET, "https://example.com/api", json={"key": "value"}, status=200)

    result = get("https://example.com/api", token=None)

    assert result == {"key": "value"}


@resp_mock.activate
def test_get_returns_list():
    """Успешный ответ с JSON-массивом возвращается как list."""
    resp_mock.add(resp_mock.GET, "https://example.com/api", json=[1, 2, 3], status=200)

    result = get("https://example.com/api", token=None)

    assert result == [1, 2, 3]


@resp_mock.activate
def test_get_passes_query_params():
    """Query-параметры передаются в запрос."""
    resp_mock.add(resp_mock.GET, "https://example.com/api", json={}, status=200)

    get("https://example.com/api", token=None, params={"page": 1, "per_page": 100})

    # Проверяем, что параметры действительно попали в URL запроса
    assert "page=1" in resp_mock.calls[0].request.url
    assert "per_page=100" in resp_mock.calls[0].request.url


# =============================================================================
# Заголовки авторизации
# =============================================================================

@resp_mock.activate
def test_get_sends_auth_header_when_token_given():
    """Токен передаётся в заголовке Authorization: Bearer."""
    resp_mock.add(resp_mock.GET, "https://example.com/api", json={}, status=200)

    get("https://example.com/api", token="my-secret-token")

    assert resp_mock.calls[0].request.headers["Authorization"] == "Bearer my-secret-token"


@resp_mock.activate
def test_get_no_auth_header_without_token():
    """Без токена заголовок Authorization не отправляется."""
    resp_mock.add(resp_mock.GET, "https://example.com/api", json={}, status=200)

    get("https://example.com/api", token=None)

    assert "Authorization" not in resp_mock.calls[0].request.headers


@resp_mock.activate
def test_get_sends_github_api_version_header():
    """Версия GitHub API указана в каждом запросе."""
    resp_mock.add(resp_mock.GET, "https://example.com/api", json={}, status=200)

    get("https://example.com/api", token=None)

    assert resp_mock.calls[0].request.headers["X-GitHub-Api-Version"] == "2022-11-28"


# =============================================================================
# Обработка HTTP-ошибок
# =============================================================================

@resp_mock.activate
def test_get_raises_runtime_error_on_404():
    """HTTP 404 преобразуется в RuntimeError с кодом ошибки в сообщении."""
    resp_mock.add(
        resp_mock.GET, "https://example.com/api", json={"message": "Not Found"}, status=404
    )

    with pytest.raises(RuntimeError, match="404"):
        get("https://example.com/api", token=None)


@resp_mock.activate
def test_get_raises_runtime_error_on_500():
    """HTTP 500 преобразуется в RuntimeError."""
    resp_mock.add(
        resp_mock.GET, "https://example.com/api", body="Internal Server Error", status=500
    )

    with pytest.raises(RuntimeError, match="500"):
        get("https://example.com/api", token=None)


@resp_mock.activate
def test_get_raises_runtime_error_on_401():
    """HTTP 401 (неверный токен) преобразуется в RuntimeError."""
    resp_mock.add(
        resp_mock.GET, "https://example.com/api", json={"message": "Bad credentials"}, status=401
    )

    with pytest.raises(RuntimeError, match="401"):
        get("https://example.com/api", token="invalid-token")


# =============================================================================
# Обработка сетевых ошибок
# =============================================================================

@resp_mock.activate
def test_get_raises_on_timeout():
    """Таймаут запроса преобразуется в RuntimeError с упоминанием таймаута."""
    resp_mock.add(
        resp_mock.GET,
        "https://example.com/api",
        body=requests.exceptions.Timeout(),
    )

    with pytest.raises(RuntimeError, match="таймаут"):
        get("https://example.com/api", token=None)


@resp_mock.activate
def test_get_retries_on_connection_error_and_succeeds(monkeypatch):
    """
    При ConnectionError клиент повторяет запрос и в итоге получает ответ.

    Монкипатчим time.sleep, чтобы тест не ждал реальные секунды.
    """
    monkeypatch.setattr(time, "sleep", lambda _: None)

    # Первые два запроса падают с ошибкой соединения
    resp_mock.add(
        resp_mock.GET, "https://example.com/api",
        body=requests.exceptions.ConnectionError("connection refused"),
    )
    resp_mock.add(
        resp_mock.GET, "https://example.com/api",
        body=requests.exceptions.ConnectionError("connection refused"),
    )
    # Третья попытка успешна
    resp_mock.add(resp_mock.GET, "https://example.com/api", json={"ok": True}, status=200)

    result = get("https://example.com/api", token=None)

    assert result == {"ok": True}
    assert len(resp_mock.calls) == 3  # Два провала + один успех


@resp_mock.activate
def test_get_raises_after_max_retries_exhausted(monkeypatch):
    """После MAX_RETRIES неудачных попыток выбрасывается RuntimeError."""
    monkeypatch.setattr(time, "sleep", lambda _: None)

    # Все четыре попытки (1 + 3 retry) падают
    for _ in range(4):
        resp_mock.add(
            resp_mock.GET, "https://example.com/api",
            body=requests.exceptions.ConnectionError("unreachable"),
        )

    with pytest.raises(RuntimeError, match="подключиться"):
        get("https://example.com/api", token=None)


# =============================================================================
# Обработка Rate Limit
# =============================================================================

@resp_mock.activate
def test_get_waits_and_retries_on_rate_limit(monkeypatch):
    """
    При 403 Rate Limit клиент ждёт и повторяет запрос.

    Важно: rate limit не должен считаться как «попытка» (attempt не растёт).
    """
    monkeypatch.setattr(time, "sleep", lambda _: None)

    # Первый ответ - rate limit
    resp_mock.add(
        resp_mock.GET, "https://example.com/api",
        json={"message": "rate limit exceeded"},
        status=403,
        headers={"X-RateLimit-Reset": str(int(time.time()) + 5)},
    )
    # Второй ответ - успех
    resp_mock.add(resp_mock.GET, "https://example.com/api", json={"data": 42}, status=200)

    result = get("https://example.com/api", token=None)

    assert result == {"data": 42}
    # Проверяем, что было ровно два запроса: rate-limit + повтор
    assert len(resp_mock.calls) == 2
