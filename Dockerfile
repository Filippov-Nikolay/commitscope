FROM python:3.12-slim

WORKDIR /app

# Копируем только зависимости отдельным слоем - Docker кеширует его,
# пока requirements.txt не меняется, повторная сборка занимает секунды
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код после зависимостей - меняется чаще,
# но пересборка дешёвая: зависимости уже закешированы
COPY github_parser/ ./github_parser/
COPY static/        ./static/
COPY api.py         .
COPY main.py        .

EXPOSE 8000

# Без --reload: в контейнере нет смысла следить за файлами
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
